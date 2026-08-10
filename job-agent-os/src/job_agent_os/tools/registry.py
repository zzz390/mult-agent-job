"""Tool registry with LLM-callable support.

Provides:
- @register_tool decorator with args_schema for LLM function-calling
- Auto-discovery of tools in subdirectories
- Grouping tools by Agent name
- Conversion to LangChain StructuredTool (bind_tools compatible)
- get_bindable_tools_by_names() for ReAct agents
"""

import importlib
import pkgutil
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel


@dataclass
class ToolEntry:
    """Registered tool metadata."""

    name: str
    description: str
    func: Callable
    agent_group: str
    is_async: bool = False
    tags: list[str] = field(default_factory=list)
    args_schema: type[BaseModel] | None = None

    def to_structured_tool(self) -> StructuredTool:
        """Convert to a LangChain StructuredTool that LLM can call via bind_tools."""
        kwargs: dict[str, Any] = {
            "name": self.name,
            "description": self.description,
        }
        if self.args_schema:
            kwargs["args_schema"] = self.args_schema

        if self.is_async:
            kwargs["coroutine"] = self.func
            kwargs["func"] = None
        else:
            kwargs["func"] = self.func

        return StructuredTool.from_function(**kwargs)


# Global tool registry
_tool_registry: dict[str, ToolEntry] = {}


def register_tool(
    name: str,
    description: str = "",
    agent_group: str = "common",
    tags: list[str] | None = None,
    args_schema: type[BaseModel] | None = None,
) -> Callable:
    """Decorator to register a function as an LLM-callable tool.

    Args:
        name: Unique tool name
        description: Tool description (defaults to function docstring)
        agent_group: Which agent group this tool belongs to
        tags: Optional tags for categorization
        args_schema: Pydantic model defining the tool's input parameters

    Usage:
        class MyInput(BaseModel):
            query: str = Field(description="search query")

        @register_tool(name="my_tool", agent_group="search", args_schema=MyInput)
        async def my_tool(query: str) -> dict:
            ...
    """

    def decorator(func: Callable) -> Callable:
        tool_description = description or (func.__doc__ or "").strip().split("\n")[0]

        entry = ToolEntry(
            name=name,
            description=tool_description,
            func=func,
            agent_group=agent_group,
            is_async=_is_coroutine_function(func),
            tags=tags or [],
            args_schema=args_schema,
        )
        _tool_registry[name] = entry
        return func

    return decorator


def _is_coroutine_function(func: Callable) -> bool:
    """Check if a function is async."""
    import asyncio

    return asyncio.iscoroutinefunction(func)


def get_tool(name: str) -> ToolEntry | None:
    """Get a registered tool by name."""
    return _tool_registry.get(name)


def get_tools_by_agent(agent_name: str) -> list[ToolEntry]:
    """Get all tools registered for a specific agent group."""
    return [entry for entry in _tool_registry.values() if entry.agent_group == agent_name]


def get_all_tools() -> list[ToolEntry]:
    """Get all registered tools."""
    return list(_tool_registry.values())


def get_tool_names() -> list[str]:
    """Get all registered tool names."""
    return list(_tool_registry.keys())


def get_bindable_tools_by_names(tool_names: list[str]) -> list[StructuredTool]:
    """Get LangChain StructuredTools by name list — for llm.bind_tools().

    This is the primary interface used by ReAct agents to get their callable tools.
    """
    tools = []
    for name in tool_names:
        entry = _tool_registry.get(name)
        if entry:
            tools.append(entry.to_structured_tool())
    return tools


def get_bindable_tools_by_group(agent_group: str) -> list[StructuredTool]:
    """Get all bindable tools for an agent group."""
    entries = get_tools_by_agent(agent_group)
    return [entry.to_structured_tool() for entry in entries]


def to_langchain_tool(entry: ToolEntry) -> StructuredTool:
    """Convert a ToolEntry to a LangChain StructuredTool (legacy compat)."""
    return entry.to_structured_tool()


def get_langchain_tools(agent_name: str) -> list[StructuredTool]:
    """Get LangChain-formatted tools for a specific agent (legacy compat)."""
    return get_bindable_tools_by_group(agent_name)


