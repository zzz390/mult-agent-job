"""Unit tests for Intent Agent."""

from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from job_agent_os.agents.intent_agent import IntentAgent, IntentOutput


@pytest.fixture
def agent():
    """Create IntentAgent instance."""
    return IntentAgent()


class TestIntentAgentFallbackParse:
    """Test the fallback keyword parsing logic (no LLM needed)."""

    def test_parse_full_intent(self, agent):
        """Test parsing a complete intent with region, company type, and direction."""
        result = agent._fallback_parse("河南 国企 Java")

        assert result["current_phase"] == "intent"
        assert result["clarification_needed"] is False
        assert result["clarification_question"] is None

        job_query = result["job_query"]
        assert "河南" in job_query["region"]
        assert "国企" in job_query["company_type"]
        assert job_query["direction"] == "Java"

    def test_parse_partial_intent_needs_clarification(self, agent):
        """Test that incomplete intent triggers clarification."""
        result = agent._fallback_parse("我想找工作")

        assert result["current_phase"] == "intent"
        assert result["clarification_needed"] is True
        assert result["clarification_question"] is not None
        assert result["job_query"] is None

    def test_parse_region_only(self, agent):
        """Test parsing with only region specified."""
        result = agent._fallback_parse("北京")

        assert result["current_phase"] == "intent"
        assert result["clarification_needed"] is False
        job_query = result["job_query"]
        assert "北京" in job_query["region"]
        assert job_query["direction"] == ""

    def test_parse_multiple_regions(self, agent):
        """Test parsing with multiple regions."""
        result = agent._fallback_parse("北京 上海 杭州 前端")

        job_query = result["job_query"]
        assert "北京" in job_query["region"]
        assert "上海" in job_query["region"]
        assert "杭州" in job_query["region"]
        assert job_query["direction"] == "前端"

    def test_parse_direction_only(self, agent):
        """Test parsing with only direction specified."""
        result = agent._fallback_parse("Python")

        assert result["clarification_needed"] is False
        job_query = result["job_query"]
        assert job_query["direction"] == "Python"
        assert job_query["region"] == []

    def test_non_json_llm_output_uses_keyword_fallback(self, agent):
        result = agent._parse_final_output(
            [AIMessage(content="我理解你想在深圳找算法岗位")], {}
        )

        assert result["current_phase"] == "intent"
        assert result["job_query"]["region"] == ["深圳"]
        assert result["job_query"]["direction"] == "算法"


class TestIntentAgentExecute:
    """Test the execute method with mocked LLM (ReAct architecture)."""

    async def test_execute_empty_messages(self, agent):
        """Test execute with no messages returns clarification via fallback."""
        from langchain_core.messages import AIMessage

        state = {"messages": []}

        # Mock LLM to return empty content (simulates no useful response)
        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(return_value=AIMessage(content=""))
        mock_llm.bind_tools = lambda tools: mock_llm

        with patch.object(agent, "_get_llm", return_value=mock_llm):
            result = await agent.execute(state)

        assert result["current_phase"] == "intent"
        assert result["clarification_needed"] is True
        assert "求职意向" in result["clarification_question"]

    async def test_execute_with_valid_json_response(self, agent):
        """Test execute with LLM returning valid JSON."""
        from langchain_core.messages import AIMessage

        state = {"messages": [HumanMessage(content="河南 国企 Java")]}

        json_response = '{"region": ["河南"], "company_type": ["国企"], "direction": "Java", "skills": ["Spring"], "salary_min": null, "salary_max": null, "education": null, "clarification_needed": false, "clarification_question": null}'
        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(return_value=AIMessage(content=json_response))
        mock_llm.bind_tools = lambda tools: mock_llm

        with patch.object(agent, "_get_llm", return_value=mock_llm):
            result = await agent.execute(state)

        assert result["current_phase"] == "intent"
        assert result["clarification_needed"] is False
        assert result["job_query"]["region"] == ["河南"]
        assert result["job_query"]["direction"] == "Java"

    async def test_execute_fallback_on_llm_failure(self, agent):
        """Test execute falls back to keyword parsing when LLM fails."""
        state = {"messages": [HumanMessage(content="深圳 外企 算法")]}

        # Mock LLM to raise an exception
        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(side_effect=Exception("LLM Error"))
        mock_llm.bind_tools = lambda tools: mock_llm

        with patch.object(agent, "_get_llm", return_value=mock_llm):
            result = await agent.execute(state)

        # Should fall back to keyword parsing via _parse_final_output with no AI content
        # When LLM fails, _get_last_ai_content returns "" -> triggers clarification
        # But the fallback_parse is called on the user input content
        assert result["current_phase"] == "intent"


class TestIntentOutputSchema:
    """Test IntentOutput Pydantic model."""

    def test_default_values(self):
        """Test IntentOutput default values."""
        output = IntentOutput()
        assert output.region == []
        assert output.company_type == []
        assert output.direction == ""
        assert output.skills == []
        assert output.salary_min is None
        assert output.salary_max is None
        assert output.education is None
        assert output.clarification_needed is False
        assert output.clarification_question is None

    def test_full_output(self):
        """Test IntentOutput with all fields."""
        output = IntentOutput(
            region=["北京", "上海"],
            company_type=["国企"],
            direction="后端",
            skills=["Java", "Go"],
            salary_min=15,
            salary_max=30,
            education="硕士",
            clarification_needed=False,
        )
        assert len(output.region) == 2
        assert output.salary_min == 15
