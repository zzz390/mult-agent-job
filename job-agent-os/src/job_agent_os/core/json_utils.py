"""Robust JSON extraction utilities for LLM responses."""

import json
import logging
import re

logger = logging.getLogger(__name__)


def extract_json_object(text: str) -> dict:
    """Extract the first valid JSON object from LLM response text.

    Strategy:
    1. Try parsing the entire text as JSON
    2. Extract from ```json code blocks
    3. Use json.JSONDecoder.raw_decode to find valid JSON boundaries
    4. Raise ValueError if no valid JSON found
    """
    if not text or not text.strip():
        raise ValueError("Empty text, no JSON to extract")

    text = text.strip()

    # Strategy 1: Try direct parse
    try:
        result = json.loads(text)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass

    # Strategy 2: Extract from markdown code blocks
    code_block_match = re.search(r'```(?:json)?\s*\n?(\{.*?\})\s*\n?```', text, re.DOTALL)
    if code_block_match:
        try:
            result = json.loads(code_block_match.group(1))
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass

    # Strategy 3: Use raw_decode to find valid JSON object boundaries
    decoder = json.JSONDecoder()
    # Find the first '{' and try to decode from there
    for i, ch in enumerate(text):
        if ch == '{':
            try:
                result, end = decoder.raw_decode(text, i)
                if isinstance(result, dict):
                    return result
            except json.JSONDecodeError:
                continue

    raise ValueError(f"No valid JSON object found in text: {text[:200]}")


def extract_json_array(text: str) -> list:
    """Extract the first valid JSON array from LLM response text.

    Strategy:
    1. Try parsing the entire text as JSON
    2. Extract from ```json code blocks
    3. Use json.JSONDecoder.raw_decode to find valid JSON boundaries
    4. Raise ValueError if no valid JSON found
    """
    if not text or not text.strip():
        raise ValueError("Empty text, no JSON to extract")

    text = text.strip()

    # Strategy 1: Try direct parse
    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass

    # Strategy 2: Extract from markdown code blocks
    code_block_match = re.search(r'```(?:json)?\s*\n?(\[.*?\])\s*\n?```', text, re.DOTALL)
    if code_block_match:
        try:
            result = json.loads(code_block_match.group(1))
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass

    # Strategy 3: Use raw_decode to find valid JSON array boundaries
    decoder = json.JSONDecoder()
    for i, ch in enumerate(text):
        if ch == '[':
            try:
                result, end = decoder.raw_decode(text, i)
                if isinstance(result, list):
                    return result
            except json.JSONDecodeError:
                continue

    raise ValueError(f"No valid JSON array found in text: {text[:200]}")
