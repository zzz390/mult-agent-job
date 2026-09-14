"""Tests for privacy-safe, best-effort session search progress."""

from unittest.mock import AsyncMock, patch

from job_agent_os.services.session_progress import publish_search_progress
from job_agent_os.services.session_store import SessionStore


async def test_publish_search_progress_updates_aggregate_fields_without_pii():
    store = SessionStore()
    with patch.object(store, "_redis", new=AsyncMock(return_value=None)):
        await store.set(
            "session-1",
            {
                "status": "running",
                "progress": {"active_agent": "search", "items_found": 0},
            },
        )
        published = await publish_search_progress(
            "session-1",
            activity_message=(
                "正在处理 https://example.com/jobs?token=secret "
                "hr@example.com 13800138000"
            ),
            items_found=4,
            items_saved=2,
            store=store,
        )
        info = await store.get("session-1")

    assert published is True
    assert info is not None
    progress = info["progress"]
    assert progress["items_found"] == 4
    assert progress["items_saved"] == 2
    assert progress["last_activity_at"]
    assert progress["active_agent"] == "search"
    assert "https://" not in progress["activity_message"]
    assert "@example.com" not in progress["activity_message"]
    assert "13800138000" not in progress["activity_message"]


async def test_publish_search_progress_never_raises_when_store_is_unavailable():
    store = AsyncMock()
    store.get.side_effect = RuntimeError("store unavailable")

    published = await publish_search_progress(
        "session-2",
        activity_message="正在查找官方国企名录",
        store=store,
    )

    assert published is False
