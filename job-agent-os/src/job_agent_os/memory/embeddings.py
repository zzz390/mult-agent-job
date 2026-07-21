"""Embedding service wrapper.

Supports OpenAI-compatible embedding APIs (Alibaba DashScope, OpenAI, etc.).
Provides embed_text and embed_batch interfaces.
"""

import httpx

from job_agent_os.settings import get_settings


class EmbeddingService:
    """Embedding service using OpenAI-compatible API.

    Supports:
    - embed_text(text) -> list[float]
    - embed_batch(texts) -> list[list[float]]
    - Configurable model and dimension
    """

    def __init__(
        self,
        model: str | None = None,
        dimension: int | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        settings = get_settings()
        self.model = model or settings.embedding_model
        self.dimension = dimension or settings.embedding_dimension
        self.api_key = api_key or settings.embedding_api_key.get_secret_value()
        self.base_url = (base_url or settings.embedding_base_url).rstrip("/")
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=30.0,
            )
        return self._client

    async def embed_text(self, text: str) -> list[float]:
        """Embed a single text into a vector.

        Args:
            text: Input text to embed

        Returns:
            Embedding vector as list of floats
        """
        results = await self.embed_batch([text])
        return results[0]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts into vectors.

        Args:
            texts: List of input texts

        Returns:
            List of embedding vectors
        """
        if not texts:
            return []

        client = self._get_client()

        try:
            response = await client.post(
                "/embeddings",
                json={
                    "model": self.model,
                    "input": texts,
                },
            )
            response.raise_for_status()
            data = response.json()

            # Sort by index to ensure order
            embeddings = sorted(data["data"], key=lambda x: x["index"])
            return [item["embedding"] for item in embeddings]

        except httpx.HTTPStatusError as e:
            raise RuntimeError(
                f"Embedding API error: {e.response.status_code} - {e.response.text}"
            ) from e
        except httpx.RequestError as e:
            raise RuntimeError(f"Embedding API connection error: {e}") from e

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None


# Global singleton
_embedding_service: EmbeddingService | None = None


def get_embedding_service() -> EmbeddingService:
    """Get or create the global embedding service instance."""
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service
