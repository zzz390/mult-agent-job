"""Tests for Supervisor degradation chain and streamlined routing (issues #1, #2)."""

from unittest.mock import AsyncMock, MagicMock

from job_agent_os.agents.supervisor import SupervisorAgent, SupervisorDecision


def _decision_json(next_agent: str, is_finished: bool = False) -> str:
    return (
        f'{{"next_agent": "{next_agent}", "task_instruction": "t", '
        f'"reasoning": "r", "is_finished": {str(is_finished).lower()}, '
        '"final_message": null}'
    )


class TestSupervisorLLMDegradation:
    async def test_normal_route_is_deterministic_and_skips_llm(self):
        agent = SupervisorAgent()
        primary = AsyncMock()
        primary.ainvoke = AsyncMock(return_value=MagicMock(content=_decision_json("intent")))

        def get_llm(use_fallback=False):
            assert use_fallback is False
            return primary

        agent._get_llm = get_llm
        decision = await agent.decide({"job_query": None})
        assert decision.next_agent == "intent"
        primary.ainvoke.assert_not_awaited()

    async def test_fallback_llm_when_primary_replan_fails(self):
        agent = SupervisorAgent()
        primary = AsyncMock()
        primary.ainvoke = AsyncMock(side_effect=RuntimeError("primary down"))
        fallback = AsyncMock()
        fallback.ainvoke = AsyncMock(return_value=MagicMock(content=_decision_json("search")))

        def get_llm(use_fallback=False):
            return fallback if use_fallback else primary

        agent._get_llm = get_llm
        decision = await agent.decide(
            {
                "job_query": {"direction": "Java"},
                "error_state": {"error_type": "RuntimeError"},
            }
        )
        assert decision.next_agent == "search"
        primary.ainvoke.assert_awaited_once()
        fallback.ainvoke.assert_awaited_once()

    async def test_rule_fallback_when_both_llms_fail(self):
        agent = SupervisorAgent()

        def get_llm(use_fallback=False):
            llm = AsyncMock()
            llm.ainvoke = AsyncMock(side_effect=RuntimeError("all down"))
            return llm

        agent._get_llm = get_llm
        decision = await agent.decide(
            {"job_query": None, "error_state": {"error_type": "RuntimeError"}}
        )
        # Rule-based fallback: no job_query -> intent
        assert decision.next_agent == "intent"


class TestStreamlinedFallbackRouting:
    """Rule fallback no longer routes web_search/parse/tracker (issue #2)."""

    def setup_method(self):
        self.agent = SupervisorAgent()

    def test_no_intent_goes_to_intent(self):
        decision = self.agent._fallback_decision({"job_query": None})
        assert decision.next_agent == "intent"

    def test_clarification_ends_with_question(self):
        decision = self.agent._fallback_decision(
            {
                "job_query": None,
                "clarification_needed": True,
                "clarification_question": "请补充地区",
            }
        )
        assert decision.next_agent == "__end__"
        assert decision.is_finished is True
        assert decision.final_message == "请补充地区"

    def test_partial_query_still_pauses_for_clarification(self):
        decision = self.agent._fallback_decision(
            {
                "job_query": {"direction": "Java"},
                "clarification_needed": True,
                "clarification_question": "请补充地区",
            }
        )

        assert decision.next_agent == "__end__"
        assert decision.final_message == "请补充地区"

    def test_after_intent_goes_to_search_not_parse(self):
        decision = self.agent._fallback_decision(
            {"job_query": {"direction": "Java"}, "agent_execution_order": ["intent"]}
        )
        assert decision.next_agent == "search"

    def test_after_search_goes_to_match_directly(self):
        """parse is skipped — search embeds structuring now."""
        decision = self.agent._fallback_decision(
            {
                "job_query": {"direction": "Java"},
                "search_results": [{"title": "x"}],
                "parsed_jobs": [{"title": "x"}],
            }
        )
        assert decision.next_agent == "match"

    def test_after_match_goes_to_resume(self):
        decision = self.agent._fallback_decision(
            {
                "job_query": {"direction": "Java"},
                "search_results": [{"title": "x"}],
                "parsed_jobs": [{"title": "x"}],
                "match_results": [{"job": {"title": "x"}, "overall_score": 90}],
            }
        )
        assert decision.next_agent == "resume"

    def test_after_resume_goes_to_interview(self):
        decision = self.agent._fallback_decision(
            {
                "job_query": {"direction": "Java"},
                "search_results": [{"title": "x"}],
                "parsed_jobs": [{"title": "x"}],
                "match_results": [{"job": {"title": "x"}}],
                "optimized_resume": {"text": "..."},
            }
        )
        assert decision.next_agent == "interview"

    def test_all_done_ends(self):
        """No tracker hop — interview embeds application creation."""
        decision = self.agent._fallback_decision(
            {
                "job_query": {"direction": "Java"},
                "search_results": [{"title": "x"}],
                "parsed_jobs": [{"title": "x"}],
                "match_results": [{"job": {"title": "x"}}],
                "optimized_resume": {"text": "..."},
                "interview_questions": [{"question": "q"}],
            }
        )
        assert decision.next_agent == "__end__"
        assert decision.is_finished is True

    def test_pipeline_never_routes_merged_agents(self):
        """Walk a full pipeline; web_search/parse/tracker must never appear."""
        state = {}
        seen = []
        for _ in range(10):
            decision = self.agent._fallback_decision(state)
            seen.append(decision.next_agent)
            if decision.is_finished:
                break
            # simulate the effect of each agent
            if decision.next_agent == "intent":
                state["job_query"] = {"direction": "Java"}
            elif decision.next_agent == "search":
                state["search_results"] = [{"title": "x"}]
                state["parsed_jobs"] = [{"title": "x"}]
            elif decision.next_agent == "match":
                state["match_results"] = [{"job": {"title": "x"}}]
            elif decision.next_agent == "resume":
                state["optimized_resume"] = {"text": "r"}
            elif decision.next_agent == "interview":
                state["interview_questions"] = [{"q": 1}]

        assert "web_search" not in seen
        assert "parse" not in seen
        assert "tracker" not in seen
        assert seen[-1] == "__end__"


class TestSupervisorDecisionModel:
    def test_decision_model_defaults(self):
        d = SupervisorDecision(next_agent="intent", task_instruction="t", reasoning="r")
        assert d.is_finished is False
        assert d.final_message is None


async def test_supervisor_node_includes_current_phase(monkeypatch):
    """Harness output validation requires every node to declare its phase."""
    from job_agent_os.graph import nodes

    async def passthrough(_name, _state, operation):
        return await operation()

    monkeypatch.setattr(nodes, "_run_node", passthrough)
    monkeypatch.setattr(
        nodes.supervisor_agent,
        "decide",
        AsyncMock(
            return_value=SupervisorDecision(
                next_agent="search",
                task_instruction="search",
                reasoning="ready",
            )
        ),
    )

    result = await nodes.supervisor_node({})

    assert result["current_phase"] == "supervisor"
