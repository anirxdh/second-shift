"""Check every account connection the live demo needs. Read-only: nothing is written
to Slack, Google, or Anthropic (the only local write is the Google token cache).

    uv run python scripts/check_setup.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from second_shift.adapters.google_auth import PROJECT_ROOT, client_file, load_env, token_file  # noqa: E402

SLACK_SCOPES = {"channels:history", "channels:read", "channels:join", "chat:write", "users:read"}
failures = 0


def line(status: str, what: str, fix: str = "") -> None:
    global failures
    failures += status == "FAIL"
    print(f"{status:4}  {what}" + (f"  ->  fix: {fix}" if fix and status != "PASS" else ""))


def check_anthropic() -> None:
    if not os.getenv("ANTHROPIC_API_KEY"):
        return line("FAIL", "ANTHROPIC_API_KEY is set", "create a key at console.anthropic.com and put it in .env")
    import anthropic

    client = anthropic.Anthropic()
    try:
        client.models.list(limit=1)
    except anthropic.APIError as err:
        return line("FAIL", f"Anthropic API key works ({type(err).__name__})", "check ANTHROPIC_API_KEY in .env")
    line("PASS", "Anthropic API key works")
    model = os.getenv("SECOND_SHIFT_MODEL")
    if model:
        try:
            client.models.retrieve(model)
            line("PASS", f"Model {model} is available")
        except anthropic.APIError as err:
            line("FAIL", f"Model {model} is available ({type(err).__name__})",
                 "set SECOND_SHIFT_MODEL in .env to a model id your key can use")


def check_slack() -> None:
    token = os.getenv("SLACK_BOT_TOKEN")
    if not token:
        return line("FAIL", "SLACK_BOT_TOKEN is set", "copy the Bot User OAuth Token (xoxb-...) into .env (SETUP.md step 2)")
    from slack_sdk import WebClient
    from slack_sdk.errors import SlackApiError

    from second_shift.adapters.slack import SlackChat

    try:
        auth = WebClient(token=token, timeout=15).auth_test()
    except SlackApiError as err:
        return line("FAIL", f"Slack token works (auth.test: {err.response.get('error')})",
                    "reinstall the app and copy a fresh xoxb- token into .env")
    line("PASS", f"Slack token works (bot {auth.get('user')} in workspace {auth.get('team')})")
    header = next((v for k, v in auth.headers.items() if k.lower() == "x-oauth-scopes"), None)
    granted = {s.strip() for s in header.split(",")} if header else set(SLACK_SCOPES)  # unknown: assume ok
    missing = SLACK_SCOPES - granted
    line("FAIL" if missing else "PASS", "Slack app has the scopes it needs" + (f" (missing {sorted(missing)})" if missing else ""),
         "recreate the app from slack-app-manifest.yaml and reinstall it")
    name = (os.getenv("SLACK_DISPATCH_CHANNEL") or "dispatch").lstrip("#")
    try:
        channel = SlackChat(token, name).find_channel()
    except Exception as err:  # noqa: BLE001 - report any failure as a FAIL line
        return line("FAIL", f"Slack channel #{name} is readable ({err})", "check the app's channels:read scope")
    if channel is None:
        return line("FAIL", f"Slack channel #{name} exists", f"create a public channel named #{name}")
    if channel.get("is_member"):
        line("PASS", f"Slack channel #{name} exists and the bot is a member")
    elif "channels:join" in granted:
        line("PASS", f"Slack channel #{name} exists; the bot will join it on first use")
    else:
        line("FAIL", f"Slack bot can join #{name}", f"in Slack, type /invite @Second Shift in #{name}")


def check_google() -> None:
    from second_shift.adapters.google_auth import build_service, get_credentials
    from second_shift.adapters.google_errors import execute

    if not client_file().exists():
        return line("FAIL", f"Google OAuth client file at {client_file().relative_to(PROJECT_ROOT)}",
                    "SETUP.md step 1: create a Desktop OAuth client, download its JSON to that path")
    if not token_file().exists():
        print("      Google sign-in opens in your browser now (first run only). Approve all requested access.")
    try:
        get_credentials()
    except Exception as err:  # noqa: BLE001
        return line("FAIL", f"Google sign-in ({err})", "delete secrets/google_token.json and run this again")
    line("PASS", "Google sign-in works")

    try:
        execute(build_service("calendar", "v3").calendarList().list(maxResults=1))
        line("PASS", "Google Calendar API reachable")
    except Exception as err:  # noqa: BLE001
        line("FAIL", f"Google Calendar API reachable ({err})", "enable 'Google Calendar API' in the Cloud project")

    demo = os.getenv("DEMO_GMAIL", "").strip()
    try:
        me = execute(build_service("gmail", "v1").users().getProfile(userId="me"))["emailAddress"]
        if not demo:
            line("FAIL", f"DEMO_GMAIL is set (signed in as {me})", f"set DEMO_GMAIL={me} in .env")
        elif me.lower() != demo.lower():
            line("FAIL", f"DEMO_GMAIL matches the signed-in account ({demo} vs {me})",
                 "fix DEMO_GMAIL, or delete secrets/google_token.json and sign in with that account")
        else:
            line("PASS", f"Gmail API reachable; signed in as {me}")
    except Exception as err:  # noqa: BLE001
        line("FAIL", f"Gmail API reachable ({err})", "enable 'Gmail API' in the Cloud project")

    try:
        build_service("sheets", "v4")
        line("PASS", "Google Sheets client builds")
    except Exception as err:  # noqa: BLE001
        return line("FAIL", f"Google Sheets client builds ({err})", "enable 'Google Sheets API' in the Cloud project")
    check_seeded()


def check_seeded() -> None:
    from second_shift.adapters.google_calendar import GoogleCalendar
    from second_shift.adapters.google_sheets import GoogleSheets
    from second_shift.adapters.live import load_state, STATE_FILE

    if not STATE_FILE.exists():
        return line("TODO", "Live demo seeded", "run `uv run python scripts/seed_live.py`")
    state = load_state()
    try:
        title = GoogleSheets(state["spreadsheet_id"]).title()
        line("PASS" if title else "FAIL", f"Seeded spreadsheet opens ({title or 'not found'})",
             "run `uv run python scripts/seed_live.py` to recreate it")
    except Exception as err:  # noqa: BLE001
        line("FAIL", f"Seeded spreadsheet opens ({err})", "enable 'Google Sheets API' in the Cloud project")
    try:
        have = GoogleCalendar().list_calendars()
        cals = state.get("calendars", {})
        found = sum(1 for cid in cals.values() if cid in have)
        line("PASS" if cals and found == len(cals) else "FAIL", f"Seeded technician calendars found ({found}/{len(cals)})",
             "run `uv run python scripts/seed_live.py` to recreate them")
    except Exception as err:  # noqa: BLE001
        line("FAIL", f"Seeded technician calendars found ({err})", "run `uv run python scripts/seed_live.py`")


def main() -> int:
    env = PROJECT_ROOT / ".env"
    line("PASS" if env.exists() else "FAIL", ".env exists", "cp .env.example .env, then fill it in (SETUP.md)")
    load_env()
    for check in (check_anthropic, check_slack, check_google):
        try:
            check()
        except Exception as err:  # noqa: BLE001 - one broken check must not hide the others
            line("FAIL", f"{check.__name__} crashed: {err!r}")
    print("\nAll good." if not failures else f"\n{failures} check(s) failed.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
