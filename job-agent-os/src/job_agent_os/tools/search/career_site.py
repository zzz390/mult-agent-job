"""Bounded career-site discovery and dynamic ATS extraction.

Company sites rarely expose vacancies on the first page returned by a search
engine.  This module follows likely recruitment/navigation links for a small,
fixed number of pages and hands supported JavaScript applicant-tracking systems
to a dedicated adapter.  The crawler is deliberately read-only and bounded.
"""

from __future__ import annotations

import asyncio
import heapq
import logging
import re
from dataclasses import dataclass
from itertools import count
from typing import TYPE_CHECKING
from urllib.parse import urljoin, urlparse, urlunparse

import httpx
from bs4 import BeautifulSoup

from job_agent_os.tools.parse.html_parser import (
    DnsResolutionError,
    UnsafeUrlError,
    _assert_safe_url,
)

if TYPE_CHECKING:
    from playwright.async_api import BrowserContext

type JobRecord = dict[str, object]

logger = logging.getLogger(__name__)

_MAX_REDIRECTS = 5
_MAX_RESPONSE_BYTES = 2 * 1024 * 1024
_CAREER_TERMS = (
    "招聘",
    "诚聘",
    "招贤",
    "人才",
    "加入我们",
    "加入",
    "社会招聘",
    "校园招聘",
    "校招",
    "社招",
    "实习",
    "career",
    "careers",
    "recruit",
    "recruitment",
    "talent",
    "vacancy",
    "vacancies",
    "jobs",
)
_BRIDGE_TERMS = (
    "关于我们",
    "走进",
    "认识我们",
    "人力资源",
    "about",
    "company",
    "corporate",
)
_JOB_URL_RE = re.compile(r"(?:#/|/)(?:job|jobs|position|positions|vacancy)/", re.I)
_MOKA_HOSTS = ("app.mokahr.com",)
_MULTIPART_PUBLIC_SUFFIXES = ("com.cn", "net.cn", "org.cn", "gov.cn")


@dataclass(frozen=True, slots=True)
class CareerPage:
    """A fetched static page plus the links needed for bounded traversal."""

    url: str
    title: str
    text: str
    links: tuple[tuple[str, str], ...]


