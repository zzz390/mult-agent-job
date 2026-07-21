"""牛客 platform adapter."""

import asyncio
import time

import httpx
from bs4 import BeautifulSoup

from job_agent_os.tools.search.base import PlatformAdapter


class NiukeAdapter(PlatformAdapter):
    """牛客 search adapter for campus recruitment jobs."""

    platform_name = "niuke"
    rate_limit = 5
    base_url = "https://www.nowcoder.com"

    def __init__(self) -> None:
        self._last_request_time: float = 0
        self._min_interval: float = 60.0 / self.rate_limit

    async def _rate_limit_wait(self) -> None:
        elapsed = time.time() - self._last_request_time
        if elapsed < self._min_interval:
            await asyncio.sleep(self._min_interval - elapsed)
        self._last_request_time = time.time()

    def _build_search_url(self, query: dict) -> str:
        keyword = query.get("direction", "") or " ".join(query.get("skills", []))
        return f"{self.base_url}/recommend/jobs/search?keyword={keyword}"

    def _get_headers(self) -> dict[str, str]:
        return {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }

    async def search(self, query: dict) -> list[dict]:
        """Search jobs on Niuke."""
        await self._rate_limit_wait()
        url = self._build_search_url(query)
        jobs: list[dict] = []

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(url, headers=self._get_headers())
                response.raise_for_status()

                soup = BeautifulSoup(response.text, "html.parser")
                job_cards = soup.select(".job-item, .recommend-job-item, .job-card")

                for card in job_cards[:20]:
                    job = self._parse_job_card(card)
                    if job:
                        jobs.append(job)

        except httpx.TimeoutException:
            raise TimeoutError("Niuke search timed out")
        except httpx.HTTPStatusError as e:
            raise ConnectionError(f"Niuke returned status {e.response.status_code}")
        except Exception as e:
            raise RuntimeError(f"Niuke search failed: {str(e)}")

        return jobs

    def _parse_job_card(self, card: BeautifulSoup) -> dict | None:
        try:
            title_el = card.select_one(".job-name, .position-name, h3")
            company_el = card.select_one(".company-name, .corp-name")
            salary_el = card.select_one(".job-salary, .salary")
            location_el = card.select_one(".job-area, .work-city")
            link_el = card.select_one("a[href]")

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
        return raw
