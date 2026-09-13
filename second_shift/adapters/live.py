"""Wire the real adapters together. Resource ids come from secrets/live_state.json,
which scripts/seed_live.py writes."""

from __future__ import annotations

import json
import os
from typing import Any

from .base import PermanentError, Ports
from .gmail import GmailMail
from .google_auth import PROJECT_ROOT, load_env
from .google_calendar import GoogleCalendar
from .google_sheets import GoogleSheets
from .slack import SlackChat

STATE_FILE = PROJECT_ROOT / "secrets" / "live_state.json"
SEED_HINT = "Run `uv run python scripts/seed_live.py` first."


def load_state() -> dict[str, Any]:
    if not STATE_FILE.exists():
        raise PermanentError(f"{STATE_FILE} not found: the live demo hasn't been seeded. {SEED_HINT}")
    return json.loads(STATE_FILE.read_text())


def save_state(state: dict[str, Any]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2) + "\n")


def build_live_ports() -> Ports:
    load_env()
    state = load_state()
    if not state.get("spreadsheet_id"):
        raise PermanentError(f"{STATE_FILE} has no spreadsheet_id. {SEED_HINT}")
    # Cheap env checks (Slack token, DEMO_GMAIL) run before Google sign-in can open a browser.
    chat = SlackChat(os.getenv("SLACK_BOT_TOKEN", ""), os.getenv("SLACK_DISPATCH_CHANNEL") or "dispatch")
    mail = GmailMail(os.getenv("DEMO_GMAIL", ""))
    return Ports(sheets=GoogleSheets(state["spreadsheet_id"]), calendar=GoogleCalendar(), chat=chat, mail=mail,
                 mode="live")
