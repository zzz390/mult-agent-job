"""Checkpointer configuration (Postgres/Memory)."""

import logging

from langgraph.checkpoint.memory import MemorySaver

from job_agent_os.settings import get_settings

logger = logging.getLogger(__name__)


def get_checkpointer():
    """Get checkpointer instance.

    In development, use MemorySaver.
    In production, use AsyncPostgresSaver with fallback to MemorySaver on failure.
    """
    settings = get_settings()

    if settings.env == "prod":
        try:
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

            # Convert SQLAlchemy asyncpg URL to plain PostgreSQL URL
            db_url = settings.database_url.replace("+asyncpg", "")
            checkpointer = AsyncPostgresSaver.from_conn_string(db_url)
            logger.info("Using AsyncPostgresSaver for production checkpointer")
            return checkpointer
        except Exception as e:
            logger.warning(
                "Failed to initialize AsyncPostgresSaver, "
                f"falling back to MemorySaver: {e}"
            )

    # Default to MemorySaver for development or production fallback
    return MemorySaver()
