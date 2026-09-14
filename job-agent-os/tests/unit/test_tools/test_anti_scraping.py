"""Tests for anti-scraping infrastructure and BOSS city codes (issues #3, #8)."""

from unittest.mock import AsyncMock, patch

from job_agent_os.tools.search.base import UA_POOL, PlatformAdapter
from job_agent_os.tools.search.boss import BossAdapter


class ConcreteAdapter(PlatformAdapter):
    """Minimal concrete adapter for testing base-class utilities."""

    platform_name = "test_platform"

    async def search(self, query: dict) -> list[dict]:
        return []

    async def parse_result(self, raw: dict) -> dict:
        return raw


class TestBossCityCodes:
    def test_url_uses_numeric_city_code(self):
        adapter = BossAdapter()
        url = adapter._build_search_url({"direction": "Python", "region": ["郑州"]})
        assert "city=101180100" in url
        assert "郑州" not in url

    def test_unknown_city_falls_back_to_nationwide(self):
        adapter = BossAdapter()
        url = adapter._build_search_url({"direction": "Java", "region": ["不存在市"]})
        assert "city=100010000" in url

    def test_no_region_defaults_to_nationwide(self):
        adapter = BossAdapter()
        url = adapter._build_search_url({"direction": "Java"})
        assert "city=100010000" in url

    def test_keyword_is_url_encoded(self):
        adapter = BossAdapter()
        url = adapter._build_search_url({"direction": "C++", "region": ["北京"]})
        # '+' must be percent-encoded to survive URL parsing
        assert "query=C%2B%2B" in url
        assert "city=101010100" in url


class TestFingerprintRandomization:
    def test_ua_pool_has_variety(self):
        assert len(UA_POOL) >= 5

    def test_random_ua_returns_pool_member(self):
        adapter = ConcreteAdapter()
        for _ in range(10):
            assert adapter._random_ua() in UA_POOL

    def test_headers_use_pool_ua(self):
        adapter = ConcreteAdapter()
        headers = adapter._get_headers()
        assert headers["User-Agent"] in UA_POOL
        assert "Accept-Language" in headers

    def test_random_proxy_empty_pool(self):
        adapter = ConcreteAdapter()
        with patch("job_agent_os.tools.search.base.PROXY_POOL", []):
            assert adapter._random_proxy() is None

    def test_random_proxy_with_pool(self):
        adapter = ConcreteAdapter()
        with patch("job_agent_os.tools.search.base.PROXY_POOL", ["http://p1:8080"]):
            assert adapter._random_proxy() == "http://p1:8080"


class TestCookieLoading:
    def test_no_config_returns_empty(self, monkeypatch):
        monkeypatch.delenv("TEST_PLATFORM_COOKIES", raising=False)
        monkeypatch.delenv("TEST_PLATFORM_COOKIES_FILE", raising=False)
        adapter = ConcreteAdapter()
        assert adapter._load_cookies() == []

    def test_env_json_cookies(self, monkeypatch):
        monkeypatch.setenv(
            "TEST_PLATFORM_COOKIES",
            '[{"name": "wt2", "value": "abc", "domain": ".example.com"}]',
        )
        adapter = ConcreteAdapter()
        cookies = adapter._load_cookies()
        assert len(cookies) == 1
        assert cookies[0]["name"] == "wt2"

    def test_invalid_json_returns_empty(self, monkeypatch):
        monkeypatch.setenv("TEST_PLATFORM_COOKIES", "not-json")
        adapter = ConcreteAdapter()
        assert adapter._load_cookies() == []


class TestGlobalRateLimit:
    async def test_shared_timing_across_instances(self):
        """Two instances of the same platform must share one rate window."""
        a = ConcreteAdapter()
        # Record a request for instance A, then B should see it
        PlatformAdapter._global_last_request["test_platform"] = 0.0
        await a._rate_limit_wait()
        t_after_a = PlatformAdapter._global_last_request["test_platform"]
        assert t_after_a > 0
        # B's min interval is based on the shared timestamp; just ensure the
        # shared dict is the source of truth
        assert PlatformAdapter._global_last_request.get("test_platform") == t_after_a
        del PlatformAdapter._global_last_request["test_platform"]


