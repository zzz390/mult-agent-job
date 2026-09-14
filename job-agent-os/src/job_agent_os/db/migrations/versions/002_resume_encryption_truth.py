"""Mark plaintext resumes honestly.

Revision ID: 002
Revises: 001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("UPDATE resumes SET is_encrypted = false WHERE is_encrypted = true")
    op.alter_column(
        "resumes", "is_encrypted", server_default=sa.text("false"), nullable=False
    )


def downgrade() -> None:
    op.alter_column(
        "resumes", "is_encrypted", server_default=sa.text("true"), nullable=False
    )
