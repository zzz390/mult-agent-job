"""Tests for bounded career-page discovery and Moka route handling."""

from unittest.mock import AsyncMock, patch

from job_agent_os.tools.search.career_site import (
    CareerPage,
    CareerSiteCrawler,
    _moka_jobs_url,
)


def test_moka_home_url_is_normalized_to_jobs_route():
    assert (
        _moka_jobs_url("https://app.mokahr.com/campus_apply/caih/6773#/home")
        == "https://app.mokahr.com/campus_apply/caih/6773#/jobs"
    )


async def test_crawler_follows_bridge_and_career_links_to_external_moka():
    crawler = CareerSiteCrawler(max_depth=3, max_pages=8, max_jobs=5)
    pages = {
        "https://example.com/": CareerPage(
            url="https://example.com/",
            title="示例集团",
            text="集团首页",
            links=(("关于我们", "https://example.com/about"),),
        ),
        "https://example.com/about": CareerPage(
            url="https://example.com/about",
            title="关于我们",
            text="了解集团",
            links=(("人才招聘", "https://example.com/about/talent"),),
        ),
        "https://example.com/about/talent": CareerPage(
            url="https://example.com/about/talent",
            title="诚聘英才",
            text="社会招聘 校园招聘",
            links=(
                (
                    "校园招聘",
                    "https://app.mokahr.com/campus_apply/example/123#/home",
                ),
            ),
        ),
    }

    async def fake_fetch(_client, url, _headers):
        return pages.get(url)

    crawler._fetch_static_page = AsyncMock(side_effect=fake_fetch)
    moka_job = {
        "title": "研发工程师",
        "company": "示例集团有限公司",
        "location": "北京",
        "raw_description": "负责研发",
        "source_url": "https://app.mokahr.com/campus_apply/example/123#/job/abc",
        "source_platform": "official_website",
    }
    with patch(
        "job_agent_os.tools.search.career_site.scrape_moka_jobs",
        new=AsyncMock(return_value=[moka_job]),
    ) as scrape:
        jobs = await crawler.crawl(
            ["https://example.com/"],
            company="示例集团有限公司",
            region="北京",
            keyword="研发",
        )

    assert jobs == [moka_job]
    scrape.assert_awaited_once()
    assert scrape.await_args.args[0].endswith("#/home")


async def test_crawler_keeps_static_job_pages_as_fallback():
    crawler = CareerSiteCrawler(max_depth=3, max_pages=4, max_jobs=5)
    pages = {
        "https://example.com/career": CareerPage(
            url="https://example.com/career",
            title="人才招聘",
            text="查看岗位",
            links=(("Python工程师", "https://example.com/career/python"),),
        ),
        "https://example.com/career/python": CareerPage(
            url="https://example.com/career/python",
            title="Python工程师",
            text="岗位招聘：负责数据平台开发",
            links=(),
        ),
    }

    async def fake_fetch(_client, url, _headers):
        return pages.get(url)

    crawler._fetch_static_page = AsyncMock(side_effect=fake_fetch)
    jobs = await crawler.crawl(
        ["https://example.com/career"],
        company="示例集团有限公司",
        region="上海",
        keyword="Python",
    )

    assert len(jobs) == 1
    assert jobs[0]["title"] == "Python工程师"
    assert jobs[0]["source_url"] == "https://example.com/career/python"
