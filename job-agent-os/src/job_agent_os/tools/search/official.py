"""Official-first search for municipal state-owned enterprise vacancies.

The search is deliberately two-stage:

1. find a city/province SASAC or government enterprise directory;
2. search the discovered enterprises' own domains for recruitment pages.

Search snippets are only discovery evidence.  Every returned record must point
to a non-aggregator HTTP(S) page whose title/snippet identifies both the
enterprise and recruitment content.  Nothing is synthesized from model memory.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from urllib.parse import parse_qs, unquote, urlparse
from xml.etree import ElementTree

import httpx
from bs4 import BeautifulSoup

from job_agent_os.tools.parse.html_parser import fetch_and_extract_html
from job_agent_os.tools.search.career_site import CareerSiteCrawler

logger = logging.getLogger(__name__)

_RECRUITMENT_WORDS = ("招聘", "招募", "岗位", "职位", "人才", "career", "jobs")
_EXCLUDED_DOMAINS = (
    "iguopin.com",
    "zhipin.com",
    "nowcoder.com",
    "liepin.com",
    "51job.com",
    "zhaopin.com",
    "lagou.com",
    "jobui.com",
    "kanzhun.com",
    "baidu.com",
    "zhihu.com",
    "sohu.com",
    "163.com",
    "qq.com",
    "toutiao.com",
    "weixin.qq.com",
)
_COMPANY_SUFFIX = (
    r"(?:集团股份有限公司|集团有限责任公司|集团有限公司|股份有限公司|"
    r"有限责任公司|有限公司|集团公司|集团)"
)
_COMPANY_RE = re.compile(rf"([\u4e00-\u9fffA-Za-z0-9·（）()]{{2,40}}{_COMPANY_SUFFIX})")

# The callback is intentionally supplied by the service layer rather than
# importing SessionStore here.  This keeps the crawler independently usable
# in tests/CLI jobs and makes UI progress entirely best-effort.
ProgressCallback = Callable[..., Awaitable[object]]


@dataclass(frozen=True, slots=True)
class SearchHit:
    """One web-search result."""

    title: str
    url: str
    description: str = ""


@dataclass(slots=True)
class OfficialSearchOutcome:
    """Products and diagnostics from the two-stage search."""

    jobs: list[dict] = field(default_factory=list)
    companies: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class OfficialSoeJobSearcher:
    """Discover local SOEs from official directories, then search their sites."""

    def __init__(
        self,
        *,
        search_endpoint: str | None = None,
        max_companies: int = 6,
        max_jobs: int = 20,
    ) -> None:
        self.search_endpoint = search_endpoint or os.getenv(
            "OFFICIAL_SEARCH_ENDPOINT", "https://html.duckduckgo.com/html/"
        )
        self.max_companies = max_companies
        self.max_jobs = max_jobs

    async def search(
        self,
        query: dict,
        *,
        progress_callback: ProgressCallback | None = None,
    ) -> OfficialSearchOutcome:
        """Run city SOE discovery followed by official-domain job discovery."""
        regions = [str(item).strip() for item in query.get("region", []) if item]
        if not regions:
            await self._report_progress(
                progress_callback,
                activity_message="官网搜索需要补充城市或省份",
                items_found=0,
                items_saved=0,
            )
            return OfficialSearchOutcome(errors=["官网优先搜索需要城市或省份"])

        region = regions[0]
        keyword = self._extract_keyword(query)
        errors: list[str] = []
        await self._report_progress(
            progress_callback,
            activity_message="正在查找官方国企名录",
            items_found=0,
            items_saved=0,
        )
        try:
            companies = await self._discover_soes(region)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Official SOE discovery failed for %s: %s", region, exc)
            await self._report_progress(
                progress_callback,
                activity_message="官方国企名录查询暂时不可用",
                items_found=0,
            )
            return OfficialSearchOutcome(errors=[f"国企名录搜索失败: {exc}"])

        if not companies:
            await self._report_progress(
                progress_callback,
                activity_message="未发现可查询的官方企业名录",
                items_found=0,
            )
            return OfficialSearchOutcome(errors=[f"未从{region}官方国资页面识别到企业"])

        semaphore = asyncio.Semaphore(3)
        progress_lock = asyncio.Lock()
        completed_companies = 0
        found_urls: set[str] = set()

        await self._report_progress(
            progress_callback,
            activity_message=f"已发现 {len(companies)} 家企业，开始查询官网招聘信息",
            items_found=0,
        )

        async def search_company(company: str) -> tuple[list[dict], str | None]:
            nonlocal completed_companies
            async with semaphore:
                try:
                    batch, error = (
                        await self._search_company_jobs(
                            company,
                            region,
                            keyword,
                            progress_callback=progress_callback,
                        ),
                        None,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Official career search failed for %s: %s", company, exc)
                    batch, error = [], f"{company}官网招聘搜索失败: {exc}"

            # Publish only aggregate counts, never company names or URLs.  The
            # lock keeps concurrent callbacks from overwriting each other's
            # count/message in the session store.
            async with progress_lock:
                completed_companies += 1
                for job in batch:
                    source_url = str(job.get("source_url") or "")
                    if source_url:
                        found_urls.add(source_url)
                found_count = min(len(found_urls), self.max_jobs)
                await self._report_progress(
                    progress_callback,
                    activity_message=(
                        "官网招聘信息查询中："
                        f"已完成 {completed_companies}/{len(companies)} 家企业，"
                        f"已发现 {found_count} 条岗位"
                    ),
                    items_found=found_count,
                )
            return batch, error

        batches = await asyncio.gather(*(search_company(company) for company in companies))
        jobs: list[dict] = []
        seen_urls: set[str] = set()
        for batch, error in batches:
            if error:
                errors.append(error)
            for job in batch:
                url = job["source_url"]
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                jobs.append(job)
                if len(jobs) >= self.max_jobs:
                    break
            if len(jobs) >= self.max_jobs:
                break

        await self._report_progress(
            progress_callback,
            activity_message=(
                f"官网招聘信息查询完成，已发现 {len(jobs)} 条岗位" if jobs else "官网招聘信息查询完成，暂未发现匹配岗位"
            ),
            items_found=len(jobs),
        )

        return OfficialSearchOutcome(
            jobs=jobs,
            companies=companies,
            errors=errors,
        )

    @staticmethod
    async def _report_progress(
        callback: ProgressCallback | None,
        *,
        activity_message: str,
        items_found: int | None = None,
        items_saved: int | None = None,
    ) -> None:
        """Best-effort UI reporting that can never fail the crawl itself."""
        if callback is None:
            return
        try:
            await asyncio.wait_for(
                callback(
                    activity_message=activity_message,
                    items_found=items_found,
                    items_saved=items_saved,
                ),
                timeout=1.0,
            )
        except Exception:  # noqa: BLE001
            logger.debug("Official search progress callback failed", exc_info=True)

    async def _discover_soes(self, region: str) -> list[str]:
        queries = (
            f'{region} "国企矩阵" 国资委',
            f"{region} 国资委 监管企业 名录 官方",
        )
        companies: list[str] = []
        seen: set[str] = set()
        official_pages: list[SearchHit] = []

        for search_query in queries:
            hits = await self._search_web(search_query)
            for hit in hits:
                if not self._is_government_source(hit):
                    continue
                for company in self.extract_company_names(f"{hit.title}\n{hit.description}"):
                    if company not in seen:
                        seen.add(company)
                        companies.append(company)
                if all(page.url != hit.url for page in official_pages):
                    official_pages.append(hit)
            if len(companies) >= self.max_companies:
                return companies[: self.max_companies]

        official_pages.sort(key=self._directory_page_score, reverse=True)
        for hit in official_pages[:3]:
            page_text = await fetch_and_extract_html(hit.url)
            for company in self.extract_company_names(page_text):
                if company not in seen:
                    seen.add(company)
                    companies.append(company)
                if len(companies) >= self.max_companies:
                    return companies
        return companies[: self.max_companies]

    @staticmethod
    def _directory_page_score(hit: SearchHit) -> int:
        text = f"{hit.title} {hit.description} {hit.url}"
        score = 0
        if "国企矩阵" in text or "/gqjz/" in hit.url:
            score += 5
        if "监管企业" in text or "企业名录" in text or "企业名单" in text:
            score += 3
        if "国资委" in text:
            score += 1
        return score

    async def _search_company_jobs(
        self,
        company: str,
        region: str,
        keyword: str,
        *,
        progress_callback: ProgressCallback | None = None,
    ) -> list[dict]:
        query_parts = [f'"{company}"', "官网", "招聘"]
        if keyword:
            query_parts.append(keyword)
        hits = await self._search_web(" ".join(query_parts))
        # A company's homepage may not mention recruitment in the search
        # snippet.  Keep exact company matches (score 2) so the bounded career
        # crawler can discover an "about -> talent -> campus" path itself.
        candidates = [hit for hit in hits if self._official_candidate_score(company, hit) >= 2]
        if not candidates:
            return []

        best_domain = urlparse(
            max(candidates, key=lambda hit: self._official_candidate_score(company, hit)).url
        ).hostname
        if not best_domain:
            return []

        recruitment_hits = [
            hit
            for hit in candidates
            if urlparse(hit.url).hostname == best_domain
            and self._contains_recruitment_text(f"{hit.title} {hit.description}")
        ]
        if not recruitment_hits:
            site_query = f"site:{best_domain} {company} 招聘 {keyword}".strip()
            recruitment_hits = [
                hit
                for hit in await self._search_web(site_query)
                if urlparse(hit.url).hostname == best_domain
                and self._contains_recruitment_text(f"{hit.title} {hit.description} {hit.url}")
            ]

        # Search snippets are only entry-point discovery.  Follow likely
        # navigation links for up to three levels and render supported public
        # ATS pages (currently Moka) to obtain individual, source-backed jobs.
        entry_hits = recruitment_hits or [hit for hit in candidates if urlparse(hit.url).hostname == best_domain][:1]
        await self._report_progress(
            progress_callback,
            activity_message="Search Agent 正在追踪企业官网招聘入口（最多 3 层）",
        )
        crawler = CareerSiteCrawler(max_depth=3, max_pages=12, max_jobs=self.max_jobs)
        deep_jobs = await crawler.crawl(
            [hit.url for hit in entry_hits],
            company=company,
            region=region,
            keyword=keyword,
        )
        if deep_jobs:
            await self._report_progress(
                progress_callback,
                activity_message=f"已从官网招聘系统读取 {len(deep_jobs)} 条岗位详情",
            )
            return deep_jobs

        jobs: list[dict] = []
        for hit in recruitment_hits[:4]:
            context = f"{hit.title}\n{hit.description}"
            page_text = await fetch_and_extract_html(hit.url)
            if page_text:
                context = f"{context}\n{page_text[:12000]}"
            if not self._contains_recruitment_text(context):
                continue
            if keyword and keyword.lower() not in context.lower():
                continue
            jobs.append(
                {
                    "title": self._clean_title(hit.title),
                    "company": company,
                    "company_type": "国企",
                    "location": region,
                    "salary": "",
                    "skills_required": [keyword] if keyword else [],
                    "raw_description": self._clean_text(page_text[:4000] if page_text else hit.description),
                    "source_url": hit.url,
                    "source_platform": "official_website",
                }
            )
        return jobs

    async def _search_web(self, query: str) -> list[SearchHit]:
        """Search lightweight HTML, with Bing RSS as a no-result fallback."""
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; JobAgentOS/1.0)",
            "Accept": "text/html, application/xhtml+xml, application/rss+xml",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True, verify=True) as client:
            response = await client.get(
                self.search_endpoint,
                params={"q": query},
                headers=headers,
            )
            response.raise_for_status()
            hits = self._parse_search_html(response.text)
            if hits:
                return hits

            response = await client.get(
                "https://www.bing.com/search",
                params={"format": "rss", "q": query},
                headers=headers,
            )
            response.raise_for_status()

        return self._parse_search_rss(response.content)

    @classmethod
    def _parse_search_html(cls, html: str) -> list[SearchHit]:
        soup = BeautifulSoup(html, "html.parser")
        hits: list[SearchHit] = []
        for result in soup.select(".result")[:10]:
            title_link = result.select_one(".result__a")
            if not title_link:
                continue
            title = cls._clean_text(title_link.get_text(" "))
            url = cls._unwrap_search_url(str(title_link.get("href") or ""))
            snippet = result.select_one(".result__snippet")
            description = cls._clean_text(snippet.get_text(" ") if snippet else "")
            parsed = urlparse(url)
            if title and parsed.scheme in {"http", "https"} and parsed.hostname:
                hits.append(SearchHit(title=title, url=url, description=description))
        return hits

    @staticmethod
    def _unwrap_search_url(url: str) -> str:
        if url.startswith("//"):
            url = f"https:{url}"
        parsed = urlparse(url)
        redirected = parse_qs(parsed.query).get("uddg")
        if redirected:
            return unquote(redirected[0])
        return url

    @classmethod
    def _parse_search_rss(cls, content: bytes) -> list[SearchHit]:
        root = ElementTree.fromstring(content)
        hits: list[SearchHit] = []
        for item in root.findall(".//item")[:10]:
            title = cls._clean_text(item.findtext("title") or "")
            url = (item.findtext("link") or "").strip()
            description = cls._clean_text(item.findtext("description") or "")
            parsed = urlparse(url)
            if title and parsed.scheme in {"http", "https"} and parsed.hostname:
                hits.append(SearchHit(title=title, url=url, description=description))
        return hits

    @classmethod
    def extract_company_names(cls, text: str) -> list[str]:
        """Extract enterprise legal names from official-directory text."""
        if not text:
            return []
        cleaned = BeautifulSoup(text, "html.parser").get_text("\n")
        names: list[str] = []
        seen: set[str] = set()
        for segment in re.split(r"[\s，,。；;、|]+", cleaned):
            segment = re.sub(r"^[0-9一二三四五六七八九十、.．（）()\-]+", "", segment)
            segment = re.sub(r"^(?:国企矩阵|监管企业|市属企业|企业名单)", "", segment)
            for match in _COMPANY_RE.finditer(segment):
                name = match.group(1).strip("-—：:（）()")
                if 4 <= len(name) <= 45 and name not in seen:
                    seen.add(name)
                    names.append(name)
        return names

    @staticmethod
    def _extract_keyword(query: dict) -> str:
        direction = str(query.get("direction") or "").strip()
        if direction:
            return direction
        skills = [str(item).strip() for item in query.get("skills", []) if item]
        return " ".join(skills[:3])

    @staticmethod
    def _clean_text(value: str) -> str:
        return " ".join(BeautifulSoup(value, "html.parser").get_text(" ").split())

    @classmethod
    def _clean_title(cls, title: str) -> str:
        cleaned = cls._clean_text(title)
        return re.sub(r"\s*[-_|—].*$", "", cleaned).strip() or "招聘公告"

    @staticmethod
    def _contains_recruitment_text(text: str) -> bool:
        lowered = text.lower()
        return any(word in lowered for word in _RECRUITMENT_WORDS)

    @staticmethod
    def _company_core(company: str) -> str:
        return re.sub(_COMPANY_SUFFIX + r"$", "", company).strip()

    @classmethod
    def _is_excluded_domain(cls, hostname: str) -> bool:
        hostname = hostname.lower().strip(".")
        return any(hostname == domain or hostname.endswith(f".{domain}") for domain in _EXCLUDED_DOMAINS)

    @classmethod
    def _is_government_source(cls, hit: SearchHit) -> bool:
        hostname = (urlparse(hit.url).hostname or "").lower()
        if hostname.endswith(".gov.cn") or hostname == "sasac.gov.cn":
            return True
        text = f"{hit.title} {hit.description}"
        return ("国资委" in text or "人民政府" in text) and not cls._is_excluded_domain(hostname)

    @classmethod
    def _official_candidate_score(cls, company: str, hit: SearchHit) -> int:
        hostname = (urlparse(hit.url).hostname or "").lower()
        if not hostname or cls._is_excluded_domain(hostname):
            return -100
        text = f"{hit.title} {hit.description}"
        core = cls._company_core(company)
        score = 0
        if len(core) >= 4 and core in text:
            score += 2
        if cls._contains_recruitment_text(f"{text} {hit.url}"):
            score += 2
        if any(part in hit.url.lower() for part in ("career", "job", "recruit", "hr")):
            score += 1
        if hostname.endswith(".gov.cn"):
            score += 1
        return score


async def search_official_soe_jobs(
    query: dict,
    *,
    progress_callback: ProgressCallback | None = None,
) -> OfficialSearchOutcome:
    """Convenience entry point used by the deterministic SearchAgent path."""
    return await OfficialSoeJobSearcher().search(query, progress_callback=progress_callback)
