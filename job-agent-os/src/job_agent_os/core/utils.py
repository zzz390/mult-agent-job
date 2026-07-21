"""Common utility functions."""

from datetime import UTC, datetime
from uuid import UUID, uuid4


def generate_uuid() -> str:
    """Generate a new UUID string."""
    return str(uuid4())


def generate_uuid_obj() -> UUID:
    """Generate a new UUID object."""
    return uuid4()


def utc_now() -> datetime:
    """Get current UTC datetime."""
    return datetime.now(UTC)


def truncate_text(text: str, max_len: int = 500, suffix: str = "...") -> str:
    """Truncate text to a maximum length."""
    if len(text) <= max_len:
        return text
    return text[: max_len - len(suffix)] + suffix


def mask_email(email: str) -> str:
    """Mask email for privacy (e.g., z***@example.com)."""
    parts = email.split("@")
    if len(parts) != 2:
        return email
    name = parts[0]
    if len(name) <= 1:
        masked_name = name
    else:
        masked_name = name[0] + "*" * (len(name) - 1)
    return f"{masked_name}@{parts[1]}"


def mask_phone(phone: str) -> str:
    """Mask phone number for privacy (e.g., 138****1234)."""
    if len(phone) < 7:
        return phone
    return phone[:3] + "****" + phone[-4:]
