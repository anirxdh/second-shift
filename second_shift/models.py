"""Domain model. Times are minutes since local midnight on the plan day."""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, Field


def fmt(minutes: int | None) -> str:
    """480 -> '8:00 AM'."""
    if minutes is None:
        return "-"
    h, m = divmod(int(minutes), 60)
    suffix = "AM" if h < 12 else "PM"
    h12 = h % 12 or 12
    return f"{h12}:{m:02d} {suffix}"


class Technician(BaseModel):
    id: str
    name: str
    skills: list[str]
    equipment: list[str] = Field(default_factory=list)
    shift_start: int
    shift_end: int
    home_zone: str
    slack_user_id: str | None = None
    calendar_id: str | None = None

    def can_do(self, job: "Job") -> bool:
        return set(job.required_skills) <= set(self.skills) and set(job.required_equipment) <= set(
            self.equipment
        )


class Job(BaseModel):
    id: str
    customer: str
    customer_email: str
    address: str
    zone: str
    service: str
    required_skills: list[str]
    required_equipment: list[str] = Field(default_factory=list)
    duration: int
    window_start: int  # earliest promised arrival
    window_end: int  # latest promised arrival
    start: int | None  # scheduled start; None = not scheduled
    tech_id: str | None
    protected: bool = False  # time is contractually fixed
    priority: int = 2  # 1 urgent, 2 normal, 3 flexible

    @property
    def end(self) -> int | None:
        return None if self.start is None else self.start + self.duration


class Company(BaseModel):
    name: str
    timezone: str
    zones: list[str]
    travel: dict[str, dict[str, int]]  # minutes, zone -> zone
    technicians: list[Technician]
    jobs: list[Job]

    def tech(self, tech_id: str) -> Technician:
        return next(t for t in self.technicians if t.id == tech_id)

    def job(self, job_id: str) -> Job:
        return next(j for j in self.jobs if j.id == job_id)

    def travel_min(self, a: str, b: str) -> int:
        return self.travel[a][b]

    def fingerprint(self) -> str:
        """Hash of everything a plan depends on. Used to detect stale plans."""
        payload = {
            "techs": sorted(
                [t.id, sorted(t.skills), sorted(t.equipment), t.shift_start, t.shift_end, t.home_zone]
                for t in self.technicians
            ),
            "jobs": sorted(
                [
                    j.id,
                    j.tech_id,
                    j.start,
                    j.duration,
                    j.window_start,
                    j.window_end,
                    sorted(j.required_skills),
                    sorted(j.required_equipment),
                    j.protected,
                ]
                for j in self.jobs
            ),
        }
        raw = json.dumps(payload, sort_keys=True, default=str).encode()
        return hashlib.sha256(raw).hexdigest()[:16]


class Absence(BaseModel):
    tech_id: str
    start: int
    end: int
    reason: str = "callout"  # "callout" or "calendar_busy" (a non-job event on their calendar)


class Assignment(BaseModel):
    job_id: str
    tech_id: str
    start: int


ChangeKind = Literal["reassigned", "retimed", "unassigned", "unchanged"]


class JobChange(BaseModel):
    job_id: str
    kind: ChangeKind
    from_tech: str | None
    to_tech: str | None
    from_start: int | None
    to_start: int | None
    customer_notice: bool
    note: str = ""


class Plan(BaseModel):
    id: str
    absences: list[Absence]
    assignments: list[Assignment]
    unassigned: list[str]
    changes: list[JobChange]
    solver_status: str
    objective: dict[str, int] = Field(default_factory=dict)
    source_fingerprint: str
    solve_ms: int = 0

    def assignment(self, job_id: str) -> Assignment | None:
        return next((a for a in self.assignments if a.job_id == job_id), None)

    def changed(self) -> list[JobChange]:
        return [c for c in self.changes if c.kind != "unchanged"]
