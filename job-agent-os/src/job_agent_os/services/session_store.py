"""Session store backed by Redis (issue #6).

Replaces the unreliable in-process `_sessions` dict:
- Survives process restarts and multi-worker deployments (Redis-backed)
- Automatic TTL expiry (7 days) so stale sessions don't leak memory
- Keeps an in-process write-through cache so hot-path reads stay O(1)
  and code without Redis access still works in degraded mode
"""

import asyncio
import json
import logging
import time
from typing import Any, cast

from job_agent_os.db.redis import get_redis
from job_agent_os.settings import get_settings

logger = logging.getLogger(__name__)

_KEY_PREFIX = "session:"
_DEFAULT_TTL_SECONDS = 86400 * 7  # 7 days

_ATOMIC_UPDATE_LUA = """
local raw = redis.call('GET', KEYS[1])
if not raw then
  return nil
end
local current = cjson.decode(raw)
local patch = cjson.decode(ARGV[2])
for key, value in pairs(patch) do
  if key == 'progress' and type(value) == 'table' and type(current[key]) == 'table' then
    for nested_key, nested_value in pairs(value) do
      current[key][nested_key] = nested_value
    end
  else
    current[key] = value
  end
end
local updated = cjson.encode(current)
redis.call('SETEX', KEYS[1], ARGV[1], updated)
return updated
"""


class SessionStore:
    """Redis-backed session info store with in-process write-through cache."""

    def __init__(self, ttl_seconds: int = _DEFAULT_TTL_SECONDS) -> None:
        self.ttl_seconds = ttl_seconds
        # Local data is only a bounded degraded-mode fallback. Redis remains
        # authoritative so multiple workers observe each other's updates.
        self._local: dict[str, dict[str, Any]] = {}
        self._local_expires: dict[str, float] = {}
        self._update_lock = asyncio.Lock()

    @staticmethod
    def _key(session_id: str) -> str:
        return f"{_KEY_PREFIX}{session_id}"

    # --- Internal helpers ---

    async def _redis(self) -> Any | None:
        """Return the Redis client, or None when Redis is unreachable."""
        try:
            return get_redis()
        except Exception as e:  # noqa: BLE001
            logger.warning("Redis unavailable, session store degrades to memory-only: %s", e)
            return None

    @staticmethod
    def _decode_info(raw: str | bytes | bytearray) -> dict[str, Any] | None:
        """Decode and validate a stored session object."""
        try:
            decoded: object = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None
        if not isinstance(decoded, dict):
            return None
        return cast(dict[str, Any], decoded)

    # --- Public API ---

    async def set(self, session_id: str, info: dict[str, Any]) -> None:
        """Create or replace session info (write-through to Redis)."""
        self._local[session_id] = info
        self._local_expires[session_id] = time.monotonic() + self.ttl_seconds
        redis = await self._redis()
        if redis is None:
            return
        try:
            await redis.setex(
                self._key(session_id),
                self.ttl_seconds,
                json.dumps(info, ensure_ascii=False, default=str),
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("Redis set failed for session %s: %s", session_id, e)

    async def get(self, session_id: str) -> dict[str, Any] | None:
        """Get session info from Redis, falling back locally on an outage."""
        redis = await self._redis()
        if redis is None:
            return self._get_local(session_id)
        try:
            raw = await redis.get(self._key(session_id))
        except Exception as e:  # noqa: BLE001
            logger.warning("Redis get failed for session %s: %s", session_id, e)
            return self._get_local(session_id)
        if not raw:
            self._local.pop(session_id, None)
            self._local_expires.pop(session_id, None)
            return None
        info = self._decode_info(raw)
        if info is None:
            logger.warning("Corrupted session payload for %s, ignoring", session_id)
            return None
        self._local[session_id] = info
        self._local_expires[session_id] = time.monotonic() + self.ttl_seconds
        return info

    def _get_local(self, session_id: str) -> dict[str, Any] | None:
        if session_id in self._local and session_id not in self._local_expires:
            return self._local[session_id]
        expires_at = self._local_expires.get(session_id, 0)
        if expires_at <= time.monotonic():
            self._local.pop(session_id, None)
            self._local_expires.pop(session_id, None)
            return None
        return self._local.get(session_id)

    async def update(
        self, session_id: str, **fields: Any
    ) -> dict[str, Any] | None:
        """Atomically merge fields into existing session info.

        Returns the updated info dict, or None if the session is unknown.
        """
        redis = await self._redis()
        if redis is not None:
            try:
                raw = await redis.eval(
                    _ATOMIC_UPDATE_LUA,
                    1,
                    self._key(session_id),
                    self.ttl_seconds,
                    json.dumps(fields, ensure_ascii=False, default=str),
                )
                if raw is None:
                    self._local.pop(session_id, None)
                    self._local_expires.pop(session_id, None)
                    return None
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8")
                if isinstance(raw, str | bytes | bytearray):
                    info = self._decode_info(raw)
                    if info is None:
                        raise ValueError("Redis returned a non-object session payload")
                    self._local[session_id] = info
                    self._local_expires[session_id] = (
                        time.monotonic() + self.ttl_seconds
                    )
                    return info
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    "Atomic Redis update failed for session %s: %s", session_id, e
                )

        # Degraded mode and simple test doubles use a process-local lock.
        async with self._update_lock:
            info = await self.get(session_id)
            if info is None:
                return None
            for key, value in fields.items():
                if (
                    key == "progress"
                    and isinstance(value, dict)
                    and isinstance(info.get(key), dict)
                ):
                    info[key] = {**info[key], **value}
                else:
                    info[key] = value
            await self.set(session_id, info)
            return info

    async def update_progress(
        self, session_id: str, **progress_fields: Any
    ) -> dict[str, Any] | None:
        """Merge only changed progress fields without overwriting peer updates."""
        return await self.update(session_id, progress=progress_fields)

    async def delete(self, session_id: str) -> None:
        """Remove a session from cache and Redis."""
        self._local.pop(session_id, None)
        self._local_expires.pop(session_id, None)
        redis = await self._redis()
        if redis is None:
            return
        try:
            await redis.delete(self._key(session_id))
        except Exception as e:  # noqa: BLE001
            logger.warning("Redis delete failed for session %s: %s", session_id, e)

    async def list_all(self) -> dict[str, dict[str, Any]]:
        """Return all known sessions (local cache merged with Redis scan)."""
        merged: dict[str, dict[str, Any]] = {
            sid: info
            for sid, info in self._local.items()
            if sid not in self._local_expires
            or self._local_expires[sid] > time.monotonic()
        }

        redis = await self._redis()
        if redis is None:
            return merged

        try:
            cursor = 0
            while True:
                cursor, keys = await redis.scan(
                    cursor=cursor, match=f"{_KEY_PREFIX}*", count=200
                )
                for key in keys:
                    sid = str(key).removeprefix(_KEY_PREFIX)
                    if sid in merged:
                        continue
                    try:
                        raw = await redis.get(key)
                        if raw and (info := self._decode_info(raw)) is not None:
                            merged[sid] = info
                    except (json.JSONDecodeError, TypeError):
                        continue
                if cursor == 0:
                    break
        except Exception as e:  # noqa: BLE001
            logger.warning("Redis scan failed, listing local sessions only: %s", e)

        return merged


# Global store instance
_store: SessionStore | None = None


def get_session_store() -> SessionStore:
    """Get or create the global session store."""
    global _store
    if _store is None:
        settings = get_settings()
        ttl = getattr(settings, "session_ttl_seconds", _DEFAULT_TTL_SECONDS)
        _store = SessionStore(ttl_seconds=ttl)
    return _store
