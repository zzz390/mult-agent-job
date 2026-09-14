"""Tests for config-driven intent fallback parsing (issue #1)."""

import pytest

from job_agent_os.agents.intent_agent import IntentAgent
from job_agent_os.core import config_loader


@pytest.fixture
def agent():
    return IntentAgent()


@pytest.fixture(autouse=True)
def _fresh_config():
    """Ensure config cache doesn't leak between tests."""
    config_loader.clear_config_cache()
    yield
    config_loader.clear_config_cache()


class TestConfigLoader:
    def test_load_intent_keywords_sections(self):
        kw = config_loader.load_intent_keywords()
        assert "regions" in kw
        assert "company_types" in kw
        assert "directions" in kw
        assert len(kw["regions"]) > 12  # must exceed old hardcoded list

    def test_load_boss_city_codes(self):
        codes = config_loader.load_boss_city_codes()
        assert codes["郑州"] == "101180100"
        assert codes["全国"] == "100010000"
        assert all(isinstance(v, str) for v in codes.values())


class TestExpandedRegionCoverage:
    """Regions that previously triggered 'unrecognized' must now parse."""

    def test_xian_python(self, agent):
        result = agent._fallback_parse("西安 Python")
        assert result["clarification_needed"] is False
        assert "西安" in result["job_query"]["region"]
        assert result["job_query"]["direction"] == "Python"

    def test_suzhou_frontend(self, agent):
        result = agent._fallback_parse("苏州 前端")
        assert result["clarification_needed"] is False
        assert "苏州" in result["job_query"]["region"]
        assert result["job_query"]["direction"] == "前端"

    def test_qingdao_bigdata(self, agent):
        result = agent._fallback_parse("青岛 大数据 国企")
        assert "青岛" in result["job_query"]["region"]
        assert "国企" in result["job_query"]["company_type"]
        assert result["job_query"]["direction"] == "大数据"


class TestBackwardCompatibleParsing:
    """Existing behaviors covered by the original hardcoded list must hold."""

    def test_henan_java(self, agent):
        result = agent._fallback_parse("河南 国企 Java")
        assert result["clarification_needed"] is False
        assert "河南" in result["job_query"]["region"]
        assert "国企" in result["job_query"]["company_type"]
        assert result["job_query"]["direction"] == "Java"

    def test_gibberish_needs_clarification(self, agent):
        result = agent._fallback_parse("我想找工作")
        assert result["clarification_needed"] is True
        assert result["job_query"] is None

    def test_case_insensitive_direction(self, agent):
        result = agent._fallback_parse("python")
        assert result["clarification_needed"] is False
        assert result["job_query"]["direction"] == "Python"
