"""Offline tests for the real adapters. Google clients are the real discovery-built
ones (bundled discovery docs) talking to HttpMockSequence, so request paths and
parameter names are checked against the actual API schemas. No network."""

from __future__ import annotations

import base64
import email
import importlib.util
import json
import sys
from email import policy
from pathlib import Path
from unittest.mock import MagicMock
from urllib.error import URLError
from urllib.parse import parse_qs, unquote, urlparse

import httplib2
import pytest
from google.auth.exceptions import RefreshError
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import HttpMockSequence
from slack_sdk.errors import SlackApiError
from slack_sdk.web.slack_response import SlackResponse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from second_shift.adapters import live  # noqa: E402
from second_shift.adapters.base import PermanentError, TransientError  # noqa: E402
from second_shift.adapters.gmail import GmailMail, is_demo_recipient, key_tag  # noqa: E402
from second_shift.adapters.google_calendar import GoogleCalendar  # noqa: E402
from second_shift.adapters.google_errors import execute, to_port_error  # noqa: E402
from second_shift.adapters.google_sheets import GoogleSheets, column_letter  # noqa: E402
from second_shift.adapters.slack import SlackChat  # noqa: E402
from second_shift.sheet_codec import JOB_COLS  # noqa: E402

DEMO = "demo.inbox@gmail.com"


@pytest.fixture(autouse=True)
def plan_day(monkeypatch):
    monkeypatch.setenv("DEMO_DATE", "2026-09-13")
    monkeypatch.setenv("DEMO_TIMEZONE", "America/Los_Angeles")


def google(name: str, version: str, *responses: tuple[int, object]):
    """Real discovery client over a scripted HTTP sequence. Returns (service, http)."""
    seq = [({"status": str(s)}, b if isinstance(b, str) else json.dumps(b)) for s, b in responses]
    http = HttpMockSequence(seq)
    return build(name, version, http=http, static_discovery=True), http


def requests_made(http) -> list[tuple[str, str, dict, dict]]:
    """(method, path, query, json_body) for each request."""
    out = []
    for uri, method, body, _headers in http.request_sequence:
        u = urlparse(uri)
        out.append((method, unquote(u.path), {k: v[0] for k, v in parse_qs(u.query).items()},
                    json.loads(body) if body else {}))
    return out


def http_error(status: int, body: dict | None = None) -> HttpError:
    return HttpError(httplib2.Response({"status": status}), json.dumps(body or {}).encode())


# ---------------- Gmail ----------------
@pytest.mark.parametrize("to", [DEMO, "demo.inbox+cust-lee@gmail.com", "DEMO.INBOX+X@Gmail.com", " demo.inbox+x@gmail.com "])
def test_gmail_guard_allows_demo_inbox_and_plus_aliases(to):
    assert is_demo_recipient(to, DEMO)


@pytest.mark.parametrize("to", [
    "someone@gmail.com", "demo.inbox@evil.com", "demo.inboxx@gmail.com", "evil+demo.inbox@gmail.com",
    "demo.inbox+x@gmail.com, boss@corp.com", "Rosa <demo.inbox+x@gmail.com>", "demo.inbox+x@gmail.com\nBcc: a@b.com",
    "demo.inbox@gmail.com.evil.com", "demo.inbox+x@gmail.com@evil.com", "", "demo.inbox",
])
def test_gmail_guard_blocks_everyone_else(to):
    assert not is_demo_recipient(to, DEMO)


def test_gmail_guard_blocks_everything_without_demo_address():
    assert not is_demo_recipient("+x@gmail.com", "@gmail.com")
    with pytest.raises(PermanentError):
        GmailMail("", service=MagicMock())


def test_gmail_send_refuses_real_recipient_before_any_api_call():
    service = MagicMock()
    with pytest.raises(PermanentError, match="Refusing"):
        GmailMail(DEMO, service=service).send("rosa.hernandez@gmail.com", "Hi", "Body", key="plan-1:mail:J101")
    service.users.assert_not_called()


def test_gmail_send_builds_tagged_message():
    service, http = google("gmail", "v1", (200, {"id": "m123", "threadId": "t1"}))
    mid = GmailMail(DEMO, service=service).send("demo.inbox+cust-lee@gmail.com", "New technician", "Hello Rosa",
                                                 key="plan-1:mail:J101")
    assert mid == "m123"
    [(method, path, _query, body)] = requests_made(http)
    assert (method, path) == ("POST", "/gmail/v1/users/me/messages/send")
    msg = email.message_from_bytes(base64.urlsafe_b64decode(body["raw"]), policy=policy.default)
    assert msg["To"] == "demo.inbox+cust-lee@gmail.com"
    assert msg["From"] == DEMO
    assert msg["Subject"] == f"New technician [{key_tag('plan-1:mail:J101')}]"
    assert msg["X-Second-Shift-Key"] == "plan-1:mail:J101"
    assert msg.get_content().strip() == "Hello Rosa"


