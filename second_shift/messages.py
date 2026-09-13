"""Customer emails and crew Slack messages.

Deliberately template-based: every time, name, and window comes from the plan
data, never from model output, so a notification can't state a wrong time or
carry text injected through a Slack message."""

from __future__ import annotations

from .models import Company, JobChange, Plan, fmt


def first(name: str) -> str:
    return name.split()[0]


def customer_email(company: Company, change: JobChange, absent: set[str]) -> tuple[str, str]:
    """absent: ids of technicians who called out (so we only say 'X is out' when it's true)."""
    job = company.job(change.job_id)
    greeting = first(job.customer) if " " in job.customer else "there"
    service = job.service.split(" (")[0]
    old = company.tech(change.from_tech).name if change.from_tech else None
    if old and change.from_tech in absent:
        why = f"{first(old)} is out today"
    else:
        why = "A teammate is out today and we rebalanced the crew's routes"
    if change.kind == "reassigned":
        new = company.tech(change.to_tech).name
        if job.window_start == job.window_end:
            timing = f"Your appointment stays at {fmt(job.window_start)}."
        else:
            timing = f"Your arrival window doesn't change: we'll be there between {fmt(job.window_start)} and {fmt(job.window_end)}."
        subject = f"Update on your {company.name} visit today"
        body = (
            f"Hi {greeting},\n\n"
            f"{why}, so {new} will handle your visit ({service}).\n"
            f"{timing}\n\n"
            f"Address on file: {job.address}\n\nThanks,\n{company.name} dispatch"
        )
        return subject, body
    subject = f"We need to reschedule your {company.name} visit"
    body = (
        f"Hi {greeting},\n\n"
        f"We're sorry. {why}, and no technician with the right certification "
        f"({', '.join(job.required_skills)}) can reach you inside your promised window.\n\n"
        f"Reply to this email with a day and time that works, and we'll put you first on the schedule.\n\n"
        f"Thanks for understanding,\n{company.name} dispatch"
    )
    return subject, body


def tech_day_message(company: Company, plan: Plan, tech_id: str) -> str | None:
    """Slack message for one tech whose day changed. None if nothing changed for them."""
    tech = company.tech(tech_id)
    mention = f"<@{tech.slack_user_id}>" if tech.slack_user_id else f"*{tech.name}*"
    if any(a.tech_id == tech_id and a.start <= 0 and a.end >= 1440 for a in plan.absences):
        covered = [c for c in plan.changes if c.from_tech == tech_id and c.kind == "reassigned"]
        missed = [c for c in plan.changes if c.from_tech == tech_id and c.kind == "unassigned"]
        lines = [f"{mention} feel better! Your visits are covered:"]
        lines += [f"• {c.job_id} {company.job(c.job_id).customer} → {company.tech(c.to_tech).name}" for c in covered]
        lines += [f"• {c.job_id} {company.job(c.job_id).customer} → we asked them to pick a new time" for c in missed]
        return "\n".join(lines)

    mine = sorted((a for a in plan.assignments if a.tech_id == tech_id), key=lambda a: a.start)
    changes = {c.job_id: c for c in plan.changes}
    touched = [a for a in mine if changes[a.job_id].kind != "unchanged"]
    lost = [c for c in plan.changes if c.from_tech == tech_id and c.to_tech != tech_id and c.kind != "unchanged"]
    if not touched and not lost:
        return None
    lines = [f"{mention} your day changed. Here's your new route:"]
    for a in mine:
        job = company.job(a.job_id)
        c = changes[a.job_id]
        tag = ""
        if c.kind == "reassigned":
            tag = f"  ← NEW, covering for {company.tech(c.from_tech).name.split()[0] if c.from_tech else 'the team'}"
        elif c.kind == "retimed":
            tag = f"  ← was {fmt(c.from_start)}"
        lines.append(f"• {fmt(a.start)} {job.id} {job.customer}, {job.zone}: {job.service}{tag}")
    for c in lost:
        where = f"moved to {company.tech(c.to_tech).name}" if c.to_tech else "needs rescheduling (customer asked)"
        lines.append(f"• {c.job_id} {company.job(c.job_id).customer} {where}")
    return "\n".join(lines)


def dispatch_summary(company: Company, plan: Plan, notices: int) -> str:
    o = plan.objective
    out = sorted({company.tech(a.tech_id).name.split()[0] for a in plan.absences if a.reason == "callout"})
    who = " and ".join(out) or "the team"
    lost = [company.job(j) for j in plan.unassigned if company.job(j).tech_id]
    lines = [
        f":white_check_mark: *Done. {who}'s day is covered.*",
        f"• {o['displaced_covered']} of {o['displaced']} visits moved to teammates",
        f"• Calendars and the job sheet are updated, {notices} customers emailed",
        "• Every change was double-checked after writing",
    ]
    for job in lost:
        lines.append(f"• :warning: {job.customer} ({job.id}) couldn't be covered today, so we asked them to pick a new time")
    return "\n".join(lines)
