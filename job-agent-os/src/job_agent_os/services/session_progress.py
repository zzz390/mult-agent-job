"""Best-effort, privacy-safe session progress updates for long-running work."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from job_agent_os.core.utils import utc_now
from job_agent_os.services.session_store import get_session_store

if TYPE_CHECKING:
    from job_agent_os.services.session_store import SessionStore

logger = logging.getLogger(__name__)

_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
_EMAIL_RE = re.compile(r"\b[^\s@]+@[^\s@]+\.[^\s@]+\b")
_PHONE_RE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
_MAX_ACTIVITY_MESSAGE_LENGTH = 160


def _safe_message(message: str) -> str:
    """Return a short display message without URLs or obvious PII."""
    safe = _URL_RE.sub("官网页面", str(message))
    safe = _EMAIL_RE.sub("联系信息", safe)
    safe = _PHONE_RE.sub("联系电话", safe)
    return " ".join(safe.split())[:_MAX_ACTIVITY_MESSAGE_LENGTH]


def _counter(value: int | None, previous: object) -> int | None:
    """Normalise optional counters without allowing negative UI values."""
    if value is None:
        return None
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        try:
            return max(0, int(previous))
        except (TypeError, ValueError):
            return 0


async def publish_search_progress(
    session_id: str | None,
    *,
    activity_message: str,
    items_found: int | None = None,
    items_saved: int | None = None,
    store: SessionStore | None = None,
) -> bool:
    """Publish search activity without letting observability interrupt crawling.

    The caller supplies only a user-safe, human-readable phase message.  This
    helper additionally strips accidental URLs and obvious contact details so
    raw crawler output is never copied into the session/SSE payload.
    """
    if not session_id:
        return False

    try:
        session_store = store or get_session_store()
        info = await session_store.get(session_id)
        if info is None:
            return False

        progress = dict(info.get("progress") or {})
        progress["activity_message"] = _safe_message(activity_message)
        progress["last_activity_at"] = utc_now().isoformat()

        found = _counter(items_found, progress.get("items_found"))
        saved = _counter(items_saved, progress.get("items_saved"))
        if found is not None:
            progress["items_found"] = found
        if saved is not None:
            progress["items_saved"] = saved

        await session_store.update(
            session_id,
            progress={
                key: progress[key]
                for key in (
                    "activity_message",
                    "last_activity_at",
                    "items_found",
                    "items_saved",
                )
                if key in progress
            },
            updated_at=utc_now().isoformat(),
        )
        return True
    except Exception:  # noqa: BLE001
        # Progress is deliberately auxiliary: a Redis outage or a deleted
        # session must not cancel a network crawl or prevent a DB write.
        logger.debug("Unable to publish search activity", exc_info=True)
        return False
