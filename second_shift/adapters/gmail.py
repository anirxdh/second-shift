"""MailPort on the Gmail API.

Safety: send() refuses any recipient other than the demo inbox or a plus-alias
of it, so the live demo can never email a real third party.

Idempotency: the subject carries a tag derived from the key ("[SS-3fa2b9c1d0]")
and the key rides in an X-Second-Shift-Key header. find_by_key searches Sent for
the tag. Gmail search can lag a few seconds behind a send, so for messages this
process sent we check the known id directly; the engine's ledger is the first
line of defense against double sends.
"""

from __future__ import annotations

import base64
import hashlib
from email.message import EmailMessage
from typing import Any

from .base import PermanentError
from .google_auth import build_service
from .google_errors import execute

_FORBIDDEN_CHARS = set(" ,;<>\"'()[]\\\r\n\t")


def key_tag(key: str) -> str:
    return "SS-" + hashlib.sha1(key.encode()).hexdigest()[:10]


def is_demo_recipient(to: str, demo_gmail: str) -> bool:
    """True only for `demo_gmail` itself or user+anything@same-domain. One bare address, no display name."""
    user, _, domain = (demo_gmail or "").strip().lower().partition("@")
    addr = (to or "").strip().lower()
    if not user or not domain or addr.count("@") != 1 or _FORBIDDEN_CHARS & set(addr):
        return False
    local, _, dom = addr.partition("@")
    return dom == domain and (local == user or local.startswith(user + "+"))


class GmailMail:
    def __init__(self, demo_gmail: str, service: Any | None = None) -> None:
        user, _, domain = (demo_gmail or "").strip().partition("@")
        if not user or not domain:
            raise PermanentError("DEMO_GMAIL is not set. Put the Gmail address you signed in with in .env.")
        self.demo_gmail = demo_gmail.strip()
        self._svc = service or build_service("gmail", "v1")
        self._sent: dict[str, str] = {}  # key -> message id, for sends made by this process

    def send(self, to: str, subject: str, body: str, key: str) -> str:
        if not is_demo_recipient(to, self.demo_gmail):
            raise PermanentError(f"Refusing to email {to!r}: the demo only emails {self.demo_gmail} or its +aliases.")
        msg = EmailMessage()
        msg["From"] = self.demo_gmail
        msg["To"] = to.strip()
        msg["Subject"] = f"{subject} [{key_tag(key)}]"
        msg["X-Second-Shift-Key"] = key
        msg.set_content(body)
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        sent = execute(self._svc.users().messages().send(userId="me", body={"raw": raw}))
        self._sent[key] = sent["id"]
        return sent["id"]

    def find_by_key(self, key: str) -> str | None:
        messages = self._svc.users().messages()
        known = self._sent.get(key)
        if known and execute(messages.get(userId="me", id=known, format="minimal"), none_on=(404,)):
            return known
        found = execute(messages.list(userId="me", q=f'in:sent "{key_tag(key)}"', maxResults=5))
        hits = found.get("messages") or []
        return hits[0]["id"] if hits else None
