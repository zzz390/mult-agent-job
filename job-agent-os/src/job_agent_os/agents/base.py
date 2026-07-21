"""Base Agent class and protocol."""

from abc import ABC, abstractmethod
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from job_agent_os.graph.state import JobAgentState
from job_agent_os.prompts.loader import load_prompt
from job_agent_os.settings import get_settings


class BaseAgent(ABC):
    """Base class for all agents.

    Each agent has:
    - A unique name
    - A list of required tools
    - A prompt key for loading prompts
    - An execute method that processes state and returns partial state update
    """

    name: str = "base"
    required_tools: list[str] = []
    prompt_key: str = ""

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

    def _get_structured_llm(self, schema: type[BaseModel], use_fallback: bool = False) -> Any:
        """Get LLM with structured output binding."""
        llm = self._get_llm(use_fallback=use_fallback)
        return llm.with_structured_output(schema)

    def _build_messages(self, state: JobAgentState, **kwargs: Any) -> list[BaseMessage]:
        """Build messages for LLM call."""
        system_prompt, user_prompt = load_prompt(self.prompt_key, kwargs)
        return [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]

    @abstractmethod
    async def execute(self, state: JobAgentState) -> dict:
        """Execute the agent and return partial state update.

        Args:
            state: Current workflow state

        Returns:
            Dictionary with state updates
        """
        pass

    async def __call__(self, state: JobAgentState) -> dict:
        """Make agent callable as a LangGraph node."""
        return await self.execute(state)
