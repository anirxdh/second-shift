"""Independent rule checker. Shares no logic with the solver on purpose:
it re-derives every rule from the raw data, so a solver bug can't hide itself.
Also used on the state read back from Calendar after execution."""

from __future__ import annotations

from pydantic import BaseModel

from .models import Absence, Company, Plan, fmt


class Violation(BaseModel):
    code: str
    detail: str
    job_id: str | None = None
    tech_id: str | None = None


def check_schedule(
    company: Company,
    placements: dict[str, list[tuple[str, int]]],
    absences: list[Absence] = (),
    original: Company | None = None,
) -> list[Violation]:
    """placements: job_id -> list of (tech_id, start). More than one entry = duplicate."""
    v: list[Violation] = []
    techs = {t.id: t for t in company.technicians}
    by_tech: dict[str, list[tuple[int, int, str]]] = {}

    for job_id, entries in placements.items():
        job = company.job(job_id)
        if len(entries) > 1:
            v.append(Violation(code="DUPLICATE", job_id=job_id, detail=f"{job_id} is booked {len(entries)} times."))
        for tech_id, start in entries:
            tech = techs.get(tech_id)
            if tech is None:
                v.append(Violation(code="UNKNOWN_TECH", job_id=job_id, tech_id=tech_id, detail=f"No tech {tech_id}."))
                continue
            end = start + job.duration
            missing = set(job.required_skills) - set(tech.skills)
            if missing:
                v.append(Violation(code="SKILL", job_id=job_id, tech_id=tech_id,
                                   detail=f"{tech.name} lacks {', '.join(sorted(missing))} for {job_id}."))
            missing_eq = set(job.required_equipment) - set(tech.equipment)
            if missing_eq:
                v.append(Violation(code="EQUIPMENT", job_id=job_id, tech_id=tech_id,
                                   detail=f"{tech.name} lacks {', '.join(sorted(missing_eq))} for {job_id}."))
            if not (job.window_start <= start <= job.window_end):
                v.append(Violation(code="WINDOW", job_id=job_id, tech_id=tech_id,
                                   detail=f"{job_id} starts {fmt(start)}, outside {fmt(job.window_start)}-{fmt(job.window_end)}."))
            earliest = tech.shift_start + company.travel_min(tech.home_zone, job.zone)
            if start < earliest or end > tech.shift_end:
                v.append(Violation(code="SHIFT", job_id=job_id, tech_id=tech_id,
                                   detail=f"{job_id} at {fmt(start)}-{fmt(end)} is outside {tech.name}'s reachable shift."))
            for ab in absences:
                if ab.tech_id == tech_id and start < ab.end and ab.start < end:
                    v.append(Violation(code="ABSENT", job_id=job_id, tech_id=tech_id,
                                       detail=f"{tech.name} is out during {job_id}."))
            if original is not None:
                before = original.job(job_id)
                if before.protected and start != before.start:
                    v.append(Violation(code="PROTECTED_MOVED", job_id=job_id,
                                       detail=f"Protected {job_id} moved from {fmt(before.start)} to {fmt(start)}."))
                tech_out = any(ab.tech_id == before.tech_id for ab in absences)
                if before.protected and tech_id != before.tech_id and not tech_out:
                    v.append(Violation(code="PROTECTED_MOVED", job_id=job_id,
                                       detail=f"Protected {job_id} changed tech although {before.tech_id} is available."))
            by_tech.setdefault(tech_id, []).append((start, end, job_id))

    for tech_id, items in by_tech.items():
        items.sort()
        for (s1, e1, j1), (s2, _e2, j2) in zip(items, items[1:]):
            gap_needed = company.travel_min(company.job(j1).zone, company.job(j2).zone)
            if s2 < e1:
                v.append(Violation(code="DOUBLE_BOOKED", tech_id=tech_id, job_id=j2,
                                   detail=f"{techs[tech_id].name}: {j1} and {j2} overlap."))
            elif s2 < e1 + gap_needed:
                v.append(Violation(code="TRAVEL", tech_id=tech_id, job_id=j2,
                                   detail=f"{techs[tech_id].name}: {s2 - e1} min between {j1} and {j2}, needs {gap_needed}."))
    return v


def check_plan(company: Company, plan: Plan) -> list[Violation]:
    placements = {a.job_id: [(a.tech_id, a.start)] for a in plan.assignments}
    v = check_schedule(company, placements, plan.absences, original=company)
    accounted = [a.job_id for a in plan.assignments] + list(plan.unassigned)
    for job in company.jobs:
        n = accounted.count(job.id)
        if n != 1:
            v.append(Violation(code="ACCOUNTING", job_id=job.id, detail=f"{job.id} appears {n} times in the plan."))
    return v
