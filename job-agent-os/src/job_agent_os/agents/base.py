"""Base Agent class with ReAct tool-calling loop.

Each agent is a ReAct agent that:
1. Receives a task from the Supervisor (via state)
2. Uses LLM with bound tools to decide actions
3. Calls tools, observes results, and iterates
4. Produces a final structured output to update the shared state
"""

import asyncio
import json
import logging
import threading
from abc import ABC, abstractmethod
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_openai import ChatOpenAI

from job_agent_os.core.llm_usage import (
    collect_message_usage,
    empty_token_usage,
    message_content_to_text,
)
from job_agent_os.graph.state import JobAgentState
from job_agent_os.settings import get_settings
from job_agent_os.tools.registry import get_bindable_tools_by_names

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """Base class for all ReAct agents.

    Each agent has:
    - A unique name
    - A system_prompt defining its role and capabilities
    - A list of agent_tools (tool names it can call via LLM function-calling)
    - A ReAct execution loop (LLM → tool_call → observe → repeat)
    """

    name: str = "base"
    system_prompt: str = ""
    agent_tools: list[str] = []
    max_iterations: int = 5  # Prevent infinite tool-calling loops

    def __init__(self) -> None:
        self._llm: ChatOpenAI | None = None
        self._llm_fallback: ChatOpenAI | None = None
        self._llm_lock = threading.Lock()

    def _get_llm(self, use_fallback: bool = False) -> ChatOpenAI:
        """Get or create LLM instance."""
        from job_agent_os.harness.recovery_manager import (
            is_fallback_model_requested,
        )

        use_fallback = use_fallback or is_fallback_model_requested()
        with self._llm_lock:
            if use_fallback:
                if self._llm_fallback is None:
                    settings = get_settings()
                    self._llm_fallback = ChatOpenAI(
                        model=settings.openai_model_fallback,
                        api_key=settings.openai_api_key.get_secret_value(),
                        base_url=settings.openai_base_url,
                        temperature=settings.openai_temperature,
                        max_tokens=settings.openai_max_tokens,
                        timeout=settings.openai_timeout,
                    )
                return self._llm_fallback

            if self._llm is None:
                settings = get_settings()
                self._llm = ChatOpenAI(
                    model=settings.openai_model,
                    api_key=settings.openai_api_key.get_secret_value(),
                    base_url=settings.openai_base_url,
                    temperature=settings.openai_temperature,
                    max_tokens=settings.openai_max_tokens,
                    timeout=settings.openai_timeout,
                )
            return self._llm

    def _get_tool_names(self, state: JobAgentState | None = None) -> list[str]:
        """Return tools available for this invocation."""
        return self.agent_tools

    def _build_react_executor(
        self, state: JobAgentState | None = None
    ) -> tuple[Any, Any, dict[str, Any]]:
        """Build ReAct executor: LLM with bound tools + tool lookup map.

        Returns:
            (llm_with_tools, llm_with_tools_fallback, tool_map)
            where tool_map is {name: StructuredTool}
        """
        llm = self._get_llm(
            use_fallback=bool((state or {}).get("use_fallback_model"))
        )
        llm_fallback = self._get_llm(use_fallback=True)
        tools = get_bindable_tools_by_names(self._get_tool_names(state))
        tool_map = {t.name: t for t in tools}

        if tools:
            llm_with_tools = llm.bind_tools(tools)
            llm_with_tools_fallback = llm_fallback.bind_tools(tools)
        else:
            llm_with_tools = llm
            llm_with_tools_fallback = llm_fallback

        return llm_with_tools, llm_with_tools_fallback, tool_map

    async def execute(self, state: JobAgentState) -> dict[str, Any]:
        """Execute the agent using ReAct loop.

        Flow:
        1. Build initial messages (system prompt + task context)
        2. LLM decides: call a tool OR produce final answer
        3. If tool_call: execute tool, append ToolMessage, loop back to 2
        4. If final answer: parse output and return state update

        Token usage from every LLM response is accumulated and attached
        to the returned state update (see issue #11: token accounting).
        """
        llm_with_tools, llm_with_tools_fallback, tool_map = self._build_react_executor(
            state
        )
        messages = self._build_initial_messages(state)
        # Hook for async pre-processing (e.g. long-term memory recall)
        messages = await self._prepare_messages(state, messages)
        use_fallback = False
        retried = False
        accumulated_usage = empty_token_usage()

        for iteration in range(self.max_iterations):
            active_llm = llm_with_tools_fallback if use_fallback else llm_with_tools
            try:
                response: AIMessage = await active_llm.ainvoke(messages)
            except Exception as e:
                logger.warning(f"[{self.name}] LLM call failed at iteration {iteration}: {e}")
                if not retried:
                    # Switch to fallback LLM and retry once
                    use_fallback = True
                    retried = True
                    logger.info(f"[{self.name}] Retrying with fallback LLM...")
                    continue
                # Retry exhausted — set error state and return
                return {
                    "current_phase": self.name,
                    "error_state": {
                        "error_type": type(e).__name__,
                        "error_message": str(e),
                        "retry_count": 1,
                    },
                    "execution_log": [
                        {"agent": self.name, "status": "failed", "error": str(e)}
                    ],
                    "token_usage": accumulated_usage,
                }

            # Collect token usage from this LLM response
            self._collect_usage(response, accumulated_usage)

            messages.append(response)

            # Check if LLM wants to call tools
            if not response.tool_calls:
                # LLM produced final answer — no more tool calls
                break

            # Execute all tool calls
            for tc in response.tool_calls:
                tool_name = tc["name"]
                tool_args = tc["args"]
                tool_call_id = tc["id"]

                tool_fn = tool_map.get(tool_name)
                if not tool_fn:
                    result_str = json.dumps({"error": f"Tool '{tool_name}' not found"})
                else:
                    try:
                        timeout = get_settings().harness_tool_timeout_seconds
                        async with asyncio.timeout(timeout):
                            result = await tool_fn.ainvoke(tool_args)
                        result_str = json.dumps(result, ensure_ascii=False, default=str)
                    except TimeoutError:
                        logger.warning(
                            "[%s] Tool '%s' timed out", self.name, tool_name
                        )
                        result_str = json.dumps(
                            {"error": f"Tool '{tool_name}' timed out after {timeout}s"}
                        )
                    except Exception as e:
                        logger.warning(f"[{self.name}] Tool '{tool_name}' failed: {e}")
                        result_str = json.dumps({"error": str(e)})

                messages.append(
                    ToolMessage(content=result_str, tool_call_id=tool_call_id, name=tool_name)
                )

        result = self._parse_final_output(messages, state)
        # Attach accumulated token usage so the state reducer can sum it up
        if isinstance(result, dict):
            result["token_usage"] = accumulated_usage
        return result

    @staticmethod
    def _collect_usage(
        response: AIMessage, accumulated: dict[str, int | float]
    ) -> None:
        """Accumulate token usage from an LLM response's usage_metadata."""
        try:
            collect_message_usage(response, accumulated)
        except (TypeError, ValueError):
            logger.debug("Skipping malformed usage_metadata")

    async def _prepare_messages(
        self, state: JobAgentState, messages: list[BaseMessage]
    ) -> list[BaseMessage]:
        """Async hook to enrich initial messages before the ReAct loop.

        Subclasses may override this to inject long-term memory context,
        retrieved documents, etc. Default implementation is a no-op.
        """
        return messages

    @abstractmethod
    def _build_initial_messages(self, state: JobAgentState) -> list[BaseMessage]:
        """Build initial messages for the ReAct loop.

        Should include:
        - SystemMessage with the agent's role prompt
        - HumanMessage with the specific task (from Supervisor's task_instruction)
        """
        pass

    @abstractmethod
    def _parse_final_output(
        self, messages: list[BaseMessage], state: JobAgentState
    ) -> dict[str, Any]:
        """Parse the ReAct conversation into a state update dict.

        Extracts meaningful results from tool call outputs and/or
        the LLM's final text response.
        """
        pass

    def _get_task_instruction(self, state: JobAgentState) -> str:
        """Get the task instruction from Supervisor."""
        return state.get("task_instruction", "")

    def _get_last_ai_content(self, messages: list[BaseMessage]) -> str:
        """Get the last AI message content (final answer text)."""
        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and msg.content and not msg.tool_calls:
                return message_content_to_text(msg.content)
        return ""

    async def __call__(self, state: JobAgentState) -> dict[str, Any]:
        """Make agent callable as a LangGraph node."""
        return await self.execute(state)
