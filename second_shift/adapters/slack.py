"""ChatPort on the Slack Web API. Every post carries message metadata
{"event_type": "second_shift", "event_payload": {"key": key}} so find_by_key can
tell whether a write already happened."""

from __future__ import annotations

import http.client
from typing import Any
from urllib.error import URLError

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from .base import ChatMessage, PermanentError, TransientError

EVENT_TYPE = "second_shift"
_NETWORK_ERRORS = (URLError, TimeoutError, ConnectionError, http.client.HTTPException)
# Slack's "try again" codes (some arrive with HTTP 200). A write may have landed; the engine checks find_by_key.
_TRANSIENT_CODES = {"ratelimited", "service_unavailable", "internal_error", "fatal_error"}
# Channel housekeeping, not something a person said.
_SYSTEM_SUBTYPES = {"channel_join", "channel_leave", "channel_topic", "channel_purpose", "channel_name",
                    "channel_archive", "channel_unarchive"}


def slack_error(err: SlackApiError) -> TransientError | PermanentError:
    status = getattr(err.response, "status_code", 0) or 0
    code = err.response.get("error") if err.response is not None else None
    if code in _TRANSIENT_CODES or status == 429 or status >= 500:
        return TransientError(f"Slack {code or status}")
    needed = err.response.get("needed") if err.response is not None else None
    return PermanentError(f"Slack error: {code or status}" + (f" (app needs scope {needed})" if needed else ""))


class SlackChat:
    def __init__(self, token: str, channel_name: str, client: WebClient | None = None) -> None:
        if client is None and not token:
            raise PermanentError("SLACK_BOT_TOKEN is not set. See SETUP.md step 2.")
        # No SDK-level retries: a silently retried post could double-post. The engine
        # retries TransientError itself, after checking find_by_key.
        self._client = client or WebClient(token=token, timeout=15, retry_handlers=[])
        self.channel_name = channel_name.strip().lstrip("#")
        self._channel_id: str | None = None
        self._names: dict[str, str | None] = {}

    @property
    def channel_id(self) -> str:
        """Resolve the dispatch channel by name once; join it if the bot isn't a member."""
        if self._channel_id is None:
            channel = self.find_channel()
            if channel is None:
                raise PermanentError(
                    f"Slack channel #{self.channel_name} not found. Create a public channel named "
                    f"#{self.channel_name} in the workspace (SETUP.md step 2)."
                )
            if not channel.get("is_member"):
                self._call("conversations_join", channel=channel["id"])
            self._channel_id = channel["id"]
        return self._channel_id

    def find_channel(self) -> dict[str, Any] | None:
        """The public channel named `channel_name`, or None."""
        cursor = None
        while True:
            page = self._call("conversations_list", types="public_channel", exclude_archived=True, limit=200,
                              cursor=cursor)
            for channel in page.get("channels") or []:
                if channel.get("name") == self.channel_name:
                    return channel
            cursor = (page.get("response_metadata") or {}).get("next_cursor")
            if not cursor:
                return None

    # ---------- ChatPort ----------
    def history(self, limit: int = 50) -> list[ChatMessage]:
        page = self._call("conversations_history", channel=self.channel_id, limit=limit, include_all_metadata=True)
        return [
            ChatMessage(ts=m["ts"], user=m.get("user"), text=m.get("text", ""), bot=bool(m.get("bot_id")))
            for m in page.get("messages") or []
            if m.get("subtype") not in _SYSTEM_SUBTYPES
        ]

    def post(self, text: str, key: str) -> str:
        resp = self._call("chat_postMessage", channel=self.channel_id, text=text, unfurl_links=False,
                          unfurl_media=False, metadata={"event_type": EVENT_TYPE, "event_payload": {"key": key}})
        return resp["ts"]

    def find_by_key(self, key: str) -> str | None:
        page = self._call("conversations_history", channel=self.channel_id, limit=200, include_all_metadata=True)
        for m in page.get("messages") or []:
            meta = m.get("metadata") or {}
            if meta.get("event_type") == EVENT_TYPE and (meta.get("event_payload") or {}).get("key") == key:
                return m["ts"]
        return None

    def user_name(self, user_id: str) -> str | None:
        if not user_id:
            return None
        if user_id not in self._names:
            resp = self._call("users_info", none_on=("user_not_found",), user=user_id)
            user = resp["user"] if resp is not None else {}
            profile = user.get("profile") or {}
            self._names[user_id] = (profile.get("display_name") or profile.get("real_name")
                                    or user.get("real_name") or user.get("name") or None)
        return self._names[user_id]

    # ---------- helpers ----------
    def _call(self, method: str, none_on: tuple[str, ...] = (), **kwargs: Any) -> Any:
        """Call a WebClient method; map failures to Transient/PermanentError.
        Returns None when the Slack error code is in `none_on`."""
        try:
            return getattr(self._client, method)(**kwargs)
        except SlackApiError as err:
            if err.response is not None and err.response.get("error") in none_on:
                return None
            raise slack_error(err) from err
        except _NETWORK_ERRORS as err:
            raise TransientError(f"Network error talking to Slack: {err!r}") from err
