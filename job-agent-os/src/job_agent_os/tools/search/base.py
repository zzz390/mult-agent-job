"""Platform adapter abstract base class."""

from abc import ABC, abstractmethod
from typing import Any


class PlatformAdapter(ABC):
    """Abstract base class for job platform adapters.

    Each platform (BOSS, Niuke, Guopin, etc.) implements this interface.
    """

    platform_name: str = "base"
    rate_limit: int = 10  # requests per minute

    @abstractmethod
    async def search(self, query: dict) -> list[dict]:
        """Search jobs on the platform.

        Args:
            query: Structured job query (JobQuery schema)

        Returns:
            List of raw job items
        """
        pass

    @abstractmethod
    async def parse_result(self, raw: dict) -> dict:
        """Parse a raw search result into structured format.

        Args:
            raw: Raw search result from platform

        Returns:
            Structured job data
        """
        pass

    def _build_search_url(self, query: dict) -> str:
        """Build search URL from query (override in subclass)."""
        return ""

    def _get_headers(self) -> dict[str, str]:
        """Get request headers (override in subclass)."""
        return {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
