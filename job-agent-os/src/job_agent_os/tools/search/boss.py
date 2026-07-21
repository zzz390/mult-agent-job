"""BOSS直聘 platform adapter."""

import asyncio
import time

import httpx
from bs4 import BeautifulSoup

from job_agent_os.tools.search.base import PlatformAdapter


class BossAdapter(PlatformAdapter):
    """BOSS直聘 search adapter.

    Uses httpx to fetch search results from BOSS Zhipin.
    Implements rate limiting and graceful error handling.
    """

    platform_name = "boss"
    rate_limit = 5  # requests per minute
    base_url = "https://www.zhipin.com"

    def __init__(self) -> None:
        self._last_request_time: float = 0
        self._min_interval: float = 60.0 / self.rate_limit

    async def _rate_limit_wait(self) -> None:
        """Wait to respect rate limit."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self._min_interval:
            await asyncio.sleep(self._min_interval - elapsed)
        self._last_request_time = time.time()

    def _build_search_url(self, query: dict) -> str:
        """Build BOSS search URL from structured query."""
        keyword = query.get("direction", "") or " ".join(query.get("skills", []))
        city = query.get("region", [""])[0] if query.get("region") else ""
        # BOSS uses city code, simplified here
        return f"{self.base_url}/web/geek/job?query={keyword}&city={city}"

    def _get_headers(self) -> dict[str, str]:
        """Get request headers for BOSS."""
        return {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": self.base_url,
        }

    async def search(self, query: dict) -> list[dict]:
        """Search jobs on BOSS Zhipin.

        Args:
            query: Structured job query

        Returns:
            List of raw job items
        """
        await self._rate_limit_wait()

        url = self._build_search_url(query)
        jobs: list[dict] = []

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(url, headers=self._get_headers())
                response.raise_for_status()

                soup = BeautifulSoup(response.text, "html.parser")
                job_cards = soup.select(".job-card-wrapper, .job-list li")

                for card in job_cards[:20]:  # Limit results
                    job = self._parse_job_card(card, query)
                    if job:
                        jobs.append(job)

        except httpx.TimeoutException:
            raise TimeoutError(f"BOSS search timed out for query: {query}")
        except httpx.HTTPStatusError as e:
            raise ConnectionError(f"BOSS returned status {e.response.status_code}")
        except Exception as e:
            raise RuntimeError(f"BOSS search failed: {str(e)}")

        return jobs

    def _parse_job_card(self, card: BeautifulSoup, query: dict) -> dict | None:
        """Parse a single job card from search results."""
        try:
            title_el = card.select_one(".job-name, .job-title")
            company_el = card.select_one(".company-name a, .company-text")
            salary_el = card.select_one(".salary, .job-salary")
            location_el = card.select_one(".job-area, .job-location")
            link_el = card.select_one("a[href*='job_detail']")

            title = title_el.get_text(strip=True) if title_el else ""
            company = company_el.get_text(strip=True) if company_el else ""
            salary = salary_el.get_text(strip=True) if salary_el else ""
            location = location_el.get_text(strip=True) if location_el else ""

            if not title or not company:
                return None

            source_url = ""
            if link_el and link_el.get("href"):
                href = link_el["href"]
                source_url = f"{self.base_url}{href}" if href.startswith("/") else href

            return {
                "title": title,
                "company": company,
                "salary": salary,
                "location": location,
                "source_url": source_url,
                "source_platform": self.platform_name,
                "raw_description": "",
            }
        except Exception:
            return None

    async def parse_result(self, raw: dict) -> dict:
        """Parse a raw search result into structured format."""
        return raw
