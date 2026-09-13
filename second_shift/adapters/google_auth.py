"""Google OAuth for a desktop app: consent once in the browser, then a cached token."""

from __future__ import annotations

import functools
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from .base import PermanentError

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
]


def load_env() -> None:
    """Load the project's .env (existing environment variables win)."""
    load_dotenv(PROJECT_ROOT / ".env")


def _path(var: str, default: str) -> Path:
    p = Path(os.getenv(var) or default)
    return p if p.is_absolute() else PROJECT_ROOT / p


def client_file() -> Path:
    return _path("GOOGLE_OAUTH_CLIENT_FILE", "secrets/google_oauth_client.json")


def token_file() -> Path:
    return _path("GOOGLE_TOKEN_FILE", "secrets/google_token.json")


def _cached() -> Credentials | None:
    path = token_file()
    if not path.exists():
        return None
    try:
        creds = Credentials.from_authorized_user_file(str(path))
    except ValueError:
        return None
    if not creds.has_scopes(SCOPES):
        return None  # token from an older scope set: ask again
    if creds.valid:
        return creds
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            return creds
        except RefreshError:
            return None  # revoked or expired refresh token: ask again
    return None


@functools.cache
def get_credentials() -> Credentials:
    """Cached token if usable, else the browser consent flow (first run only)."""
    load_env()
    creds = _cached()
    if creds is None:
        secrets = client_file()
        if not secrets.exists():
            raise PermanentError(
                f"Google OAuth client file not found at {secrets}. Follow SETUP.md step 1 "
                "(create a Desktop OAuth client and save its JSON there)."
            )
        # Google lets the user untick scopes; report that ourselves instead of oauthlib's cryptic Warning.
        os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")
        print("Opening a browser for Google sign-in (first run only). Approve all requested access.")
        flow = InstalledAppFlow.from_client_secrets_file(str(secrets), SCOPES)
        creds = flow.run_local_server(port=0)
        missing = set(SCOPES) - set(creds.granted_scopes or SCOPES)
        if missing:
            raise PermanentError(
                "Google sign-in did not grant: " + ", ".join(sorted(s.rsplit("/", 1)[-1] for s in missing))
                + ". Run again and tick every checkbox on the consent screen."
            )
    path = token_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(creds.to_json())
    path.chmod(0o600)  # holds a refresh token
    return creds


def build_service(name: str, version: str) -> Any:
    """Discovery client (bundled discovery docs, no network needed to build)."""
    return build(name, version, credentials=get_credentials(), cache_discovery=False)
