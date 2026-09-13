"""Re-plan the day with a constraint solver (OR-Tools CP-SAT).

Hard rules: skills, equipment, promised arrival windows, shift hours (including the
drive from home), absences, no overlap, and drive time between consecutive jobs.
Protected jobs keep their exact time.

Preferences, in order: cover as many jobs as possible (urgent first), never bump
another customer unless it saves a strictly more urgent job, keep techs on their
own jobs, and move start times as little as possible.
"""

from __future__ import annotations

import time
import uuid

from ortools.sat.python import cp_model

from .models import Absence, Assignment, Company, Job, JobChange, Plan

PRIORITY_WEIGHT = {1: 3, 2: 2, 3: 1}
W_COVER = 1000
W_PROTECTED = 10_000
W_BUMP = 1_500
W_TECH_CHANGE = 60
W_SHIFT = 1


def _overlaps(a0: int, a1: int, b0: int, b1: int) -> bool:
    return a0 < b1 and b0 < a1


def displaced_job_ids(company: Company, absences: list[Absence]) -> set[str]:
    out = set()
    for job in company.jobs:
        if job.tech_id is None or job.start is None:
            continue
        for ab in absences:
            if ab.tech_id == job.tech_id and _overlaps(job.start, job.end, ab.start, ab.end):
                out.add(job.id)
    return out


def _full_day_absent(company: Company, absences: list[Absence]) -> set[str]:
    out = set()
    for ab in absences:
        tech = company.tech(ab.tech_id)
        if ab.start <= tech.shift_start and ab.end >= tech.shift_end:
            out.add(ab.tech_id)
    return out


def solve(
    company: Company,
    absences: list[Absence],
    *,
    now: int | None = None,
    plan_id: str | None = None,
    allow_bumping: bool = True,
    time_limit_s: float = 10.0,
) -> Plan:
    t0 = time.perf_counter()
    plan_id = plan_id or f"plan-{uuid.uuid4().hex[:8]}"
    displaced = displaced_job_ids(company, absences)
    gone = _full_day_absent(company, absences)
    absences_by_tech: dict[str, list[Absence]] = {}
    for ab in absences:
        absences_by_tech.setdefault(ab.tech_id, []).append(ab)

    m = cp_model.CpModel()
    start: dict[str, cp_model.IntVar] = {}
    assigned: dict[str, cp_model.IntVar] = {}
    x: dict[tuple[str, str], cp_model.IntVar] = {}
    notes: dict[str, str] = {}
    modeled: list[Job] = []

    for job in company.jobs:
        was_scheduled = job.start is not None and job.tech_id is not None
        frozen = now is not None and was_scheduled and job.start < now
        if frozen and job.id in displaced:
            notes[job.id] = "Was due to start before the call-out came in."
            continue

        fixed_time = job.protected or frozen
        if fixed_time:
            lo = hi = job.start
        else:
            lo = max(job.window_start, now) if now is not None else job.window_start
            hi = job.window_end
            if lo > hi:
                notes[job.id] = "Its arrival window has already passed."
                continue

        keep_tech = (job.protected or frozen) and job.id not in displaced
        if keep_tech:
            eligible = [company.tech(job.tech_id)]
        else:
            eligible = [t for t in company.technicians if t.can_do(job) and t.id not in gone]
        if not eligible:
            notes[job.id] = "No available technician has the required skills and equipment."
            continue

        modeled.append(job)
        start[job.id] = m.new_int_var(lo, hi, f"s_{job.id}")
        assigned[job.id] = m.new_bool_var(f"a_{job.id}")
        for tech in eligible:
            x[job.id, tech.id] = m.new_bool_var(f"x_{job.id}_{tech.id}")
        m.add(sum(x[job.id, t.id] for t in eligible) == assigned[job.id])

    # Per-technician rules.
    for tech in company.technicians:
        jobs_t = [j for j in modeled if (j.id, tech.id) in x]
        for job in jobs_t:
            lit = x[job.id, tech.id]
            s = start[job.id]
            m.add(s >= tech.shift_start + company.travel_min(tech.home_zone, job.zone)).only_enforce_if(lit)
            m.add(s + job.duration <= tech.shift_end).only_enforce_if(lit)
            for ab in absences_by_tech.get(tech.id, []):
                before = m.new_bool_var(f"before_{job.id}_{tech.id}_{ab.start}")
                m.add(s + job.duration <= ab.start).only_enforce_if([lit, before])
                m.add(s >= ab.end).only_enforce_if([lit, before.Not()])

    # No overlap on the same tech, with drive time between jobs.
    for i, a in enumerate(modeled):
        for b in modeled[i + 1 :]:
            common = [t.id for t in company.technicians if (a.id, t.id) in x and (b.id, t.id) in x]
            if not common:
                continue
            a_first = m.new_bool_var(f"o_{a.id}_{b.id}")
            for tid in common:
                both = [x[a.id, tid], x[b.id, tid]]
                m.add(start[a.id] + a.duration + company.travel_min(a.zone, b.zone) <= start[b.id]).only_enforce_if(
                    both + [a_first]
                )
                m.add(start[b.id] + b.duration + company.travel_min(b.zone, a.zone) <= start[a.id]).only_enforce_if(
                    both + [a_first.Not()]
                )

    # Objective.
    terms = []
    for job in modeled:
        weight = W_PROTECTED if job.protected else W_COVER * PRIORITY_WEIGHT[job.priority]
        terms.append(weight * assigned[job.id])
        was_scheduled = job.start is not None and job.tech_id is not None
        if was_scheduled and job.id not in displaced:
            bump = W_BUMP if allow_bumping else 1_000_000
            terms.append(-bump * (1 - assigned[job.id]))
            if (job.id, job.tech_id) in x:
                terms.append(-W_TECH_CHANGE * (assigned[job.id] - x[job.id, job.tech_id]))
            else:
                terms.append(-W_TECH_CHANGE * assigned[job.id])
        if job.start is not None:
            dev = m.new_int_var(0, 24 * 60, f"dev_{job.id}")
            m.add_abs_equality(dev, start[job.id] - job.start)
            terms.append(-W_SHIFT * dev)
    m.maximize(sum(terms))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_s
    solver.parameters.num_workers = 1  # deterministic: same input, same plan
    solver.parameters.random_seed = 0
    status = solver.solve(m)
    status_name = solver.status_name(status)

    assignments: list[Assignment] = []
    unassigned: list[str] = []
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        for job in modeled:
            if not solver.value(assigned[job.id]):
                unassigned.append(job.id)
                notes.setdefault(
                    job.id,
                    "No qualified technician has room inside the promised arrival window "
                    "without breaking a more urgent visit.",
                )
                continue
            tech_id = next(tid for (jid, tid) in x if jid == job.id and solver.value(x[jid, tid]))
            assignments.append(Assignment(job_id=job.id, tech_id=tech_id, start=solver.value(start[job.id])))
    else:
        unassigned.extend(j.id for j in modeled)

    modeled_ids = {j.id for j in modeled}
    unassigned.extend(j.id for j in company.jobs if j.id not in modeled_ids)

    plan = Plan(
        id=plan_id,
        absences=absences,
        assignments=assignments,
        unassigned=sorted(set(unassigned)),
        changes=[],
        solver_status=status_name,
        source_fingerprint=company.fingerprint(),
        solve_ms=int((time.perf_counter() - t0) * 1000),
    )
    plan.changes = diff(company, plan, notes)
    plan.objective = summarize(company, plan, displaced)
    return plan


