"""Convert between plan-day minutes and real datetimes."""

from __future__ import annotations

import base64
import hashlib
import os
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo


def tz() -> ZoneInfo:
    return ZoneInfo(os.getenv("DEMO_TIMEZONE", "America/Los_Angeles"))


def plan_day() -> date:
    raw = os.getenv("DEMO_DATE")
    if raw:
        return date.fromisoformat(raw)
    return datetime.now(tz()).date()


def to_datetime(minutes: int, day: date | None = None) -> datetime:
    day = day or plan_day()
    return datetime.combine(day, time(0, 0), tzinfo=tz()) + timedelta(minutes=minutes)


def to_minutes(dt: datetime, day: date | None = None) -> int:
    day = day or plan_day()
    local = dt.astimezone(tz())
    midnight = datetime.combine(day, time(0, 0), tzinfo=tz())
    return int((local - midnight).total_seconds() // 60)


def parse_hhmm(value: str) -> int:
    h, m = value.strip().split(":")
    return int(h) * 60 + int(m)


def hhmm(minutes: int) -> str:
    h, m = divmod(int(minutes), 60)
    return f"{h:02d}:{m:02d}"


def event_id(*parts: str) -> str:
    """Deterministic Google Calendar event id (base32hex alphabet, lowercase)."""
    digest = hashlib.sha1("|".join(parts).encode()).digest()
    return "ss" + base64.b32hexencode(digest).decode().lower().rstrip("=")


def demo_now() -> int | None:
    """Simulated 'now' for the demo (e.g. 06:45 before shifts start). None = no freezing."""
    raw = os.getenv("DEMO_NOW", "06:45")
    return parse_hhmm(raw) if raw else None
