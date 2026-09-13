"""The agent loop.

  Slack message -> parse (Claude) -> guard (deterministic) -> read Sheets + Calendar
  -> solve (CP-SAT) -> validate (independent checker) -> human approval
  -> re-read + fingerprint check -> write via ledger (idempotent, retried) -> read back + verify

The model interprets language. Code decides who does what, when, and whether it's legal.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import os
import time
import uuid
from collections import defaultdict
from typing import Any, Callable

from pydantic import BaseModel

from .adapters.base import CalendarEvent, ChatMessage, PermanentError, Ports, TransientError
from .clock import demo_now, event_id, hhmm, parse_hhmm, plan_day
from .ledger import Ledger
from .messages import customer_email, dispatch_summary, tech_day_message
from .models import Absence, Company, Plan, Technician, fmt
from .sheet_codec import tabs_to_company
from .solver import solve
from .validate import check_plan, check_schedule

TABS = ("Technicians", "Jobs", "Travel")
STATUS_BY_KIND = {"reassigned": "reassigned", "retimed": "retimed", "unassigned": "needs_reschedule"}


class Snapshot(BaseModel):
    company: Company
    events: dict[str, list[CalendarEvent]]
    busy: list[Absence]
    discrepancies: list[str]
    fingerprint: str


class Action(BaseModel):
    seq: int
    key: str
    kind: str  # calendar.create | calendar.delete | sheets.update | chat.post | mail.send
    label: str
    params: dict[str, Any]


class Check(BaseModel):
    name: str
    ok: bool
    detail: str = ""


class ParsedCallout(BaseModel):
    """What the language model extracts from a Slack message. Nothing more."""

    is_callout: bool
    tech_id: str | None = None
    whole_day: bool = False
    unavailable_from: str | None = None  # "HH:MM" 24h
    unavailable_until: str | None = None
    confidence: str = "low"  # high | medium | low
    needs_clarification: bool = False
    clarifying_question: str | None = None
    is_hypothetical: bool = False  # "what if Wei doesn't show up?" -> simulate, never write
    summary: str = ""


def guard(
    parsed: ParsedCallout,
    text: str,
    company: Company,
    sender_tech: Technician | None,
    is_dispatcher: bool,
    now: int | None,
) -> tuple[str, str | None, Absence | None]:
    """Deterministic checks on the model's reading. Returns (decision, question, absence).
    decision: 'ignore' | 'clarify' | 'plan' | 'simulate'. When in doubt, ask; never guess who is out."""
    if not parsed.is_callout:
        return "ignore", None, None
    if sender_tech is None and not is_dispatcher:
        return "clarify", "I only take call-outs from the crew or from dispatch. Can dispatch confirm who is out?", None
    if parsed.needs_clarification or parsed.confidence == "low":
        return "clarify", parsed.clarifying_question or "Who is out, and for which hours?", None
    techs = {t.id: t for t in company.technicians}
    tech = techs.get(parsed.tech_id or "")
    if tech is None:
        return "clarify", "Which technician is out?", None
    lowered = text.lower()
    named = tech.name.lower() in lowered or tech.name.split()[0].lower() in lowered
    if sender_tech is not None and sender_tech.id != tech.id and not named:
        return "clarify", f"Just checking: is it you ({sender_tech.name}) who is out, or {tech.name}?", None
    if sender_tech is None and not named:
        return "clarify", "Which technician is out? Please use their name.", None
    try:
        if parsed.whole_day:
            start, end = 0, 24 * 60
        else:
            start = parse_hhmm(parsed.unavailable_from) if parsed.unavailable_from else max(tech.shift_start, now or 0)
            end = parse_hhmm(parsed.unavailable_until) if parsed.unavailable_until else 24 * 60
    except ValueError:
        return "clarify", f"For which hours is {tech.name.split()[0]} out?", None
    if end <= start:
        return "clarify", f"For which hours is {tech.name.split()[0]} out?", None
    return ("simulate" if parsed.is_hypothetical else "plan"), None, Absence(tech_id=tech.id, start=start, end=end)


class Engine:
    def __init__(
        self,
        ports: Ports,
        ledger: Ledger,
        parser: Any = None,
        *,
        company_name: str = "Bayside Home Services",
        timezone: str = "America/Los_Angeles",
        dispatchers: set[str] | None = None,
        now: Callable[[], int | None] = demo_now,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.ports = ports
        self.ledger = ledger
        self.parser = parser
        self.company_name = company_name
        self.timezone = timezone
        self.dispatchers = dispatchers or set()
        self.now = now
        self.sleep = sleep

    # ---------- read ----------
    def snapshot(self, run_id: str | None = None) -> Snapshot:
        t0 = time.time()
        tabs = {t: self.ports.sheets.read_tab(t) for t in TABS}
        company = tabs_to_company(tabs, self.company_name, self.timezone)
        events: dict[str, list[CalendarEvent]] = defaultdict(list)
        busy: list[Absence] = []
        notes: list[str] = []
        cal_owner: dict[str, str] = {}
        for tech in company.technicians:
            if not tech.calendar_id:
                notes.append(f"{tech.name} has no calendar linked, so they are treated as unavailable.")
                busy.append(Absence(tech_id=tech.id, start=0, end=24 * 60, reason="calendar_busy"))
                continue
            cal_owner[tech.calendar_id] = tech.id
            for ev in self.ports.calendar.list_events(tech.calendar_id):
                if ev.job_id:
                    events[ev.job_id].append(ev)
                else:
                    busy.append(Absence(tech_id=tech.id, start=ev.start, end=ev.end, reason="calendar_busy"))
        for job in company.jobs:
            evs = events.get(job.id, [])
            if not evs:
                if job.tech_id:
                    notes.append(f"{job.id}: the sheet says {job.tech_id} at {fmt(job.start)}, but it has no "
                                 "calendar booking, so it is treated as unscheduled.")
                job.tech_id, job.start = None, None
                continue
            if len(evs) > 1:
                notes.append(f"{job.id}: booked {len(evs)} times in Calendar; using the earliest booking.")
            ev = min(evs, key=lambda e: e.start)
            cal_tech = cal_owner.get(ev.calendar_id)
            if (job.tech_id, job.start) != (cal_tech, ev.start):
                notes.append(f"{job.id}: the sheet says {job.tech_id or '-'} at {fmt(job.start)}; Calendar says "
                             f"{cal_tech} at {fmt(ev.start)}. Calendar wins.")
            job.tech_id, job.start = cal_tech, ev.start
        payload = [
            company.fingerprint(),
            sorted((b.tech_id, b.start, b.end) for b in busy),
            sorted((j, sorted((e.calendar_id, e.event_id) for e in evs)) for j, evs in events.items()),
        ]
        fingerprint = hashlib.sha256(json.dumps(payload, default=str).encode()).hexdigest()[:16]
        if run_id:
            self.ledger.trace(run_id, "Read Sheets + Calendar", "ok", t0, {
                "technicians": len(company.technicians), "jobs": len(company.jobs),
                "bookings": sum(len(v) for v in events.values()), "busy_blocks": len(busy),
                "discrepancies": notes, "fingerprint": fingerprint,
            })
        return Snapshot(company=company, events=dict(events), busy=busy, discrepancies=notes, fingerprint=fingerprint)

    # ---------- plan ----------
    def propose(self, absences: list[Absence], *, run_id: str | None = None, callout: dict | None = None,
                snap: Snapshot | None = None, simulate: bool = False) -> dict:
        """simulate=True makes a what-if: the full plan and checks, status 'simulated', never writable."""
        run_id = run_id or f"run-{uuid.uuid4().hex[:8]}"
        snap = snap or self.snapshot(run_id)
        t0 = time.time()
        # Call-outs from plans already carried out today still hold (Marco stays out).
        earlier = [a for a in self.active_absences() if a not in absences]
        if earlier:
            self.ledger.trace(run_id, "Earlier call-outs still in effect", "ok", t0,
                              {"absences": [a.model_dump() for a in earlier]})
        plan = solve(snap.company, list(absences) + earlier + snap.busy, now=self.now(),
                     plan_id=f"plan-{uuid.uuid4().hex[:8]}")
        plan.source_fingerprint = snap.fingerprint
        self.ledger.trace(run_id, "Solve (OR-Tools CP-SAT)", "ok" if plan.solver_status in ("OPTIMAL", "FEASIBLE") else "error",
                          t0, {"status": plan.solver_status, "ms": plan.solve_ms, **plan.objective})
        t0 = time.time()
        violations = check_plan(snap.company, plan)
        self.ledger.trace(run_id, "Independent rule check", "ok" if not violations else "error", t0,
                          {"violations": [v.detail for v in violations]})
        actions = self.build_actions(snap, plan)
        ok = not violations and plan.solver_status in ("OPTIMAL", "FEASIBLE")
        status = ("simulated" if simulate else "proposed") if ok else "rejected"
        self.ledger.save_plan(plan.id, status, {
            "simulated": simulate,
            "run_id": run_id,
            "plan_day": plan_day().isoformat(),
            "plan": plan.model_dump(),
            "company": snap.company.model_dump(),
            "events": {j: [e.model_dump() for e in evs] for j, evs in snap.events.items()},
            "actions": [a.model_dump() for a in actions],
            "violations": [v.model_dump() for v in violations],
            "discrepancies": snap.discrepancies,
            "callout": callout,
            "verification": None,
        })
        return self.view(plan.id)

    def adopt(self, plan_id: str) -> dict:
        """Turn a what-if into a real proposal, re-planned from fresh Sheets + Calendar."""
        status, body = self.ledger.get_plan(plan_id)
        absences = [Absence.model_validate(a) for a in body["plan"]["absences"] if a.get("reason") == "callout"]
        callout = dict(body.get("callout") or {}, adopted_from=plan_id)
        return self.propose(absences, callout=callout)

    def preparedness_scan(self) -> list[dict]:
        """What if each technician called out today? Pure simulation: no ledger rows, no writes.
        Reveals single points of failure (techs whose absence leaves jobs uncoverable)."""
        snap = self.snapshot()
        earlier = self.active_absences()
        rows = []
        for tech in snap.company.technicians:
            if any(a.tech_id == tech.id for a in earlier):
                continue
            plan = solve(snap.company, [Absence(tech_id=tech.id, start=0, end=24 * 60)] + earlier + snap.busy,
                         now=self.now(), plan_id=f"scan-{tech.id}")
            o = plan.objective
            lost = [c for c in plan.changes if c.kind == "unassigned" and c.from_tech == tech.id]
            rows.append({
                "tech_id": tech.id, "name": tech.name, "skills": tech.skills,
                "jobs": o["displaced"], "covered": o["displaced_covered"], "reschedule": len(lost),
                "reschedule_jobs": [{"job_id": c.job_id, "customer": snap.company.job(c.job_id).customer,
                                     "why": c.note} for c in lost],
                "reassigned": o["reassigned"], "customer_notices": o["customer_notices"],
                "valid": not check_plan(snap.company, plan), "solve_ms": plan.solve_ms,
            })
        rows.sort(key=lambda r: (-r["reschedule"], -r["jobs"], r["name"]))
        return rows

    def active_absences(self) -> list[Absence]:
        """Call-out absences from plans carried out on the current plan day."""
        today = plan_day().isoformat()
        out: list[Absence] = []
        for row in self.ledger.list_plans(limit=200):
            if row["status"] not in ("done", "done_with_issues", "executing"):
                continue
            _, body = self.ledger.get_plan(row["id"])
            if body.get("plan_day") != today:
                continue
            for a in body["plan"]["absences"]:
                ab = Absence.model_validate(a)
                if ab.reason == "callout" and ab not in out:
                    out.append(ab)
        return out

    def build_actions(self, snap: Snapshot, plan: Plan) -> list[Action]:
        company = snap.company
        seq = itertools.count()
        acts: list[Action] = []

        def add(kind: str, key: str, label: str, **params: Any) -> None:
            acts.append(Action(seq=next(seq), key=key, kind=kind, label=label, params=params))

        changes = plan.changed()
        owner = {t.calendar_id: t for t in company.technicians if t.calendar_id}
        # New bookings first, then removals: a job is never absent from every calendar mid-run.
        for c in changes:
            if c.kind in ("reassigned", "retimed"):
                job, tech = company.job(c.job_id), company.tech(c.to_tech)
                add("calendar.create", f"{plan.id}:cal+:{job.id}",
                    f"Book {job.id} ({job.customer}) on {tech.name}'s calendar at {fmt(c.to_start)}",
                    calendar_id=tech.calendar_id, event_id=event_id(plan.id, job.id), start=c.to_start,
                    end=c.to_start + job.duration, summary=f"{job.id} · {job.customer} · {job.service}",
                    description=(f"{job.address} ({job.zone})\nPromised arrival: {fmt(job.window_start)}-"
                                 f"{fmt(job.window_end)}\nSkills: {', '.join(job.required_skills)}\nPlan: {plan.id}"),
                    job_id=job.id, plan_id=plan.id)
        for c in changes:
            for ev in snap.events.get(c.job_id, []):
                who = owner[ev.calendar_id].name if ev.calendar_id in owner else ev.calendar_id
                add("calendar.delete", f"{plan.id}:cal-:{c.job_id}:{ev.event_id}",
                    f"Remove the old {c.job_id} booking from {who}'s calendar",
                    calendar_id=ev.calendar_id, event_id=ev.event_id)
        for c in changes:
            a = plan.assignment(c.job_id)
            add("sheets.update", f"{plan.id}:sheet:{c.job_id}", f"Update {c.job_id} in the Jobs sheet",
                job_id=c.job_id, values={
                    "assigned_tech": a.tech_id if a else "",
                    "scheduled_start": hhmm(a.start) if a else "",
                    "status": STATUS_BY_KIND[c.kind],
                    "last_plan": plan.id,
                })
        touched: list[str] = []
        for tid in [a.tech_id for a in plan.absences if a.reason == "callout"] + \
                   [t for c in changes for t in (c.from_tech, c.to_tech) if t]:
            if tid not in touched:
                touched.append(tid)
        for tid in touched:
            text = tech_day_message(company, plan, tid)
            if text:
                add("chat.post", f"{plan.id}:slack:{tid}", f"Tell {company.tech(tid).name} about their new day in Slack",
                    text=text)
        notices = [c for c in changes if c.customer_notice]
        called_out = {a.tech_id for a in plan.absences if a.reason == "callout"}
        for c in notices:
            job = company.job(c.job_id)
            subject, body = customer_email(company, c, called_out)
            what = "new technician" if c.kind == "reassigned" else "reschedule request"
            add("mail.send", f"{plan.id}:mail:{c.job_id}", f"Email {job.customer} ({what})",
                to=job.customer_email, subject=subject, body=body)
        add("chat.post", f"{plan.id}:slack:summary", "Post the summary to #dispatch",
            text=dispatch_summary(company, plan, len(notices)))
        return acts

    # ---------- act ----------
    def approve(self, plan_id: str) -> dict:
        got = self.ledger.get_plan(plan_id)
        if got is None:
            raise KeyError(plan_id)
        status, body = got
        run_id = body["run_id"]
        if status in ("done", "done_with_issues"):
            return self.view(plan_id)  # a second click changes nothing
        if status in ("rejected", "stale", "simulated"):
            return self.view(plan_id)  # what-ifs and invalid plans never write
        plan = Plan.model_validate(body["plan"])
        actions = [Action.model_validate(a) for a in body["actions"]]
        if status == "proposed":
            t0 = time.time()
            fresh = self.snapshot()
            if fresh.fingerprint != plan.source_fingerprint:
                self.ledger.set_status(plan_id, "stale")
                self.ledger.trace(run_id, "Re-check before writing", "stale", t0, {
                    "reason": "Sheets or Calendar changed after this plan was made. Nothing was written.",
                    "expected": plan.source_fingerprint, "found": fresh.fingerprint,
                })
                return self.view(plan_id)
            self.ledger.trace(run_id, "Re-check before writing", "ok", t0, {"fingerprint": fresh.fingerprint})
            self.ledger.set_status(plan_id, "executing")
        else:
            self.ledger.trace(run_id, "Resume from ledger", "ok", time.time(),
                              {"done": sum(1 for a in self.ledger.actions_for(plan_id) if a["status"] == "done")})
            self.ledger.set_status(plan_id, "executing")
        for act in actions:
            if not self._run(plan_id, run_id, act):
                self.ledger.set_status(plan_id, "failed")
                return self.view(plan_id)
        report = self.verify(plan_id)
        self.ledger.set_status(plan_id, "done" if all(c.ok for c in report) else "done_with_issues")
        return self.view(plan_id)

    def _run(self, plan_id: str, run_id: str, act: Action) -> bool:
        row = self.ledger.action(act.key)
        if row and row["status"] == "done":
            self.ledger.trace(run_id, act.label, "skipped", time.time(), {"reason": "already done (ledger)"})
            return True
        for attempt in range(1, 4):
            t0 = time.time()
            self.ledger.mark(act.key, plan_id, act.seq, act.kind, "pending", attempt=True)
            try:
                result = self._perform(act)
            except TransientError as e:
                self.ledger.mark(act.key, plan_id, act.seq, act.kind, "retrying", error=str(e))
                self.ledger.trace(run_id, act.label, "retry", t0, {"attempt": attempt, "error": str(e)})
                self.sleep(0.5 * 2 ** (attempt - 1))
                continue
            except PermanentError as e:
                self.ledger.mark(act.key, plan_id, act.seq, act.kind, "failed", error=str(e))
                self.ledger.trace(run_id, act.label, "error", t0, {"error": str(e)})
                return False
            self.ledger.mark(act.key, plan_id, act.seq, act.kind, "done", result=result)
            self.ledger.trace(run_id, act.label, "ok", t0, {"attempt": attempt, **result})
            return True
        self.ledger.mark(act.key, plan_id, act.seq, act.kind, "failed", error="Gave up after 3 attempts")
        return False

    def _perform(self, act: Action) -> dict:
        p = act.params
        if act.kind == "calendar.create":
            ev = self.ports.calendar.create_event(p["calendar_id"], p["event_id"], p["start"], p["end"],
                                                  p["summary"], p["description"], p["job_id"], p["plan_id"])
            return {"event_id": ev.event_id}
        if act.kind == "calendar.delete":
            self.ports.calendar.delete_event(p["calendar_id"], p["event_id"])
            return {"deleted": p["event_id"]}
        if act.kind == "sheets.update":
            self.ports.sheets.update_row("Jobs", p["job_id"], p["values"])
            return {"row": p["job_id"]}
        if act.kind == "chat.post":
            existing = self.ports.chat.find_by_key(act.key)
            if existing:
                return {"ts": existing, "deduped": True}
            return {"ts": self.ports.chat.post(p["text"], act.key)}
        if act.kind == "mail.send":
            existing = self.ports.mail.find_by_key(act.key)
            if existing:
                return {"message_id": existing, "deduped": True}
            return {"message_id": self.ports.mail.send(p["to"], p["subject"], p["body"], act.key)}
        raise PermanentError(f"Unknown action {act.kind}")

    # ---------- verify ----------
    def verify(self, plan_id: str) -> list[Check]:
        status, body = self.ledger.get_plan(plan_id)
        run_id = body["run_id"]
        t0 = time.time()
        plan = Plan.model_validate(body["plan"])
        before = Company.model_validate(body["company"])
        actions = [Action.model_validate(a) for a in body["actions"]]
        snap = self.snapshot()
        cal_owner = {t.calendar_id: t.id for t in before.technicians}
        checks: list[Check] = []
        for job in before.jobs:
            a = plan.assignment(job.id)
            evs = snap.events.get(job.id, [])
            if a:
                cal = before.tech(a.tech_id).calendar_id
                ok = len(evs) == 1 and evs[0].calendar_id == cal and evs[0].start == a.start
                got = ", ".join(f"{cal_owner.get(e.calendar_id)} {fmt(e.start)}" for e in evs) or "no booking"
                checks.append(Check(name=f"Calendar: {job.id} with {before.tech(a.tech_id).name} at {fmt(a.start)}",
                                    ok=ok, detail="" if ok else f"found {got}"))
            else:
                checks.append(Check(name=f"Calendar: {job.id} removed (needs reschedule)", ok=not evs,
                                    detail="" if not evs else f"{len(evs)} booking(s) remain"))
        placements = {j: [(cal_owner.get(e.calendar_id, "?"), e.start) for e in evs] for j, evs in snap.events.items()}
        violations = check_schedule(before, placements, plan.absences, original=before)
        checks.append(Check(name="Rules hold on the real calendars (skills, windows, travel, no double-booking)",
                            ok=not violations, detail="; ".join(v.detail for v in violations)))
        jobs_tab = self.ports.sheets.read_tab("Jobs")
        header, jobs_rows = jobs_tab[0], {r[0]: r for r in jobs_tab[1:] if r}
        for act in actions:
            if act.kind == "sheets.update":
                row = jobs_rows.get(act.params["job_id"], [])
                row = list(row) + [""] * (len(header) - len(row))
                cells = dict(zip(header, row))
                ok = all(cells.get(k, "") == v for k, v in act.params["values"].items())
                checks.append(Check(name=f"Sheet: {act.params['job_id']} row updated", ok=ok,
                                    detail="" if ok else f"row shows {[cells.get(k) for k in act.params['values']]}"))
            elif act.kind == "chat.post":
                ok = self.ports.chat.find_by_key(act.key) is not None
                checks.append(Check(name=f"Slack: {act.label.replace('Tell ', '').replace(' in Slack', '')}", ok=ok))
            elif act.kind == "mail.send":
                ok = self.ports.mail.find_by_key(act.key) is not None
                checks.append(Check(name=f"Gmail: {act.label.replace('Email ', 'sent to ')}", ok=ok))
        self.ledger.update_body(plan_id, verification=[c.model_dump() for c in checks])
        self.ledger.trace(run_id, "Read back + verify", "ok" if all(c.ok for c in checks) else "error", t0,
                          {"passed": sum(c.ok for c in checks), "total": len(checks)})
        return checks

    # ---------- Slack intake ----------
    def baseline(self) -> None:
        """Mark existing channel history as seen so startup doesn't act on old messages."""
        for m in self.ports.chat.history(limit=100):
            self.ledger.mark_seen(m.ts, "baseline")

    def handle_message(self, msg: ChatMessage) -> dict:
        if msg.bot or self.ledger.seen(msg.ts):
            return {"outcome": "ignored"}
        run_id = f"run-{msg.ts.replace('.', '')}"
        snap = self.snapshot(run_id)
        company = snap.company
        sender_tech = next((t for t in company.technicians if t.slack_user_id and t.slack_user_id == msg.user), None)
        sender_name = self.ports.chat.user_name(msg.user or "") or msg.user or "unknown"
        is_dispatcher = (msg.user in self.dispatchers) if self.dispatchers else sender_tech is None
        t0 = time.time()
        parsed: ParsedCallout = self.parser.parse(
            text=msg.text, sender_name=sender_name, sender_tech_id=sender_tech.id if sender_tech else None,
            company=company, now=self.now())
        self.ledger.trace(run_id, "Read the message (Claude)", "ok", t0, parsed.model_dump())
        t0 = time.time()
        decision, question, absence = guard(parsed, msg.text, company, sender_tech, is_dispatcher, self.now())
        self.ledger.trace(run_id, "Guardrails", decision, t0, {"question": question, "absence": absence and absence.model_dump()})
        if decision == "ignore":
            self.ledger.mark_seen(msg.ts, "ignored")
            return {"outcome": "ignored", "run_id": run_id}
        if decision == "clarify":
            self._reply(run_id, f"clarify:{msg.ts}", question)
            self.ledger.mark_seen(msg.ts, "clarify")
            return {"outcome": "clarify", "question": question, "run_id": run_id}
        callout = {"text": msg.text, "sender": sender_name, "parsed": parsed.model_dump(),
                   "absence": absence.model_dump()}
        if decision == "simulate":
            view = self.propose([absence], run_id=run_id, callout=callout, snap=snap, simulate=True)
            o, tech = view["plan"]["objective"], company.tech(absence.tech_id)
            lost = [company.job(j).customer for j in view["plan"]["unassigned"]
                    if company.job(j).tech_id == tech.id]
            text = (f"What-if: if {tech.name} is out, the plan covers {o['displaced_covered']} of {o['displaced']} of "
                    f"their jobs" + (f"; {', '.join(lost)} would need rescheduling" if lost else "") +
                    f"; {o['customer_notices']} customers would be emailed. Nothing has changed. "
                    "Dispatch can make it real in the app.")
            self._reply(run_id, f"whatif:{msg.ts}", text)
            self.ledger.mark_seen(msg.ts, "simulated")
            return {"outcome": "simulated", "plan_id": view["id"], "run_id": run_id}
        view = self.propose([absence], run_id=run_id, callout=callout, snap=snap)
        tech = company.tech(absence.tech_id)
        span = "today" if absence.start <= tech.shift_start and absence.end >= tech.shift_end else \
            f"{fmt(max(absence.start, tech.shift_start))}-{fmt(min(absence.end, tech.shift_end))}"
        o = view["plan"]["objective"]
        if view["status"] == "proposed":
            result = (f"Proposed plan covers {o['displaced_covered']} of {o['displaced']} affected jobs"
                      f"{f', {o['unassigned']} need' + ('s' if o['unassigned'] == 1 else '') + ' rescheduling' if o['unassigned'] else ''}; "
                      f"{o['customer_notices']} customers would be emailed. Nothing changes until dispatch approves.")
        else:
            result = "I couldn't produce a plan that passes every rule, so nothing will change. Dispatch, please check the app."
        link = os.getenv("APP_URL", "")
        self._reply(run_id, f"ack:{msg.ts}", f"Got it: planning around {tech.name} ({span}). {result}"
                                             f"{f' Review: {link}' if link else ''}")
        self.ledger.mark_seen(msg.ts, "planned")
        return {"outcome": "planned", "plan_id": view["id"], "run_id": run_id}

    def _reply(self, run_id: str, key: str, text: str) -> None:
        """Best-effort Slack reply (ack or question). A failure here never blocks planning."""
        t0 = time.time()
        for attempt in range(1, 4):
            try:
                if not self.ports.chat.find_by_key(key):
                    self.ports.chat.post(text, key)
                self.ledger.trace(run_id, "Reply in Slack", "ok", t0, {"attempt": attempt, "text": text})
                return
            except TransientError as e:
                self.sleep(0.5 * 2 ** (attempt - 1))
                err = str(e)
            except Exception as e:  # noqa: BLE001 - replies are non-critical by design
                err = f"{type(e).__name__}: {e}"
                break
        self.ledger.trace(run_id, "Reply in Slack", "error", t0, {"error": err, "text": text})

    def poll_once(self) -> list[dict]:
        out = []
        for m in reversed(self.ports.chat.history(limit=20)):
            if not m.bot and not self.ledger.seen(m.ts):
                out.append(self.handle_message(m))
        return out

    # ---------- view ----------
    def view(self, plan_id: str) -> dict:
        status, body = self.ledger.get_plan(plan_id)
        rows = {a["key"]: a for a in self.ledger.actions_for(plan_id)}
        for a in body["actions"]:
            row = rows.get(a["key"])
            a["status"] = row["status"] if row else "planned"
            a["attempts"] = row["attempts"] if row else 0
            a["result"] = json.loads(row["result"]) if row and row["result"] else None
            a["error"] = row["error"] if row else None
        return {"id": plan_id, "status": status, **body, "trace": self.ledger.get_trace(body["run_id"])}
