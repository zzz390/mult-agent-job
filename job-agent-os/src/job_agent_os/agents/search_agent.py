"""Search Agent - Search jobs from database and external platforms (ReAct mode).

Strategy:
1. Discover state-owned enterprises from a city SASAC/government directory
2. Search those enterprises' official sites for verifiable recruitment pages
3. Use Guopin/local cache only when the official path has no usable result

Issue #2 (agent consolidation):
- Official-site discovery and third-party fallback now run inside this agent
  instead of round-tripping through the Supervisor.
- Search results are structured into standard JD format in-place
  (formerly the separate `parse` agent), so the Supervisor no longer needs
  to route search -> parse.
"""

import asyncio
import json
import logging
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, ToolMessage

from job_agent_os.agents.base import BaseAgent
from job_agent_os.core.llm_usage import (
    empty_token_usage,
    merge_token_usage,
    message_content_to_text,
)
from job_agent_os.graph.state import JobAgentState
from job_agent_os.settings import get_settings

logger = logging.getLogger(__name__)

_THIRD_PARTY_PLATFORM_ALIASES = {
    "boss": "boss",
    "boss直聘": "boss",
    "guopin": "guopin",
    "国聘": "guopin",
    "niuke": "niuke",
    "牛客": "niuke",
}

SEARCH_SYSTEM_PROMPT = """你是岗位搜索专家。根据用户的求职意向，搜索匹配的岗位。

默认主链路已在调用你之前执行：城市国资委/政府国企名录 → 企业官网招聘页。
只有官网主链路没有结果，或者用户明确指定平台时，才使用下面的辅助工具。

你可以使用以下工具：
1. query_jobs_db - 从数据库查询已有岗位（支持按关键词、地区、企业类型筛选）
2. boss_search - 在BOSS直聘平台搜索岗位
3. guopin_search - 在国聘平台搜索国企/央企岗位
4. niuke_search - 在牛客平台搜索校招岗位
5. dedup - 对岗位列表按内容哈希去重
6. save_jobs_db - 将新岗位批量存入数据库

搜索策略：
1. 用户未指定第三方平台时，优先使用国聘作为国企岗位辅助来源
2. BOSS/牛客仅在用户明确指定时使用；遇到验证码直接停止该来源
3. 对外部搜索结果调用 dedup 去重
4. 将有真实来源URL的新岗位调用 save_jobs_db 存入数据库

最终输出：将所有搜索到的岗位以JSON数组格式输出。"""


