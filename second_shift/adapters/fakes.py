"""In-memory stand-ins for Sheets, Calendar, Slack and Gmail.

Same contracts as the real adapters, plus fault injection so the evals can
prove the engine survives rate limits, crashes mid-run, and concurrent edits.
Faults are queued per operation name: "calendar.create", "calendar.delete",
"calendar.list", "sheets.update", "chat.post", "mail.send".
  - TransientError / PermanentError instances are raised before the write.
  - The string "crash_after" performs the write, then raises CrashAfterWrite,
    simulating a process dying before it could record success.
"""

from __future__ import annotations

import itertools
from collections import defaultdict

from ..fixtures import load_company
from ..sheet_codec import company_to_tabs
from .base import CalendarEvent, ChatMessage, PermanentError, Ports, TransientError


class CrashAfterWrite(Exception):
    """The write landed but the caller never heard back."""


class Faults:
    def __init__(self) -> None:
        self.queue: dict[str, list] = defaultdict(list)
        self.calls: dict[str, int] = defaultdict(int)

    def add(self, op: str, *faults) -> None:
        self.queue[op].extend(faults)

    def before(self, op: str) -> bool:
        """Raise a queued pre-write fault. Returns True if a crash_after is armed."""
        self.calls[op] += 1
        if not self.queue[op]:
            return False
        fault = self.queue[op].pop(0)
        if fault == "crash_after":
            return True
        raise fault


class FakeSheets:
    def __init__(self, tabs: dict[str, list[list[str]]], faults: Faults) -> None:
        self.tabs = {k: [list(r) for r in v] for k, v in tabs.items()}
        self.faults = faults

    def read_tab(self, tab: str) -> list[list[str]]:
        return [list(r) for r in self.tabs[tab]]

    def write_tab(self, tab: str, rows: list[list[str]]) -> None:
        self.tabs[tab] = [list(r) for r in rows]

    def update_row(self, tab: str, key: str, values: dict[str, str]) -> None:
        crash = self.faults.before("sheets.update")
        rows = self.tabs[tab]
        header = rows[0]
        for row in rows[1:]:
            if row and row[0] == key:
                for col, value in values.items():
                    if col not in header:
                        raise PermanentError(f"No column {col}")
                    idx = header.index(col)
                    row.extend([""] * (idx + 1 - len(row)))
                    row[idx] = value
                if crash:
                    raise CrashAfterWrite("sheets.update")
                return
        raise PermanentError(f"No row {key} in {tab}")


class FakeCalendar:
    def __init__(self, faults: Faults) -> None:
        self.events: dict[str, dict[str, CalendarEvent]] = defaultdict(dict)  # cal -> id -> event
        self.deleted: set[tuple[str, str]] = set()
        self.faults = faults
        self.version = 0

    def list_events(self, calendar_id: str) -> list[CalendarEvent]:
        self.faults.before("calendar.list")
        return sorted(self.events[calendar_id].values(), key=lambda e: e.start)

    def create_event(self, calendar_id, event_id, start, end, summary, description, job_id, plan_id) -> CalendarEvent:
        crash = self.faults.before("calendar.create")
        existing = self.events[calendar_id].get(event_id)
        if existing is not None:
            return existing
        # A deleted id is restored in place, matching the real adapter's 409 -> un-cancel path.
        self.deleted.discard((calendar_id, event_id))
        ev = CalendarEvent(calendar_id=calendar_id, event_id=event_id, job_id=job_id, plan_id=plan_id,
                           start=start, end=end, summary=summary)
        self.events[calendar_id][event_id] = ev
        self.version += 1
        if crash:
            raise CrashAfterWrite("calendar.create")
        return ev

    def delete_event(self, calendar_id: str, event_id: str) -> None:
        crash = self.faults.before("calendar.delete")
        if self.events[calendar_id].pop(event_id, None) is not None:
            self.deleted.add((calendar_id, event_id))
            self.version += 1
        if crash:
            raise CrashAfterWrite("calendar.delete")

    # Test helper: someone edits the calendar by hand.
    def human_edit(self, calendar_id: str, event: CalendarEvent) -> None:
        self.events[calendar_id][event.event_id] = event
        self.version += 1


class FakeChat:
    def __init__(self, faults: Faults, users: dict[str, str] | None = None) -> None:
        self.messages: list[tuple[ChatMessage, str | None]] = []  # (message, key), oldest first
        self.users = users or {}
        self.faults = faults
        self._ts = itertools.count(1)

    def history(self, limit: int = 50) -> list[ChatMessage]:
        return [m for m, _ in reversed(self.messages)][:limit]

    def post(self, text: str, key: str) -> str:
        crash = self.faults.before("chat.post")
        ts = f"{next(self._ts)}.0001"
        self.messages.append((ChatMessage(ts=ts, user="B_SECOND_SHIFT", text=text, bot=True), key))
        if crash:
            raise CrashAfterWrite("chat.post")
        return ts

    def find_by_key(self, key: str) -> str | None:
        return next((m.ts for m, k in self.messages if k == key), None)

    def user_name(self, user_id: str) -> str | None:
        return self.users.get(user_id)

    # Test helper: a person posts in the channel.
    def human_post(self, user_id: str, text: str) -> ChatMessage:
        msg = ChatMessage(ts=f"{next(self._ts)}.0001", user=user_id, text=text)
        self.messages.append((msg, None))
        return msg

    def bot_posts(self) -> list[tuple[ChatMessage, str | None]]:
        return [(m, k) for m, k in self.messages if m.bot]


class FakeMail:
    def __init__(self, faults: Faults) -> None:
        self.sent: list[dict] = []
        self.faults = faults

    def send(self, to: str, subject: str, body: str, key: str) -> str:
        crash = self.faults.before("mail.send")
        mid = f"m{len(self.sent) + 1}"
        self.sent.append({"id": mid, "to": to, "subject": subject, "body": body, "key": key})
        if crash:
            raise CrashAfterWrite("mail.send")
        return mid

    def find_by_key(self, key: str) -> str | None:
        return next((m["id"] for m in self.sent if m["key"] == key), None)


def build_fake_ports(demo_gmail: str | None = None) -> tuple[Ports, Faults]:
    """Fake workspace seeded exactly like the live demo (same codec, same event ids scheme)."""
    from ..clock import event_id

    faults = Faults()
    company = load_company(demo_gmail)
    for tech in company.technicians:
        tech.calendar_id = f"cal-{tech.id}"
    # In the fake workspace, Marco and the dispatcher have Slack ids.
    company.technicians[0].slack_user_id = "U_MARCO"
    tabs = company_to_tabs(company)
    sheets = FakeSheets(tabs, faults)
    cal = FakeCalendar(faults)
    for job in company.jobs:
        tech = company.tech(job.tech_id)
        cal.events[tech.calendar_id][event_id("seed", job.id)] = CalendarEvent(
            calendar_id=tech.calendar_id, event_id=event_id("seed", job.id), job_id=job.id,
            start=job.start, end=job.start + job.duration, summary=f"{job.id} · {job.customer}")
    users = {"U_MARCO": "Marco Diaz", "U_DISPATCH": "Dana (dispatcher)", "U_STRANGER": "Pat Unknown"}
    ports = Ports(sheets=sheets, calendar=cal, chat=FakeChat(faults, users), mail=FakeMail(faults), mode="fake")
    return ports, faults
