"""Memory store abstraction and implementation.

Provides MemoryStore interface and PostgresMemoryStore implementation
for CRUD operations and semantic search over user memories.
"""

from abc import ABC, abstractmethod
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from job_agent_os.memory.embeddings import EmbeddingService, get_embedding_service
from job_agent_os.models.memory import Memory


class MemoryStore(ABC):
    """Abstract memory store interface."""

    @abstractmethod
    async def save_memory(
        self,
        user_id: UUID,
        key: str,
        content: dict,
        category: str = "general",
        memory_type: str = "long_term",
        importance_score: float = 0.5,
        source_agent: str | None = None,
        source_session_id: UUID | None = None,
    ) -> Memory:
        """Save or update a memory."""
        pass

    @abstractmethod
    async def get_memory(self, user_id: UUID, key: str) -> Memory | None:
        """Get a memory by key."""
        pass

    @abstractmethod
    async def get_memory_by_id(self, user_id: UUID, memory_id: UUID) -> Memory | None:
        """Get a memory by ID."""
        pass

    @abstractmethod
    async def delete_memory(self, user_id: UUID, memory_id: UUID) -> bool:
        """Soft-delete a memory."""
        pass

    @abstractmethod
    async def search_memories(
        self, user_id: UUID, query: str, category: str | None = None, top_k: int = 5
    ) -> list[Memory]:
        """Semantic search over memories."""
        pass

    @abstractmethod
    async def list_memories(
        self, user_id: UUID, category: str | None = None, limit: int = 20
    ) -> list[Memory]:
        """List memories for a user."""
        pass


class PostgresMemoryStore(MemoryStore):
    """PostgreSQL implementation of MemoryStore.

    Supports:
    - CRUD operations on memories
    - Semantic search via pgvector cosine similarity
    - Cross-session user preference storage
    """

    def __init__(
        self,
        db: AsyncSession,
        embedding_service: EmbeddingService | None = None,
    ) -> None:
        self.db = db
        self.embedding_service = embedding_service or get_embedding_service()

    async def save_memory(
        self,
        user_id: UUID,
        key: str,
        content: dict,
        category: str = "general",
        memory_type: str = "long_term",
        importance_score: float = 0.5,
        source_agent: str | None = None,
        source_session_id: UUID | None = None,
    ) -> Memory:
        """Save or update a memory. Generates embedding for semantic search."""
        # Check if memory with this key already exists
        existing = await self.get_memory(user_id, key)

        # Generate embedding from content text
        content_text = self._content_to_text(content)
        embedding = None
        try:
            embedding = await self.embedding_service.embed_text(content_text)
        except Exception:
            pass  # Embedding failure shouldn't block memory save

        if existing:
            # Update existing
            existing.content = content
            existing.content_text = content_text
            existing.category = category
            existing.importance_score = importance_score
            existing.embedding = embedding
            if source_agent:
                existing.source_agent = source_agent
            await self.db.flush()
            await self.db.refresh(existing)
            return existing

        # Create new
        memory = Memory(
            user_id=user_id,
            memory_type=memory_type,
            category=category,
            key=key,
            content=content,
            content_text=content_text,
            embedding=embedding,
            importance_score=importance_score,
            source_agent=source_agent,
            source_session_id=source_session_id,
            is_active=True,
        )
        self.db.add(memory)
        await self.db.flush()
        await self.db.refresh(memory)
        return memory

    async def get_memory(self, user_id: UUID, key: str) -> Memory | None:
        """Get a memory by key."""
        result = await self.db.execute(
            select(Memory).where(
                Memory.user_id == user_id,
                Memory.key == key,
                Memory.is_active == True,  # noqa: E712
            )
        )
        memory = result.scalar_one_or_none()
        if memory:
            memory.access_count += 1
            memory.last_accessed_at = datetime.now(UTC)
            await self.db.flush()
        return memory

    async def get_memory_by_id(self, user_id: UUID, memory_id: UUID) -> Memory | None:
        """Get a memory by ID."""
        result = await self.db.execute(
            select(Memory).where(
                Memory.id == memory_id,
                Memory.user_id == user_id,
                Memory.is_active == True,  # noqa: E712
            )
        )
        return result.scalar_one_or_none()

    async def delete_memory(self, user_id: UUID, memory_id: UUID) -> bool:
        """Soft-delete a memory."""
        result = await self.db.execute(
            select(Memory).where(
                Memory.id == memory_id,
                Memory.user_id == user_id,
            )
        )
        memory = result.scalar_one_or_none()
        if not memory:
            return False

        memory.is_active = False
        await self.db.flush()
        return True

    async def search_memories(
        self, user_id: UUID, query: str, category: str | None = None, top_k: int = 5
    ) -> list[Memory]:
        """Semantic search over memories using vector similarity."""
        try:
            query_embedding = await self.embedding_service.embed_text(query)
        except Exception:
            # Fallback to keyword search if embedding fails
            return await self._keyword_search(user_id, query, category, top_k)

        from sqlalchemy import text as sa_text

        embedding_str = f"[{','.join(str(x) for x in query_embedding)}]"

        stmt = (
            select(Memory)
            .where(
                Memory.user_id == user_id,
                Memory.is_active == True,  # noqa: E712
                Memory.embedding.isnot(None),
            )
            .order_by(Memory.embedding.cosine_distance(embedding_str))
            .limit(top_k)
        )

        if category:
            stmt = stmt.where(Memory.category == category)

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def _keyword_search(
        self, user_id: UUID, query: str, category: str | None, top_k: int
    ) -> list[Memory]:
        """Fallback keyword search when embedding is unavailable."""
        stmt = select(Memory).where(
            Memory.user_id == user_id,
            Memory.is_active == True,  # noqa: E712
            Memory.content_text.ilike(f"%{query}%"),
        )
        if category:
            stmt = stmt.where(Memory.category == category)

        stmt = stmt.order_by(Memory.importance_score.desc()).limit(top_k)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def list_memories(
        self, user_id: UUID, category: str | None = None, limit: int = 20
    ) -> list[Memory]:
        """List memories for a user."""
        stmt = select(Memory).where(
            Memory.user_id == user_id,
            Memory.is_active == True,  # noqa: E712
        )
        if category:
            stmt = stmt.where(Memory.category == category)

        stmt = stmt.order_by(Memory.created_at.desc()).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    def _content_to_text(self, content: dict) -> str:
        """Convert content dict to searchable text."""
        parts = []
        for key, value in content.items():
            if isinstance(value, str):
                parts.append(value)
            elif isinstance(value, list):
                parts.extend(str(v) for v in value)
            else:
                parts.append(str(value))
        return " ".join(parts)
