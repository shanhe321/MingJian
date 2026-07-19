"""align PostgreSQL JSONB, bootstrap scene and FK indexes

Revision ID: f0a1b2c3d4e5
Revises: e9f0a1b2c3d4
Create Date: 2026-07-17
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f0a1b2c3d4e5"
down_revision: Union[str, None] = "e9f0a1b2c3d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


JSON_COLUMNS = (
    ("detection_scenes", "class_names"),
    ("detection_scenes", "class_names_cn"),
    ("dataset_annotations", "bbox"),
    ("detection_results", "bbox"),
    ("training_tasks", "augment_config"),
    ("model_versions", "per_class_ap"),
    ("chat_messages", "tool_calls"),
)


def upgrade() -> None:
    for table, column in JSON_COLUMNS:
        op.execute(
            f'ALTER TABLE "{table}" ALTER COLUMN "{column}" '
            f'TYPE jsonb USING "{column}"::jsonb'
        )

    op.create_index("ix_dashboard_snapshots_scene_id", "dashboard_snapshots", ["scene_id"])
    op.create_index("ix_dashboard_snapshots_user_id", "dashboard_snapshots", ["user_id"])
    op.create_index(
        "ix_dataset_annotations_created_by",
        "dataset_annotations",
        ["created_by"],
        postgresql_where=sa.text("created_by IS NOT NULL"),
    )
    op.create_index(
        "ix_detection_scenes_created_by",
        "detection_scenes",
        ["created_by"],
        postgresql_where=sa.text("created_by IS NOT NULL"),
    )
    op.create_index(
        "ix_detection_tasks_model_version_id",
        "detection_tasks",
        ["model_version_id"],
        postgresql_where=sa.text("model_version_id IS NOT NULL"),
    )
    op.create_index(
        "ix_training_tasks_dataset_project_id",
        "training_tasks",
        ["dataset_project_id"],
        postgresql_where=sa.text("dataset_project_id IS NOT NULL"),
    )
    op.create_index(
        "ix_detection_results_item_task",
        "detection_results",
        ["item_id", "task_id"],
        postgresql_where=sa.text("item_id IS NOT NULL"),
    )

    # 空库必须具备可用 PCB 场景，否则注册后的普通用户无法创建数据集或检测。
    op.execute(
        """
        INSERT INTO detection_scenes
            (name, display_name, description, category, class_names,
             class_names_cn, is_active, created_at, updated_at)
        SELECT
            'pcb_defect', 'PCB缺陷检测', '系统内置 PCB 六类缺陷检测场景', 'industry',
            '["missing_hole","mouse_bite","open_circuit","short","spur","spurious_copper"]'::jsonb,
            '{"missing_hole":"漏孔","mouse_bite":"鼠咬","open_circuit":"断路","short":"短路","spur":"毛刺","spurious_copper":"多余铜"}'::jsonb,
            TRUE, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        WHERE NOT EXISTS (SELECT 1 FROM detection_scenes WHERE is_active IS TRUE)
        """
    )


def downgrade() -> None:
    # 默认场景可能已经被业务数据引用，回滚结构时保留该业务行。
    op.drop_index("ix_detection_results_item_task", table_name="detection_results")
    op.drop_index("ix_training_tasks_dataset_project_id", table_name="training_tasks")
    op.drop_index("ix_detection_tasks_model_version_id", table_name="detection_tasks")
    op.drop_index("ix_detection_scenes_created_by", table_name="detection_scenes")
    op.drop_index("ix_dataset_annotations_created_by", table_name="dataset_annotations")
    op.drop_index("ix_dashboard_snapshots_user_id", table_name="dashboard_snapshots")
    op.drop_index("ix_dashboard_snapshots_scene_id", table_name="dashboard_snapshots")
    for table, column in reversed(JSON_COLUMNS):
        op.execute(
            f'ALTER TABLE "{table}" ALTER COLUMN "{column}" '
            f'TYPE json USING "{column}"::json'
        )
