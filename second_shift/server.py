"""Dispatcher web app + JSON API.

Run:  uv run uvicorn second_shift.server:app --reload --port 8000
Mode: SECOND_SHIFT_MODE=fake (default, in-memory apps) or live (Google + Slack).
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .adapters.fakes import build_fake_ports
from .clock import demo_now, plan_day
from .engine import Engine
from .ledger import Ledger
from .models import Absence

load_dotenv()
ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
MODE = os.getenv("SECOND_SHIFT_MODE", "fake")


class State:
    engine: Engine
    faults = None
    lock = threading.RLock()  # rebuilds, polling, planning
    exec_lock = threading.Lock()  # one approval at a time; reads stay responsive meanwhile


S = State()


def _parser():
    from .parse import make_parser

    return make_parser()


def build() -> None:
    with S.lock:
        if MODE == "live":
            from .adapters.live import build_live_ports

            ports = build_live_ports()
            ledger = Ledger(ROOT / "runs" / "ledger-live.sqlite")
            dispatchers = {u.strip() for u in os.getenv("DISPATCHER_SLACK_IDS", "").split(",") if u.strip()}
        else:
            ports, S.faults = build_fake_ports(os.getenv("DEMO_GMAIL") or None)
            ledger = Ledger()
            dispatchers = {"U_DISPATCH"}
        S.engine = Engine(ports, ledger, _parser(), dispatchers=dispatchers)
        if MODE == "live":
            S.engine.baseline()


build()
app = FastAPI(title="Second Shift")
app.mount("/static", StaticFiles(directory=WEB), name="static")


@app.exception_handler(Exception)
async def json_errors(request, exc: Exception):
    """Unexpected errors come back as JSON with a readable detail, not a bare 500 page."""
    from fastapi.responses import JSONResponse

    return JSONResponse(status_code=500, content={"detail": f"{type(exc).__name__}: {exc}"})


def _poll_loop() -> None:
    while True:
        try:
            with S.lock:
                S.engine.poll_once()
        except Exception as e:  # keep polling; surface in logs
            print(f"[poll] {type(e).__name__}: {e}", file=sys.stderr)
        time.sleep(float(os.getenv("POLL_SECONDS", "4")))


if MODE == "live" and os.getenv("POLL", "1") == "1":
    threading.Thread(target=_poll_loop, daemon=True).start()


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB / "index.html")


_snap_cache: dict = {"at": 0.0, "snap": None}


def cached_snapshot():
    """Dashboard reads are cached (live Google quotas are ~60 Sheets reads/min).
    The engine itself always re-reads before planning and before writing."""
    ttl = float(os.getenv("STATE_CACHE_SECONDS", "15" if MODE == "live" else "0"))
    if _snap_cache["snap"] is None or time.time() - _snap_cache["at"] > ttl:
        _snap_cache.update(at=time.time(), snap=S.engine.snapshot())
    return _snap_cache["snap"]


@app.middleware("http")
async def invalidate_on_write(request, call_next):
    response = await call_next(request)
    if request.method == "POST":
        _snap_cache["snap"] = None
    return response


@app.get("/api/state")
def state() -> dict:
    snap = cached_snapshot()
    plans = S.engine.ledger.list_plans()
    return {
        "mode": MODE,
        "plan_day": plan_day().isoformat(),
        "now": demo_now(),
        "llm": S.engine.parser is not None,
        "company": snap.company.model_dump(),
        "busy": [b.model_dump() for b in snap.busy],
        "discrepancies": snap.discrepancies,
        "fingerprint": snap.fingerprint,
        "plans": plans,
    }


class MessageIn(BaseModel):
    text: str
    user: str = "U_DISPATCH"


@app.post("/api/messages")
def post_message(body: MessageIn) -> dict:
    """Fake mode: post into the simulated #dispatch channel and process it.
    Live mode: messages come from real Slack; use /api/poll."""
    if MODE != "fake":
        raise HTTPException(400, "In live mode, post in Slack #dispatch. The app picks it up automatically.")
    if S.engine.parser is None:
        raise HTTPException(400, "No LLM key for LLM_PROVIDER (default openai: set OPENAI_API_KEY in .env).")
    with S.lock:
        msg = S.engine.ports.chat.human_post(body.user, body.text)
        return {**S.engine.handle_message(msg), "ts": msg.ts}


@app.post("/api/poll")
def poll() -> list[dict]:
    with S.lock:
        return S.engine.poll_once()


class ManualCallout(BaseModel):
    tech_id: str
    start: int = 0
    end: int = 24 * 60


@app.post("/api/plans")
def manual_plan(body: ManualCallout) -> dict:
    """Plan without the language step (dispatcher picks the tech in the UI)."""
    with S.lock:
        return S.engine.propose([Absence(tech_id=body.tech_id, start=body.start, end=body.end)],
                                callout={"text": "(entered by dispatcher)", "sender": "dispatcher"})


@app.post("/api/whatif")
def whatif(body: ManualCallout) -> dict:
    """Simulate a call-out: full plan + checks, status 'simulated', nothing is ever written."""
    with S.lock:
        return S.engine.propose([Absence(tech_id=body.tech_id, start=body.start, end=body.end)], simulate=True,
                                callout={"text": "(what-if from the dashboard)", "sender": "dispatcher"})


@app.get("/api/whatif/scan")
def whatif_scan() -> list[dict]:
    """What if each technician called out? Ranks single points of failure. Pure simulation."""
    with S.lock:
        return S.engine.preparedness_scan()


@app.post("/api/plans/{plan_id}/adopt")
def adopt(plan_id: str) -> dict:
    """Make a what-if real: a fresh proposal from current Sheets + Calendar, awaiting approval."""
    with S.lock:
        return S.engine.adopt(plan_id)


@app.get("/api/plans")
def plans() -> list[dict]:
    return S.engine.ledger.list_plans()


@app.get("/api/plans/{plan_id}")
def get_plan(plan_id: str) -> dict:
    try:
        return S.engine.view(plan_id)
    except TypeError:
        raise HTTPException(404, "No such plan")


@app.post("/api/plans/{plan_id}/approve")
def approve(plan_id: str) -> dict:
    """Approve (or resume) a plan. A simulated crash leaves it 'executing'; approving again resumes."""
    from .adapters.fakes import CrashAfterWrite

    with S.exec_lock:
        try:
            S.engine.approve(plan_id)
            S.engine.ledger.update_body(plan_id, crashed=None)
            return S.engine.view(plan_id)
        except KeyError:
            raise HTTPException(404, "No such plan")
        except CrashAfterWrite as e:
            note = f"Simulated crash right after a write landed ({e}). Approve again to resume."
            run_id = S.engine.ledger.get_plan(plan_id)[1]["run_id"]
            S.engine.ledger.trace(run_id, "Process crashed right after a write", "error", time.time(), {"op": str(e)})
            S.engine.ledger.update_body(plan_id, crashed=note)
            return S.engine.view(plan_id)


@app.post("/api/plans/{plan_id}/replan")
def replan(plan_id: str) -> dict:
    """Make a fresh plan for the same call-out (used after a stale plan)."""
    with S.lock:
        view = S.engine.view(plan_id)
        absences = [Absence.model_validate(a) for a in view["plan"]["absences"] if a.get("reason") == "callout"]
        return S.engine.propose(absences, callout=view.get("callout"))


@app.get("/api/channel")
def channel() -> list[dict]:
    """Recent #dispatch messages (fake or live), newest last. No lock: stays live while the agent works."""
    chat = S.engine.ports.chat
    msgs = chat.history(limit=40)
    return [dict(m.model_dump(), name=chat.user_name(m.user or "") or m.user) for m in reversed(msgs)]