class CareerSiteCrawler:
    """Discover career pages up to three levels deep and extract public jobs."""

    def __init__(
        self,
        *,
        max_depth: int = 3,
        max_pages: int = 12,
        max_jobs: int = 20,
        timeout: float = 15.0,
    ) -> None:
        self.max_depth = max(0, min(max_depth, 3))
        self.max_pages = max(1, max_pages)
        self.max_jobs = max(1, max_jobs)
        self.timeout = timeout

    async def crawl(
        self,
        entry_urls: list[str],
        *,
        company: str,
        region: str,
        keyword: str = "",
    ) -> list[JobRecord]:
        """Follow likely career links and return verifiable job records."""
        roots = {self._site_key(url) for url in entry_urls if self._site_key(url)}
        pending: list[tuple[int, int, int, str]] = []
        sequence = count()
        for url in entry_urls:
            priority = 100 if self._is_moka_url(url) else self._link_score("", url) + 10
            heapq.heappush(pending, (-priority, 0, next(sequence), self._canonical_url(url)))

        visited: set[str] = set()
        ats_urls: list[str] = []
        static_candidates: list[CareerPage] = []
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; JobAgentOS/1.0; +career-discovery)",
            "Accept": "text/html,application/xhtml+xml,text/plain;q=0.8,*/*;q=0.5",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
        }

        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=False) as client:
            while pending and len(visited) < self.max_pages:
                _, depth, _, url = heapq.heappop(pending)
                if not url or url in visited:
                    continue
                visited.add(url)

                if self._is_moka_url(url):
                    ats_urls.append(url)
                    continue

                page = await self._fetch_static_page(client, url, headers)
                if page is None:
                    continue
                page_context = f"{page.title}\n{page.text}\n{page.url}"
                if self._contains_career_text(page_context):
                    static_candidates.append(page)

                if depth >= self.max_depth:
                    continue
                ranked_links: list[tuple[int, str]] = []
                for label, target in page.links:
                    target = self._canonical_url(target)
                    if not target or target in visited:
                        continue
                    if self._is_moka_url(target):
                        ats_urls.append(target)
                        continue
                    if self._site_key(target) not in roots:
                        continue
                    score = self._link_score(label, target)
                    if score > 0:
                        ranked_links.append((score, target))
                # Wide corporate menus can contain hundreds of links.  Eight
                # ranked branches per page are enough to reach about/career
                # pages without turning this into a whole-site spider.
                for score, target in sorted(ranked_links, reverse=True)[:8]:
                    heapq.heappush(pending, (-score, depth + 1, next(sequence), target))

        jobs: list[JobRecord] = []
        seen_urls: set[str] = set()
        for ats_url in dict.fromkeys(ats_urls):
            if len(jobs) >= self.max_jobs:
                break
            batch = await scrape_moka_jobs(
                ats_url,
                company=company,
                region=region,
                keyword=keyword,
                max_jobs=self.max_jobs - len(jobs),
            )
            self._extend_unique(jobs, batch, seen_urls)

        # Keep the previous static-page behaviour as a fallback.  Dynamic ATS
        # detail URLs are preferred because they identify individual vacancies.
        for page in static_candidates:
            if len(jobs) >= self.max_jobs:
                break
            context = f"{page.title}\n{page.text}"
            if keyword and keyword.lower() not in context.lower():
                continue
            if page.url in seen_urls:
                continue
            seen_urls.add(page.url)
            jobs.append(
                {
                    "title": self._clean_title(page.title),
                    "company": company,
                    "company_type": "国企",
                    "location": region,
                    "salary": "",
                    "skills_required": [keyword] if keyword else [],
                    "raw_description": self._clean_text(page.text)[:4000],
                    "source_url": page.url,
                    "source_platform": "official_website",
                }
            )
        return jobs

    async def _fetch_static_page(
        self,
        client: httpx.AsyncClient,
        url: str,
        headers: dict[str, str],
    ) -> CareerPage | None:
        current_url = url
        try:
            for _ in range(_MAX_REDIRECTS + 1):
                _assert_safe_url(current_url)
                async with client.stream("GET", current_url, headers=headers) as response:
                    if response.is_redirect:
                        location = response.headers.get("location")
                        if not location:
                            return None
                        current_url = urljoin(current_url, location)
                        continue
                    response.raise_for_status()
                    content_type = response.headers.get("content-type", "").lower()
                    if content_type and not any(
                        kind in content_type for kind in ("text/html", "application/xhtml+xml", "text/plain")
                    ):
                        return None
                    content = bytearray()
                    async for chunk in response.aiter_bytes():
                        content.extend(chunk)
                        if len(content) > _MAX_RESPONSE_BYTES:
                            return None
                    encoding = response.encoding or "utf-8"
                    html = bytes(content).decode(encoding, errors="replace")
                    return self._parse_page(html, str(response.url))
            return None
        except (UnsafeUrlError, DnsResolutionError, httpx.HTTPError, ValueError) as exc:
            logger.info("Career page fetch skipped for %s: %s", url, exc)
            return None

    @classmethod
    def _parse_page(cls, html: str, base_url: str) -> CareerPage:
        soup = BeautifulSoup(html, "html.parser")
        title = cls._clean_text(soup.title.get_text(" ") if soup.title else "")
        heading = soup.find(["h1", "h2"])
        if not title and heading:
            title = cls._clean_text(heading.get_text(" "))
        links: list[tuple[str, str]] = []
        for anchor in soup.find_all("a", href=True):
            href = str(anchor.get("href") or "").strip()
            if not href or href.startswith(("javascript:", "mailto:", "tel:")):
                continue
            links.append((cls._clean_text(anchor.get_text(" ")), urljoin(base_url, href)))
        for tag in soup(["script", "style", "noscript", "iframe"]):
            tag.decompose()
        text = cls._clean_text(soup.get_text(" "))
        return CareerPage(url=base_url, title=title, text=text, links=tuple(links))

    @staticmethod
    def _extend_unique(target: list[JobRecord], batch: list[JobRecord], seen_urls: set[str]) -> None:
        for job in batch:
            url = str(job.get("source_url") or "")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            target.append(job)

    @staticmethod
    def _clean_text(value: str) -> str:
        return " ".join(value.split())

    @classmethod
    def _clean_title(cls, title: str) -> str:
        cleaned = cls._clean_text(title)
        return re.sub(r"\s*[-_|—].*$", "", cleaned).strip() or "招聘公告"

    @staticmethod
    def _canonical_url(url: str) -> str:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return ""
        fragment = parsed.fragment if CareerSiteCrawler._is_moka_url(url) else ""
        return urlunparse(
            (parsed.scheme.lower(), parsed.netloc.lower(), parsed.path or "/", "", parsed.query, fragment)
        )

    @staticmethod
    def _site_key(url: str) -> str:
        host = (urlparse(url).hostname or "").lower().strip(".")
        labels = host.split(".")
        if len(labels) < 2:
            return host
        tail = ".".join(labels[-2:])
        if tail in _MULTIPART_PUBLIC_SUFFIXES and len(labels) >= 3:
            return ".".join(labels[-3:])
        return tail

    @staticmethod
    def _is_moka_url(url: str) -> bool:
        host = (urlparse(url).hostname or "").lower()
        return any(host == item or host.endswith(f".{item}") for item in _MOKA_HOSTS)

    @staticmethod
    def _contains_career_text(value: str) -> bool:
        lowered = value.lower()
        return any(term in lowered for term in _CAREER_TERMS)

    @staticmethod
    def _link_score(label: str, url: str) -> int:
        value = f"{label} {url}".lower()
        score = sum(4 for term in _CAREER_TERMS if term in value)
        score += sum(1 for term in _BRIDGE_TERMS if term in value)
        if _JOB_URL_RE.search(url):
            score += 5
        return score


