"""add notification reason, due date and deduplication key

Revision ID: ab192c82d7e1
Revises: e3b4a3935b14
Create Date: 2026-10-25
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "ab192c82d7e1"
down_revision: Union[str, None] = "e3b4a3935b14"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("notifications") as batch_op:
        batch_op.add_column(sa.Column("reason", sa.String(length=120), server_default="legacy", nullable=False))
        batch_op.add_column(sa.Column("due_date", sa.Date(), nullable=True))
        batch_op.add_column(sa.Column("dedupe_key", sa.String(length=180), nullable=True))
        batch_op.create_index("ix_notifications_due_date", ["due_date"], unique=False)
        batch_op.create_unique_constraint("uq_notification_dedupe_key", ["dedupe_key"])


def downgrade() -> None:
    with op.batch_alter_table("notifications") as batch_op:
        batch_op.drop_constraint("uq_notification_dedupe_key", type_="unique")
        batch_op.drop_index("ix_notifications_due_date")
        batch_op.drop_column("dedupe_key")
        batch_op.drop_column("due_date")
        batch_op.drop_column("reason")
