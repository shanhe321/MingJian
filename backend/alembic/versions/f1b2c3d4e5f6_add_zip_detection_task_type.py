"""allow ZIP as an explicit detection task type

Revision ID: f1b2c3d4e5f6
Revises: f0a1b2c3d4e5
Create Date: 2026-07-17
"""

from typing import Sequence, Union

from alembic import op


revision: str = "f1b2c3d4e5f6"
down_revision: Union[str, None] = "f0a1b2c3d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_detection_tasks_task_type", "detection_tasks", type_="check"
    )
    op.create_check_constraint(
        "ck_detection_tasks_task_type",
        "detection_tasks",
        "task_type IN ('single','batch','folder','zip','video','camera')",
    )
    op.execute(
        "COMMENT ON COLUMN detection_tasks.task_type IS "
        "'检测类型：single/batch/folder/zip/video/camera'"
    )


def downgrade() -> None:
    # 旧约束不识别 zip；回滚时保留任务并降级为兼容的 batch 类型。
    op.execute("UPDATE detection_tasks SET task_type = 'batch' WHERE task_type = 'zip'")
    op.drop_constraint(
        "ck_detection_tasks_task_type", "detection_tasks", type_="check"
    )
    op.create_check_constraint(
        "ck_detection_tasks_task_type",
        "detection_tasks",
        "task_type IN ('single','batch','folder','video','camera')",
    )
    op.execute(
        "COMMENT ON COLUMN detection_tasks.task_type IS "
        "'检测类型：single/batch/folder/video/camera'"
    )
