"""accounts and sessions (authentication)

Revision ID: 0002
Revises: 0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import banana_english.infrastructure.database.tables

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "accounts",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            banana_english.infrastructure.database.tables.UTCDateTime(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("user_id"),
    )
    with op.batch_alter_table("accounts", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_accounts_email"), ["email"], unique=True)

    op.create_table(
        "sessions",
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column(
            "created_at",
            banana_english.infrastructure.database.tables.UTCDateTime(),
            nullable=False,
        ),
        sa.Column(
            "expires_at",
            banana_english.infrastructure.database.tables.UTCDateTime(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("token_hash"),
    )
    with op.batch_alter_table("sessions", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_sessions_user_id"), ["user_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("sessions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_sessions_user_id"))

    op.drop_table("sessions")
    with op.batch_alter_table("accounts", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_accounts_email"))

    op.drop_table("accounts")
