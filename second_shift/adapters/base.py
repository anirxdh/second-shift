"""The four app ports. Real adapters (Google, Slack) and in-memory fakes both
implement these, so the engine and the evals run the same code either way.

Every write is idempotent from the caller's side:
- Calendar events use caller-chosen ids; creating an id that exists returns the
  existing event instead of making a duplicate.
- Slack and Gmail writes carry a `key`; `find_by_key` lets the engine check
  whether a write already happened before retrying it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel


class TransientError(Exception):
    """Rate limit, 5xx, timeout. Safe to retry."""


class PermanentError(Exception):
    """Auth, validation, missing scope. Retrying won't help."""


class CalendarEvent(BaseModel):
    calendar_id: str
    event_id: str
    job_id: str | None
    plan_id: str | None = None
    start: int  # minutes since local midnight on the plan day
    end: int
    summary: str = ""


class ChatMessage(BaseModel):
    ts: str
    user: str | None
    text: str
    bot: bool = False


class SheetsPort(Protocol):
    def read_tab(self, tab: str) -> list[list[str]]:
        """All rows of a tab, header row first. Missing trailing cells may be absent."""

    def write_tab(self, tab: str, rows: list[list[str]]) -> None:
        """Replace a tab's contents (used by seeding/reset)."""

    def update_row(self, tab: str, key: str, values: dict[str, str]) -> None:
        """Set named columns on the row whose `id` column equals `key`. Idempotent."""


class CalendarPort(Protocol):
    def list_events(self, calendar_id: str) -> list[CalendarEvent]:
        """Confirmed (not cancelled) events on the plan day."""

    def create_event(
        self,
        calendar_id: str,
        event_id: str,
        start: int,
        end: int,
        summary: str,
        description: str,
        job_id: str,
        plan_id: str | None,
    ) -> CalendarEvent:
        """Create with a caller-chosen id. If the id already exists, return it unchanged."""

    def delete_event(self, calendar_id: str, event_id: str) -> None:
        """Delete. Already deleted or missing counts as success."""


class ChatPort(Protocol):
    def history(self, limit: int = 50) -> list[ChatMessage]:
        """Recent messages in the dispatch channel, newest first."""

    def post(self, text: str, key: str) -> str:
        """Post to the dispatch channel tagged with `key`. Returns message ts."""

    def find_by_key(self, key: str) -> str | None:
        """ts of a recent message tagged with `key`, else None."""

    def user_name(self, user_id: str) -> str | None:
        """Display name for a user id, else None."""


class MailPort(Protocol):
    def send(self, to: str, subject: str, body: str, key: str) -> str:
        """Send an email tagged with `key`. Returns message id."""

    def find_by_key(self, key: str) -> str | None:
        """Message id of a sent email tagged with `key`, else None."""


@dataclass
class Ports:
    sheets: SheetsPort
    calendar: CalendarPort
    chat: ChatPort
    mail: MailPort
    mode: str  # "fake" or "live"
