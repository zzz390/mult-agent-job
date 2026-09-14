"""Initial tables creation (10 tables).

Revision ID: 001
Revises: None
Create Date: 2025-01-01 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Enable pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # === users ===
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("username", sa.String(50), unique=True, nullable=False),
        sa.Column("email", sa.String(255), unique=True, nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("phone", sa.String(20), nullable=True),
        sa.Column("avatar_url", sa.String(500), nullable=True),
        sa.Column("preferences", postgresql.JSONB, server_default="{}"),
        sa.Column("job_intentions", postgresql.JSONB, server_default="[]"),
        sa.Column("subscription_config", postgresql.JSONB, server_default="{}"),
        sa.Column("token_budget_daily", sa.Integer, server_default="100000"),
        sa.Column("token_used_today", sa.Integer, server_default="0"),
        sa.Column("status", sa.String(20), server_default="active"),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # === resumes ===
    op.create_table(
        "resumes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("version", sa.String(20), server_default="v1"),
        sa.Column("raw_content", sa.Text, nullable=True),
        sa.Column("structured_data", postgresql.JSONB, server_default="{}"),
        sa.Column("file_path", sa.String(500), nullable=True),
        sa.Column("file_type", sa.String(20), nullable=True),
        sa.Column("file_size_bytes", sa.Integer, nullable=True),
        sa.Column("embedding", Vector(1024), nullable=True),
        sa.Column("chunks", postgresql.JSONB, server_default="[]"),
        sa.Column("target_direction", sa.String(100), nullable=True),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("is_encrypted", sa.Boolean, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # === jobs ===
    op.create_table(
        "jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("company", sa.String(300), nullable=False),
        sa.Column("company_type", sa.String(50), nullable=True),
        sa.Column("location", sa.String(200), nullable=True),
        sa.Column("industry", sa.String(100), nullable=True),
        sa.Column("source_platform", sa.String(50), nullable=False),
        sa.Column("source_url", sa.String(1000), nullable=False),
        sa.Column("raw_description", sa.Text, nullable=True),
        sa.Column("structured_jd", postgresql.JSONB, server_default="{}"),
        sa.Column("salary_range", sa.String(100), nullable=True),
        sa.Column("salary_min", sa.Integer, nullable=True),
        sa.Column("salary_max", sa.Integer, nullable=True),
        sa.Column("education_required", sa.String(50), nullable=True),
        sa.Column("experience_required", sa.String(100), nullable=True),
        sa.Column("skills_required", postgresql.ARRAY(sa.String), server_default="{}"),
        sa.Column("skills_preferred", postgresql.ARRAY(sa.String), server_default="{}"),
        sa.Column("headcount", sa.Integer, nullable=True),
        sa.Column("deadline", sa.Date, nullable=True),
        sa.Column("job_type", sa.String(50), nullable=True),
        sa.Column("status", sa.String(20), server_default="active"),
        sa.Column("embedding", Vector(1024), nullable=True),
        sa.Column("content_hash", sa.String(64), unique=True, nullable=True),
        sa.Column("crawled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # === applications ===
    op.create_table(
        "applications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("jobs.id"), nullable=False),
        sa.Column("resume_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("resumes.id"), nullable=False),
        sa.Column("optimized_resume_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("resumes.id"), nullable=True),
        sa.Column("status", sa.String(30), server_default="pending"),
        sa.Column("stage", sa.String(30), server_default="none"),
        sa.Column("match_score", sa.Float, nullable=True),
        sa.Column("match_report", postgresql.JSONB, nullable=True),
        sa.Column("recommendation_reason", sa.Text, nullable=True),
        sa.Column("priority", sa.String(10), server_default="medium"),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_follow_up", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_status_change", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status_history", postgresql.JSONB, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "job_id", name="uq_applications_user_job"),
    )

    # === prompt_versions ===
    op.create_table(
        "prompt_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("agent_name", sa.String(50), nullable=False),
        sa.Column("prompt_key", sa.String(100), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("system_prompt", sa.Text, nullable=False),
        sa.Column("user_prompt_template", sa.Text, nullable=False),
        sa.Column("variables_schema", postgresql.JSONB, server_default="{}"),
        sa.Column("output_schema", postgresql.JSONB, nullable=True),
        sa.Column("model_name", sa.String(100), nullable=False),
        sa.Column("temperature", sa.Float, server_default="0.1"),
        sa.Column("max_tokens", sa.Integer, server_default="4096"),
        sa.Column("top_p", sa.Float, server_default="1.0"),
        sa.Column("few_shot_examples", postgresql.JSONB, server_default="[]"),
        sa.Column("status", sa.String(20), server_default="draft"),
        sa.Column("changelog", sa.Text, nullable=True),
        sa.Column("eval_score", sa.Float, nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("agent_name", "prompt_key", "version", name="uq_prompt_version"),
    )

    # === agent_logs ===
    op.create_table(
        "agent_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("trace_id", sa.String(100), nullable=True),
        sa.Column("parent_log_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agent_logs.id"), nullable=True),
        sa.Column("agent_name", sa.String(50), nullable=False),
        sa.Column("node_name", sa.String(100), nullable=False),
        sa.Column("step_order", sa.Integer, nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("input_snapshot", postgresql.JSONB, nullable=True),
        sa.Column("output_snapshot", postgresql.JSONB, nullable=True),
        sa.Column("prompt_version_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("prompt_versions.id"), nullable=True),
        sa.Column("model_name", sa.String(100), nullable=True),
        sa.Column("prompt_tokens", sa.Integer, server_default="0"),
        sa.Column("completion_tokens", sa.Integer, server_default="0"),
        sa.Column("total_tokens", sa.Integer, server_default="0"),
        sa.Column("cost_usd", sa.Numeric(10, 6), server_default="0"),
        sa.Column("duration_ms", sa.Integer, nullable=True),
        sa.Column("retry_count", sa.Integer, server_default="0"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("error_type", sa.String(100), nullable=True),
        sa.Column("metadata", postgresql.JSONB, server_default="{}"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # === tool_calls ===
    op.create_table(
        "tool_calls",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("agent_log_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agent_logs.id"), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("tool_name", sa.String(100), nullable=False),
        sa.Column("tool_category", sa.String(50), nullable=False),
        sa.Column("call_order", sa.Integer, server_default="1"),
        sa.Column("input_params", postgresql.JSONB, nullable=False),
        sa.Column("output_result", postgresql.JSONB, nullable=True),
        sa.Column("output_summary", sa.Text, nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("duration_ms", sa.Integer, nullable=True),
        sa.Column("retry_count", sa.Integer, server_default="0"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("cache_hit", sa.Boolean, server_default="false"),
        sa.Column("tokens_consumed", sa.Integer, server_default="0"),
        sa.Column("called_at", sa.DateTime(timezone=True), nullable=False),
    )

    # === human_approvals ===
    op.create_table(
        "human_approvals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("agent_log_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agent_logs.id"), nullable=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("approval_type", sa.String(50), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("payload", postgresql.JSONB, nullable=False),
        sa.Column("options", postgresql.JSONB, server_default="[]"),
        sa.Column("priority", sa.String(10), server_default="normal"),
        sa.Column("status", sa.String(20), server_default="pending"),
        sa.Column("action", sa.String(20), nullable=True),
        sa.Column("feedback", sa.Text, nullable=True),
        sa.Column("modified_payload", postgresql.JSONB, nullable=True),
        sa.Column("timeout_seconds", sa.Integer, nullable=True),
        sa.Column("auto_action_on_timeout", sa.String(20), server_default="skip"),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # === memories ===
    op.create_table(
        "memories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("memory_type", sa.String(30), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("key", sa.String(200), nullable=False),
        sa.Column("content", postgresql.JSONB, nullable=False),
        sa.Column("content_text", sa.Text, nullable=True),
        sa.Column("embedding", Vector(1024), nullable=True),
        sa.Column("importance_score", sa.Float, server_default="0.5"),
        sa.Column("access_count", sa.Integer, server_default="0"),
        sa.Column("source_agent", sa.String(50), nullable=True),
        sa.Column("source_session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # === evaluations ===
    op.create_table(
        "evaluations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("agent_log_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agent_logs.id"), nullable=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("eval_type", sa.String(50), nullable=False),
        sa.Column("agent_name", sa.String(50), nullable=False),
        sa.Column("metric_name", sa.String(100), nullable=False),
        sa.Column("score", sa.Float, nullable=False),
        sa.Column("eval_input", postgresql.JSONB, nullable=True),
        sa.Column("eval_output", postgresql.JSONB, nullable=True),
        sa.Column("ground_truth", postgresql.JSONB, nullable=True),
        sa.Column("judge_method", sa.String(50), nullable=False),
        sa.Column("judge_model", sa.String(100), nullable=True),
        sa.Column("judge_reason", sa.Text, nullable=True),
        sa.Column("prompt_version_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("prompt_versions.id"), nullable=True),
        sa.Column("dataset_name", sa.String(100), nullable=True),
        sa.Column("batch_id", sa.String(100), nullable=True),
        sa.Column("status", sa.String(20), server_default="completed"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("evaluations")
    op.drop_table("memories")
    op.drop_table("human_approvals")
    op.drop_table("tool_calls")
    op.drop_table("agent_logs")
    op.drop_table("prompt_versions")
    op.drop_table("applications")
    op.drop_table("jobs")
    op.drop_table("resumes")
    op.drop_table("users")
    op.execute("DROP EXTENSION IF EXISTS vector")
