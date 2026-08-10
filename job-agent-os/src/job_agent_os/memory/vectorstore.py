"""Vector store adapter (pgvector).

Provides VectorStore interface and PgVectorStore implementation
for storing and retrieving document embeddings.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession

from job_agent_os.memory.embeddings import EmbeddingService, get_embedding_service
from job_agent_os.models.memory import Memory


@dataclass
class Document:
    """A document with content and metadata."""

    content: str
    metadata: dict = field(default_factory=dict)
    doc_id: str | None = None
    score: float | None = None


class VectorStore(ABC):
    """Abstract vector store interface."""

    @abstractmethod
    async def add_documents(self, documents: list[Document], user_id: UUID) -> list[str]:
        """Add documents to the store. Returns list of document IDs."""
        pass

    @abstractmethod
    async def similarity_search(
        self, query: str, user_id: UUID, top_k: int = 5
    ) -> list[Document]:
        """Search for similar documents. Returns documents sorted by relevance."""
        pass

    @abstractmethod
    async def delete_document(self, doc_id: str, user_id: UUID) -> bool:
        """Delete a document by ID."""
        pass


class PgVectorStore(VectorStore):
    """PostgreSQL + pgvector implementation of VectorStore.

    Uses the memories table with pgvector extension for
    cosine similarity search.
    """

    def __init__(
        self,
        db: AsyncSession,
        embedding_service: EmbeddingService | None = None,
    ) -> None:
        self.db = db
        self.embedding_service = embedding_service or get_embedding_service()

    async def add_documents(self, documents: list[Document], user_id: UUID) -> list[str]:
        """Add documents: embed content and store in DB."""
        if not documents:
            return []

        # Batch embed all document contents
        texts = [doc.content for doc in documents]
        embeddings = await self.embedding_service.embed_batch(texts)

        doc_ids: list[str] = []
        for doc, embedding in zip(documents, embeddings, strict=False):
            memory = Memory(
                user_id=user_id,
                memory_type="rag_chunk",
                category=doc.metadata.get("category", "document"),
                key=doc.metadata.get("key", doc.doc_id or "chunk"),
                content=doc.metadata,
                content_text=doc.content,
                embedding=embedding,
                importance_score=doc.metadata.get("importance", 0.5),
                source_agent=doc.metadata.get("source_agent"),
                is_active=True,
            )
            self.db.add(memory)
            await self.db.flush()
            doc_ids.append(str(memory.id))

        return doc_ids

    async def similarity_search(
        self, query: str, user_id: UUID, top_k: int = 5
    ) -> list[Document]:
        """Search for similar documents using cosine similarity."""
        # Embed the query
        query_embedding = await self.embedding_service.embed_text(query)

        # Use pgvector cosine distance operator
        embedding_str = f"[{','.join(str(x) for x in query_embedding)}]"

        stmt = (
            select(
                Memory.id,
                Memory.content_text,
                Memory.content,
                Memory.category,
                Memory.key,
                (1 - Memory.embedding.cosine_distance(embedding_str)).label("similarity"),
            )
            .where(
                Memory.user_id == user_id,
                Memory.is_active == True,  # noqa: E712
                Memory.embedding.isnot(None),
            )
            .order_by(literal_column("similarity").desc())
            .limit(top_k)
        )

        result = await self.db.execute(stmt)
        rows = result.all()

        documents = []
        for row in rows:
            documents.append(
                Document(
                    content=row.content_text or "",
                    metadata={
                        **(row.content or {}),
                        "category": row.category,
                        "key": row.key,
                    },
                    doc_id=str(row.id),
                    score=float(row.similarity) if row.similarity else None,
                )
            )

        return documents

    async def delete_document(self, doc_id: str, user_id: UUID) -> bool:
        """Soft-delete a document."""
        result = await self.db.execute(
            select(Memory).where(
                Memory.id == UUID(doc_id),
                Memory.user_id == user_id,
            )
        )
        memory = result.scalar_one_or_none()
        if not memory:
            return False

        memory.is_active = False
        await self.db.flush()
        return True
