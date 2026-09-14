"""Safety and fan-out tests for explicit multi-platform job search."""

import asyncio
from unittest.mock import AsyncMock, patch

from job_agent_os.agents.base import BaseAgent
from job_agent_os.agents.search_agent import SearchAgent
from job_agent_os.tools.search.base import PlatformAdapter
from job_agent_os.tools.search.boss import BossAdapter
from job_agent_os.tools.search.guopin import GuopinAdapter
from job_agent_os.tools.search.niuke import NiukeAdapter


async def test_same_platform_searches_are_single_flight():
    """A slow BOSS search must prevent a second BOSS render from overlapping."""
    PlatformAdapter._search_locks.pop("boss", None)
    active = {"current": 0, "maximum": 0}
    first_entered = asyncio.Event()
    release = asyncio.Event()

    async def slow_search_once(_self, _query):
        active["current"] += 1
        active["maximum"] = max(active["maximum"], active["current"])
        first_entered.set()
        await release.wait()
        active["current"] -= 1
        return []

    try:
        with patch.object(BossAdapter, "_search_once", new=slow_search_once):
            first = asyncio.create_task(BossAdapter().search({}))
            await first_entered.wait()
            second = asyncio.create_task(BossAdapter().search({}))
            await asyncio.sleep(0)

            assert active["maximum"] == 1
            release.set()
            await asyncio.gather(first, second)
    finally:
        PlatformAdapter._search_locks.pop("boss", None)


async def test_explicit_platforms_search_in_parallel_and_merge_results():
    """Independent platforms should fan out, while result order stays stable."""
    active = {"current": 0, "maximum": 0}
    all_started = asyncio.Event()
    release = asyncio.Event()

    async def slow_search(self, _query):
        active["current"] += 1
        active["maximum"] = max(active["maximum"], active["current"])
        if active["current"] == 3:
            all_started.set()
        await release.wait()
        active["current"] -= 1
        return [
            {
                "title": f"{self.platform_name} 岗位",
                "company": f"{self.platform_name} 公司",
                "source_url": f"https://{self.platform_name}.example/jobs/1",
                "source_platform": self.platform_name,
            }
        ]

    agent = SearchAgent()
    state = {
        "job_query": {"direction": "Python", "region": ["上海"]},
        "requested_platforms": ["boss", "guopin", "niuke"],
    }
    try:
        with (
            patch.object(BossAdapter, "search", new=slow_search),
            patch.object(GuopinAdapter, "search", new=slow_search),
            patch.object(NiukeAdapter, "search", new=slow_search),
        ):
            task = asyncio.create_task(agent._search_requested_platforms(state, ["boss", "guopin", "niuke"]))
            await asyncio.wait_for(all_started.wait(), timeout=1)
            assert active["maximum"] == 3
            release.set()
            result = await task
    finally:
        release.set()

    assert result["platforms_searched"] == ["boss", "guopin", "niuke"]
    assert [job["source_platform"] for job in result["search_results"]] == [
        "boss",
        "guopin",
        "niuke",
    ]


async def test_execute_uses_parallel_path_only_for_multiple_explicit_platforms():
    """Multi-platform selections bypass the serial ReAct tool-call loop."""
    agent = SearchAgent()
    parallel_result = {
        "current_phase": "search",
        "search_results": [],
        "search_errors": [],
        "platforms_searched": ["boss", "guopin"],
    }
    agent._search_requested_platforms = AsyncMock(return_value=parallel_result)
    agent._persist_verified_results = AsyncMock(side_effect=lambda result: result)
    agent._maybe_parse_inline = AsyncMock(side_effect=lambda _state, result: result)

    with patch.object(
        BaseAgent,
        "execute",
        new=AsyncMock(side_effect=AssertionError("serial ReAct path should not run")),
    ):
        result = await agent.execute(
            {
                "job_query": {"direction": "Python"},
                "requested_platforms": ["BOSS直聘", "国聘"],
            }
        )

    assert result is parallel_result
    agent._search_requested_platforms.assert_awaited_once_with(
        {
            "job_query": {"direction": "Python"},
            "requested_platforms": ["BOSS直聘", "国聘"],
        },
        ["boss", "guopin"],
    )
