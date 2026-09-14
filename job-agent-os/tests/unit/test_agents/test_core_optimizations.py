"""Regression tests for the core multi-agent correctness optimizations."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from job_agent_os.agents.interview_agent import InterviewAgent
from job_agent_os.agents.match_agent import MatchAgent
from job_agent_os.agents.resume_agent import ResumeAgent
from job_agent_os.core.llm_usage import collect_message_usage, empty_token_usage
from job_agent_os.graph.selectors import selected_recommendations
from job_agent_os.harness.budget_controller import BudgetController
from job_agent_os.harness.guard_rails import (
    GuardRailChain,
    GuardRailViolation,
    TokenBudgetGuard,
)
from job_agent_os.harness.runtime import HarnessRuntime
from job_agent_os.harness.trace_manager import TraceManager
from job_agent_os.schemas.approval import ApprovalRespondRequest
from job_agent_os.services.approval_service import (
    ApprovalService,
    _select_reviewed_recommendations,
)


def _recommendation(job_id: str, title: str = "后端") -> dict:
    return {
        "job": {"id": job_id, "title": title, "company": "示例公司"},
        "overall_score": 80,
        "recommendation_reason": "匹配",
    }


def test_explicit_empty_review_does_not_fall_back_to_unreviewed_matches() -> None:
    state = {
        "match_results": [_recommendation("original")],
        "approved_recommendations": [],
    }

    assert selected_recommendations(state) == []


def test_review_selection_only_accepts_original_recommendations() -> None:
    originals = [_recommendation("a"), _recommendation("b")]
    requested = [_recommendation("b"), _recommendation("invented")]

    selected = _select_reviewed_recommendations(originals, requested)

    assert [item["job"]["id"] for item in selected] == ["b"]


async def test_approved_review_injects_original_recommendations_into_graph() -> None:
    graph = AsyncMock()
    store = AsyncMock()
    original = [_recommendation("reviewed")]
    approval = SimpleNamespace(
        session_id=uuid4(),
        approval_type="recommendation_review",
        payload={"recommendations": original},
    )

    async def no_op_resume(_session_id: str) -> None:
        return None

    with (
        patch("job_agent_os.graph.main_graph.get_main_graph", return_value=graph),
        patch(
            "job_agent_os.services.session_store.get_session_store",
            return_value=store,
        ),
        patch(
            "job_agent_os.services.approval_service._resume_session_background",
            side_effect=no_op_resume,
        ),
    ):
        await ApprovalService(AsyncMock())._resume_graph(
            approval, ApprovalRespondRequest(action="approve")
        )
        await asyncio.sleep(0)

    state_update = graph.aupdate_state.await_args.args[1]
    assert state_update["approved_recommendations"] == original


class TestDeterministicMatch:
    async def test_scores_all_four_dimensions_with_version_and_confidence(self) -> None:
        state = {
            "parsed_jobs": [
                {
                    "id": "j1",
                    "title": "Python 后端",
                    "company": "A",
                    "location": "北京",
                    "skills_required": ["Python", "FastAPI"],
                    "education": "本科",
                    "experience": "1年以上",
                }
            ],
            "user_profile": {
                "skills": ["Python"],
                "education": {"degree": "本科"},
                "experience_years": 2,
                "preferred_locations": ["北京"],
            },
        }

        result = await MatchAgent().execute(state)

        match = result["match_results"][0]
        assert match["score_breakdown"] == {
            "skill": 50.0,
            "education": 100.0,
            "experience": 100.0,
            "location": 100.0,
        }
        assert match["overall_score"] == 75.0
        assert match["score_confidence"] == 1.0
        assert match["scoring_version"] == "deterministic-v1"

    async def test_known_hard_location_mismatch_is_filtered(self) -> None:
        result = await MatchAgent().execute(
            {
                "parsed_jobs": [
                    {"title": "后端", "company": "A", "location": "上海"}
                ],
                "user_profile": {"preferred_locations": ["北京"]},
            }
        )

        assert result["match_results"] == []

    async def test_missing_profile_caps_score(self) -> None:
        result = await MatchAgent().execute(
            {
                "parsed_jobs": [
                    {"title": "后端", "company": "A", "skills_required": []}
                ],
                "user_profile": None,
            }
        )

        assert result["match_results"][0]["overall_score"] == 20.0


async def test_resume_uses_reviewed_target_and_calls_generator_once() -> None:
    optimizer = AsyncMock(
        return_value={"optimized_resume": "优化结果", "resume_diff": []}
    )
    state = {
        "match_results": [_recommendation("original")],
        "approved_recommendations": [_recommendation("approved", "已确认岗位")],
        "user_profile": {"skills": ["Python"]},
    }

    with patch(
        "job_agent_os.agents.resume_agent.optimize_resume_keywords", optimizer
    ):
        result = await ResumeAgent().execute(state)

    assert result["optimized_resume"] == "优化结果"
    optimizer.assert_awaited_once()
    assert "已确认岗位" in optimizer.await_args.kwargs["job_description"]
    assert "original" not in optimizer.await_args.kwargs["job_description"]


async def test_interview_and_tracking_share_reviewed_target() -> None:
    tech = AsyncMock(return_value=[{"type": "technical", "question": "Q"}])
    behavior = AsyncMock(return_value=[{"type": "behavioral", "question": "B"}])
    state = {
        "match_results": [_recommendation("original")],
        "approved_recommendations": [_recommendation("approved", "已确认岗位")],
        "user_profile": {"projects": []},
    }

    with patch(
        "job_agent_os.agents.interview_agent.generate_tech_questions", tech
    ), patch(
        "job_agent_os.agents.interview_agent.generate_behavior_questions", behavior
    ):
        result = await InterviewAgent().execute(state)

    assert [item["id"] for item in result["interview_questions"]] == [1, 2]
    assert result["applications"][0]["job_id"] == "approved"
    assert tech.await_args.kwargs["job_title"] == "已确认岗位"
    assert behavior.await_args.kwargs["job_title"] == "已确认岗位"


def test_output_contract_rejects_incomplete_search_result() -> None:
    guard = GuardRailChain().get_guard("output_validation")
    assert guard is not None

    with pytest.raises(GuardRailViolation):
        guard.after_node("search", {}, {"current_phase": "search"})


def test_trace_snapshot_redacts_identifiers_and_resume_body() -> None:
    trace = TraceManager()
    span_id = trace.on_node_start(
        "resume",
        "resume",
        {
            "user_message": "联系 13800138000 或 alice@example.com",
            "raw_content": "身份证 11010519491231002X",
        },
    )

    log = trace.on_node_end(
        span_id,
        {"optimized_resume": "包含很多私人履历的完整简历正文"},
    )

    assert log["input_snapshot"]["user_message"] == (
        "联系 [REDACTED_PHONE] 或 [REDACTED_EMAIL]"
    )
    assert log["input_snapshot"]["raw_content"].startswith("[redacted-text:")
    assert log["output_snapshot"]["optimized_resume"].startswith(
        "[redacted-text:"
    )

    error_span = trace.on_node_start("resume", "resume")
    error_log = trace.on_node_error(
        error_span, RuntimeError("请求失败 alice@example.com 13800138000")
    )
    assert "alice@example.com" not in error_log["error_message"]
    assert "13800138000" not in error_log["error_message"]


def test_nested_llm_usage_is_accumulated() -> None:
    usage = empty_token_usage()
    response = SimpleNamespace(
        usage_metadata={
            "input_tokens": 12,
            "output_tokens": 5,
            "total_tokens": 17,
        }
    )

    collect_message_usage(response, usage)
    collect_message_usage(response, usage)

    assert usage == {
        "prompt_tokens": 24,
        "completion_tokens": 10,
        "total_tokens": 34,
        "cost_usd": 0.0,
    }


async def test_checkpointed_budget_activates_fallback_for_next_node() -> None:
    runtime = HarnessRuntime()
    session_id = "not-a-uuid"
    runtime._budget_controllers[session_id] = BudgetController(budget=100)
    runtime._trace_managers[session_id] = TraceManager()
    runtime._guard_chains[session_id] = GuardRailChain()

    async def operation() -> dict:
        return {
            "current_phase": "intent",
            "job_query": {"direction": "Python"},
            "clarification_needed": False,
            "token_usage": {"total_tokens": 0},
        }

    result = await runtime.execute_node(
        "intent",
        {"session_id": session_id, "token_usage": {"total_tokens": 95}},
        operation,
    )

    assert result["use_fallback_model"] is True


async def test_exhausted_checkpoint_budget_blocks_before_node_call() -> None:
    runtime = HarnessRuntime()
    session_id = "not-a-uuid"
    runtime._budget_controllers[session_id] = BudgetController(budget=100)
    runtime._trace_managers[session_id] = TraceManager()
    runtime._guard_chains[session_id] = GuardRailChain(
        [TokenBudgetGuard(max_tokens=100)]
    )
    operation = AsyncMock(return_value={"current_phase": "intent"})

    with pytest.raises(GuardRailViolation):
        await runtime.execute_node(
            "intent",
            {"session_id": session_id, "token_usage": {"total_tokens": 100}},
            operation,
        )

    operation.assert_not_awaited()
