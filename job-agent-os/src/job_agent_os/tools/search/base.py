"""Platform adapter abstract base class with anti-detection utilities.

Issue #3 fixes provided here for all platform adapters:
- Randomized User-Agent pool (a single hardcoded UA gets flagged quickly)
- Optional proxy rotation via PROXY_POOL / JOB_PROXY_POOL env var
- Cookie injection from env (pre-logged-in sessions for sites like BOSS)
- Optional Playwright rendering for JS-heavy pages (falls back to httpx)
- Process-wide per-platform rate limiting shared across adapter instances
"""

import asyncio
import json
import logging
import os
import random
import time
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, ClassVar

import httpx

logger = logging.getLogger(__name__)

# Realistic desktop browser UA pool
UA_POOL: list[str] = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
]


def _load_proxy_pool() -> list[str]:
    """Load proxy pool from the JOB_PROXY_POOL env var (comma-separated URLs).

    Example: JOB_PROXY_POOL="http://user:pass@p1:8080,http://p2:3128"
    """
    raw = os.environ.get("JOB_PROXY_POOL", "").strip()
    if not raw:
        return []
    return [p.strip() for p in raw.split(",") if p.strip()]


PROXY_POOL: list[str] = _load_proxy_pool()


class PlatformAdapter(ABC):
    """Abstract base class for job platform adapters.

    Each platform (BOSS, Niuke, Guopin, etc.) implements this interface.
    """

    platform_name: str = "base"
    rate_limit: int = 10  # requests per minute
    # Subclasses set True when the platform renders job lists via JS
    render_with_playwright: bool = False
    # CSS selector to wait for when rendering with Playwright (optional)
    playwright_wait_selector: str | None = None

    # --- Process-wide request coordination (shared across instances) ---
    _global_last_request: ClassVar[dict[str, float]] = {}
    _rate_locks: ClassVar[dict[str, asyncio.Lock]] = {}
    # A rate limiter alone spaces out request *starts*, but a slow browser
    # render can still overlap with a second request to the same platform.
    # Keep one in-flight search per platform/account/IP to avoid creating that
    # burst while allowing searches against different platforms to run together.
    _search_locks: ClassVar[dict[str, asyncio.Lock]] = {}

    def __init__(self) -> None:
        # Kept for backward compatibility; authoritative timing is global
        self._last_request_time: float = 0
        self._min_interval: float = 60.0 / max(self.rate_limit, 1)

    @classmethod
    def _get_rate_lock(cls) -> asyncio.Lock:
        """Return the process-wide rate-limit lock for this platform."""
        lock = PlatformAdapter._rate_locks.get(cls.platform_name)
        if lock is None:
            lock = asyncio.Lock()
            PlatformAdapter._rate_locks[cls.platform_name] = lock
        return lock

    @classmethod
    def _get_search_lock(cls) -> asyncio.Lock:
        """Return the process-wide single-flight lock for this platform."""
        lock = PlatformAdapter._search_locks.get(cls.platform_name)
        if lock is None:
            lock = asyncio.Lock()
            PlatformAdapter._search_locks[cls.platform_name] = lock
        return lock

    async def _rate_limit_wait(self) -> None:
        """Wait to respect the per-platform rate limit (global across instances)."""
        lock = self._get_rate_lock()
        async with lock:
            last = self._global_last_request.get(self.platform_name, 0.0)
            elapsed = time.time() - last
            if elapsed < self._min_interval:
                await asyncio.sleep(self._min_interval - elapsed)
            self._global_last_request[self.platform_name] = time.time()
            self._last_request_time = self._global_last_request[self.platform_name]

    @asynccontextmanager
    async def _single_flight_search(self) -> AsyncIterator[None]:
        """Serialize searches to one platform without blocking other platforms.

        Adapters use this around their complete ``search`` operation.  That
        means an explicit BOSS + Guopin + Niuke request can fan out across the
        three independent platforms, while two BOSS searches never overlap
        (even when the first Playwright render is slow).  The existing per
        request rate limiter remains responsible for the 5-rpm spacing.
        """
        async with self._get_search_lock():
            yield

    # --- Fingerprint randomization ---

    def _random_ua(self) -> str:
        return random.choice(UA_POOL)

    def _random_proxy(self) -> str | None:
        return random.choice(PROXY_POOL) if PROXY_POOL else None

    # --- Cookie injection (pre-authenticated sessions) ---

    def _load_cookies(self) -> list[dict]:
        """Load cookies for this platform from env config.

        Reads, in order:
        1. {PLATFORM}_COOKIES      — JSON array string, e.g. [{"name":..., "value":..., "domain":...}]
        2. {PLATFORM}_COOKIES_FILE — path to a JSON file with the same structure

        Returns an empty list when nothing is configured.
        """
        env_key = self.platform_name.upper()
        raw = os.environ.get(f"{env_key}_COOKIES", "").strip()
        if not raw:
            file_path = os.environ.get(f"{env_key}_COOKIES_FILE", "").strip()
            if file_path and Path(file_path).exists():
                try:
                    raw = Path(file_path).read_text(encoding="utf-8")
                except OSError as e:
                    logger.warning("Failed to read cookies file %s: %s", file_path, e)
                    return []
        if not raw:
            return []
        try:
            cookies = json.loads(raw)
            if isinstance(cookies, list):
                return [c for c in cookies if isinstance(c, dict) and c.get("name")]
        except json.JSONDecodeError:
            logger.warning("Invalid %s cookies config, ignoring", env_key)
        return []

    # --- Fetching helpers ---

    def _get_headers(self) -> dict[str, str]:
        """Browser-like request headers with a randomized User-Agent."""
        return {
            "User-Agent": self._random_ua(),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }

    def _httpx_client_kwargs(self) -> dict[str, Any]:
        """Common httpx client kwargs with TLS verification always enabled."""
        kwargs: dict[str, Any] = {
            "timeout": 15.0,
            "verify": True,
            "follow_redirects": True,
        }
        proxy = self._random_proxy()
        if proxy:
            kwargs["proxy"] = proxy
        return kwargs

    async def _fetch_page(self, url: str, extra_headers: dict[str, str] | None = None) -> str:
        """Fetch a page, preferring Playwright for JS-rendered platforms.

        Falls back to plain httpx when Playwright is disabled, unavailable,
        or fails — so the adapter keeps working (with degraded results)
        even without a browser installation.
        """
        if self.render_with_playwright:
            try:
                return await self._fetch_with_playwright(url)
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    "[%s] Playwright fetch failed (%s); falling back to httpx",
                    self.platform_name, e,
                )

        headers = self._get_headers()
        if extra_headers:
            headers.update(extra_headers)
        async with httpx.AsyncClient(**self._httpx_client_kwargs()) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.text

    async def _fetch_with_playwright(self, url: str) -> str:
        """Render the page with headless Chromium (random UA, cookies, proxy, stealth)."""
        from playwright.async_api import async_playwright

        proxy = self._random_proxy()
        async with async_playwright() as p:
            launch_kwargs: dict[str, Any] = {
                "headless": True,
                "args": [
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                ],
            }
            if proxy:
                launch_kwargs["proxy"] = {"server": proxy}
            browser = await p.chromium.launch(**launch_kwargs)
            try:
                context = await browser.new_context(
                    user_agent=self._random_ua(),
                    locale="zh-CN",
                    viewport={"width": 1440, "height": 900},
                )
                # Remove navigator.webdriver detection flag
                await context.add_init_script(
                    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
                )
                cookies = self._load_cookies()
                if cookies:
                    await context.add_cookies(cookies)
                page = await context.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                if self.playwright_wait_selector:
                    try:
                        await page.wait_for_selector(
                            self.playwright_wait_selector, timeout=8000
                        )
                    except Exception:  # noqa: BLE001
                        # Selector may legitimately be absent (zero results)
                        await page.wait_for_timeout(1500)
                return await page.content()
            finally:
                await browser.close()

    def _extract_keyword(self, query: dict) -> str:
        """Extract search keyword with priority: direction -> keywords -> skills.

        Args:
            query: Query dictionary (from JobQuery or raw dict)

        Returns:
            Extracted keyword string
        """
        if query.get("direction"):
            return str(query["direction"]).strip()
        keywords = query.get("keywords")
        if keywords and isinstance(keywords, list):
            return " ".join(str(k) for k in keywords if k).strip()
        skills = query.get("skills")
        if skills and isinstance(skills, list):
            return " ".join(str(s) for s in skills if s).strip()
        return ""

    # --- Abstract interface ---

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