def test_gmail_find_by_key_searches_sent_for_tag():
    service, http = google("gmail", "v1", (200, {"messages": [{"id": "m9", "threadId": "t9"}]}),
                           (200, {"resultSizeEstimate": 0}))
    mail = GmailMail(DEMO, service=service)
    assert mail.find_by_key("k1") == "m9"
    assert mail.find_by_key("k2") is None
    (_, path, query, _), _ = requests_made(http)
    assert path == "/gmail/v1/users/me/messages"
    assert query["q"] == f'in:sent "{key_tag("k1")}"'
    assert key_tag("k1").startswith("SS-") and len(key_tag("k1")) == 13


def test_gmail_find_by_key_checks_own_sends_by_id_not_search():
    service, http = google("gmail", "v1", (200, {"id": "m1"}), (200, {"id": "m1"}))
    mail = GmailMail(DEMO, service=service)
    mail.send(DEMO, "s", "b", key="k")
    assert mail.find_by_key("k") == "m1"
    assert requests_made(http)[1][:2] == ("GET", "/gmail/v1/users/me/messages/m1")


# ---------------- Google error mapping ----------------
@pytest.mark.parametrize("err, kind", [
    (http_error(429), TransientError),
    (http_error(500), TransientError),
    (http_error(503), TransientError),
    (http_error(403, {"error": {"code": 403, "message": "Rate Limit Exceeded",
                                "errors": [{"reason": "rateLimitExceeded"}]}}), TransientError),
    (http_error(403, {"error": {"code": 403, "errors": [{"reason": "userRateLimitExceeded"}]}}), TransientError),
    (http_error(403, {"error": {"code": 403, "status": "PERMISSION_DENIED",
                                "details": [{"reason": "RATE_LIMIT_EXCEEDED"}]}}), TransientError),
    (http_error(403, {"error": {"code": 403, "errors": [{"reason": "forbidden"}]}}), PermanentError),
    (http_error(401), PermanentError),
    (http_error(400), PermanentError),
    (http_error(404), PermanentError),
    (TimeoutError("timed out"), TransientError),
    (ConnectionResetError("reset"), TransientError),
])
def test_google_error_mapping(err, kind):
    assert isinstance(to_port_error(err), kind)


def test_execute_none_on_and_mapping():
    service, _ = google("calendar", "v3", (404, {"error": {"code": 404}}), (503, "Service Unavailable"))
    assert execute(service.events().delete(calendarId="c", eventId="e"), none_on=(404,)) is None
    with pytest.raises(TransientError):
        execute(service.events().delete(calendarId="c", eventId="e"), none_on=(404,))


@pytest.mark.parametrize("raised, kind", [
    (TimeoutError("read timed out"), TransientError),
    (httplib2.ServerNotFoundError("no dns"), TransientError),
    (RefreshError("invalid_grant"), PermanentError),
])
def test_execute_maps_network_and_auth_failures(raised, kind):
    request = MagicMock()
    request.execute.side_effect = raised
    with pytest.raises(kind):
        execute(request)


# ---------------- Calendar ----------------
OURS = {"id": "ssabc", "status": "confirmed", "summary": "J101 · Rosa",
        "start": {"dateTime": "2026-09-13T08:15:00-07:00"}, "end": {"dateTime": "2026-09-13T09:45:00-07:00"},
        "extendedProperties": {"private": {"app": "second-shift", "job_id": "J101", "plan_id": ""}}}
FOREIGN = {"id": "dentist", "status": "confirmed", "summary": "Dentist",
           "start": {"dateTime": "2026-09-13T20:00:00Z"}, "end": {"dateTime": "2026-09-13T21:00:00Z"},
           "extendedProperties": {"private": {"job_id": "J999"}}}
ALL_DAY = {"id": "holiday", "status": "confirmed", "start": {"date": "2026-09-13"}, "end": {"date": "2026-09-14"}}


