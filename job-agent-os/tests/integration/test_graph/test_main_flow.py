"""Integration tests for Supervisor-loop graph flow."""

from unittest.mock import AsyncMock, patch

from langchain_core.messages import HumanMessage

from job_agent_os.graph.edges import route_from_supervisor
from job_agent_os.graph.state import JobAgentState


class TestSupervisorRouting:
    """Test Supervisor routing edge function."""

    def test_route_to_intent(self):
        """Should route to intent when next_agent is intent."""
        state: JobAgentState = {"next_agent": "intent", "is_finished": False}
        assert route_from_supervisor(state) == "intent"

    def test_route_to_search(self):
        """Should route to search when next_agent is search."""
        state: JobAgentState = {"next_agent": "search", "is_finished": False}
        assert route_from_supervisor(state) == "search"

    def test_route_to_end_when_finished(self):
        """Should route to __end__ when is_finished is True."""
        state: JobAgentState = {"next_agent": "search", "is_finished": True}
        assert route_from_supervisor(state) == "__end__"

    def test_route_to_end_when_no_agent(self):
        """Should route to __end__ when next_agent is empty."""
        state: JobAgentState = {"next_agent": "", "is_finished": False}
        assert route_from_supervisor(state) == "__end__"

    def test_route_to_end_for_invalid_agent(self):
        """Should route to __end__ for unknown agent names."""
        state: JobAgentState = {"next_agent": "nonexistent_agent", "is_finished": False}
        assert route_from_supervisor(state) == "__end__"

    def test_route_to_all_valid_agents(self):
        """Should correctly route to all valid specialist agents."""
        valid_agents = ["intent", "search", "match", "resume", "interview"]
        for agent in valid_agents:
            state: JobAgentState = {"next_agent": agent, "is_finished": False}
            assert route_from_supervisor(state) == agent


class TestGraphBuild:
    """Test graph construction."""

    def test_build_main_graph_compiles(self):
        """Main graph should compile without errors."""
        from job_agent_os.graph.main_graph import build_main_graph

        graph = build_main_graph()
        assert graph is not None

    def test_graph_has_supervisor_node(self):
        """Graph should contain the supervisor node."""
        from job_agent_os.graph.main_graph import build_main_graph

        graph = build_main_graph()
        graph_repr = graph.get_graph()
        node_ids = list(graph_repr.nodes.keys())
        assert "supervisor" in node_ids

    def test_graph_has_all_specialist_nodes(self):
        """Graph should contain all specialist agent nodes."""
        from job_agent_os.graph.main_graph import build_main_graph

        graph = build_main_graph()
        graph_repr = graph.get_graph()
        node_ids = list(graph_repr.nodes.keys())

        expected_nodes = ["supervisor", "intent", "search", "match", "resume", "interview"]
        for node_name in expected_nodes:
            assert node_name in node_ids, f"Node '{node_name}' not found in graph"

        for merged_node in ("web_search", "parse", "tracker"):
            assert merged_node not in node_ids

    def test_graph_has_no_old_hitl_nodes(self):
        """Graph should NOT contain old HITL nodes."""
        from job_agent_os.graph.main_graph import build_main_graph

        graph = build_main_graph()
        graph_repr = graph.get_graph()
        node_ids = list(graph_repr.nodes.keys())

        old_nodes = ["human_clarify", "human_review", "human_approve"]
        for node_name in old_nodes:
            assert node_name not in node_ids, f"Old node '{node_name}' should not be in graph"


class TestGraphExecution:
    """Test graph execution with mocked Supervisor."""

    async def test_supervisor_routes_to_intent_then_ends(self):
        """Test: supervisor -> intent -> supervisor -> END."""
        from job_agent_os.graph.main_graph import build_main_graph

        graph = build_main_graph()

        # Supervisor first routes to intent, then finishes
        call_count = {"n": 0}

        async def mock_supervisor_decide(state):
            call_count["n"] += 1
            if call_count["n"] == 1:
                from job_agent_os.agents.supervisor import SupervisorDecision
                return SupervisorDecision(
                    next_agent="intent",
                    task_instruction="解析用户意图",
                    reasoning="需要先解析意图",
                    is_finished=False,
                )
            else:
                from job_agent_os.agents.supervisor import SupervisorDecision
                return SupervisorDecision(
                    next_agent="__end__",
                    task_instruction="",
                    reasoning="任务完成",
                    is_finished=True,
                    final_message="完成",
                )

        mock_intent_result = {
            "current_phase": "intent",
            "job_query": {"region": ["河南"], "direction": "Python"},
            "clarification_needed": False,
        }

        with (
            patch("job_agent_os.graph.nodes.supervisor_agent") as m_sup,
            patch("job_agent_os.graph.nodes.intent_agent") as m_intent,
        ):
            m_sup.decide = mock_supervisor_decide
            m_intent.execute = AsyncMock(return_value=mock_intent_result)

            config = {"configurable": {"thread_id": "test-supervisor-1"}}
            initial_state = {
                "messages": [HumanMessage(content="河南 国企 Python")],
            }

            result = await graph.ainvoke(initial_state, config=config)

            # Intent agent should have been called
            m_intent.execute.assert_called_once()
            # Should have job_query from intent
            assert result.get("job_query") is not None
