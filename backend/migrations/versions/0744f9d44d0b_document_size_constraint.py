"""document size constraint

Revision ID: 0744f9d44d0b
Revises: 5c6c2e27c740
Create Date: 2026-10-24 23:18:54.402298
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0744f9d44d0b'
down_revision: Union[str, None] = '5c6c2e27c740'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SQLite needs batch mode to rebuild the table for a new constraint.
    with op.batch_alter_table('instrument_documents') as batch_op:
        batch_op.create_check_constraint('ck_document_size_positive', 'size_bytes > 0')
    with op.batch_alter_table('extracted_document_fields') as batch_op:
        batch_op.create_check_constraint(
            'ck_extracted_field_value_status',
            "value_status IN ('unknown', 'found', 'missing')",
        )


def downgrade() -> None:
    with op.batch_alter_table('instrument_documents') as batch_op:
        batch_op.drop_constraint('ck_document_size_positive', type_='check')
    with op.batch_alter_table('extracted_document_fields') as batch_op:
        batch_op.drop_constraint('ck_extracted_field_value_status', type_='check')
