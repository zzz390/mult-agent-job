"""Tool registry (auto-discovery and grouping).

Provides:
- @register_tool decorator for registering tools
- Auto-discovery of tools in subdirectories
- Grouping tools by Agent name
- Conversion to LangChain Tool format
"""

import importlib
import pkgutil
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from langchain_core.tools import StructuredTool


@dataclass
class ToolEntry:
    """Registered tool metadata."""

    name: str
    description: str
    func: Callable
    agent_group: str
    is_async: bool = False
    tags: list[str] = field(default_factory=list)


# Global tool registry
_tool_registry: dict[str, ToolEntry] = {}


def register_tool(
    name: str,
    description: str = "",
    agent_group: str = "common",
    tags: list[str] | None = None,
) -> Callable:
    """Decorator to register a function as a tool.

    Args:
        name: Unique tool name
        description: Tool description (defaults to function docstring)
        agent_group: Which agent group this tool belongs to
        tags: Optional tags for categorization

    Usage:
        @register_tool(name="dedup", agent_group="search")
        def dedup_jobs(jobs: list[dict]) -> list[dict]:
            ...
    """

    def decorator(func: Callable) -> Callable:
        tool_description = description or (func.__doc__ or "").strip().split("\n")[0]
        is_async = importlib.util.find_spec("asyncio") is not None and (
            hasattr(func, "__wrapped__")
            or func.__class__.__name__ == "function"
            and _is_coroutine_function(func)
        )

        entry = ToolEntry(
            name=name,
            description=tool_description,
            func=func,
            agent_group=agent_group,
            is_async=_is_coroutine_function(func),
            tags=tags or [],
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


def to_langchain_tool(entry: ToolEntry) -> StructuredTool:
    """Convert a ToolEntry to a LangChain StructuredTool."""
    if entry.is_async:
        return StructuredTool.from_function(
            func=None,
            coroutine=entry.func,
            name=entry.name,
            description=entry.description,
        )
    return StructuredTool.from_function(
        func=entry.func,
        name=entry.name,
        description=entry.description,
    )


def get_langchain_tools(agent_name: str) -> list[StructuredTool]:
    """Get LangChain-formatted tools for a specific agent."""
    entries = get_tools_by_agent(agent_name)
    return [to_langchain_tool(entry) for entry in entries]


def discover_tools() -> None:
    """Auto-discover and import all tool modules in subdirectories.

    This imports all Python modules under tools/ subdirectories,
    which triggers @register_tool decorators.
    """
    import job_agent_os.tools as tools_pkg

    package_path = tools_pkg.__path__
    for importer, module_name, is_pkg in pkgutil.walk_packages(
        package_path, prefix="job_agent_os.tools."
    ):
        # Skip __init__ and registry itself
        if module_name.endswith("__init__") or module_name.endswith("registry"):
            continue
        try:
            importlib.import_module(module_name)
        except Exception:
            pass  # Skip modules that fail to import


def register_builtin_tools() -> None:
    """Manually register built-in tools that aren't decorated."""
    from job_agent_os.tools.common.dedup import dedup_jobs
    from job_agent_os.tools.interview.behavior_question_gen import generate_behavior_questions
    from job_agent_os.tools.interview.tech_question_gen import generate_tech_questions
    from job_agent_os.tools.match.rule_filter import batch_rule_filter
    from job_agent_os.tools.match.skill_matcher import compute_skill_score, match_skills
    from job_agent_os.tools.parse.html_parser import fetch_and_extract_html
    from job_agent_os.tools.parse.jd_structurer import structure_jd
    from job_agent_os.tools.resume.keyword_optimizer import optimize_resume_keywords

    # Search tools
    if "dedup" not in _tool_registry:
        _tool_registry["dedup"] = ToolEntry(
            name="dedup",
            description="Deduplicate jobs based on content hash",
            func=dedup_jobs,
            agent_group="search",
        )

    # Parse tools
    if "html_parser" not in _tool_registry:
        _tool_registry["html_parser"] = ToolEntry(
            name="html_parser",
            description="Fetch a URL and extract main text content",
            func=fetch_and_extract_html,
            agent_group="parse",
            is_async=True,
        )
    if "jd_structurer" not in _tool_registry:
        _tool_registry["jd_structurer"] = ToolEntry(
            name="jd_structurer",
            description="Structure raw JD text into parsed format using LLM",
            func=structure_jd,
            agent_group="parse",
            is_async=True,
        )

    # Match tools
    if "rule_filter" not in _tool_registry:
        _tool_registry["rule_filter"] = ToolEntry(
            name="rule_filter",
            description="Filter jobs by hard constraints (education, location)",
            func=batch_rule_filter,
            agent_group="match",
        )
    if "skill_matcher" not in _tool_registry:
        _tool_registry["skill_matcher"] = ToolEntry(
            name="skill_matcher",
            description="Match job skills against user skills (exact + fuzzy)",
            func=match_skills,
            agent_group="match",
        )

    # Resume tools
    if "keyword_optimizer" not in _tool_registry:
        _tool_registry["keyword_optimizer"] = ToolEntry(
            name="keyword_optimizer",
            description="Optimize resume keywords for target JD using LLM",
            func=optimize_resume_keywords,
            agent_group="resume",
            is_async=True,
        )

    # Interview tools
    if "tech_question_gen" not in _tool_registry:
        _tool_registry["tech_question_gen"] = ToolEntry(
            name="tech_question_gen",
            description="Generate technical interview questions using LLM",
            func=generate_tech_questions,
            agent_group="interview",
            is_async=True,
        )
    if "behavior_question_gen" not in _tool_registry:
        _tool_registry["behavior_question_gen"] = ToolEntry(
            name="behavior_question_gen",
            description="Generate behavioral interview questions (STAR) using LLM",
            func=generate_behavior_questions,
            agent_group="interview",
            is_async=True,
        )


def init_registry() -> None:
    """Initialize the tool registry: discover + register builtins."""
    discover_tools()
    register_builtin_tools()


# Auto-initialize on import
init_registry()
