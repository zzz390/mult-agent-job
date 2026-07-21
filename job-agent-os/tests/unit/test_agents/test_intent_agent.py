"""Unit tests for Intent Agent."""

from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import HumanMessage

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


class TestIntentAgentExecute:
    """Test the execute method with mocked LLM."""

    async def test_execute_empty_messages(self, agent):
        """Test execute with no messages returns clarification."""
        state = {"messages": []}
        result = await agent.execute(state)

        assert result["current_phase"] == "intent"
        assert result["clarification_needed"] is True
        assert "求职意向" in result["clarification_question"]

    async def test_execute_with_structured_output(self, agent):
        """Test execute with successful structured output."""
        state = {"messages": [HumanMessage(content="河南 国企 Java")]}

        with patch.object(agent, "_parse_with_structured_output", new_callable=AsyncMock) as mock_parse:
            mock_parse.return_value = {
                "current_phase": "intent",
                "job_query": {
                    "region": ["河南"],
                    "company_type": ["国企"],
                    "direction": "Java",
                    "skills": ["Spring", "MySQL"],
                    "salary_min": 10,
                    "salary_max": 20,
                    "education": "本科",
                },
                "clarification_needed": False,
                "clarification_question": None,
            }
            result = await agent.execute(state)

        assert result["current_phase"] == "intent"
        assert result["clarification_needed"] is False
        assert result["job_query"]["region"] == ["河南"]

    async def test_execute_fallback_on_llm_failure(self, agent):
        """Test execute falls back to keyword parsing when LLM fails."""
        state = {"messages": [HumanMessage(content="深圳 外企 算法")]}

        with patch.object(agent, "_parse_with_structured_output", new_callable=AsyncMock) as mock_structured:
            mock_structured.side_effect = Exception("LLM Error")
            with patch.object(agent, "_parse_with_json", new_callable=AsyncMock) as mock_json:
                mock_json.side_effect = Exception("JSON Error")
                result = await agent.execute(state)

        # Should fall back to keyword parsing
        assert result["current_phase"] == "intent"
        assert result["clarification_needed"] is False
        assert "深圳" in result["job_query"]["region"]
        assert "外企" in result["job_query"]["company_type"]
        assert result["job_query"]["direction"] == "算法"


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