def diff(company: Company, plan: Plan, notes: dict[str, str] | None = None) -> list[JobChange]:
    notes = notes or {}
    changes = []
    for job in company.jobs:
        a = plan.assignment(job.id)
        if a is None:
            changes.append(
                JobChange(
                    job_id=job.id,
                    kind="unassigned",
                    from_tech=job.tech_id,
                    to_tech=None,
                    from_start=job.start,
                    to_start=None,
                    customer_notice=job.tech_id is not None,
                    note=notes.get(job.id, "Could not be covered."),
                )
            )
        elif a.tech_id != job.tech_id:
            changes.append(
                JobChange(
                    job_id=job.id,
                    kind="reassigned",
                    from_tech=job.tech_id,
                    to_tech=a.tech_id,
                    from_start=job.start,
                    to_start=a.start,
                    customer_notice=True,
                    note="New technician, same promised arrival window.",
                )
            )
        elif a.start != job.start:
            changes.append(
                JobChange(
                    job_id=job.id,
                    kind="retimed",
                    from_tech=job.tech_id,
                    to_tech=a.tech_id,
                    from_start=job.start,
                    to_start=a.start,
                    customer_notice=False,
                    note="Still inside the promised arrival window, so no customer notice is needed.",
                )
            )
        else:
            changes.append(
                JobChange(
                    job_id=job.id,
                    kind="unchanged",
                    from_tech=job.tech_id,
                    to_tech=a.tech_id,
                    from_start=job.start,
                    to_start=a.start,
                    customer_notice=False,
                )
            )
    return changes


def day_routes(company: Company, assignments: list[Assignment]) -> dict[str, list[Assignment]]:
    routes: dict[str, list[Assignment]] = {t.id: [] for t in company.technicians}
    for a in sorted(assignments, key=lambda a: a.start):
        routes.setdefault(a.tech_id, []).append(a)
    return routes


def travel_minutes(company: Company, assignments: list[Assignment]) -> int:
    total = 0
    for tech_id, route in day_routes(company, assignments).items():
        if not route:
            continue
        zone = company.tech(tech_id).home_zone
        for a in route:
            job_zone = company.job(a.job_id).zone
            total += company.travel_min(zone, job_zone)
            zone = job_zone
    return total


def summarize(company: Company, plan: Plan, displaced: set[str]) -> dict[str, int]:
    kinds = [c.kind for c in plan.changes]
    return {
        "jobs_total": len(company.jobs),
        "displaced": len(displaced),
        "displaced_covered": sum(1 for j in displaced if plan.assignment(j) is not None),
        "unassigned": len(plan.unassigned),
        "reassigned": kinds.count("reassigned"),
        "retimed": kinds.count("retimed"),
        "customer_notices": sum(1 for c in plan.changes if c.customer_notice),
        "travel_minutes": travel_minutes(company, plan.assignments),
    }
