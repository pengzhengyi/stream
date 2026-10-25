"""Create the linked_account table, and say whose login a Job uses.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-25 23:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import medleyplay.persistence.schema

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this revision."""
    op.create_table(
        "linked_account",
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("site", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("expires_at", medleyplay.persistence.schema.UtcDateTime(), nullable=True),
        sa.Column("saved_at", medleyplay.persistence.schema.UtcDateTime(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.CheckConstraint("revision >= 1", name=op.f("ck_linked_account_revision")),
        sa.CheckConstraint(
            "state IN ('valid', 'needs_sign_in')", name=op.f("ck_linked_account_state")
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["account.id"],
            name=op.f("fk_linked_account_account_id_account"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("account_id", "site", name=op.f("pk_linked_account")),
    )
    op.add_column("job", sa.Column("login_account_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    """Revert this revision."""
    op.drop_column("job", "login_account_id")
    op.drop_table("linked_account")