def test_calendar_list_events_maps_ours_foreign_and_skips_all_day():
    service, http = google("calendar", "v3", (200, {"items": [OURS, FOREIGN, ALL_DAY]}))
    events = GoogleCalendar(service=service).list_events("cal1")
    assert [(e.event_id, e.job_id, e.plan_id, e.start, e.end) for e in events] == [
        ("ssabc", "J101", None, 495, 585),
        ("dentist", None, None, 780, 840),  # 20:00Z = 13:00 PDT; not ours, so no job_id
    ]
    [(method, path, query, _)] = requests_made(http)
    assert (method, path) == ("GET", "/calendar/v3/calendars/cal1/events")
    assert query["timeMin"] == "2026-09-13T00:00:00-07:00" and query["timeMax"] == "2026-09-14T00:00:00-07:00"
    assert query["singleEvents"] == "true" and query["showDeleted"] == "false" and query["orderBy"] == "startTime"


def test_calendar_create_event_sends_id_and_tags():
    service, http = google("calendar", "v3", (200, "echo_request_body"))
    ev = GoogleCalendar(service=service).create_event("cal1", "ssnew", 495, 585, "J101 · Rosa", "desc", "J101", None)
    assert (ev.event_id, ev.job_id, ev.plan_id, ev.start, ev.end, ev.calendar_id) == ("ssnew", "J101", None, 495, 585, "cal1")
    [(method, path, _, body)] = requests_made(http)
    assert (method, path) == ("POST", "/calendar/v3/calendars/cal1/events")
    assert body["id"] == "ssnew"
    assert body["start"] == {"dateTime": "2026-09-13T08:15:00-07:00", "timeZone": "America/Los_Angeles"}
    assert body["extendedProperties"]["private"] == {"app": "second-shift", "job_id": "J101", "plan_id": ""}
    assert body["reminders"] == {"useDefault": False}


def test_calendar_create_existing_id_returns_it_unchanged():
    service, http = google("calendar", "v3", (409, {"error": {"code": 409, "message": "duplicate"}}), (200, OURS))
    ev = GoogleCalendar(service=service).create_event("cal1", "ssabc", 600, 690, "x", "y", "J101", "plan-2")
    assert (ev.start, ev.end, ev.plan_id) == (495, 585, None)  # the existing event, not the new fields
    assert [(m, p) for m, p, _, _ in requests_made(http)] == [
        ("POST", "/calendar/v3/calendars/cal1/events"), ("GET", "/calendar/v3/calendars/cal1/events/ssabc")]


@pytest.mark.parametrize("got", [(200, {**OURS, "status": "cancelled"}), (410, {"error": {"code": 410}})])
def test_calendar_create_restores_deleted_event_instead_of_duplicating(got):
    service, http = google("calendar", "v3", (409, {"error": {"code": 409}}), got, (200, "echo_request_body"))
    ev = GoogleCalendar(service=service).create_event("cal1", "ssabc", 600, 690, "x", "y", "J101", "plan-2")
    assert (ev.start, ev.end, ev.plan_id) == (600, 690, "plan-2")
    method, path, _, body = requests_made(http)[2]
    assert (method, path) == ("PUT", "/calendar/v3/calendars/cal1/events/ssabc")
    assert body["status"] == "confirmed" and body["extendedProperties"]["private"]["plan_id"] == "plan-2"


@pytest.mark.parametrize("status", [204, 404, 410])
def test_calendar_delete_treats_missing_as_success(status):
    service, _ = google("calendar", "v3", (status, "" if status == 204 else {"error": {"code": status}}))
    GoogleCalendar(service=service).delete_event("cal1", "ssabc")


def test_calendar_delete_rate_limit_is_transient():
    service, _ = google("calendar", "v3", (403, {"error": {"code": 403, "errors": [{"reason": "rateLimitExceeded"}]}}))
    with pytest.raises(TransientError):
        GoogleCalendar(service=service).delete_event("cal1", "ssabc")


def test_calendar_clear_day_deletes_only_ours():
    other_ours = {**OURS, "id": "ssdef"}
    service, http = google("calendar", "v3", (200, {"items": [OURS, FOREIGN, other_ours]}), (204, ""), (204, ""))
    assert GoogleCalendar(service=service).clear_day("cal1") == 2
    assert [(m, p) for m, p, _, _ in requests_made(http)[1:]] == [
        ("DELETE", "/calendar/v3/calendars/cal1/events/ssabc"), ("DELETE", "/calendar/v3/calendars/cal1/events/ssdef")]


def test_calendar_find_and_create_calendar():
    service, http = google("calendar", "v3",
                           (200, {"items": [{"id": "a@group", "summary": "Other"}], "nextPageToken": "p2"}),
                           (200, {"items": [{"id": "b@group", "summary": "Second Shift · Marco Diaz"}]}),
                           (200, {"id": "new@group", "summary": "Second Shift · Priya Shah"}))
    cal = GoogleCalendar(service=service)
    assert cal.find_calendar("Second Shift · Marco Diaz") == "b@group"
    assert cal.create_calendar("Second Shift · Priya Shah") == "new@group"
    method, path, _, body = requests_made(http)[2]
    assert (method, path, body["timeZone"]) == ("POST", "/calendar/v3/calendars", "America/Los_Angeles")


