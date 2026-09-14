"""Regression tests for the findings assessed in ISSUES_AND_SOLUTIONS.md."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from langgraph.graph import END, START, StateGraph

from job_agent_os.graph.state import JobAgentState
from job_agent_os.harness.recovery_manager import (
    RecoveryManager,
    is_fallback_model_requested,
)
from job_agent_os.schemas.application import ApplicationStatusUpdate
from job_agent_os.schemas.approval import ApprovalRespondRequest
from job_agent_os.services.application_service import (
    VALID_TRANSITIONS,
    ApplicationService,
)
from job_agent_os.services.approval_service import ApprovalService
from job_agent_os.services.session_service import SessionService
from job_agent_os.tools.match.skill_matcher import match_skills
from job_agent_os.tools.parse.jd_structurer import structure_jd


def test_current_run_lists_overwrite_stale_state() -> None:
    async def replace_results(_state: JobAgentState) -> dict:
        return {"search_results": [{"id": "new"}], "match_results": [{"id": "new"}]}

    workflow = StateGraph(JobAgentState)
    workflow.add_node("replace", replace_results)
    workflow.add_edge(START, "replace")
    workflow.add_edge("replace", END)

    result = asyncio.run(
        workflow.compile().ainvoke(
            {
                "search_results": [{"id": "stale"}],
                "match_results": [{"id": "stale"}],
            }
        )
    )

    assert result["search_results"] == [{"id": "new"}]
    assert result["match_results"] == [{"id": "new"}]


def test_skill_matching_uses_exact_names_and_aliases() -> None:
    result = match_skills(
        ["JavaScript", "Django", "MongoDB", "Golang", "PostgreSQL"],
        ["Java", "Go", "Postgres"],
    )

    assert result["matched_skills"] == ["Golang", "PostgreSQL"]
    assert result["missing_skills"] == ["JavaScript", "Django", "MongoDB"]


async def test_recovery_degradation_reaches_agent_context() -> None:
    recovery = RecoveryManager(max_retries=1)
    attempts: list[bool] = []

    async def operation() -> str:
        attempts.append(is_fallback_model_requested())
        if len(attempts) == 1:
            raise RuntimeError("primary failed")
        return "ok"

    assert await recovery.execute_with_recovery(operation, "agent") == "ok"
    assert attempts == [False, True]
    assert is_fallback_model_requested() is False


async def test_valid_llm_jd_without_confidence_stays_usable() -> None:
    llm = MagicMock()
    llm.ainvoke = AsyncMock(
        return_value=SimpleNamespace(content='{"title":"后端","company":"示例公司"}')
    )
    with (
        patch(
            "job_agent_os.tools.parse.jd_structurer.ChatOpenAI",
            return_value=llm,
        ),
        patch(
            "job_agent_os.tools.parse.jd_structurer.load_prompt",
            return_value=("system", "user"),
        ),
    ):
        result = await structure_jd("后端", "示例公司", "Python FastAPI")

    assert result["parse_confidence"] == 0.8


def test_kanban_allows_corrections_without_arbitrary_jumps() -> None:
    assert "pending" in VALID_TRANSITIONS["applied"]
    assert "applied" in VALID_TRANSITIONS["written_test"]
    assert VALID_TRANSITIONS["rejected"] == ["pending"]
    assert "offer" not in VALID_TRANSITIONS["pending"]


async def test_manual_status_update_records_audit_history() -> None:
    db = AsyncMock()
    service = ApplicationService(db)
    application = SimpleNamespace(
        status="applied",
        stage="none",
        notes=None,
        next_follow_up=None,
        status_history=[{"status": "applied"}],
        last_status_change=None,
    )
    service.get_application = AsyncMock(return_value=application)  # type: ignore[method-assign]

    await service.update_status(
        SimpleNamespace(id=uuid4()),
        uuid4(),
        ApplicationStatusUpdate(status="pending", notes="误拖，撤销"),
    )

    assert application.status == "pending"
    assert application.status_history[-1]["from_status"] == "applied"
    assert application.status_history[-1]["source"] == "manual"


async def test_rejected_recommendations_reroute_to_match() -> None:
    graph = AsyncMock()
    store = AsyncMock()
    service = ApprovalService(AsyncMock())
    approval = SimpleNamespace(
        session_id=uuid4(), approval_type="recommendation_review"
    )

    async def no_op_resume(_session_id: str) -> None:
        return None

    with (
        patch(
            "job_agent_os.graph.main_graph.get_main_graph", return_value=graph
        ),
        patch(
            "job_agent_os.services.session_store.get_session_store",
            return_value=store,
        ),
        patch(
            "job_agent_os.services.approval_service._resume_session_background",
            side_effect=no_op_resume,
        ),
    ):
        await service._resume_graph(
            approval,
            ApprovalRespondRequest(action="reject", feedback="更关注后端岗位"),
        )
        await asyncio.sleep(0)

    _, state_update = graph.aupdate_state.await_args.args
    assert graph.aupdate_state.await_args.kwargs == {"as_node": "supervisor"}
    assert state_update["next_agent"] == "match"
    assert state_update["match_results"] == []
    assert state_update["human_feedback"] == "更关注后端岗位"
    assert store.update.await_args.kwargs["status"] == "running"


async def test_clarification_reply_clears_stale_pipeline_products() -> None:
    graph = AsyncMock()
    service = SessionService(AsyncMock())
    session_id = uuid4()
    user = SimpleNamespace(id=uuid4())
    service.store = AsyncMock()
    service.store.get.return_value = {
        "user_id": str(user.id),
        "status": "waiting_input",
    }

    def close_background(coro) -> None:
        coro.close()

    with (
        patch(
            "job_agent_os.graph.main_graph.get_main_graph", return_value=graph
        ),
        patch(
            "job_agent_os.services.session_service._spawn_background",
            side_effect=close_background,
        ),
    ):
        from job_agent_os.schemas.session import SessionMessage

        await service.send_message(
            user,
            session_id,
            SessionMessage(content="改为上海的 Python 后端岗位"),
        )

    state_update = graph.aupdate_state.await_args.args[1]
    assert state_update["search_results"] == []
    assert state_update["parsed_jobs"] == []
    assert state_update["match_results"] == []
    assert state_update["interview_questions"] == []
    assert graph.aupdate_state.await_args.kwargs == {"as_node": "supervisor"}


async def test_delete_session_cancels_workflow_and_removes_owned_history() -> None:
    session_id = uuid4()
    user = SimpleNamespace(id=uuid4())
    service = SessionService(AsyncMock())
    service.store = AsyncMock()
    service.store.get.return_value = {
        "user_id": str(user.id),
        "status": "running",
    }
    runtime = MagicMock()

    with patch(
        "job_agent_os.services.session_service.get_harness_runtime",
        return_value=runtime,
    ):
        result = await service.delete_session(user, session_id)

    runtime.cancel_session.assert_called_once_with(str(session_id))
    service.store.delete.assert_awaited_once_with(str(session_id))
    assert result == {"session_id": str(session_id), "status": "deleted"}


async def test_runtime_publishes_current_agent_to_session_store() -> None:
    from job_agent_os.harness.runtime import HarnessRuntime

    session_id = str(uuid4())
    runtime = HarnessRuntime()
    runtime._active_sessions[session_id] = {"status": "running"}
    store = AsyncMock()
    store.get.return_value = {
        "progress": {
            "completed_steps": ["supervisor"],
            "current_step": None,
            "pending_steps": [],
        }
    }

    with patch(
        "job_agent_os.services.session_store.get_session_store", return_value=store
    ):
        await runtime._publish_node_activity(session_id, "intent", "running")

    assert store.update.await_args.args[0] == session_id
    progress = store.update.await_args.kwargs["progress"]
    assert progress["current_step"] == "intent"
    assert progress["active_agent"] == "intent"
    assert progress["active_agent_status"] == "running"


async def test_sse_closes_after_waiting_approval() -> None:
    from job_agent_os.api.v1.sessions import stream_session

    service = AsyncMock()
    store = AsyncMock()
    store.get.return_value = {
        "current_phase": "resume",
        "status": "waiting_approval",
        "progress": {},
    }
    with (
        patch("job_agent_os.api.v1.sessions.SessionService", return_value=service),
        patch(
            "job_agent_os.api.v1.sessions.get_session_store", return_value=store
        ),
    ):
        response = await stream_session(uuid4(), AsyncMock(), SimpleNamespace())
        chunks = [chunk async for chunk in response.body_iterator]

    body = "".join(
        chunk.decode() if isinstance(chunk, bytes) else chunk for chunk in chunks
    )
    assert '"status": "waiting_approval"' in body
    assert '"done": true' in body
    assert store.get.await_count == 1