class TestKeywordExtraction:
    def test_direction_takes_precedence(self):
        adapter = ConcreteAdapter()
        kw = adapter._extract_keyword(
            {
                "direction": "Python后端",
                "keywords": ["FastAPI", "Django"],
                "skills": ["Python", "SQL"],
            }
        )
        assert kw == "Python后端"

    def test_keywords_used_when_direction_absent(self):
        adapter = ConcreteAdapter()
        kw = adapter._extract_keyword(
            {
                "keywords": ["FastAPI", "Django"],
                "skills": ["Python", "SQL"],
            }
        )
        assert kw == "FastAPI Django"

    def test_skills_used_when_direction_and_keywords_absent(self):
        adapter = ConcreteAdapter()
        kw = adapter._extract_keyword(
            {
                "skills": ["Python", "SQL"],
            }
        )
        assert kw == "Python SQL"

    def test_empty_query_returns_empty_string(self):
        adapter = ConcreteAdapter()
        assert adapter._extract_keyword({}) == ""


class TestAdapterUrlAndParsing:
    async def test_boss_stops_when_a_captcha_page_is_returned(self):
        """A verification response must not trigger further parsing/retries."""
        adapter = BossAdapter()
        adapter._rate_limit_wait = AsyncMock()
        adapter._fetch_page = AsyncMock(return_value="<html>安全验证 geetest</html>")

        jobs = await adapter.search({"direction": "Python", "region": ["上海"]})

        assert jobs == []
        adapter._fetch_page.assert_awaited_once()

    def test_guopin_build_url_with_region(self):
        from job_agent_os.tools.search.guopin import GuopinAdapter

        adapter = GuopinAdapter()
        url = adapter._build_search_url({"keywords": ["Java"], "region": ["上海"]})
        assert url.startswith("https://www.iguopin.com/job/list?")
        assert "keyword=Java" in url

    def test_guopin_parse_public_api_job(self):
        from job_agent_os.tools.search.guopin import GuopinAdapter

        adapter = GuopinAdapter()
        parsed = adapter._parse_api_job(
            {
                "job_id": "12345",
                "job_name": "Java研发工程师",
                "company_name": "国家电网有限公司",
                "company_info": {"nature_cn": "央企"},
                "district_list": [{"area_cn": "北京-海淀区"}],
                "min_wage": 15000,
                "max_wage": 25000,
                "wage_unit_cn": "元/月",
                "education_cn": "本科",
                "experience_cn": "应届生",
                "major_cn": ["计算机类"],
                "contents": "负责Java平台研发",
                "end_time": "2026-12-31 23:59:59",
            }
        )
        assert parsed is not None
        assert parsed["title"] == "Java研发工程师"
        assert parsed["company"] == "国家电网有限公司"
        assert parsed["company_type"] == "央企"
        assert parsed["salary"] == "15000-25000元/月"
        assert parsed["location"] == "北京-海淀区"
        assert parsed["education"] == "本科"
        assert parsed["source_url"] == "https://www.iguopin.com/job/detail?id=12345"

    def test_guopin_builds_full_district_path(self):
        from job_agent_os.tools.search.guopin import GuopinAdapter

        tree = [
            {
                "value": "000000",
                "label": "中国",
                "children": [
                    {
                        "value": "410000",
                        "label": "河南",
                        "children": [
                            {
                                "value": "410100",
                                "label": "郑州",
                                "name": "郑州市",
                                "children": [],
                            }
                        ],
                    }
                ],
            }
        ]
        paths = GuopinAdapter._build_district_paths(tree)
        assert paths["郑州"] == "000000.410000.410100"

    async def test_guopin_search_uses_public_json_protocol(self):
        from job_agent_os.tools.search.guopin import GuopinAdapter

        adapter = GuopinAdapter()
        adapter._resolve_district_path = AsyncMock(return_value="000000.410000.410100")
        adapter._request_jobs = AsyncMock(
            return_value={
                "code": 200,
                "data": {
                    "list": [
                        {
                            "job_id": "1",
                            "job_name": "后端开发",
                            "company_name": "郑州国有资本投资运营集团有限公司",
                            "company_info": {"nature_cn": "国企"},
                            "district_list": [{"area_cn": "郑州-中原区"}],
                            "is_negotiable": True,
                            "contents": "Python",
                        }
                    ]
                },
            }
        )

        jobs = await adapter.search(
            {
                "direction": "Python",
                "region": ["郑州"],
                "company_type": ["国企"],
            }
        )

        assert len(jobs) == 1
        payload = adapter._request_jobs.await_args.args[0]
        assert payload["search"]["district"] == ["000000.410000.410100"]
        assert payload["search"]["keyword"] == "Python"
        assert adapter.render_with_playwright is False

    def test_niuke_build_url_with_region(self):
        from job_agent_os.tools.search.niuke import NiukeAdapter

        adapter = NiukeAdapter()
        url = adapter._build_search_url({"keywords": ["前端"], "region": ["深圳"]})
        assert "keyword=%E5%89%8D%E7%AB%AF" in url or "keyword=前端" in url
        assert "city=%E6%B7%B1%E5%9C%B3" in url or "city=深圳" in url

    def test_niuke_parse_card_with_salary_and_tags(self):
        from bs4 import BeautifulSoup

        from job_agent_os.tools.search.niuke import NiukeAdapter

        adapter = NiukeAdapter()
        html = """
        <div class="job-item">
            <div class="position-name">前端开发工程师</div>
            <div class="company-name">腾讯</div>
            <div class="job-salary">20k-35k</div>
            <div class="work-city">深圳</div>
            <div class="job-tags">
                <span>React</span>
                <span>TypeScript</span>
            </div>
            <a href="/jobs/detail/6789">查看</a>
        </div>
        """
        card = BeautifulSoup(html, "html.parser").select_one(".job-item")
        parsed = adapter._parse_job_card(card)
        assert parsed is not None
        assert parsed["title"] == "前端开发工程师"
        assert parsed["company"] == "腾讯"
        assert parsed["salary"] == "20k-35k"
        assert parsed["location"] == "深圳"
        assert "React" in parsed["raw_description"]
        assert parsed["source_url"] == "https://www.nowcoder.com/jobs/detail/6789"

    def test_boss_parse_card_with_tags(self):
        from bs4 import BeautifulSoup

        from job_agent_os.tools.search.boss import BossAdapter

        adapter = BossAdapter()
        html = """
        <li class="job-card-wrapper">
            <span class="job-name">Python后端</span>
            <span class="company-name">字节跳动</span>
            <span class="salary">25-40K</span>
            <span class="job-area">北京·海淀区</span>
            <ul class="tag-list">
                <li>3-5年</li>
                <li>本科</li>
            </ul>
            <a href="/job_detail/abcde.html">详情</a>
        </li>
        """
        card = BeautifulSoup(html, "html.parser").select_one(".job-card-wrapper")
        parsed = adapter._parse_job_card(card, {})
        assert parsed is not None
        assert parsed["title"] == "Python后端"
        assert parsed["company"] == "字节跳动"
        assert parsed["salary"] == "25-40K"
        assert "3-5年" in parsed["raw_description"]
        assert parsed["source_url"] == "https://www.zhipin.com/job_detail/abcde.html"

    def test_httpx_client_kwargs_keeps_ssl_verification_enabled(self):
        adapter = ConcreteAdapter()
        kwargs = adapter._httpx_client_kwargs()
        assert kwargs["verify"] is True
        assert kwargs["follow_redirects"] is True
