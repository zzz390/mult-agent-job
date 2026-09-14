"""Tests for agent consolidation and token usage reducer (issues #2, #11)."""

from unittest.mock import AsyncMock, patch

from job_agent_os.agents.interview_agent import InterviewAgent
from job_agent_os.agents.search_agent import SearchAgent
from job_agent_os.graph.state import add_token_usage


class TestTokenUsageReducer:
    def test_accumulates(self):
        a = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15, "cost_usd": 0.1}
        b = {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5, "cost_usd": 0.05}
        merged = add_token_usage(a, b)
        assert merged["prompt_tokens"] == 13
        assert merged["completion_tokens"] == 7
        assert merged["total_tokens"] == 20
        assert merged["cost_usd"] == 0.15000000000000002 or abs(merged["cost_usd"] - 0.15) < 1e-9

    def test_none_inputs(self):
        merged = add_token_usage(None, None)
        assert merged["total_tokens"] == 0

    def test_one_sided(self):
        merged = add_token_usage(None, {"total_tokens": 7})
        assert merged["total_tokens"] == 7


class TestInterviewTrackerMerge:
    def setup_method(self):
        self.agent = InterviewAgent()

    def test_create_applications_from_matches(self):
        state = {
            "match_results": [
                {
                    "job": {"id": "j1", "title": "后端", "company": "A"},
                    "overall_score": 90,
                    "recommendation_reason": "fit",
                },
                {
                    "job": {"id": "j2", "title": "前端", "company": "B"},
                    "overall_score": 80,
                    "recommendation_reason": "ok",
                },
            ]
        }
        apps = self.agent._create_applications(state)
        assert len(apps) == 2
        assert apps[0]["job_id"] == "j1"
        assert apps[0]["status"] == "pending"
        assert apps[0]["match_score"] == 90

    def test_applications_capped_at_five(self):
        state = {"match_results": [{"job": {"id": f"j{i}", "title": f"t{i}"}, "overall_score": 50} for i in range(10)]}
        assert len(self.agent._create_applications(state)) == 5

    def test_kanban_state_shape(self):
        apps = [{"job_id": "j1"}]
        kanban = InterviewAgent._build_kanban_state(apps)
        assert kanban["pending"] == apps
        for col in ("applied", "round1", "offer", "rejected"):
            assert kanban[col] == []

    async def test_execute_embeds_tracker(self):
        """execute() must add applications without a separate tracker hop."""
        state = {"match_results": [{"job": {"id": "j1", "title": "后端", "company": "A"}, "overall_score": 90}]}
        with patch(
            "job_agent_os.agents.interview_agent.generate_tech_questions",
            new=AsyncMock(return_value=[{"id": 99, "type": "technical"}]),
        ), patch(
            "job_agent_os.agents.interview_agent.generate_behavior_questions",
            new=AsyncMock(return_value=[]),
        ):
            result = await self.agent.execute(state)

        assert result["interview_questions"] == [{"id": 1, "type": "technical"}]
        assert len(result["applications"]) == 1
        assert "kanban_state" in result
        assert "tracker" in result.get("agent_execution_order", [])

    async def test_execute_skips_tracker_when_applications_exist(self):
        state = {
            "match_results": [{"job": {"id": "j1"}, "overall_score": 90}],
            "applications": [{"job_id": "already"}],
        }
        with patch(
            "job_agent_os.agents.interview_agent.generate_tech_questions",
            new=AsyncMock(return_value=[]),
        ), patch(
            "job_agent_os.agents.interview_agent.generate_behavior_questions",
            new=AsyncMock(return_value=[]),
        ):
            result = await self.agent.execute(state)
        assert "applications" not in result

    def test_approved_recommendations_are_the_only_application_targets(self):
        state = {
            "match_results": [
                {"job": {"id": "original", "title": "原岗位"}, "overall_score": 90}
            ],
            "approved_recommendations": [
                {"job": {"id": "approved", "title": "已确认岗位"}, "overall_score": 80}
            ],
        }

        applications = self.agent._create_applications(state)

        assert [item["job_id"] for item in applications] == ["approved"]


class TestSearchInlineParse:
    def setup_method(self):
        self.agent = SearchAgent()

    async def test_inline_parse_structures_results(self):
        state: dict = {}
        result = {
            "search_results": [{"title": "t", "company": "c"}],
            "search_errors": [],
        }
        with patch(
            "job_agent_os.tools.parse.jd_structurer.structure_jds_parallel",
            new=AsyncMock(return_value=([{"title": "t", "parse_confidence": 0.9}], [])),
        ):
            out = await self.agent._maybe_parse_inline(state, result)

        assert out["parsed_jobs"] == [{"title": "t", "parse_confidence": 0.9}]
        assert out["parse_failures"] == []

    async def test_inline_parse_skipped_when_already_parsed(self):
        state: dict = {"parsed_jobs": [{"title": "existing"}]}
        result = {"search_results": [{"title": "t"}]}
        out = await self.agent._maybe_parse_inline(state, result)
        assert "parsed_jobs" not in out

    async def test_inline_parse_skipped_without_results(self):
        out = await self.agent._maybe_parse_inline({}, {"search_results": []})
        assert "parsed_jobs" not in out

    async def test_inline_parse_failure_keeps_passthrough_jobs(self):
        result = {
            "search_results": [
                {
                    "title": "后端工程师",
                    "company": "示例公司",
                    "source_url": "https://example.com/jobs/1",
                }
            ],
            "search_errors": [],
        }
        with patch(
            "job_agent_os.tools.parse.jd_structurer.structure_jds_parallel",
            new=AsyncMock(side_effect=TimeoutError("parse timeout")),
        ):
            out = await self.agent._maybe_parse_inline({}, result)

        assert out["parsed_jobs"][0]["title"] == "后端工程师"
        assert out["parsed_jobs"][0]["parse_note"] == "fallback_unparsed"
        assert out["parse_failures"] == ["https://example.com/jobs/1"]
        assert out["search_errors"][0]["tool"] == "jd_structurer"

    def test_official_and_auxiliary_results_merge_without_duplicates(self):
        official = {
            "search_results": [
                {
                    "title": "官网岗位",
                    "company": "X",
                    "source_url": "https://x.example/jobs/1",
                }
            ],
            "platforms_searched": ["official_soe_web"],
            "search_errors": [],
        }
        auxiliary = {
            "search_results": [
                {
                    "title": "官网岗位",
                    "company": "X",
                    "source_url": "https://x.example/jobs/1",
                },
                {
                    "title": "国聘岗位",
                    "company": "Y",
                    "source_url": "https://www.iguopin.com/job/detail?id=2",
                },
            ],
            "platforms_searched": ["guopin"],
            "search_errors": [],
        }

        out = self.agent._merge_search_results(official, auxiliary)

        assert len(out["search_results"]) == 2
        assert out["platforms_searched"] == ["official_soe_web", "guopin"]

    def test_default_tools_exclude_captcha_platforms_for_soe_search(self):
        tools = self.agent._get_tool_names({"job_query": {"company_type": ["国企"]}})

        assert "guopin_search" in tools
        assert "boss_search" not in tools
        assert "niuke_search" not in tools
