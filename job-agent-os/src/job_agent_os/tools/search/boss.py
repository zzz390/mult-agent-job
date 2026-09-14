"""BOSS直聘 platform adapter.

Issue #3 / #8 fixes:
- City names are mapped to BOSS numeric city codes via configs/boss_city_codes.yaml
  (passing a Chinese city name silently returns nationwide results)
- Job lists are JS-rendered, so Playwright is preferred (httpx fallback kept)
- Randomized UA + optional proxy + cookie injection from the base class
- Updated CSS selectors for the current BOSS page layout (with fallbacks)
"""

import logging
from urllib.parse import quote, urljoin

import httpx
from bs4 import BeautifulSoup

from job_agent_os.core.config_loader import load_boss_city_codes
from job_agent_os.tools.search.base import PlatformAdapter

logger = logging.getLogger(__name__)


class BossAdapter(PlatformAdapter):
    """BOSS直聘 search adapter.

    Fetches search results from BOSS Zhipin with rate limiting,
    fingerprint randomization and graceful error handling.
    """

    platform_name = "boss"
    rate_limit = 5  # requests per minute
    base_url = "https://www.zhipin.com"

    # BOSS renders the job list with JS; plain httpx gets an empty shell page
    render_with_playwright = True
    playwright_wait_selector = ".search-job-result, .job-list-box"

    # Candidate selectors for the job card container across BOSS revisions
    _CARD_SELECTORS = [
        ".job-card-wrapper",
        ".search-job-result .job-list li",
        ".job-list-box li",
        ".job-list li",
        ".job-card-box",
        "li.job-card-wrapper",
    ]

    def _build_search_url(self, query: dict) -> str:
        """Build BOSS search URL using the numeric city code (issue #8)."""
        keyword = self._extract_keyword(query)
        city_name = query.get("region", [""])[0] if query.get("region") else ""
        city_codes = load_boss_city_codes()
        # Unknown/absent city falls back to nationwide instead of a broken query
        city_code = city_codes.get(city_name, city_codes.get("全国", "100010000"))
        return f"{self.base_url}/web/geek/job?query={quote(keyword)}&city={city_code}"

    async def search(self, query: dict) -> list[dict]:
        """Search jobs on BOSS Zhipin.

        Args:
            query: Structured job query

        Returns:
            List of raw job items
        """
        async with self._single_flight_search():
            return await self._search_once(query)

    async def _search_once(self, query: dict) -> list[dict]:
        """Run one rate-limited BOSS request while holding the platform slot."""
        await self._rate_limit_wait()

        url = self._build_search_url(query)
        jobs: list[dict] = []

        try:
            html = await self._fetch_page(url, extra_headers={"Referer": self.base_url})

            # Check for anti-bot / captcha verification page
            if (
                "security-check" in html
                or "安全验证" in html
                or "geetest" in html
                or "verify-slider" in html
            ):
                logger.warning(
                    "BOSS search triggered anti-bot security check page (captcha). "
                    "Stopping this source without attempting to bypass verification."
                )
                return []

            soup = BeautifulSoup(html, "html.parser")
            job_cards = self._select_job_cards(soup)

            for card in job_cards[:20]:  # Limit results
                job = self._parse_job_card(card, query)
                if job:
                    jobs.append(job)

            if not jobs:
                logger.warning(
                    "BOSS search returned 0 parseable cards (possible anti-bot page or layout change)"
                )

        except httpx.TimeoutException as e:
            raise TimeoutError(f"BOSS search timed out for query: {query}") from e
        except httpx.HTTPStatusError as e:
            raise ConnectionError(
                f"BOSS returned status {e.response.status_code}"
            ) from e
        except (TimeoutError, ConnectionError):
            raise
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(f"BOSS search failed: {str(e)}") from e

        return jobs

    def _select_job_cards(self, soup: BeautifulSoup) -> list:
        """Try multiple card selectors across BOSS layout revisions."""
        for selector in self._CARD_SELECTORS:
            cards = soup.select(selector)
            if cards:
                return cards
        return []

    def _parse_job_card(self, card: BeautifulSoup, query: dict) -> dict | None:
        """Parse a single job card from search results."""
        try:
            title_el = card.select_one(".job-name, .job-title, .job-title .job-name")
            company_el = card.select_one(".company-name a, .company-name, .company-text")
            salary_el = card.select_one(".salary, .job-salary")
            location_el = card.select_one(".job-area, .job-location")
            link_el = card.select_one("a[href*='job_detail']") or card.select_one("a[href]")

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

            # Extract tags (e.g. experience, education, tech tags)
            tag_elements = card.select(".tag-list li, .job-info .tag-item, .job-tags span")
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
        """Parse a raw search result into structured format."""
        return raw
