"""Small helpers for consistent token accounting across agents and tools."""

import json
from typing import Any


def empty_token_usage() -> dict[str, int | float]:
    return {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "cost_usd": 0.0,
    }


def collect_message_usage(message: Any, target: dict[str, int | float]) -> None:
    """Accumulate LangChain usage metadata into a mutable usage object."""
    usage = getattr(message, "usage_metadata", None)
    if not isinstance(usage, dict):
        return
    target["prompt_tokens"] = int(target.get("prompt_tokens", 0)) + int(
        usage.get("input_tokens", 0) or 0
    )
    target["completion_tokens"] = int(target.get("completion_tokens", 0)) + int(
        usage.get("output_tokens", 0) or 0
    )
    target["total_tokens"] = int(target.get("total_tokens", 0)) + int(
        usage.get("total_tokens", 0) or 0
    )


def merge_token_usage(
    *items: dict[str, int | float] | None,
) -> dict[str, int | float]:
    merged = empty_token_usage()
    for item in items:
        if not item:
            continue
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            merged[key] = int(merged[key]) + int(item.get(key, 0) or 0)
        merged["cost_usd"] = float(merged["cost_usd"]) + float(
            item.get("cost_usd", 0.0) or 0.0
        )
    return merged


def message_content_to_text(content: object) -> str:
    """Normalize LangChain's text-or-block message content to safe text."""
    if isinstance(content, str):
        return content
    return json.dumps(content, ensure_ascii=False, default=str)
