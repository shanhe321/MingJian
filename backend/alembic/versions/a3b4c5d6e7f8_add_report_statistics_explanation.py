"""add report statistics explanation

Revision ID: a3b4c5d6e7f8
Revises: a2b3c4d5e6f7
Create Date: 2026-07-18
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a3b4c5d6e7f8"
down_revision: Union[str, None] = "a2b3c4d5e6f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("detection_reports", sa.Column("statistics_explanation", sa.Text(), nullable=True, comment="结果统计解读"))
    op.add_column("detection_reports", sa.Column("statistics_explanation_source", sa.String(length=20), nullable=True, comment="统计解读来源：agent/rules"))
    op.add_column("detection_reports", sa.Column("statistics_explanation_generated_at", sa.DateTime(), nullable=True, comment="统计解读生成时间"))


def downgrade() -> None:
    op.drop_column("detection_reports", "statistics_explanation_generated_at")
    op.drop_column("detection_reports", "statistics_explanation_source")
    op.drop_column("detection_reports", "statistics_explanation")
