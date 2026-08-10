"""RAG engine (Embedding + Retrieval).

Provides RAGPipeline for:
- index_resume(resume) -> chunk + embed + store
- retrieve_relevant(query, top_k) -> relevant chunks
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from job_agent_os.memory.embeddings import EmbeddingService, get_embedding_service
from job_agent_os.memory.vectorstore import Document, PgVectorStore


class RAGPipeline:
    """RAG Pipeline for resume indexing and retrieval.

    Workflow:
    1. index_resume: Split resume into chunks -> embed -> store in pgvector
    2. retrieve_relevant: Embed query -> cosine similarity search -> return chunks
    """

    def __init__(
        self,
        db: AsyncSession,
        embedding_service: EmbeddingService | None = None,
        chunk_size: int = 500,
        chunk_overlap: int = 100,
    ) -> None:
        self.db = db
        self.embedding_service = embedding_service or get_embedding_service()
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.vector_store = PgVectorStore(db, self.embedding_service)

    async def index_resume(self, resume: dict, user_id: UUID) -> list[str]:
        """Index a resume: split into chunks, embed, and store.

        Args:
            resume: Resume data dict with sections like skills, experience, projects
            user_id: User ID for ownership

        Returns:
            List of stored document IDs
        """
        # Extract text sections from resume
        chunks = self._split_resume_into_chunks(resume)

        if not chunks:
            return []

        # Create Document objects with metadata
        documents = [
            Document(
                content=chunk["text"],
                metadata={
                    "category": "resume",
                    "key": f"resume_{chunk['section']}_{i}",
                    "section": chunk["section"],
                    "source_agent": "resume_agent",
                    "importance": 0.8,
                },
            )
            for i, chunk in enumerate(chunks)
        ]

        # Store via vector store
        doc_ids = await self.vector_store.add_documents(documents, user_id)
        return doc_ids

    async def retrieve_relevant(
        self, query: str, user_id: UUID, top_k: int = 5
    ) -> list[Document]:
        """Retrieve relevant resume chunks for a query.

        Args:
            query: Search query (e.g., job description or question)
            user_id: User ID to scope search
            top_k: Number of results to return

        Returns:
            List of relevant Documents sorted by similarity
        """
        return await self.vector_store.similarity_search(query, user_id, top_k)

    async def index_text(
        self, text: str, user_id: UUID, category: str = "general", key: str = "doc"
    ) -> list[str]:
        """Index arbitrary text content.

        Args:
            text: Text content to index
            user_id: User ID
            category: Memory category
            key: Memory key prefix

        Returns:
            List of stored document IDs
        """
        chunks = self._split_text_into_chunks(text)

        documents = [
            Document(
                content=chunk,
                metadata={
                    "category": category,
                    "key": f"{key}_{i}",
                    "importance": 0.5,
                },
            )
            for i, chunk in enumerate(chunks)
        ]

        return await self.vector_store.add_documents(documents, user_id)

    def _split_resume_into_chunks(self, resume: dict) -> list[dict]:
        """Split resume dict into text chunks by section."""
        chunks: list[dict] = []

        section_map = {
            "skills": "技能",
            "experience": "工作经历",
            "projects": "项目经历",
            "education": "教育背景",
            "summary": "个人总结",
        }

        for field_name, section_label in section_map.items():
            value = resume.get(field_name)
            if not value:
                continue

            # Convert to text
            if isinstance(value, list):
                text = "\n".join(str(item) for item in value)
            elif isinstance(value, dict):
                text = "\n".join(f"{k}: {v}" for k, v in value.items())
            else:
                text = str(value)

            if not text.strip():
                continue

            # Split long sections into overlapping chunks
            text_chunks = self._split_text_into_chunks(text)
            for chunk_text in text_chunks:
                chunks.append({"section": section_label, "text": chunk_text})

        return chunks

    def _split_text_into_chunks(self, text: str) -> list[str]:
        """Split text into overlapping chunks, preferring sentence boundaries.

        When a chunk would exceed chunk_size, the algorithm attempts to break
        at a sentence boundary (Chinese punctuation, English punctuation, or
        newline) to avoid splitting sentences across chunks.
        """
        if len(text) <= self.chunk_size:
            return [text] if text.strip() else []

        # Sentence boundary separators, ordered by preference
        separators = ["\n", "。", "！", "？", ". ", "! ", "? "]

        chunks: list[str] = []
        start = 0
        while start < len(text):
            end = start + self.chunk_size
            if end < len(text):
                # Try to break at a sentence boundary within the chunk
                for sep in separators:
                    boundary = text.rfind(sep, start, end)
                    if boundary > start + self.chunk_size // 2:
                        end = boundary + len(sep)
                        break
            else:
                end = len(text)

            chunk = text[start:end]
            if chunk.strip():
                chunks.append(chunk.strip())

            # Stop if we've reached the end of the text
            if end >= len(text):
                break

            # Advance with overlap, ensuring forward progress
            step = end - start - self.chunk_overlap
            if step <= 0:
                step = 1
            start += step

        return chunks
