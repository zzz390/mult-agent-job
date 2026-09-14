"""Tests for the city SOE directory -> official career site search path."""

from unittest.mock import AsyncMock, patch
from urllib.parse import quote

from job_agent_os.tools.search.official import (
    OfficialSoeJobSearcher,
    SearchHit,
)


def test_extracts_company_names_from_sasac_directory_text():
    text = """
    国企矩阵
    郑州产业投资集团有限公司
    郑州交通发展投资集团有限公司
    中原环保股份有限公司
    """

    names = OfficialSoeJobSearcher.extract_company_names(text)

    assert names == [
        "郑州产业投资集团有限公司",
        "郑州交通发展投资集团有限公司",
        "中原环保股份有限公司",
    ]


def test_parses_lightweight_search_html_and_unwraps_target_url():
    target = "https://gzw.zhengzhou.gov.cn/gqjz/index.jhtml"
    html = f"""
    <div class="result">
      <a class="result__a" href="//duckduckgo.com/l/?uddg={quote(target)}">
        国企矩阵 - 郑州市国资委
      </a>
      <a class="result__snippet">郑州产业投资集团有限公司</a>
    </div>
    """

    hits = OfficialSoeJobSearcher._parse_search_html(html)

    assert len(hits) == 1
    assert hits[0].url == target
    assert "郑州产业投资集团有限公司" in hits[0].description


async def test_two_stage_search_returns_only_official_domain_jobs():
    searcher = OfficialSoeJobSearcher(max_companies=1)
    government_hit = SearchHit(
        title="国企矩阵 - 郑州市国资委",
        url="https://gzw.zhengzhou.gov.cn/gqjz/index.jhtml",
        description="郑州产业投资集团有限公司",
    )
    third_party_hit = SearchHit(
        title="郑州产业投资集团有限公司招聘",
        url="https://www.zhipin.com/gongsi/example.html",
        description="Python岗位",
    )
    official_hit = SearchHit(
        title="社会招聘 - 郑州产业投资集团有限公司",
        url="https://www.zzci.cn/career/2026-python.html",
        description="Python工程师招聘公告",
    )

    async def fake_search(query: str):
        if "国资委" in query or "国企矩阵" in query:
            return [government_hit]
        return [third_party_hit, official_hit]

    searcher._search_web = AsyncMock(side_effect=fake_search)
    with (
        patch(
            "job_agent_os.tools.search.official.CareerSiteCrawler.crawl",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "job_agent_os.tools.search.official.fetch_and_extract_html",
            new=AsyncMock(return_value="Python工程师招聘，负责平台开发"),
        ),
    ):
        outcome = await searcher.search(
            {
                "region": ["郑州"],
                "direction": "Python",
                "company_type": ["国企"],
            }
        )

    assert outcome.companies == ["郑州产业投资集团有限公司"]
    assert len(outcome.jobs) == 1
    assert outcome.jobs[0]["source_url"].startswith("https://www.zzci.cn/")
    assert outcome.jobs[0]["source_platform"] == "official_website"


async def test_missing_region_does_not_guess_a_city():
    outcome = await OfficialSoeJobSearcher().search({"direction": "Java"})

    assert outcome.jobs == []
    assert "城市或省份" in outcome.errors[0]


async def test_official_search_reports_safe_aggregate_progress():
    searcher = OfficialSoeJobSearcher(max_companies=1)
    searcher._discover_soes = AsyncMock(return_value=["郑州产业投资集团有限公司"])
    searcher._search_company_jobs = AsyncMock(
        return_value=[
            {
                "title": "Python工程师",
                "company": "郑州产业投资集团有限公司",
                "source_url": "https://www.zzci.cn/career/secret-token.html",
            }
        ]
    )
    events: list[dict] = []

    async def collect_progress(**event):
        events.append(event)

    outcome = await searcher.search(
        {"region": ["郑州"], "direction": "Python"},
        progress_callback=collect_progress,
    )

    assert len(outcome.jobs) == 1
    assert events[0]["activity_message"] == "正在查找官方国企名录"
    assert any("开始查询官网招聘信息" in event["activity_message"] for event in events)
    assert any("已完成 1/1 家企业" in event["activity_message"] for event in events)
    assert events[-1]["items_found"] == 1
    assert all("https://" not in event["activity_message"] for event in events)
