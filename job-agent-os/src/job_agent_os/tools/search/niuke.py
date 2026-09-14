"""牛客 platform adapter.

Uses the shared anti-detection fetch path from PlatformAdapter
(random UA, optional proxy, global rate limiting — issue #3).
"""

import logging
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from job_agent_os.tools.search.base import PlatformAdapter

logger = logging.getLogger(__name__)


class NiukeAdapter(PlatformAdapter):
    """牛客 search adapter for campus recruitment jobs."""

    platform_name = "niuke"
    rate_limit = 5
    base_url = "https://www.nowcoder.com"

    # 牛客 job lists are JS-rendered; try Playwright first
    render_with_playwright = True
    playwright_wait_selector = ".job-item, .recommend-job-item, .job-card"

    _CARD_SELECTORS = [
        ".job-item",
        ".recommend-job-item",
        ".job-card",
        ".job-item-box",
        "div[class*='job-item']",
        "div[class*='jobCard']",
        "div[class*='job-card']",
        "li[class*='job-item']",
    ]

    def _build_search_url(self, query: dict) -> str:
        from urllib.parse import quote

        keyword = self._extract_keyword(query)
        region = query.get("region", [""])[0] if query.get("region") else ""
        url = f"{self.base_url}/recommend/jobs/search?keyword={quote(keyword)}"
        if region:
            url += f"&city={quote(region)}"
        return url

    async def search(self, query: dict) -> list[dict]:
        """Search jobs on Niuke."""
        async with self._single_flight_search():
            return await self._search_once(query)

    async def _search_once(self, query: dict) -> list[dict]:
        """Run one rate-limited Niuke request while holding the platform slot."""
        await self._rate_limit_wait()
        url = self._build_search_url(query)
        jobs: list[dict] = []

        try:
            html = await self._fetch_page(url)

            soup = BeautifulSoup(html, "html.parser")
            job_cards = []
            for selector in self._CARD_SELECTORS:
                job_cards = soup.select(selector)
                if job_cards:
                    break

            for card in job_cards[:20]:
                job = self._parse_job_card(card)
                if job:
                    jobs.append(job)

        except httpx.TimeoutException as e:
            raise TimeoutError("Niuke search timed out") from e
        except httpx.HTTPStatusError as e:
            raise ConnectionError(
                f"Niuke returned status {e.response.status_code}"
            ) from e
        except (TimeoutError, ConnectionError):
            raise
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(f"Niuke search failed: {str(e)}") from e

        return jobs

    def _parse_job_card(self, card: BeautifulSoup) -> dict | None:
        try:
            title_el = card.select_one(".job-name, .position-name, h3, [class*='title']")
            company_el = card.select_one(".company-name, .corp-name, [class*='company']")
            salary_el = card.select_one(
                ".job-salary, .salary, .pay, .salary-range, [class*='salary']"
            )
            location_el = card.select_one(
                ".job-area, .work-city, [class*='city'], [class*='area'], [class*='location']"
            )
            link_el = card.select_one("a[href]")

            title = title_el.get_text(strip=True) if title_el else ""
            company = company_el.get_text(strip=True) if company_el else ""
            salary = salary_el.get_text(strip=True) if salary_el else ""
            location = location_el.get_text(strip=True) if location_el else ""

            if not title or not company:
                return None

            source_url = ""
            if link_el and link_el.get("href"):
                href = str(link_el["href"])
                source_url = urljoin(self.base_url, href)

            tag_elements = card.select(".tag-list span, .tag-item, .job-tags span, .tag")
            tags = [t.get_text(strip=True) for t in tag_elements if t.get_text(strip=True)]
            raw_desc = ", ".join(tags) if tags else ""

            return {
                "title": title,
                "company": company,
                "salary": salary,
                "location": location,
                "source_url": source_url,
                "source_platform": self.platform_name,
                "raw_description": raw_desc,
            }
        except Exception:  # noqa: BLE001
            return None

    async def parse_result(self, raw: dict) -> dict:
        return raw