class SearchAgent(BaseAgent):
    """Search Agent searches for jobs using database + external platforms (ReAct).

    Also embeds two former standalone steps (issue #2):
    - deterministic official-site search and auxiliary fallback
    - in-place JD structuring (parse) of the results
    """

    name = "search"
    system_prompt = SEARCH_SYSTEM_PROMPT
    agent_tools = ["query_jobs_db", "boss_search", "guopin_search", "niuke_search", "dedup", "save_jobs_db"]
    max_iterations = 6

    # How many search results to structure in-place (parse step)
    max_jobs_to_parse = 15

    def _get_tool_names(self, state: JobAgentState | None = None) -> list[str]:
        """Honor the platform allow-list supplied by the API caller."""
        common = ["query_jobs_db", "dedup", "save_jobs_db"]
        requested = {
            str(item).strip().lower() for item in (state or {}).get("requested_platforms", []) if str(item).strip()
        }
        if not requested:
            company_types = {
                str(item).strip() for item in ((state or {}).get("job_query") or {}).get("company_type", []) if item
            }
            if not company_types or company_types & {
                "国企",
                "央企",
                "国有企业",
                "中央企业",
            }:
                return common + ["guopin_search"]
            return self.agent_tools
        platform_tools = {
            "boss": "boss_search",
            "boss直聘": "boss_search",
            "guopin": "guopin_search",
            "国聘": "guopin_search",
            "niuke": "niuke_search",
            "牛客": "niuke_search",
        }
        return common + list(dict.fromkeys(platform_tools[item] for item in requested if item in platform_tools))

    async def execute(self, state: JobAgentState) -> dict[str, Any]:
        """Run deterministic official-first search, then optional auxiliaries."""
        requested = self._normalized_requested_platforms(state)
        web_aliases = {"web", "website", "company", "company_website", "官网"}
        third_party_aliases = set(_THIRD_PARTY_PLATFORM_ALIASES)
        requested_platforms = self._requested_third_party_platforms(state)

        official_result: dict[str, Any] | None = None
        # Explicitly selected, independent sources may run together.  Each
        # adapter still takes a process-wide single-flight slot for its own
        # platform and keeps its existing 5-rpm limit, so this never increases
        # same-site pressure (notably for BOSS and Niuke).
        if len(requested_platforms) > 1 and requested <= third_party_aliases:
            result = await self._search_requested_platforms(state, requested_platforms)
        elif self._should_search_official(state, requested, web_aliases):
            official_result = await self._official_first_search(state)
            has_explicit_third_party = bool(requested & third_party_aliases)
            if (official_result.get("search_results") and not has_explicit_third_party) or (
                requested and requested <= web_aliases
            ):
                result = official_result
            elif has_explicit_third_party:
                result = self._merge_search_results(official_result, await super().execute(state))
            else:
                result = self._merge_search_results(official_result, await self._default_auxiliary_search(state))
        else:
            result = await super().execute(state)

        jobs_to_persist = result.get("search_results") or []
        if jobs_to_persist:
            await self._publish_search_progress(
                state,
                activity_message=f"正在保存已发现的 {len(jobs_to_persist)} 条岗位",
                items_found=len(jobs_to_persist),
            )

        result = await self._persist_verified_results(result)
        saved_count = result.pop("_progress_items_saved", None)
        if jobs_to_persist:
            canonical_count = len(result.get("search_results") or [])
            if saved_count is None:
                await self._publish_search_progress(
                    state,
                    activity_message="岗位保存暂未完成，继续处理已发现的岗位",
                    items_found=canonical_count,
                )
            else:
                await self._publish_search_progress(
                    state,
                    activity_message=f"岗位保存完成，新增 {saved_count} 条岗位",
                    items_found=canonical_count,
                    items_saved=saved_count,
                )
        result = await self._maybe_parse_inline(state, result)
        return result

    @staticmethod
    def _normalized_requested_platforms(state: JobAgentState) -> set[str]:
        return {str(item).strip().lower() for item in state.get("requested_platforms", []) if str(item).strip()}

    @staticmethod
    def _requested_third_party_platforms(state: JobAgentState) -> list[str]:
        """Return explicitly requested third-party platforms in UI order."""
        platforms: list[str] = []
        for item in state.get("requested_platforms", []):
            platform = _THIRD_PARTY_PLATFORM_ALIASES.get(str(item).strip().lower())
            if platform and platform not in platforms:
                platforms.append(platform)
        return platforms

    async def _search_requested_platforms(
        self, state: JobAgentState, platforms: list[str]
    ) -> dict[str, Any]:
        """Search explicitly selected, independent platforms concurrently.

        The fan-out is deliberately capped by the three supported platforms.
        Same-platform requests are serialized inside ``PlatformAdapter`` so a
        second session cannot overlap a BOSS/Niuke browser request.
        """
        from job_agent_os.tools.search.boss import BossAdapter
        from job_agent_os.tools.search.guopin import GuopinAdapter
        from job_agent_os.tools.search.niuke import NiukeAdapter

        adapters: dict[
            str, type[BossAdapter] | type[GuopinAdapter] | type[NiukeAdapter]
        ] = {
            "boss": BossAdapter,
            "guopin": GuopinAdapter,
            "niuke": NiukeAdapter,
        }
        query = dict(state.get("job_query") or {})

        async def search_one(
            platform: str,
        ) -> tuple[str, list[dict[str, Any]], str | None]:
            try:
                jobs = await adapters[platform]().search(dict(query))
                return platform, jobs, None
            except Exception as exc:  # noqa: BLE001 - one source must not stop peers
                logger.warning("[search] %s explicit search failed: %s", platform, exc)
                return platform, [], str(exc)

        outcomes = await asyncio.gather(*(search_one(platform) for platform in platforms))
        jobs: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()
        for platform, platform_jobs, error in outcomes:
            if error:
                errors.append({"tool": f"{platform}_search", "error": error})
            for job in platform_jobs:
                if not isinstance(job, dict):
                    continue
                key = (
                    str(job.get("source_url") or ""),
                    str(job.get("company") or ""),
                    str(job.get("title") or ""),
                )
                if key in seen:
                    continue
                seen.add(key)
                jobs.append(job)

        return {
            "current_phase": "search",
            "search_results": jobs,
            "search_errors": errors,
            "platforms_searched": platforms,
            "token_usage": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "cost_usd": 0.0,
            },
        }

    @staticmethod
    def _should_search_official(
        state: JobAgentState,
        requested: set[str],
        web_aliases: set[str],
    ) -> bool:
        if requested and not requested.intersection(web_aliases):
            return False
        company_types = {str(item).strip() for item in (state.get("job_query") or {}).get("company_type", []) if item}
        state_owned = {"国企", "央企", "国有企业", "中央企业"}
        return not company_types or bool(company_types & state_owned)

    @staticmethod
    async def _publish_search_progress(
        state: JobAgentState,
        *,
        activity_message: str,
        items_found: int | None = None,
        items_saved: int | None = None,
    ) -> None:
        """Send safe search activity to the session store without blocking work."""
        try:
            from job_agent_os.services.session_progress import publish_search_progress

            await publish_search_progress(
                str(state.get("session_id") or ""),
                activity_message=activity_message,
                items_found=items_found,
                items_saved=items_saved,
            )
        except Exception:  # noqa: BLE001
            # The helper itself catches store errors.  This outer boundary also
            # protects crawling if progress wiring/imports ever regress.
            logger.debug("Unable to publish SearchAgent progress", exc_info=True)

    async def _official_first_search(
        self, state: JobAgentState
    ) -> dict[str, Any]:
        from job_agent_os.tools.search.official import search_official_soe_jobs

        async def report_progress(**progress: object) -> None:
            found = progress.get("items_found")
            saved = progress.get("items_saved")
            await self._publish_search_progress(
                state,
                activity_message=str(progress.get("activity_message") or "正在查询官网招聘信息"),
                items_found=found if isinstance(found, int) else None,
                items_saved=saved if isinstance(saved, int) else None,
            )

        outcome = await search_official_soe_jobs(
            state.get("job_query") or {}, progress_callback=report_progress
        )
        return {
            "current_phase": "search",
            "search_results": outcome.jobs,
            "search_errors": [{"tool": "official_soe_web", "error": error} for error in outcome.errors],
            "platforms_searched": ["official_soe_web"],
            "token_usage": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "cost_usd": 0.0,
            },
        }

    async def _default_auxiliary_search(
        self, state: JobAgentState
    ) -> dict[str, Any]:
        """Use Guopin, then the local cache, after the official path is empty."""
        query = dict(state.get("job_query") or {})
        if not query.get("company_type"):
            query["company_type"] = ["国企", "央企"]
        errors: list[dict[str, Any]] = []
        platforms = ["guopin"]
        jobs: list[dict[str, Any]] = []

        try:
            from job_agent_os.tools.search.guopin import GuopinAdapter

            jobs = await GuopinAdapter().search(query)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[search] Guopin auxiliary search failed: %s", exc)
            errors.append({"tool": "guopin_search", "error": str(exc)})

        if not jobs:
            platforms.append("database")
            try:
                from job_agent_os.tools.common.db_tools import query_jobs_db

                regions = query.get("region") or []
                jobs = await query_jobs_db(
                    keyword=str(query.get("direction") or ""),
                    region=str(regions[0]) if regions else "",
                    company_type="国企",
                    limit=20,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("[search] Local cache lookup failed: %s", exc)
                errors.append({"tool": "query_jobs_db", "error": str(exc)})

        return {
            "current_phase": "search",
            "search_results": jobs,
            "search_errors": errors,
            "platforms_searched": platforms,
            "token_usage": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "cost_usd": 0.0,
            },
        }

    @staticmethod
    def _merge_search_results(
        primary: dict[str, Any], secondary: dict[str, Any]
    ) -> dict[str, Any]:
        jobs: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()
        for job in list(primary.get("search_results", [])) + list(secondary.get("search_results", [])):
            key = (
                str(job.get("source_url") or ""),
                str(job.get("company") or ""),
                str(job.get("title") or ""),
            )
            if key in seen:
                continue
            seen.add(key)
            jobs.append(job)
        return {
            **primary,
            "current_phase": "search",
            "search_results": jobs,
            "search_errors": list(primary.get("search_errors", [])) + list(secondary.get("search_errors", [])),
            "platforms_searched": list(
                dict.fromkeys(
                    list(primary.get("platforms_searched", [])) + list(secondary.get("platforms_searched", []))
                )
            ),
            "token_usage": secondary.get("token_usage", primary.get("token_usage", {})),
        }

    async def _persist_verified_results(
        self, result: dict[str, Any]
    ) -> dict[str, Any]:
        """Persist sourced jobs deterministically instead of trusting the LLM."""
        jobs = result.get("search_results", [])
        if not jobs:
            return result
        try:
            from job_agent_os.tools.common.db_tools import persist_jobs_db_with_count

            result["search_results"], result["_progress_items_saved"] = await persist_jobs_db_with_count(jobs)
        except Exception as e:  # noqa: BLE001
            logger.warning("[search] Deterministic job persistence failed: %s", e)
            result.setdefault("search_errors", []).append({"tool": "persist_jobs_db", "error": str(e)})
        return result

    async def _maybe_parse_inline(
        self, state: JobAgentState, result: dict[str, Any]
    ) -> dict[str, Any]:
        """Structure search results in-place (formerly the separate parse agent)."""
        raw_jobs = result.get("search_results", [])
        already_parsed = state.get("parsed_jobs") or result.get("parsed_jobs")
        if not raw_jobs or already_parsed:
            return result

        try:
            from job_agent_os.tools.parse.jd_structurer import structure_jds_parallel

            jobs_to_parse = raw_jobs[: self.max_jobs_to_parse]
            await self._publish_search_progress(
                state,
                activity_message=f"正在解析 {len(jobs_to_parse)} 条岗位信息",
                items_found=len(raw_jobs),
            )
            parse_usage = empty_token_usage()
            async with asyncio.timeout(
                get_settings().harness_tool_timeout_seconds
            ):
                parsed_jobs, parse_failures = await structure_jds_parallel(
                    jobs_to_parse,
                    use_fallback=bool(state.get("use_fallback_model")),
                    usage_sink=parse_usage,
                )
            result["parsed_jobs"] = parsed_jobs
            result["parse_failures"] = parse_failures
            result["token_usage"] = merge_token_usage(
                result.get("token_usage"), parse_usage
            )
            await self._publish_search_progress(
                state,
                activity_message=f"已完成 {len(parsed_jobs)} 条岗位信息解析",
                items_found=len(raw_jobs),
            )
        except Exception as e:  # noqa: BLE001
            # Keep the pipeline moving with source fields intact. Re-running
            # Search would repeat external requests and the standalone Parse
            # node is deliberately not routable in the six-agent graph.
            logger.warning("[search] Inline parse failed, using passthrough JDs: %s", e)
            result["parsed_jobs"] = [
                {**job, "parse_confidence": 0.0, "parse_note": "fallback_unparsed"}
                for job in raw_jobs[: self.max_jobs_to_parse]
                if isinstance(job, dict)
            ]
            result["parse_failures"] = [
                str(job.get("source_url") or job.get("title") or "unknown")
                for job in raw_jobs[: self.max_jobs_to_parse]
                if isinstance(job, dict)
            ]
            result.setdefault("search_errors", []).append(
                {"tool": "jd_structurer", "error": str(e)}
            )
        return result

    def _build_initial_messages(self, state: JobAgentState) -> list[BaseMessage]:
        """Build search task from job_query."""
        job_query = state.get("job_query", {})
        task = self._get_task_instruction(state)

        query_desc = json.dumps(job_query, ensure_ascii=False) if job_query else "未指定"
        content = f"请搜索符合以下求职条件的岗位：\n{query_desc}"
        requested = state.get("requested_platforms", [])
        if requested:
            content += f"\n仅允许搜索这些平台：{json.dumps(requested, ensure_ascii=False)}"
        if task:
            content += f"\n\nSupervisor 补充指令：{task}"

        return [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=content),
        ]

    def _parse_final_output(
        self, messages: list[BaseMessage], state: JobAgentState
    ) -> dict[str, Any]:
        """Extract search results from tool call outputs."""
        all_jobs: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        platforms_searched: list[str] = []

        # Collect results from all tool messages
        for msg in messages:
            if not isinstance(msg, ToolMessage):
                continue
            tool_name = getattr(msg, "name", "")
            try:
                data = json.loads(message_content_to_text(msg.content))
            except (json.JSONDecodeError, TypeError):
                continue

            # Handle error responses
            if isinstance(data, dict) and "error" in data:
                errors.append({"tool": tool_name or "unknown", "error": data["error"]})
                continue

            # query_jobs_db returns list of jobs
            if isinstance(data, list):
                all_jobs.extend(data)
                # Map tool name to platform name
                platform_map = {
                    "query_jobs_db": "database",
                    "boss_search": "boss",
                    "guopin_search": "guopin",
                    "niuke_search": "niuke",
                }
                platform = platform_map.get(tool_name)
                if platform and platform not in platforms_searched:
                    platforms_searched.append(platform)
            elif isinstance(data, int):
                # save_jobs_db returns count
                pass

        # Also try to parse from the final AI message (in case LLM summarized)
        if not all_jobs:
            content = self._get_last_ai_content(messages)
            if content:
                try:
                    if "[" in content:
                        json_str = content[content.index("[") : content.rindex("]") + 1]
                        parsed = json.loads(json_str)
                        if isinstance(parsed, list):
                            all_jobs = parsed
                except (json.JSONDecodeError, ValueError):
                    pass

        return {
            "current_phase": "search",
            "search_results": all_jobs,
            "search_errors": errors,
            "platforms_searched": platforms_searched or ["none"],
        }


# Singleton instance
search_agent = SearchAgent()