# ---------------- Sheets ----------------
@pytest.mark.parametrize("index, letters", [(0, "A"), (25, "Z"), (26, "AA"), (51, "AZ"), (52, "BA"), (701, "ZZ"), (702, "AAA")])
def test_column_letter(index, letters):
    assert column_letter(index) == letters


JOBS = [JOB_COLS, ["J101", "Rosa"], ["J102", "Brightside"]]


def test_sheets_update_row_writes_named_cells_on_matching_row():
    service, http = google("sheets", "v4", (200, {"values": JOBS}), (200, {}))
    GoogleSheets("SID", service=service).update_row("Jobs", "J102", {"assigned_tech": "T2", "last_plan": "plan-1"})
    (m1, p1, _, _), (m2, p2, _, body) = requests_made(http)
    assert (m1, p1) == ("GET", "/v4/spreadsheets/SID/values/'Jobs'")
    assert (m2, p2) == ("POST", "/v4/spreadsheets/SID/values:batchUpdate")
    assert body == {"valueInputOption": "RAW", "data": [
        {"range": "'Jobs'!N3", "values": [["T2"]]}, {"range": "'Jobs'!Q3", "values": [["plan-1"]]}]}


@pytest.mark.parametrize("key, values", [("J999", {"status": "x"}), ("J101", {"no_such_column": "x"})])
def test_sheets_update_row_rejects_unknown_row_or_column_without_writing(key, values):
    service, http = google("sheets", "v4", (200, {"values": JOBS}))
    with pytest.raises(PermanentError):
        GoogleSheets("SID", service=service).update_row("Jobs", key, values)
    assert len(http.request_sequence) == 1  # the read only


def test_sheets_read_tab_returns_strings_and_handles_empty():
    service, _ = google("sheets", "v4", (200, {"values": [["id", "n"], ["J1", 5]]}), (200, {"range": "'Travel'!A1"}))
    sheets = GoogleSheets("SID", service=service)
    assert sheets.read_tab("Jobs") == [["id", "n"], ["J1", "5"]]
    assert sheets.read_tab("Travel") == []


def test_sheets_write_tab_adds_missing_tab_then_clears_and_writes_raw():
    service, http = google("sheets", "v4",
                           (200, {"sheets": [{"properties": {"sheetId": 0, "title": "Sheet1"}}]}),
                           (200, {"replies": [{"addSheet": {"properties": {"sheetId": 77, "title": "Jobs"}}}]}),
                           (200, {}), (200, {}), (200, {}))
    GoogleSheets("SID", service=service).write_tab("Jobs", [["id", "zone"], ["J1", "North"]])
    reqs = requests_made(http)
    assert [(m, p) for m, p, _, _ in reqs] == [
        ("GET", "/v4/spreadsheets/SID"), ("POST", "/v4/spreadsheets/SID:batchUpdate"),
        ("POST", "/v4/spreadsheets/SID/values/'Jobs':clear"), ("PUT", "/v4/spreadsheets/SID/values/'Jobs'!A1"),
        ("POST", "/v4/spreadsheets/SID:batchUpdate")]
    assert reqs[1][3] == {"requests": [{"addSheet": {"properties": {"title": "Jobs"}}}]}
    assert reqs[3][2]["valueInputOption"] == "RAW" and reqs[3][3]["values"] == [["id", "zone"], ["J1", "North"]]
    formatting = reqs[4][3]["requests"]
    assert len(formatting) == 4 and json.dumps(formatting).count('"sheetId": 77') == 4


def test_sheets_create_spreadsheet_with_tabs():
    service, http = google("sheets", "v4", (200, {"spreadsheetId": "NEW"}))
    assert GoogleSheets.create_spreadsheet("T", ["Technicians", "Jobs"], service=service) == "NEW"
    body = requests_made(http)[0][3]
    assert body == {"properties": {"title": "T"}, "sheets": [{"properties": {"title": "Technicians"}},
                                                               {"properties": {"title": "Jobs"}}]}


# ---------------- Slack ----------------
def slack_err(code: str, status: int = 200) -> SlackApiError:
    resp = SlackResponse(client=None, http_verb="POST", api_url="https://slack.com/api/x", req_args={},
                         data={"ok": False, "error": code}, headers={}, status_code=status)
    return SlackApiError("failed", resp)


