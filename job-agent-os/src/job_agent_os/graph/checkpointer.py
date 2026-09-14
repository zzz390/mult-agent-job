"""Lifecycle-managed LangGraph checkpointer configuration."""

import logging
from contextlib import AbstractAsyncContextManager
from typing import Any

from langgraph.checkpoint.memory import MemorySaver

from job_agent_os.settings import get_settings

logger = logging.getLogger(__name__)

_checkpointer: Any | None = None
_checkpointer_context: AbstractAsyncContextManager[Any] | None = None


async def init_checkpointer() -> Any:
    """Initialize the shared checkpointer and create its database tables.

    ``AsyncPostgresSaver.from_conn_string`` returns an async context manager;
    retaining and entering it for the application lifespan is required. A
    production process must never silently lose durable workflow state.
    """
    global _checkpointer, _checkpointer_context

    if _checkpointer is not None:
        return _checkpointer

    settings = get_settings()
    if settings.env == "test":
        _checkpointer = MemorySaver()
        return _checkpointer

    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        db_url = settings.database_url.replace("+asyncpg", "")
        context = AsyncPostgresSaver.from_conn_string(db_url)
        checkpointer = await context.__aenter__()
        await checkpointer.setup()
        _checkpointer_context = context
        _checkpointer = checkpointer
        logger.info("Using durable AsyncPostgresSaver (env=%s)", settings.env)
    except Exception:
        if settings.env == "prod":
            logger.exception("Durable Postgres checkpointer initialization failed")
            raise
        logger.exception(
            "Postgres checkpointer unavailable; using MemorySaver in %s only",
            settings.env,
        )
        _checkpointer = MemorySaver()

    return _checkpointer


def get_checkpointer() -> Any:
    """Return the lifespan-initialized checkpointer.

    Tests that compile the graph without starting FastAPI receive an isolated
    in-memory saver. Startup initializes the durable implementation first.
    """
    if _checkpointer is not None:
        return _checkpointer
    return MemorySaver()


async def close_checkpointer() -> None:
    """Release the Postgres saver connection pool/context."""
    global _checkpointer, _checkpointer_context
    if _checkpointer_context is not None:
        await _checkpointer_context.__aexit__(None, None, None)
    _checkpointer = None
    _checkpointer_context = None
