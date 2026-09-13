"""Map Google API failures onto the ports' TransientError / PermanentError."""

from __future__ import annotations

import http.client
import json
import ssl
import threading
from collections.abc import Collection
from typing import Any

import httplib2
from google.auth.exceptions import RefreshError, TransportError
from googleapiclient.errors import HttpError

from .base import PermanentError, TransientError

# 403s that mean "slow down" rather than "not allowed".
_RATE_LIMIT_REASONS = {"ratelimitexceeded", "userratelimitexceeded", "rate_limit_exceeded"}
NETWORK_ERRORS: tuple[type[BaseException], ...] = (
    TimeoutError,  # includes socket.timeout
    ConnectionError,
    ssl.SSLError,
    http.client.HTTPException,
    httplib2.ServerNotFoundError,
    TransportError,
)

# httplib2 connections are not thread-safe; the web server may call ports from
# several threads, so Google calls are serialized.
_LOCK = threading.Lock()


def http_status(err: HttpError) -> int:
    return int(getattr(err.resp, "status", 0) or 0)


def _reasons(err: HttpError) -> set[str]:
    """Machine-readable reasons from both Google error formats (errors[] and details[])."""
    try:
        error = json.loads(err.content.decode("utf-8")).get("error", {})
    except (ValueError, UnicodeDecodeError, AttributeError):
        return set()
    if not isinstance(error, dict):
        return set()
    items = (error.get("errors") or []) + (error.get("details") or [])
    return {str(i.get("reason", "")).lower() for i in items if isinstance(i, dict)}


def to_port_error(err: BaseException) -> TransientError | PermanentError:
    if isinstance(err, HttpError):
        status = http_status(err)
        msg = f"Google API {status}: {err.reason}"
        if status == 429 or 500 <= status < 600:
            return TransientError(msg)
        if status == 403 and _reasons(err) & _RATE_LIMIT_REASONS:
            return TransientError(msg)
        if status in (401, 403) and "scope" in str(err.reason).lower():
            msg += " (delete secrets/google_token.json and sign in again, ticking every box)"
        return PermanentError(msg)
    if isinstance(err, RefreshError):
        return PermanentError(
            f"Google sign-in expired or was revoked ({err}). Delete secrets/google_token.json and "
            "run `uv run python scripts/check_setup.py` to sign in again."
        )
    if isinstance(err, NETWORK_ERRORS):
        return TransientError(f"Network error talking to Google: {err!r}")
    return PermanentError(repr(err))


def execute(request: Any, none_on: Collection[int] = ()) -> Any:
    """Run a googleapiclient request, raising only TransientError / PermanentError.

    Returns None instead of raising when the HTTP status is in `none_on`
    (e.g. 404 on delete, 409 on insert-with-id). No automatic retries: a blind
    retry of a non-idempotent write (Gmail send) could duplicate it.
    """
    try:
        with _LOCK:
            return request.execute()
    except HttpError as err:
        if http_status(err) in none_on:
            return None
        raise to_port_error(err) from err
    except (RefreshError, *NETWORK_ERRORS) as err:
        raise to_port_error(err) from err
