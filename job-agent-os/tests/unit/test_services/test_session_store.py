"""Tests for the Redis-backed session store (issue #6)."""

import json
from unittest.mock import AsyncMock, patch

from job_agent_os.services.session_store import SessionStore


def _fake_redis():
    """AsyncMock Redis with a dict backing store."""
    store: dict[str, str] = {}
    redis = AsyncMock()

    async def setex(key, ttl, value):
        store[key] = value
        return True

    async def get(key):
        return store.get(key)

    async def delete(key):
        return 1 if store.pop(key, None) is not None else 0

    redis.setex = AsyncMock(side_effect=setex)
    redis.get = AsyncMock(side_effect=get)
    redis.delete = AsyncMock(side_effect=delete)
    redis._store = store
    return redis


def _patch_redis(store: SessionStore, redis):
    """Patch the async _redis() helper to return our fake client."""
    return patch.object(store, "_redis", new=AsyncMock(return_value=redis))


class TestSessionStoreWithRedis:
    async def test_set_and_get_roundtrip_via_redis(self):
        redis = _fake_redis()
        store = SessionStore()
        with _patch_redis(store, redis):
            await store.set("s1", {"status": "running", "user_id": "u1"})
            store._local.clear()
            info = await store.get("s1")

        assert info is not None
        assert info["status"] == "running"
        assert info["user_id"] == "u1"

    async def test_ttl_is_applied(self):
        redis = _fake_redis()
        store = SessionStore(ttl_seconds=1234)
        with _patch_redis(store, redis):
            await store.set("s2", {"status": "running"})

        args = redis.setex.call_args[0]
        assert args[0] == "session:s2"
        assert args[1] == 1234

    async def test_update_merges_fields(self):
        redis = _fake_redis()
        store = SessionStore()
        with _patch_redis(store, redis):
            await store.set("s3", {"status": "running", "phase": "a"})
            updated = await store.update("s3", status="completed")

        assert updated is not None
        assert updated["status"] == "completed"
        assert updated["phase"] == "a"

    async def test_update_missing_session_returns_none(self):
        store = SessionStore()
        with _patch_redis(store, _fake_redis()):
            assert await store.update("nope", status="x") is None

    async def test_delete_removes_from_both(self):
        redis = _fake_redis()
        store = SessionStore()
        with _patch_redis(store, redis):
            await store.set("s4", {"status": "running"})
            await store.delete("s4")
            assert await store.get("s4") is None


class TestSessionStoreDegradedMode:
    """When Redis is unavailable the store must still work in-memory."""

    async def test_memory_only_when_redis_fails(self):
        store = SessionStore()
        with _patch_redis(store, None):
            await store.set("s5", {"status": "running"})
            info = await store.get("s5")

        assert info is not None
        assert info["status"] == "running"

    async def test_list_all_returns_local_when_redis_down(self):
        store = SessionStore()
        with _patch_redis(store, None):
            await store.set("a", {"user_id": "1"})
            await store.set("b", {"user_id": "2"})
            all_sessions = await store.list_all()

        assert set(all_sessions.keys()) == {"a", "b"}


class TestSessionStoreSerialization:
    def test_decode_normalizes_empty_arrays_encoded_by_lua_cjson(self):
        raw = json.dumps(
            {
                "progress": {"completed_steps": ["intent"], "pending_steps": {}},
                "results_summary": {
                    "recommendations": [],
                    "resume_diff": {},
                    "interview_questions": {},
                    "agent_execution_order": ["intent"],
                },
            }
        )

        info = SessionStore._decode_info(raw)

        assert info is not None
        assert info["progress"]["pending_steps"] == []
        assert info["results_summary"]["resume_diff"] == []
        assert info["results_summary"]["interview_questions"] == []

    async def test_non_json_native_values_survive(self):
        """datetime-like values get stringified by default=str."""
        from datetime import UTC, datetime

        redis = _fake_redis()
        store = SessionStore()
        now = datetime.now(UTC)
        with _patch_redis(store, redis):
            await store.set("s6", {"status": "running", "started_at": now})
            store._local.clear()
            info = await store.get("s6")

        assert info is not None
        assert info["started_at"] == json.loads(redis._store["session:s6"])["started_at"]
