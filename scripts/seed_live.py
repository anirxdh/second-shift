"""Seed or reset the live demo: Sheet tabs, one Google Calendar per technician,
and the plan day's bookings.

Idempotent. Reuses the spreadsheet and calendars recorded in
secrets/live_state.json, deletes our events on the plan day, books every
scheduled job again (fresh event ids per run), and rewrites the tabs.

    uv run python scripts/seed_live.py            # do it
    uv run python scripts/seed_live.py --dry-run  # show what would happen; no API calls

Optional .env: DEMO_SLACK_USER_MAP="T1=U0123,T2=U0456" links technicians to Slack users.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from second_shift.adapters.base import TransientError  # noqa: E402
from second_shift.adapters.google_auth import build_service, load_env  # noqa: E402
from second_shift.adapters.google_calendar import GoogleCalendar  # noqa: E402
from second_shift.adapters.google_sheets import GoogleSheets  # noqa: E402
from second_shift.adapters.live import STATE_FILE, save_state  # noqa: E402
from second_shift.clock import event_id, plan_day  # noqa: E402
from second_shift.fixtures import load_company  # noqa: E402
from second_shift.models import Company, Job, fmt  # noqa: E402
from second_shift.sheet_codec import company_to_tabs  # noqa: E402

TITLE = "Second Shift - Bayside Home Services"


def calendar_name(tech_name: str) -> str:
    return f"Second Shift · {tech_name}"


def summary(job: Job) -> str:
    return f"{job.id} · {job.customer} · {job.service}"


def description(job: Job) -> str:
    return (f"{job.address} ({job.zone})\nPromised arrival: {fmt(job.window_start)}-{fmt(job.window_end)}\n"
            f"Skills: {', '.join(job.required_skills)}")


def parse_slack_map(raw: str) -> dict[str, str]:
    """'T1=U0123, T2=U0456' -> {'T1': 'U0123', 'T2': 'U0456'}"""
    pairs = (part.split("=", 1) for part in raw.split(",") if "=" in part)
    return {k.strip(): v.strip() for k, v in pairs if k.strip() and v.strip()}


def retry[T](fn: Callable[..., T], *args: Any, attempts: int = 4) -> T:
    """Retry an idempotent write on TransientError (rate limits, 5xx) with backoff."""
    for attempt in range(1, attempts + 1):
        try:
            return fn(*args)
        except TransientError as err:
            if attempt == attempts:
                raise
            print(f"    transient error ({err}); retrying in {2 ** attempt}s")
            time.sleep(2 ** attempt)
    raise AssertionError("unreachable")


def scheduled(company: Company, tech_id: str) -> list[Job]:
    return sorted((j for j in company.jobs if j.tech_id == tech_id and j.start is not None), key=lambda j: j.start)


def dry_run(company: Company, state: dict[str, Any]) -> None:
    sheet = state.get("spreadsheet_id")
    print(f"Spreadsheet: {f'reuse {sheet} (or create {TITLE!r} if it is gone)' if sheet else f'create {TITLE!r}'}")
    for tech in company.technicians:
        cal = state.get("calendars", {}).get(tech.id)
        how = f"reuse {cal}" if cal else f"find or create {calendar_name(tech.name)!r}"
        print(f"Calendar for {tech.name} ({tech.id}): {how}; slack_user_id={tech.slack_user_id or '-'}")
        print("  delete our events on the plan day, then book:")
        for job in scheduled(company, tech.id):
            print(f"    {fmt(job.start)}-{fmt(job.start + job.duration)}  {summary(job)}")
    for tab, rows in company_to_tabs(company).items():
        print(f"Tab {tab!r}: write {len(rows) - 1} rows + header")
    print(f"Save {STATE_FILE}")
    print("Dry run: nothing was changed.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="print what would happen without calling any API")
    args = parser.parse_args()

    load_env()
    demo_gmail = os.getenv("DEMO_GMAIL", "").strip()
    if not demo_gmail and not args.dry_run:
        print("DEMO_GMAIL is not set in .env (SETUP.md step 1).")
        return 1
    company = load_company(demo_gmail or None)
    state: dict[str, Any] = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
    slack_map = parse_slack_map(os.getenv("DEMO_SLACK_USER_MAP", ""))
    known = {t.id for t in company.technicians}
    for tech_id in sorted(set(slack_map) - known):
        print(f"Warning: DEMO_SLACK_USER_MAP names unknown technician {tech_id!r}; ignored.")
    for tech in company.technicians:
        tech.slack_user_id = slack_map.get(tech.id)
    day = plan_day()
    print(f"Plan day: {day.isoformat()} ({os.getenv('DEMO_TIMEZONE', 'America/Los_Angeles')})")
    if args.dry_run:
        dry_run(company, state)
        return 0

    # 1. Spreadsheet: reuse the recorded one if it still exists.
    sheets_svc = build_service("sheets", "v4")
    sheets = GoogleSheets(state["spreadsheet_id"], service=sheets_svc) if state.get("spreadsheet_id") else None
    if sheets is not None and sheets.title() is None:
        print("Recorded spreadsheet no longer exists; creating a new one.")
        sheets = None
    if sheets is None:
        tabs = list(company_to_tabs(company))
        sheets = GoogleSheets(GoogleSheets.create_spreadsheet(TITLE, tabs, service=sheets_svc), service=sheets_svc)
        print(f"Created spreadsheet {TITLE!r}")

    # 2. One calendar per technician: recorded id, else same name, else create.
    cal = GoogleCalendar()
    existing = cal.list_calendars()
    by_name = {name: cid for cid, name in existing.items()}
    calendars: dict[str, str] = {}
    for tech in company.technicians:
        cid = state.get("calendars", {}).get(tech.id)
        if cid not in existing:
            cid = by_name.get(calendar_name(tech.name))
            if cid is None:
                cid = cal.create_calendar(calendar_name(tech.name))
                print(f"Created calendar {calendar_name(tech.name)!r}")
        tech.calendar_id = calendars[tech.id] = cid
    # Record ids now so a re-run after a failure reuses them instead of creating duplicates.
    save_state({**state, "spreadsheet_id": sheets.spreadsheet_id, "calendars": calendars})

    # 3. Bookings: clear ours for the day, then book each scheduled job with a fresh id.
    seed_run = f"{datetime.now(timezone.utc):%Y%m%d%H%M%S}-{uuid.uuid4().hex[:6]}"
    total = 0
    for tech in company.technicians:
        removed = retry(cal.clear_day, tech.calendar_id)
        jobs = scheduled(company, tech.id)
        for job in jobs:
            retry(cal.create_event, tech.calendar_id, event_id("seed", seed_run, job.id), job.start,
                  job.start + job.duration, summary(job), description(job), job.id, None)
        total += len(jobs)
        print(f"{tech.name}: removed {removed} old event(s), booked {len(jobs)}")

    # 4. Tabs (Technicians now carry calendar and Slack ids).
    for tab, rows in company_to_tabs(company).items():
        retry(sheets.write_tab, tab, rows)
        print(f"Wrote tab {tab!r} ({len(rows) - 1} rows)")

    save_state({"spreadsheet_id": sheets.spreadsheet_id, "calendars": calendars,
                "seeded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "plan_day": day.isoformat(), "seed_run": seed_run})
    print(f"\nSeeded {len(company.technicians)} calendars and {total} bookings for {day.isoformat()}.")
    print(f"Spreadsheet: {sheets.url}")
    print(f"State saved to {STATE_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
