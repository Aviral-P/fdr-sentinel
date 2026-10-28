"""mark integrity findings system generated

Revision ID: e3b4a3935b14
Revises: 016290bb0ee6
Create Date: 2026-10-25 00:43:04.975690
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e3b4a3935b14'
down_revision: Union[str, None] = '016290bb0ee6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SQLite cannot add a non-native enum and its implicit check in one ALTER.
    with op.batch_alter_table('integrity_findings') as batch_op:
        batch_op.add_column(
            sa.Column('data_origin', sa.String(length=22), server_default='system_generated', nullable=False)
        )
        batch_op.create_check_constraint(
            'ck_integrity_finding_data_origin',
            "data_origin IN ('user_submitted', 'extracted', 'system_generated', 'independently_verified', 'synthetic_demo')",
        )


def downgrade() -> None:
    with op.batch_alter_table('integrity_findings') as batch_op:
        batch_op.drop_constraint('ck_integrity_finding_data_origin', type_='check')
        batch_op.drop_column('data_origin')
