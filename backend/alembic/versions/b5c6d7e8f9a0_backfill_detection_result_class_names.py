"""backfill PCB detection result class display names

Revision ID: b5c6d7e8f9a0
Revises: a4b5c6d7e8f9
Create Date: 2026-07-22
"""

from typing import Sequence, Union

from alembic import op


revision: str = "b5c6d7e8f9a0"
down_revision: Union[str, None] = "a4b5c6d7e8f9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE detection_results
        SET class_name_cn = CASE class_name
            WHEN 'missing_hole' THEN '漏孔'
            WHEN 'mouse_bite' THEN '鼠咬'
            WHEN 'open_circuit' THEN '断路'
            WHEN 'short' THEN '短路'
            WHEN 'spur' THEN '毛刺'
            WHEN 'spurious_copper' THEN '多余铜'
        END
        WHERE class_name_cn IS NULL
          AND class_name IN (
              'missing_hole', 'mouse_bite', 'open_circuit',
              'short', 'spur', 'spurious_copper'
          )
        """
    )


def downgrade() -> None:
    # 数据回填无法区分迁移前缺失值与迁移后新增值，回滚时保留已补齐的展示名称。
    pass
