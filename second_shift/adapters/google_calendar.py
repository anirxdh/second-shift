"""CalendarPort on the Google Calendar API. One secondary calendar per technician.

Events we create carry extendedProperties.private {app: "second-shift", job_id, plan_id};
anything else on a technician's calendar is treated as a busy block (job_id None).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ..clock import to_datetime, to_minutes, tz
from .base import CalendarEvent, PermanentError
from .google_auth import build_service
from .google_errors import execute

APP_TAG = "second-shift"


def _private(item: dict[str, Any]) -> dict[str, str]:
    return (item.get("extendedProperties") or {}).get("private") or {}


def is_ours(item: dict[str, Any]) -> bool:
    return _private(item).get("app") == APP_TAG


def to_event(calendar_id: str, item: dict[str, Any]) -> CalendarEvent | None:
    """Google event -> CalendarEvent; None for all-day events (no dateTime)."""
    start, end = (item.get("start") or {}).get("dateTime"), (item.get("end") or {}).get("dateTime")
    if not start or not end:
        return None
    ours, private = is_ours(item), _private(item)
    return CalendarEvent(
        calendar_id=calendar_id,
        event_id=item["id"],
        job_id=(private.get("job_id") or None) if ours else None,
        plan_id=(private.get("plan_id") or None) if ours else None,
        start=to_minutes(datetime.fromisoformat(start)),
        end=to_minutes(datetime.fromisoformat(end)),
        summary=item.get("summary", ""),
    )


def event_body(event_id: str, start: int, end: int, summary: str, description: str, job_id: str,
               plan_id: str | None) -> dict[str, Any]:
    zone = tz().key
    return {
        "id": event_id,
        "summary": summary,
        "description": description,
        "start": {"dateTime": to_datetime(start).isoformat(), "timeZone": zone},
        "end": {"dateTime": to_datetime(end).isoformat(), "timeZone": zone},
        "extendedProperties": {"private": {"app": APP_TAG, "job_id": job_id, "plan_id": plan_id or ""}},
        "reminders": {"useDefault": False},
    }


class GoogleCalendar:
    def __init__(self, service: Any | None = None) -> None:
        self._svc = service or build_service("calendar", "v3")

    # ---------- CalendarPort ----------
    def list_events(self, calendar_id: str) -> list[CalendarEvent]:
        events = (to_event(calendar_id, item) for item in self._day_items(calendar_id))
        return [e for e in events if e is not None]

    def create_event(self, calendar_id: str, event_id: str, start: int, end: int, summary: str,
                     description: str, job_id: str, plan_id: str | None) -> CalendarEvent:
        body = event_body(event_id, start, end, summary, description, job_id, plan_id)
        events = self._svc.events()
        item = execute(events.insert(calendarId=calendar_id, body=body), none_on=(409,))
        if item is None:
            # 409: the id is taken. Either an earlier attempt landed (return it unchanged)
            # or the event was deleted, which Google keeps as "cancelled" (restore it in place).
            item = execute(events.get(calendarId=calendar_id, eventId=event_id), none_on=(404, 410))
            if item is None or item.get("status") == "cancelled":
                item = execute(events.update(calendarId=calendar_id, eventId=event_id,
                                             body={**body, "status": "confirmed"}))
        event = to_event(calendar_id, item)
        if event is None:
            raise PermanentError(f"Event {event_id} on {calendar_id} is an all-day event, not a job booking")
        return event

    def delete_event(self, calendar_id: str, event_id: str) -> None:
        execute(self._svc.events().delete(calendarId=calendar_id, eventId=event_id), none_on=(404, 410))

    # ---------- seeding helpers ----------
    def list_calendars(self) -> dict[str, str]:
        """calendar id -> summary for calendars we can write to."""
        out: dict[str, str] = {}
        token = None
        while True:
            page = execute(self._svc.calendarList().list(minAccessRole="writer", maxResults=250, pageToken=token))
            out.update({c["id"]: c.get("summary", "") for c in page.get("items", [])})
            token = page.get("nextPageToken")
            if not token:
                return out

    def find_calendar(self, summary: str) -> str | None:
        return next((cid for cid, name in self.list_calendars().items() if name == summary), None)

    def create_calendar(self, summary: str) -> str:
        return execute(self._svc.calendars().insert(body={"summary": summary, "timeZone": tz().key}))["id"]

    def clear_day(self, calendar_id: str) -> int:
        """Delete every event we created on the plan day. Returns how many."""
        ours = [item["id"] for item in self._day_items(calendar_id) if is_ours(item)]
        for event_id in ours:
            self.delete_event(calendar_id, event_id)
        return len(ours)

    def _day_items(self, calendar_id: str) -> list[dict[str, Any]]:
        """Raw confirmed events overlapping the plan day [00:00, 24:00)."""
        items: list[dict[str, Any]] = []
        token = None
        while True:
            page = execute(self._svc.events().list(
                calendarId=calendar_id, timeMin=to_datetime(0).isoformat(), timeMax=to_datetime(24 * 60).isoformat(),
                singleEvents=True, showDeleted=False, orderBy="startTime", timeZone=tz().key, maxResults=250,
                pageToken=token))
            items += [i for i in page.get("items", []) if i.get("status") != "cancelled"]
            token = page.get("nextPageToken")
            if not token:
                return items
