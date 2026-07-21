"""PromptVersion ORM model."""

from uuid import UUID

from sqlalchemy import Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from job_agent_os.models.base import Base, TimestampMixin, UUIDMixin


class PromptVersion(Base, UUIDMixin, TimestampMixin):
    """Prompt version management table."""

    __tablename__ = "prompt_versions"
    __table_args__ = (
        UniqueConstraint("agent_name", "prompt_key", "version", name="uq_prompt_version"),
    )

    agent_name: Mapped[str] = mapped_column(String(50), nullable=False)
    prompt_key: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    user_prompt_template: Mapped[str] = mapped_column(Text, nullable=False)
    variables_schema: Mapped[dict] = mapped_column(JSONB, default=dict)
    output_schema: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    temperature: Mapped[float] = mapped_column(Float, default=0.1)
    max_tokens: Mapped[int] = mapped_column(Integer, default=4096)
    top_p: Mapped[float] = mapped_column(Float, default=1.0)
    few_shot_examples: Mapped[list] = mapped_column(JSONB, default=list)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    changelog: Mapped[str | None] = mapped_column(Text, nullable=True)
    eval_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
