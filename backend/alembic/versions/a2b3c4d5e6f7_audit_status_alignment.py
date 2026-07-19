"""normalize audit result status values

Revision ID: a2b3c4d5e6f7
Revises: f1b2c3d4e5f6
Create Date: 2026-07-17
"""

from typing import Sequence, Union

from alembic import op


revision: str = "a2b3c4d5e6f7"
down_revision: Union[str, None] = "f1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "UPDATE operation_logs SET status = 'failed' "
        "WHERE status IN ('failure', 'error')"
    )
    op.execute(
        "UPDATE operation_logs SET status = 'success' "
        "WHERE status IS NULL OR status NOT IN ('success', 'failed')"
    )
    op.create_check_constraint(
        "ck_operation_logs_status",
        "operation_logs",
        "status IN ('success','failed')",
    )
    op.execute(
        "COMMENT ON COLUMN operation_logs.status IS "
        "'操作结果：success/failed'"
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_operation_logs_status", "operation_logs", type_="check"
    )
    op.execute(
        "COMMENT ON COLUMN operation_logs.status IS "
        "'操作结果：success/failure'"
    )