def discover_tools() -> None:
    """Auto-discover and import all tool modules in subdirectories."""
    import job_agent_os.tools as tools_pkg

    package_path = tools_pkg.__path__
    for importer, module_name, is_pkg in pkgutil.walk_packages(
        package_path, prefix="job_agent_os.tools."
    ):
        if module_name.endswith("__init__") or module_name.endswith("registry"):
            continue
        try:
            importlib.import_module(module_name)
        except Exception:
            pass


def register_builtin_tools() -> None:
    """Manually register built-in tools that aren't decorated."""
    from job_agent_os.tools.common.dedup import dedup_jobs
    from job_agent_os.tools.interview.behavior_question_gen import generate_behavior_questions
    from job_agent_os.tools.interview.tech_question_gen import generate_tech_questions
    from job_agent_os.tools.match.rule_filter import batch_rule_filter
    from job_agent_os.tools.match.skill_matcher import match_skills
    from job_agent_os.tools.parse.html_parser import fetch_and_extract_html
    from job_agent_os.tools.parse.jd_structurer import structure_jd
    from job_agent_os.tools.resume.keyword_optimizer import optimize_resume_keywords

    # --- Schemas for builtin tools ---
    from pydantic import Field

    class DedupInput(BaseModel):
        """去重工具输入"""
        jobs: list[dict] = Field(description="待去重的岗位列表，每项需含 title 和 company 字段")

    class HtmlParseInput(BaseModel):
        """HTML解析工具输入"""
        url: str = Field(description="要抓取的网页URL")

    class JdStructureInput(BaseModel):
        """JD结构化工具输入"""
        title: str = Field(description="岗位标题")
        company: str = Field(description="公司名称")
        raw_description: str = Field(description="原始岗位描述文本")
        source_platform: str = Field(default="", description="来源平台")
        source_url: str = Field(default="", description="来源URL")

    class RuleFilterInput(BaseModel):
        """规则过滤工具输入"""
        jobs: list[dict] = Field(description="待过滤的岗位列表")
        user_profile: dict = Field(description="用户画像，含 education、preferred_locations 等")

    class SkillMatchInput(BaseModel):
        """技能匹配工具输入"""
        job_skills: list[str] = Field(description="岗位要求的技能列表")
        user_skills: list[str] = Field(description="用户拥有的技能列表")

    class ResumeOptimizeInput(BaseModel):
        """简历优化工具输入"""
        resume_content: str = Field(description="用户当前简历文本")
        job_description: str = Field(description="目标岗位描述")

    class TechQuestionInput(BaseModel):
        """技术面试题生成工具输入"""
        job_title: str = Field(description="目标岗位名称")
        skills: list[str] = Field(description="需要考察的技术技能")
        difficulty: str = Field(default="mixed", description="难度: easy/medium/hard/mixed")
        count: int = Field(default=5, description="生成题目数量")

    class BehaviorQuestionInput(BaseModel):
        """行为面试题生成工具输入"""
        job_title: str = Field(description="目标岗位名称")
        experiences: list[str] = Field(default_factory=list, description="用户项目/实习经历摘要")
        count: int = Field(default=5, description="生成题目数量")

    class PlatformSearchInput(BaseModel):
        """平台搜索工具输入"""
        keyword: str = Field(description="搜索关键词（岗位方向）")
        region: str = Field(default="", description="搜索地区")
        company_type: str = Field(default="", description="企业类型筛选")

    # Register tools with schemas
    if "dedup" not in _tool_registry:
        _tool_registry["dedup"] = ToolEntry(
            name="dedup",
            description="对岗位列表按内容哈希去重，返回不重复的岗位列表",
            func=dedup_jobs,
            agent_group="search",
            args_schema=DedupInput,
        )

    if "html_parser" not in _tool_registry:
        _tool_registry["html_parser"] = ToolEntry(
            name="html_parser",
            description="抓取指定URL网页并提取正文文本内容",
            func=fetch_and_extract_html,
            agent_group="parse",
            is_async=True,
            args_schema=HtmlParseInput,
        )

    if "jd_structurer" not in _tool_registry:
        _tool_registry["jd_structurer"] = ToolEntry(
            name="jd_structurer",
            description="使用LLM将原始岗位描述文本结构化为标准JD格式（含技能、学历、职责等）",
            func=structure_jd,
            agent_group="parse",
            is_async=True,
            args_schema=JdStructureInput,
        )

    if "rule_filter" not in _tool_registry:
        _tool_registry["rule_filter"] = ToolEntry(
            name="rule_filter",
            description="按硬性条件（学历、地区）过滤岗位列表，返回通过筛选的岗位",
            func=batch_rule_filter,
            agent_group="match",
            args_schema=RuleFilterInput,
        )

    if "skill_matcher" not in _tool_registry:
        _tool_registry["skill_matcher"] = ToolEntry(
            name="skill_matcher",
            description="将岗位技能要求与用户技能进行精确+模糊匹配，返回匹配/缺失列表和匹配率",
            func=match_skills,
            agent_group="match",
            args_schema=SkillMatchInput,
        )

    if "keyword_optimizer" not in _tool_registry:
        _tool_registry["keyword_optimizer"] = ToolEntry(
            name="keyword_optimizer",
            description="使用LLM针对目标岗位优化简历关键词和措辞，返回修改对比",
            func=optimize_resume_keywords,
            agent_group="resume",
            is_async=True,
            args_schema=ResumeOptimizeInput,
        )

    if "tech_question_gen" not in _tool_registry:
        _tool_registry["tech_question_gen"] = ToolEntry(
            name="tech_question_gen",
            description="使用LLM生成技术面试题（含参考答案和评分标准）",
            func=generate_tech_questions,
            agent_group="interview",
            is_async=True,
            args_schema=TechQuestionInput,
        )

    if "behavior_question_gen" not in _tool_registry:
        _tool_registry["behavior_question_gen"] = ToolEntry(
            name="behavior_question_gen",
            description="使用LLM生成行为面试题（STAR格式，含追问和评分标准）",
            func=generate_behavior_questions,
            agent_group="interview",
            is_async=True,
            args_schema=BehaviorQuestionInput,
        )

    # Platform search tools
    if "boss_search" not in _tool_registry:
        from job_agent_os.tools.search.boss import BossAdapter

        async def _boss_search(keyword: str, region: str = "", company_type: str = "") -> list[dict]:
            adapter = BossAdapter()
            query = {"direction": keyword, "region": [region] if region else [], "company_type": [company_type] if company_type else []}
            return await adapter.search(query)

        _tool_registry["boss_search"] = ToolEntry(
            name="boss_search",
            description="在BOSS直聘平台搜索岗位",
            func=_boss_search,
            agent_group="search",
            is_async=True,
            args_schema=PlatformSearchInput,
        )

    if "guopin_search" not in _tool_registry:
        from job_agent_os.tools.search.guopin import GuopinAdapter

        async def _guopin_search(keyword: str, region: str = "", company_type: str = "") -> list[dict]:
            adapter = GuopinAdapter()
            query = {"direction": keyword, "region": [region] if region else [], "company_type": [company_type] if company_type else []}
            return await adapter.search(query)

        _tool_registry["guopin_search"] = ToolEntry(
            name="guopin_search",
            description="在国聘平台搜索国企/央企岗位",
            func=_guopin_search,
            agent_group="search",
            is_async=True,
            args_schema=PlatformSearchInput,
        )

    if "niuke_search" not in _tool_registry:
        from job_agent_os.tools.search.niuke import NiukeAdapter

        async def _niuke_search(keyword: str, region: str = "", company_type: str = "") -> list[dict]:
            adapter = NiukeAdapter()
            query = {"direction": keyword, "region": [region] if region else [], "company_type": [company_type] if company_type else []}
            return await adapter.search(query)

        _tool_registry["niuke_search"] = ToolEntry(
            name="niuke_search",
            description="在牛客平台搜索校招岗位",
            func=_niuke_search,
            agent_group="search",
            is_async=True,
            args_schema=PlatformSearchInput,
        )


def init_registry() -> None:
    """Initialize the tool registry: discover + register builtins."""
    discover_tools()
    register_builtin_tools()


# Auto-initialize on import
init_registry()