def _moka_jobs_url(url: str) -> str:
    """Normalize any Moka organisation/home URL to its complete jobs route."""
    parsed = urlparse(url)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", parsed.query, "/jobs"))


async def scrape_moka_jobs(
    url: str,
    *,
    company: str,
    region: str,
    keyword: str = "",
    max_jobs: int = 20,
) -> list[JobRecord]:
    """Render a public Moka career site and extract list/detail records.

    Moka's public page is a hash-routed SPA, so a plain HTTP client never sees
    the job cards.  Playwright is optional at runtime: failures degrade to an
    empty batch and allow the caller's static fallback to continue.
    """
    try:
        _assert_safe_url(url)
        from playwright.async_api import async_playwright

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled", "--disable-dev-shm-usage"],
            )
            try:
                context = await browser.new_context(
                    locale="zh-CN",
                    viewport={"width": 1440, "height": 900},
                    user_agent=(
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/126.0.0.0 Safari/537.36"
                    ),
                )
                await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
                # Collect more cards than the result limit so a selective
                # keyword can still match jobs on later list pages.
                entries = await _collect_moka_entries(
                    context,
                    _moka_jobs_url(url),
                    max(50, max_jobs * 5),
                )
                matching = [
                    entry for entry in entries if not keyword or keyword.lower() in entry["search_text"].lower()
                ][:max_jobs]

                # Bound detail-page parallelism to avoid request bursts.
                semaphore = asyncio.Semaphore(3)

                async def scrape_detail(entry: dict[str, str]) -> JobRecord | None:
                    async with semaphore:
                        return await _scrape_moka_detail(
                            context,
                            entry,
                            company=company,
                            region=region,
                            keyword=keyword,
                        )

                details = await asyncio.gather(*(scrape_detail(entry) for entry in matching))
                return [job for job in details if job is not None]
            finally:
                await browser.close()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Moka career page rendering failed for %s: %s", url, exc)
        return []


