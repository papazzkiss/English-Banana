"""access control: user role and status, teacher-student links, question review

Revision ID: 0004
Revises: 0003

Additive only. Every existing user becomes an active student (server defaults), so accounts,
sessions and progress are untouched. The first admin is set on the server:
`python -m banana_english.manage set-role <email> admin`.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import banana_english.infrastructure.database.tables

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("role", sa.String(length=16), server_default="student", nullable=False)
        )
        batch_op.add_column(
            sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False)
        )
        batch_op.create_index(batch_op.f("ix_users_role"), ["role"], unique=False)

    op.create_table(
        "teacher_students",
        sa.Column("teacher_id", sa.String(length=36), nullable=False),
        sa.Column("student_id", sa.String(length=36), nullable=False),
        sa.Column(
            "created_at",
            banana_english.infrastructure.database.tables.UTCDateTime(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["teacher_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("teacher_id", "student_id"),
    )
    with op.batch_alter_table("teacher_students", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_teacher_students_student_id"), ["student_id"], unique=False
        )

    with op.batch_alter_table("bank_questions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("reviewed_by", sa.String(length=36), nullable=True))
        batch_op.add_column(
            sa.Column(
                "reviewed_at",
                banana_english.infrastructure.database.tables.UTCDateTime(),
                nullable=True,
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("bank_questions", schema=None) as batch_op:
        batch_op.drop_column("reviewed_at")
        batch_op.drop_column("reviewed_by")

    with op.batch_alter_table("teacher_students", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_teacher_students_student_id"))
    op.drop_table("teacher_students")

    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_users_role"))
        batch_op.drop_column("is_active")
        batch_op.drop_column("role")
