"""Checkpointer configuration (Postgres/Memory)."""

from langgraph.checkpoint.memory import MemorySaver

from job_agent_os.settings import get_settings


def get_checkpointer() -> MemorySaver:
    """Get checkpointer instance.

    In development, use MemorySaver.
    In production, use AsyncPostgresSaver.
    """
    settings = get_settings()

    if settings.env == "prod":
        # For production, use PostgresSaver
        # from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        # return AsyncPostgresSaver.from_conn_string(settings.database_url)
        pass

    # Default to MemorySaver for development
    return MemorySaver()
"""Checkpointer configuration (Postgres/Memory)."""
