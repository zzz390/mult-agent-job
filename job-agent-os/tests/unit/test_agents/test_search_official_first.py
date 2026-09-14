"""SearchAgent ordering tests for official-first SOE search."""

from unittest.mock import AsyncMock, patch

from job_agent_os.agents.base import BaseAgent
from job_agent_os.agents.search_agent import SearchAgent
from job_agent_os.tools.search.official import OfficialSearchOutcome


async def test_default_soe_search_stops_after_verified_official_result():
    agent = SearchAgent()
    official_job = {
        "title": "信息化岗位招聘公告",
        "company": "郑州产业投资集团有限公司",
        "company_type": "国企",
        "source_url": "https://www.zzci.cn/career/1.html",
        "source_platform": "official_website",
    }
    agent._official_first_search = AsyncMock(
        return_value={
            "current_phase": "search",
            "search_results": [official_job],
            "search_errors": [],
            "platforms_searched": ["official_soe_web"],
            "token_usage": {"total_tokens": 0},
        }
    )
    agent._persist_verified_results = AsyncMock(side_effect=lambda result: result)
    agent._maybe_parse_inline = AsyncMock(side_effect=lambda _state, result: result)

    with patch.object(
        BaseAgent,
        "execute",
        new=AsyncMock(side_effect=AssertionError("third party should not run")),
    ):
        result = await agent.execute(
            {
                "job_query": {
                    "region": ["郑州"],
                    "company_type": ["国企"],
                    "direction": "Python",
                }
            }
        )

    assert result["search_results"] == [official_job]
    assert result["platforms_searched"] == ["official_soe_web"]


async def test_default_search_uses_auxiliary_only_when_official_is_empty():
    agent = SearchAgent()
    agent._official_first_search = AsyncMock(
        return_value={
            "current_phase": "search",
            "search_results": [],
            "search_errors": [],
            "platforms_searched": ["official_soe_web"],
            "token_usage": {"total_tokens": 0},
        }
    )
    agent._default_auxiliary_search = AsyncMock(
        return_value={
            "current_phase": "search",
            "search_results": [
                {
                    "title": "后端开发",
                    "company": "某国企",
                    "source_url": "https://www.iguopin.com/job/detail?id=1",
                }
            ],
            "search_errors": [],
            "platforms_searched": ["guopin"],
            "token_usage": {"total_tokens": 0},
        }
    )
    agent._persist_verified_results = AsyncMock(side_effect=lambda result: result)
    agent._maybe_parse_inline = AsyncMock(side_effect=lambda _state, result: result)

    result = await agent.execute({"job_query": {"region": ["郑州"], "direction": "Python"}})

    agent._default_auxiliary_search.assert_awaited_once()
    assert result["platforms_searched"] == ["official_soe_web", "guopin"]


async def test_official_progress_callback_is_forwarded_to_session_store():
    agent = SearchAgent()

    async def fake_official_search(_query, *, progress_callback):
        await progress_callback(
            activity_message="正在查找官方国企名录",
            items_found=0,
            items_saved=0,
        )
        return OfficialSearchOutcome()

    with (
        patch(
            "job_agent_os.tools.search.official.search_official_soe_jobs",
            new=AsyncMock(side_effect=fake_official_search),
        ),
        patch(
            "job_agent_os.services.session_progress.publish_search_progress",
            new=AsyncMock(return_value=True),
        ) as publish_progress,
    ):
        result = await agent._official_first_search(
            {"session_id": "session-1", "job_query": {"region": ["郑州"]}}
        )

    assert result["search_results"] == []
    publish_progress.assert_awaited_once_with(
        "session-1",
        activity_message="正在查找官方国企名录",
        items_found=0,
        items_saved=0,
    )
