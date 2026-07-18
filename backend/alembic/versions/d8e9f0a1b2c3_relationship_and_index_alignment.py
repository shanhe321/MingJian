"""align existing foreign keys and supporting indexes

Revision ID: d8e9f0a1b2c3
Revises: c7d8e9f0a1b2
Create Date: 2026-07-17 11:35:00
"""

from typing import Sequence, Union

from alembic import op

revision: str = "d8e9f0a1b2c3"
down_revision: Union[str, None] = "c7d8e9f0a1b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


FK_RULES = (
    ("user_roles", "user_roles_user_id_fkey", "users", ["user_id"], ["id"], "CASCADE"),
    ("user_roles", "user_roles_role_id_fkey", "roles", ["role_id"], ["id"], "RESTRICT"),
    ("dataset_projects", "dataset_projects_user_id_fkey", "users", ["user_id"], ["id"], "RESTRICT"),
    ("dataset_projects", "dataset_projects_scene_id_fkey", "detection_scenes", ["scene_id"], ["id"], "RESTRICT"),
    ("dataset_images", "dataset_images_dataset_project_id_fkey", "dataset_projects", ["dataset_project_id"], ["id"], "CASCADE"),
    ("dataset_annotations", "dataset_annotations_image_id_fkey", "dataset_images", ["image_id"], ["id"], "CASCADE"),
    ("detection_tasks", "detection_tasks_user_id_fkey", "users", ["user_id"], ["id"], "RESTRICT"),
    ("detection_tasks", "detection_tasks_scene_id_fkey", "detection_scenes", ["scene_id"], ["id"], "RESTRICT"),
    ("detection_results", "detection_results_task_id_fkey", "detection_tasks", ["task_id"], ["id"], "CASCADE"),
    ("training_tasks", "training_tasks_user_id_fkey", "users", ["user_id"], ["id"], "RESTRICT"),
    ("training_metrics", "training_metrics_task_id_fkey", "training_tasks", ["task_id"], ["id"], "CASCADE"),
    ("model_versions", "model_versions_training_task_id_fkey", "training_tasks", ["training_task_id"], ["id"], "SET NULL"),
    ("chat_sessions", "chat_sessions_user_id_fkey", "users", ["user_id"], ["id"], "RESTRICT"),
    ("chat_messages", "chat_messages_session_id_fkey", "chat_sessions", ["session_id"], ["id"], "CASCADE"),
    ("operation_logs", "operation_logs_user_id_fkey", "users", ["user_id"], ["id"], "SET NULL"),
)


def _replace_fk(table, name, target, local, remote, ondelete):
    op.drop_constraint(name, table, type_="foreignkey")
    op.create_foreign_key(name, table, target, local, remote, ondelete=ondelete)


def upgrade() -> None:
    for rule in FK_RULES:
        _replace_fk(*rule)
    op.execute("CREATE INDEX IF NOT EXISTS ix_users_created_at ON users (created_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_dataset_projects_status ON dataset_projects (status)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_dataset_projects_created_at ON dataset_projects (created_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_dataset_images_checksum ON dataset_images (checksum)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_detection_results_created_at ON detection_results (created_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_model_versions_training_task_id ON model_versions (training_task_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_model_versions_status ON model_versions (status)")


def downgrade() -> None:
    for index_name, table in (
        ("ix_model_versions_status", "model_versions"),
        ("ix_model_versions_training_task_id", "model_versions"),
        ("ix_detection_results_created_at", "detection_results"),
        ("ix_dataset_images_checksum", "dataset_images"),
        ("ix_dataset_projects_created_at", "dataset_projects"),
        ("ix_dataset_projects_status", "dataset_projects"),
        ("ix_users_created_at", "users"),
    ):
        op.drop_index(index_name, table_name=table)
    for table, name, target, local, remote, _ondelete in reversed(FK_RULES):
        _replace_fk(table, name, target, local, remote, None)
