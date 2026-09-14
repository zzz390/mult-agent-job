"""Privacy helpers for content sent to external model providers."""

import re
from typing import Any

_EMAIL = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
_PHONE = re.compile(r"(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)")
_CN_ID = re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")


def redact_pii(value: Any) -> Any:
    """Recursively remove direct identifiers while preserving job evidence."""
    if isinstance(value, str):
        value = _EMAIL.sub("[REDACTED_EMAIL]", value)
        value = _PHONE.sub("[REDACTED_PHONE]", value)
        return _CN_ID.sub("[REDACTED_ID]", value)
    if isinstance(value, list):
        return [redact_pii(item) for item in value]
    if isinstance(value, dict):
        return {key: redact_pii(item) for key, item in value.items()}
    return value
