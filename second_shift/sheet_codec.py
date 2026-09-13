"""Company <-> spreadsheet rows. Shared by the fake and real Sheets adapters so
the parsing code is exercised in every test.

Tabs:
  Technicians: master data plus Slack user and Calendar ids.
  Jobs:        requirements, customer, promised window, and the booking columns
               the engine writes back (assigned_tech, scheduled_start, status, last_plan).
  Travel:      drive-time matrix in minutes.

The schedule of record (who is where, when) is Google Calendar. The Jobs tab's
booking columns are a mirror the engine keeps in sync and reconciles on load.
"""

from __future__ import annotations

from .clock import hhmm, parse_hhmm
from .models import Company, Job, Technician

TECH_COLS = ["id", "name", "skills", "equipment", "shift_start", "shift_end", "home_zone", "slack_user_id", "calendar_id"]
JOB_COLS = [
    "id", "customer", "customer_email", "address", "zone", "service", "required_skills", "required_equipment",
    "duration_min", "window_start", "window_end", "priority", "protected",
    "assigned_tech", "scheduled_start", "status", "last_plan",
]


def _split(v: str) -> list[str]:
    return [p.strip() for p in (v or "").split(",") if p.strip()]


def _rows_to_dicts(rows: list[list[str]]) -> list[dict[str, str]]:
    if not rows:
        return []
    header = [h.strip() for h in rows[0]]
    out = []
    for row in rows[1:]:
        if not any(cell.strip() for cell in row):
            continue
        padded = list(row) + [""] * (len(header) - len(row))
        out.append(dict(zip(header, padded)))
    return out


def company_to_tabs(company: Company) -> dict[str, list[list[str]]]:
    techs = [TECH_COLS] + [
        [t.id, t.name, ", ".join(t.skills), ", ".join(t.equipment), hhmm(t.shift_start), hhmm(t.shift_end),
         t.home_zone, t.slack_user_id or "", t.calendar_id or ""]
        for t in company.technicians
    ]
    jobs = [JOB_COLS] + [
        [j.id, j.customer, j.customer_email, j.address, j.zone, j.service, ", ".join(j.required_skills),
         ", ".join(j.required_equipment), str(j.duration), hhmm(j.window_start), hhmm(j.window_end), str(j.priority),
         "yes" if j.protected else "no", j.tech_id or "", hhmm(j.start) if j.start is not None else "",
         "scheduled", ""]
        for j in company.jobs
    ]
    travel = [["from \\ to"] + company.zones] + [
        [a] + [str(company.travel[a][b]) for b in company.zones] for a in company.zones
    ]
    return {"Technicians": techs, "Jobs": jobs, "Travel": travel}


def tabs_to_company(tabs: dict[str, list[list[str]]], name: str, timezone: str) -> Company:
    techs = [
        Technician(
            id=r["id"], name=r["name"], skills=_split(r["skills"]), equipment=_split(r["equipment"]),
            shift_start=parse_hhmm(r["shift_start"]), shift_end=parse_hhmm(r["shift_end"]),
            home_zone=r["home_zone"], slack_user_id=r.get("slack_user_id") or None,
            calendar_id=r.get("calendar_id") or None,
        )
        for r in _rows_to_dicts(tabs["Technicians"])
    ]
    jobs = [
        Job(
            id=r["id"], customer=r["customer"], customer_email=r["customer_email"], address=r["address"],
            zone=r["zone"], service=r["service"], required_skills=_split(r["required_skills"]),
            required_equipment=_split(r["required_equipment"]), duration=int(r["duration_min"]),
            window_start=parse_hhmm(r["window_start"]), window_end=parse_hhmm(r["window_end"]),
            priority=int(r["priority"] or 2), protected=r["protected"].strip().lower() in ("yes", "true", "1"),
            tech_id=r.get("assigned_tech") or None,
            start=parse_hhmm(r["scheduled_start"]) if r.get("scheduled_start") else None,
        )
        for r in _rows_to_dicts(tabs["Jobs"])
    ]
    travel_rows = tabs["Travel"]
    zones = [z.strip() for z in travel_rows[0][1:]]
    travel = {row[0].strip(): {z: int(v) for z, v in zip(zones, row[1:])} for row in travel_rows[1:] if row}
    return Company(name=name, timezone=timezone, zones=zones, travel=travel, technicians=techs, jobs=jobs)
