"""Base Agent class with ReAct tool-calling loop.

Each agent is a ReAct agent that:
1. Receives a task from the Supervisor (via state)
2. Uses LLM with bound tools to decide actions
3. Calls tools, observes results, and iterates
4. Produces a final structured output to update the shared state
"""

import json
import logging
from abc import ABC, abstractmethod
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_openai import ChatOpenAI

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

    def _get_llm(self, use_fallback: bool = False) -> ChatOpenAI:
        """Get or create LLM instance."""
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

    def _build_react_executor(self) -> tuple[Any, Any, dict]:
        """Build ReAct executor: LLM with bound tools + tool lookup map.

        Returns:
            (llm_with_tools, llm_with_tools_fallback, tool_map)
            where tool_map is {name: StructuredTool}
        """
        llm = self._get_llm()
        llm_fallback = self._get_llm(use_fallback=True)
        tools = get_bindable_tools_by_names(self.agent_tools)
        tool_map = {t.name: t for t in tools}

        if tools:
            llm_with_tools = llm.bind_tools(tools)
            llm_with_tools_fallback = llm_fallback.bind_tools(tools)
        else:
            llm_with_tools = llm
            llm_with_tools_fallback = llm_fallback

        return llm_with_tools, llm_with_tools_fallback, tool_map

    async def execute(self, state: JobAgentState) -> dict:
        """Execute the agent using ReAct loop.

        Flow:
        1. Build initial messages (system prompt + task context)
        2. LLM decides: call a tool OR produce final answer
        3. If tool_call: execute tool, append ToolMessage, loop back to 2
        4. If final answer: parse output and return state update
        """
        llm_with_tools, llm_with_tools_fallback, tool_map = self._build_react_executor()
        messages = self._build_initial_messages(state)
        use_fallback = False
        retried = False

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
                }

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
                        result = await tool_fn.ainvoke(tool_args)
                        result_str = json.dumps(result, ensure_ascii=False, default=str)
                    except Exception as e:
                        logger.warning(f"[{self.name}] Tool '{tool_name}' failed: {e}")
                        result_str = json.dumps({"error": str(e)})

                messages.append(
                    ToolMessage(content=result_str, tool_call_id=tool_call_id, name=tool_name)
                )

        return self._parse_final_output(messages, state)

    @abstractmethod
    def _build_initial_messages(self, state: JobAgentState) -> list[BaseMessage]:
        """Build initial messages for the ReAct loop.

        Should include:
        - SystemMessage with the agent's role prompt
        - HumanMessage with the specific task (from Supervisor's task_instruction)
        """
        pass

    @abstractmethod
    def _parse_final_output(self, messages: list[BaseMessage], state: JobAgentState) -> dict:
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
                return msg.content
        return ""

    async def __call__(self, state: JobAgentState) -> dict:
        """Make agent callable as a LangGraph node."""
        return await self.execute(state)