def slack(messages: list[dict] | None = None, member: bool = True) -> tuple[SlackChat, MagicMock]:
    client = MagicMock()
    client.conversations_list.side_effect = [
        {"channels": [{"id": "C1", "name": "general"}], "response_metadata": {"next_cursor": "cur"}},
        {"channels": [{"id": "C2", "name": "dispatch", "is_member": member}], "response_metadata": {"next_cursor": ""}},
    ]
    client.conversations_history.return_value = {"messages": messages or []}
    return SlackChat("xoxb-test", "#dispatch", client=client), client


def test_slack_resolves_channel_across_pages_and_joins_once():
    chat, client = slack(member=False)
    chat.history()
    chat.history()
    assert client.conversations_list.call_count == 2
    client.conversations_join.assert_called_once_with(channel="C2")
    assert client.conversations_history.call_args.kwargs["channel"] == "C2"


def test_slack_missing_channel_is_permanent_with_hint():
    client = MagicMock()
    client.conversations_list.return_value = {"channels": [], "response_metadata": {"next_cursor": ""}}
    with pytest.raises(PermanentError, match="#dispatch"):
        SlackChat("xoxb-test", "dispatch", client=client).history()


def test_slack_history_maps_bot_flag_and_skips_channel_housekeeping():
    chat, _ = slack([
        {"ts": "3.0", "user": "UBOT", "bot_id": "B1", "text": "Plan posted"},
        {"ts": "2.0", "user": "U1", "subtype": "channel_join", "text": "<@U1> has joined the channel"},
        {"ts": "1.0", "user": "U1", "text": "Marco is out sick today"},
    ])
    assert [(m.ts, m.user, m.bot) for m in chat.history(10)] == [("3.0", "UBOT", True), ("1.0", "U1", False)]


def test_slack_post_tags_metadata_and_find_by_key_matches_it():
    chat, client = slack([
        {"ts": "5.0", "bot_id": "B1", "text": "a", "metadata": {"event_type": "second_shift", "event_payload": {"key": "k1"}}},
        {"ts": "4.0", "bot_id": "B1", "text": "b", "metadata": {"event_type": "other", "event_payload": {"key": "k2"}}},
    ])
    client.chat_postMessage.return_value = {"ok": True, "ts": "6.0"}
    assert chat.post("hello", key="k3") == "6.0"
    kwargs = client.chat_postMessage.call_args.kwargs
    assert kwargs["metadata"] == {"event_type": "second_shift", "event_payload": {"key": "k3"}}
    assert kwargs["unfurl_links"] is False and kwargs["channel"] == "C2"
    assert chat.find_by_key("k1") == "5.0"
    assert chat.find_by_key("k2") is None
    assert client.conversations_history.call_args.kwargs["include_all_metadata"] is True


def test_slack_user_name_prefers_display_name_and_caches():
    chat, client = slack()
    client.users_info.side_effect = [
        {"user": {"name": "marco", "real_name": "Marco Diaz", "profile": {"display_name": "", "real_name": "Marco Diaz"}}},
        slack_err("user_not_found"),
    ]
    assert chat.user_name("U1") == "Marco Diaz"
    assert chat.user_name("U1") == "Marco Diaz"
    assert chat.user_name("U404") is None
    assert chat.user_name("") is None
    assert client.users_info.call_count == 2


@pytest.mark.parametrize("err, kind", [
    (slack_err("ratelimited", 429), TransientError),
    (slack_err("internal_error", 500), TransientError),
    (slack_err("service_unavailable"), TransientError),
    (slack_err("invalid_auth"), PermanentError),
    (slack_err("not_in_channel"), PermanentError),
    (URLError("connection reset"), TransientError),
    (TimeoutError(), TransientError),
])
def test_slack_error_mapping(err, kind):
    chat, client = slack()
    client.chat_postMessage.side_effect = err
    with pytest.raises(kind):
        chat.post("hi", key="k")


# ---------------- live wiring + seed helpers ----------------
def test_build_live_ports_explains_missing_seed(monkeypatch, tmp_path):
    monkeypatch.setattr(live, "STATE_FILE", tmp_path / "live_state.json")
    with pytest.raises(PermanentError, match="seed_live.py"):
        live.build_live_ports()


def test_seed_parse_slack_map():
    spec = importlib.util.spec_from_file_location("seed_live", ROOT / "scripts" / "seed_live.py")
    seed = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(seed)
    assert seed.parse_slack_map(" T1=U0123 , T2=U0456,bogus,T3=") == {"T1": "U0123", "T2": "U0456"}
