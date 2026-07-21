"""Integration tests for main graph flow (end-to-end)."""

from unittest.mock import AsyncMock, patch

from langchain_core.messages import HumanMessage

from job_agent_os.graph.edges import (
    after_human_clarify,
    after_human_review,
    after_resume_approval,
    should_clarify,
)
from job_agent_os.graph.state import JobAgentState


class TestConditionalEdges:
    """Test conditional edge routing functions."""

    def test_should_clarify_true(self):
        """Should route to human_clarify when clarification needed."""
        state: JobAgentState = {"clarification_needed": True}
        assert should_clarify(state) == "human_clarify"

    def test_should_clarify_false(self):
        """Should route to search when no clarification needed."""
        state: JobAgentState = {"clarification_needed": False}
        assert should_clarify(state) == "search"

    def test_should_clarify_default(self):
        """Should default to search when field missing."""
        state: JobAgentState = {}
        assert should_clarify(state) == "search"

    def test_after_human_clarify_returns_intent(self):
        """After clarification, should go back to intent."""
        state: JobAgentState = {}
        assert after_human_clarify(state) == "intent"

    def test_after_human_review_accept(self):
        """Should go to resume when review accepted."""
        state: JobAgentState = {"human_feedback": "looks good"}
        assert after_human_review(state) == "resume"

    def test_after_human_review_reject(self):
        """Should go back to match when review rejected."""
        state: JobAgentState = {"human_feedback": "reject these results"}
        assert after_human_review(state) == "match"

    def test_after_human_review_empty_feedback(self):
        """Should go to resume when no feedback."""
        state: JobAgentState = {"human_feedback": ""}
        assert after_human_review(state) == "resume"

    def test_after_resume_approval_approved(self):
        """Should go to interview when resume approved."""
        state: JobAgentState = {"resume_approved": True}
        assert after_resume_approval(state) == "interview"

    def test_after_resume_approval_rejected(self):
        """Should go back to resume when not approved."""
        state: JobAgentState = {"resume_approved": False}
        assert after_resume_approval(state) == "resume"


class TestGraphBuild:
    """Test graph construction."""

    def test_build_main_graph_compiles(self):
        """Main graph should compile without errors."""
        from job_agent_os.graph.main_graph import build_main_graph

        graph = build_main_graph()
        assert graph is not None

    def test_graph_has_expected_nodes(self):
        """Graph should contain all expected nodes."""
        from job_agent_os.graph.main_graph import build_main_graph

        graph = build_main_graph()
        # LangGraph compiled graph's get_graph().nodes is a dict
        graph_repr = graph.get_graph()
        node_ids = list(graph_repr.nodes.keys()) if isinstance(graph_repr.nodes, dict) else list(graph_repr.nodes)

        expected_nodes = [
            "intent",
            "search",
            "parse",
            "match",
            "resume",
            "interview",
            "tracker",
            "human_clarify",
            "human_review",
            "human_approve",
        ]
        for node_name in expected_nodes:
            assert node_name in node_ids, f"Node '{node_name}' not found in graph"


class TestGraphExecution:
    """Test graph execution with mocked agents."""

    async def test_intent_to_clarify_flow(self):
        """Test flow: intent -> clarification needed -> human_clarify (interrupt)."""
        from job_agent_os.graph.main_graph import build_main_graph

        graph = build_main_graph()

        # Mock intent agent to require clarification
        mock_intent_result = {
            "current_phase": "intent",
            "clarification_needed": True,
            "clarification_question": "请提供更多信息",
        }

        with patch("job_agent_os.graph.nodes.intent_agent") as mock_agent:
            mock_agent.execute = AsyncMock(return_value=mock_intent_result)

            config = {"configurable": {"thread_id": "test-thread-1"}}
            initial_state = {
                "messages": [HumanMessage(content="找工作")],
            }

            # Graph should interrupt before human_clarify
            result = await graph.ainvoke(initial_state, config=config)

            # Should have clarification data
            assert result.get("clarification_needed") is True

    async def test_full_happy_path_flow(self):
        """Test full flow: intent -> search -> parse -> match -> (interrupt at human_review)."""
        from job_agent_os.graph.main_graph import build_main_graph

        graph = build_main_graph()

        mock_intent = {
            "current_phase": "intent",
            "job_query": {"region": ["河南"], "direction": "Java", "company_type": ["国企"]},
            "clarification_needed": False,
            "clarification_question": None,
        }
        mock_search = {
            "current_phase": "search",
            "search_results": [{"title": "Java开发", "company": "中原银行"}],
            "platforms_searched": ["boss"],
        }
        mock_parse = {
            "current_phase": "parse",
            "parsed_jobs": [{"title": "Java开发", "skills": ["Java", "Spring"]}],
        }
        mock_match = {
            "current_phase": "match",
            "match_results": [{"job_title": "Java开发", "score": 0.85}],
        }

        with (
            patch("job_agent_os.graph.nodes.intent_agent") as m_intent,
            patch("job_agent_os.graph.nodes.search_agent") as m_search,
            patch("job_agent_os.graph.nodes.parse_agent") as m_parse,
            patch("job_agent_os.graph.nodes.match_agent") as m_match,
        ):
            m_intent.execute = AsyncMock(return_value=mock_intent)
            m_search.execute = AsyncMock(return_value=mock_search)
            m_parse.execute = AsyncMock(return_value=mock_parse)
            m_match.execute = AsyncMock(return_value=mock_match)

            config = {"configurable": {"thread_id": "test-thread-2"}}
            initial_state = {
                "messages": [HumanMessage(content="河南 国企 Java")],
            }

            # Should interrupt before human_review
            result = await graph.ainvoke(initial_state, config=config)

            # Verify agents were called
            m_intent.execute.assert_called_once()
            m_search.execute.assert_called_once()
            m_parse.execute.assert_called_once()
            m_match.execute.assert_called_once()

            # Should have match results
            assert result.get("match_results") is not None