async def _collect_moka_entries(context: BrowserContext, jobs_url: str, max_jobs: int) -> list[dict[str, str]]:
    page = await context.new_page()
    try:
        await page.goto(jobs_url, wait_until="domcontentloaded", timeout=30_000)
        await page.wait_for_selector('a[href*="#/job/"]', timeout=12_000)
        entries: dict[str, dict[str, str]] = {}
        for page_number in range(1, 7):
            await page.wait_for_timeout(500)
            cards = page.locator('a[href*="#/job/"]')
            for index in range(await cards.count()):
                card = cards.nth(index)
                href = await card.get_attribute("href")
                if not href:
                    continue
                detail_url = urljoin(jobs_url.split("#", 1)[0], href)
                if urlparse(detail_url).hostname != urlparse(jobs_url).hostname:
                    continue
                if detail_url in entries:
                    continue
                title_node = card.locator('[class^="title-"]').first
                location_node = card.locator('[class^="locations-"]').first
                title = (await title_node.inner_text()).strip() if await title_node.count() else ""
                location = (await location_node.inner_text()).strip() if await location_node.count() else ""
                card_text = " ".join((await card.inner_text()).split())
                entries[detail_url] = {
                    "url": detail_url,
                    "title": title or card_text or "招聘岗位",
                    "location": location,
                    "search_text": card_text,
                }
                if len(entries) >= max_jobs:
                    return list(entries.values())

            next_number = str(page_number + 1)
            next_page = page.locator(
                '.theme-pagination > [class*="pagination-item"][class*=" page-"]',
                has_text=re.compile(rf"^{re.escape(next_number)}$"),
            )
            if await next_page.count() == 0:
                break
            await next_page.first.click()
            await page.wait_for_timeout(500)
        return list(entries.values())
    finally:
        await page.close()


async def _scrape_moka_detail(
    context: BrowserContext,
    entry: dict[str, str],
    *,
    company: str,
    region: str,
    keyword: str,
) -> JobRecord | None:
    page = await context.new_page()
    try:
        await page.goto(entry["url"], wait_until="domcontentloaded", timeout=30_000)
        try:
            await page.wait_for_selector('[class*="job-description"]', timeout=10_000)
        except Exception:  # noqa: BLE001
            await page.wait_for_timeout(800)
        info = page.locator('[class*="job-info"]').first
        title = entry["title"]
        location = entry["location"] or region
        if await info.count():
            title_node = info.locator('[class^="title-"]').first
            location_node = info.locator('[class^="locations-"]').first
            if await title_node.count():
                title = (await title_node.inner_text()).strip() or title
            if await location_node.count():
                location = " ".join((await location_node.inner_text()).split()) or location
        description_nodes = page.locator('[class*="job-description"]')
        description = ""
        # Some Moka builds briefly render a "暂无" placeholder.  Select the
        # longest populated description after a short bounded wait.
        for _ in range(12):
            descriptions = [
                " ".join(text.split()) for text in await description_nodes.all_inner_texts() if text.strip()
            ]
            description = max(descriptions, key=len, default="")
            if len(description) >= 30 and description != "暂无":
                break
            await page.wait_for_timeout(400)
        if len(description) < 30 or description == "暂无":
            body = " ".join((await page.locator("body").inner_text()).split())
            description = body[:4000]
        if not title or not description:
            return None
        return {
            "title": title,
            "company": company,
            "company_type": "国企",
            "location": location,
            "salary": "",
            "skills_required": [keyword] if keyword else [],
            "raw_description": description[:4000],
            "source_url": entry["url"],
            "source_platform": "official_website",
        }
    finally:
        await page.close()
