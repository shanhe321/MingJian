"""add structured report AIGC analysis

Revision ID: a4b5c6d7e8f9
Revises: a3b4c5d6e7f8
Create Date: 2026-07-18
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "a4b5c6d7e8f9"
down_revision: Union[str, None] = "a3b4c5d6e7f8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "detection_reports",
        sa.Column("aigc_analysis", postgresql.JSONB(), nullable=True, comment="基于检测证据生成的结构化 AIGC 解读"),
    )
    op.add_column(
        "detection_reports",
        sa.Column("aigc_analysis_source", sa.String(length=20), nullable=True, comment="AIGC 解读来源：agent/rules"),
    )
    op.add_column(
        "detection_reports",
        sa.Column("aigc_analysis_generated_at", sa.DateTime(), nullable=True, comment="AIGC 解读生成时间"),
    )


def downgrade() -> None:
    op.drop_column("detection_reports", "aigc_analysis_generated_at")
    op.drop_column("detection_reports", "aigc_analysis_source")
    op.drop_column("detection_reports", "aigc_analysis")