@app.get("/api/outbox")
def outbox() -> list[dict]:
    """Fake mode only: emails the simulated Gmail sent."""
    mail = S.engine.ports.mail
    return list(getattr(mail, "sent", []))


@app.post("/api/reset")
def reset() -> dict:
    if MODE == "live":
        out = subprocess.run([sys.executable, str(ROOT / "scripts" / "seed_live.py")], capture_output=True, text=True,
                             cwd=ROOT, timeout=300)
        if out.returncode != 0:
            raise HTTPException(500, out.stderr[-2000:])
        build()
        return {"ok": True, "log": out.stdout[-2000:]}
    build()
    return {"ok": True}


@app.post("/api/demo/fault")
def demo_fault(op: str = "chat.post", kind: str = "transient") -> dict:
    """Fake mode: queue a failure for the next write of `op`.
    kind: transient (rate limit, retried) | crash (write lands, process 'dies' before recording it)."""
    if MODE != "fake":
        raise HTTPException(400, "Fault injection is only available in fake mode.")
    from .adapters.base import TransientError

    S.faults.add(op, TransientError(f"429 rate limited ({op})") if kind == "transient" else "crash_after")
    return {"ok": True, "queued": {op: kind}}


@app.get("/api/demo/faults")
def armed_faults() -> dict:
    """Fake mode: failures queued for upcoming writes."""
    if S.faults is None:
        return {}
    return {op: [f if isinstance(f, str) else "transient" for f in q] for op, q in S.faults.queue.items() if q}


@app.get("/api/runs/{run_id}/trace")
def run_trace(run_id: str) -> list[dict]:
    """Trace for any run, including ones that ended in a question or were ignored."""
    return S.engine.ledger.get_trace(run_id)


@app.post("/api/demo/edit-calendar")
def demo_edit(job_id: str = "J202", minutes: int = 15) -> dict:
    """Fake mode: simulate someone moving a booking by hand (to show the stale-plan guard)."""
    if MODE != "fake":
        raise HTTPException(400, "In live mode, drag the event in Google Calendar instead.")
    with S.lock:
        cal = S.engine.ports.calendar
        for cal_id, events in cal.events.items():
            for ev in events.values():
                if ev.job_id == job_id:
                    moved = ev.model_copy(update={"start": ev.start + minutes, "end": ev.end + minutes})
                    cal.human_edit(cal_id, moved)
                    return {"ok": True, "moved": moved.model_dump()}
    raise HTTPException(404, f"No booking for {job_id}")
