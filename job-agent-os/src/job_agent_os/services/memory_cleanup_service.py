"""Long-term memory hygiene (issue #5).

Low-quality memories (low importance, never accessed) decay the quality of
memory recall over time. This service:
- cleanup_stale_memories: soft-deletes stale low-importance memories
- start_memory_cleanup_loop: runs cleanup daily in the background
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from job_agent_os.db.session import get_session_factory
from job_agent_os.models.memory import Memory

logger = logging.getLogger(__name__)

# Defaults: memories older than this, never accessed, and of low importance
# are deactivated.
STALE_AFTER_DAYS = 30
MIN_IMPORTANCE = 0.2
CLEANUP_INTERVAL_SECONDS = 86400  # daily


async def cleanup_stale_memories(
    db: AsyncSession,
    stale_after_days: int = STALE_AFTER_DAYS,
    min_importance: float = MIN_IMPORTANCE,
) -> int:
    """Soft-delete stale, low-value memories.

    A memory is stale when it is older than `stale_after_days`, has never
    been accessed, and its importance is below `min_importance`.

    Returns the number of memories deactivated.
    """
    cutoff = datetime.now(UTC) - timedelta(days=stale_after_days)
    result = await db.execute(
        select(Memory).where(
            Memory.importance_score < min_importance,
            Memory.access_count == 0,
            Memory.created_at < cutoff,
            Memory.is_active == True,  # noqa: E712
        )
    )
    stale = result.scalars().all()
    for memory in stale:
        memory.is_active = False
    await db.flush()
    if stale:
        logger.info("Deactivated %d stale memories", len(stale))
    return len(stale)


async def _run_cleanup_once() -> None:
    """Run a single cleanup pass with its own DB session."""
    try:
        session_factory = get_session_factory()
        async with session_factory() as db:
            removed = await cleanup_stale_memories(db)
            await db.commit()
            logger.debug("Memory cleanup finished: %d removed", removed)
    except Exception as e:  # noqa: BLE001
        logger.warning("Memory cleanup failed: %s", e)


async def memory_cleanup_loop(interval_seconds: int = CLEANUP_INTERVAL_SECONDS) -> None:
    """Background loop that periodically cleans stale memories."""
    while True:
        await _run_cleanup_once()
        await asyncio.sleep(interval_seconds)


_cleanup_task: asyncio.Task | None = None


def start_memory_cleanup_loop(interval_seconds: int = CLEANUP_INTERVAL_SECONDS) -> None:
    """Start the background cleanup loop (idempotent)."""
    global _cleanup_task
    if _cleanup_task is not None and not _cleanup_task.done():
        return
    _cleanup_task = asyncio.create_task(memory_cleanup_loop(interval_seconds))


def stop_memory_cleanup_loop() -> None:
    """Stop the background cleanup loop."""
    global _cleanup_task
    if _cleanup_task is not None and not _cleanup_task.done():
        _cleanup_task.cancel()
    _cleanup_task = None
