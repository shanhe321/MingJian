"""align backend schema with the approved PCB requirements

Revision ID: c7d8e9f0a1b2
Revises: a1b2c3d4e5f6
Create Date: 2026-07-17 10:55:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "c7d8e9f0a1b2"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # RBAC: only the two roles required by the product are seeded.
    op.create_unique_constraint("uq_user_roles_user_role", "user_roles", ["user_id", "role_id"])
    op.create_unique_constraint("uq_role_permissions_role_permission", "role_permissions", ["role_id", "permission_id"])
    op.execute(
        """
        INSERT INTO roles (name, display_name, description, is_system, created_at)
        VALUES
          ('user', '普通用户', '使用检测、报告、训练、数据集和智能体功能', true, now()),
          ('admin', '管理员', '管理用户、角色、模型、全局看板和审计日志', true, now())
        ON CONFLICT (name) DO UPDATE SET
          display_name = EXCLUDED.display_name,
          description = EXCLUDED.description,
          is_system = true;

        DELETE FROM role_permissions
        WHERE role_id IN (SELECT id FROM roles WHERE name NOT IN ('user', 'admin'));
        DELETE FROM user_roles
        WHERE role_id IN (SELECT id FROM roles WHERE name NOT IN ('user', 'admin'));
        DELETE FROM roles WHERE name NOT IN ('user', 'admin');

        INSERT INTO permissions (code, name, module, description)
        VALUES
          ('detection:use', '执行检测', 'detection', '创建和查看自己的检测任务'),
          ('report:read', '查看报告', 'detection', '查看和下载自己的检测报告'),
          ('training:use', '模型训练', 'training', '管理自己的数据集和训练任务'),
          ('agent:use', '智能体交互', 'agent', '使用检测和分析智能体'),
          ('system:manage_users', '用户权限管理', 'system', '管理用户和角色'),
          ('system:global_read', '全局数据查询', 'system', '查看全局看板和审计日志'),
          ('model:manage', '模型版本管理', 'training', '切换默认模型和归档版本')
        ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name, module = EXCLUDED.module,
          description = EXCLUDED.description;

        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id FROM roles r CROSS JOIN permissions p
        WHERE (r.name = 'user' AND p.code IN ('detection:use','report:read','training:use','agent:use'))
           OR r.name = 'admin'
        ON CONFLICT (role_id, permission_id) DO NOTHING;

        INSERT INTO user_roles (user_id, role_id, created_at)
        SELECT u.id, r.id, now() FROM users u
        JOIN roles r ON r.name = CASE WHEN u.is_superuser THEN 'admin' ELSE 'user' END
        WHERE NOT EXISTS (SELECT 1 FROM user_roles ur WHERE ur.user_id = u.id)
        ON CONFLICT (user_id, role_id) DO NOTHING;
        """
    )

    op.add_column("detection_tasks", sa.Column("input_path", sa.String(500), nullable=True))
    op.add_column("detection_tasks", sa.Column("result_path", sa.String(500), nullable=True))

    op.create_table(
        "detection_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("item_index", sa.Integer(), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("input_path", sa.String(500), nullable=True),
        sa.Column("result_path", sa.String(500), nullable=True),
        sa.Column("status", sa.String(20), server_default="pending", nullable=False),
        sa.Column("defect_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("average_confidence", sa.Float(), nullable=True),
        sa.Column("inference_time", sa.Float(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint("status IN ('pending','processing','completed','failed')", name="ck_detection_items_status"),
        sa.CheckConstraint("average_confidence IS NULL OR (average_confidence >= 0 AND average_confidence <= 1)", name="ck_detection_items_confidence"),
        sa.ForeignKeyConstraint(["task_id"], ["detection_tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", "item_index", name="uq_detection_items_task_index"),
        sa.UniqueConstraint("id", "task_id", name="uq_detection_items_id_task"),
    )
    op.create_index("ix_detection_items_task_status", "detection_items", ["task_id", "status"])

    # Recover one item per task/image path. Completed tasks without any result cannot
    # be reconstructed safely and are deliberately left without fabricated images.
    op.execute(
        """
        INSERT INTO detection_items
          (task_id, item_index, file_name, input_path, result_path, status,
           defect_count, average_confidence, inference_time, created_at, completed_at)
        SELECT task_id,
               row_number() OVER (PARTITION BY task_id ORDER BY image_path)::integer - 1,
               regexp_replace(image_path, '^.*/', ''), image_path,
               max(annotated_image_url), 'completed', count(*), avg(confidence),
               max(inference_time), min(created_at), max(created_at)
        FROM detection_results
        GROUP BY task_id, image_path;
        """
    )
    op.add_column("detection_results", sa.Column("item_id", sa.Integer(), nullable=True))
    op.execute(
        """
        UPDATE detection_results r SET item_id = i.id
        FROM detection_items i
        WHERE i.task_id = r.task_id AND i.input_path = r.image_path;
        """
    )
    op.alter_column("detection_results", "annotated_image_url", new_column_name="annotated_image_path")
    op.create_index("ix_detection_results_item_id", "detection_results", ["item_id"])
    op.create_foreign_key(
        "fk_detection_results_item_task", "detection_results", "detection_items",
        ["item_id", "task_id"], ["id", "task_id"], ondelete="CASCADE",
    )

    op.create_table(
        "detection_reports",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("report_uuid", sa.String(100), nullable=False),
        sa.Column("quality_conclusion", sa.String(50), nullable=True),
        sa.Column("risk_level", sa.String(20), nullable=True),
        sa.Column("defect_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("defect_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("risk_reason", sa.Text(), nullable=True),
        sa.Column("suggestion", sa.Text(), nullable=True),
        sa.Column("report_path", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("risk_level IS NULL OR risk_level IN ('low','medium','high')", name="ck_detection_reports_risk_level"),
        sa.ForeignKeyConstraint(["task_id"], ["detection_tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("report_uuid"),
        sa.UniqueConstraint("task_id", name="uq_detection_reports_task"),
    )
    op.create_index("ix_detection_reports_report_uuid", "detection_reports", ["report_uuid"])
    op.execute(
        """
        INSERT INTO detection_reports
          (task_id, report_uuid, quality_conclusion, risk_level, defect_count,
           defect_summary, risk_reason, suggestion, created_at)
        SELECT t.id, 'legacy-' || t.id,
               CASE WHEN count(r.id) = 0 THEN '合格' ELSE '疑似缺陷' END,
               CASE WHEN count(r.id) = 0 THEN NULL
                    WHEN bool_or(r.class_name IN ('short','open_circuit','missing_hole')) THEN 'high'
                    WHEN bool_or(r.class_name = 'mouse_bite') OR count(r.id) > 1 THEN 'medium'
                    ELSE 'low' END,
               coalesce(sum(r.class_count), 0),
               COALESCE(jsonb_object_agg(r.class_name, r.class_count) FILTER (WHERE r.class_name IS NOT NULL), '{}'::jsonb),
               '由迁移根据现存检测框推导；无框历史图片无法恢复',
               CASE WHEN count(r.id) = 0 THEN '未发现缺陷' ELSE '建议复核并按缺陷类别处理' END,
               COALESCE(t.completed_at, t.created_at)
        FROM detection_tasks t
        LEFT JOIN (
          SELECT task_id, class_name, count(*) AS class_count, min(id) AS id
          FROM detection_results GROUP BY task_id, class_name
        ) r ON r.task_id = t.id
        WHERE t.status = 'completed'
        GROUP BY t.id, t.completed_at, t.created_at;
        """
    )

    op.create_table(
        "dashboard_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("scene_id", sa.Integer(), nullable=True),
        sa.Column("date_key", sa.Date(), nullable=False),
        sa.Column("total_tasks", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_images", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_defects", sa.Integer(), server_default="0", nullable=False),
        sa.Column("pass_rate", sa.Float(), server_default="0", nullable=False),
        sa.Column("defect_distribution", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("trend_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("generated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("pass_rate >= 0 AND pass_rate <= 100", name="ck_dashboard_snapshots_pass_rate"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["scene_id"], ["detection_scenes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute(
        "ALTER TABLE dashboard_snapshots ADD CONSTRAINT uq_dashboard_snapshots_dimensions "
        "UNIQUE NULLS NOT DISTINCT (date_key, scene_id, user_id)"
    )
    op.create_index("ix_dashboard_snapshots_date_scene_user", "dashboard_snapshots", ["date_key", "scene_id", "user_id"])
    op.execute(
        """
        INSERT INTO dashboard_snapshots
          (user_id, scene_id, date_key, total_tasks, total_images, total_defects,
           pass_rate, defect_distribution, trend_data, generated_at)
        SELECT t.user_id, t.scene_id, t.created_at::date, count(DISTINCT t.id),
               count(i.id), coalesce(sum(i.defect_count), 0),
               CASE WHEN count(i.id) FILTER (WHERE i.status = 'completed') = 0 THEN 0
                    ELSE round(100.0 * count(i.id) FILTER (WHERE i.status = 'completed' AND i.defect_count = 0)
                         / count(i.id) FILTER (WHERE i.status = 'completed'), 2) END,
               '{}'::jsonb, '{}'::jsonb, now()
        FROM detection_tasks t LEFT JOIN detection_items i ON i.task_id = t.id
        GROUP BY t.user_id, t.scene_id, t.created_at::date;
        """
    )

    # Remove duplicated analysis/default-model sources after their data has been
    # moved to reports and model_versions.is_default.
    op.drop_column("detection_tasks", "analysis_report")
    op.drop_column("detection_tasks", "analysis_suggestion")
    op.drop_column("detection_tasks", "risk_level")
    op.drop_column("detection_tasks", "analyzed_at")
    op.drop_constraint("detection_scenes_default_model_version_id_fkey", "detection_scenes", type_="foreignkey")
    op.drop_column("detection_scenes", "default_model_version_id")

    op.create_unique_constraint("uq_dataset_projects_user_name", "dataset_projects", ["user_id", "name"])
    op.create_unique_constraint("uq_dataset_images_project_path", "dataset_images", ["dataset_project_id", "image_path"])
    op.create_unique_constraint("uq_training_metrics_task_epoch", "training_metrics", ["task_id", "epoch"])
    op.create_unique_constraint("uq_model_versions_scene_version", "model_versions", ["scene_id", "version"])
    op.create_index(
        "uq_model_versions_scene_default", "model_versions", ["scene_id"],
        unique=True, postgresql_where=sa.text("status = 'active' AND is_default IS TRUE"),
    )
    op.create_index("ix_detection_tasks_user_status_created", "detection_tasks", ["user_id", "status", "created_at"])
    op.create_index("ix_detection_results_class_name_class_id", "detection_results", ["class_name", "class_id"])
    op.create_index("ix_training_tasks_user_status_created", "training_tasks", ["user_id", "status", "created_at"])
    op.create_index("ix_chat_sessions_user_updated", "chat_sessions", ["user_id", "updated_at"])
    op.create_index("ix_operation_logs_user_created", "operation_logs", ["user_id", "created_at"])
    op.create_index("ix_operation_logs_module_action", "operation_logs", ["module", "action"])

    for table, constraint in (
        ("detection_tasks", "ck_detection_tasks_task_type"),
        ("detection_tasks", "ck_detection_tasks_status"),
        ("detection_tasks", "ck_detection_tasks_conf"),
        ("detection_tasks", "ck_detection_tasks_iou"),
        ("detection_results", "ck_detection_results_confidence"),
        ("training_tasks", "ck_training_tasks_status"),
        ("training_tasks", "ck_training_tasks_progress"),
        ("model_versions", "ck_model_versions_status"),
        ("dataset_projects", "ck_dataset_projects_status"),
        ("dataset_images", "ck_dataset_images_split"),
        ("dataset_images", "ck_dataset_images_status"),
    ):
        expressions = {
            "ck_detection_tasks_task_type": "task_type IN ('single','batch','folder','video','camera')",
            "ck_detection_tasks_status": "status IN ('pending','processing','completed','failed')",
            "ck_detection_tasks_conf": "conf_threshold >= 0 AND conf_threshold <= 1",
            "ck_detection_tasks_iou": "iou_threshold >= 0 AND iou_threshold <= 1",
            "ck_detection_results_confidence": "confidence >= 0 AND confidence <= 1",
            "ck_training_tasks_status": "status IN ('pending','running','completed','failed','cancelled')",
            "ck_training_tasks_progress": "progress >= 0 AND progress <= 100",
            "ck_model_versions_status": "status IN ('active','archived','deleted')",
            "ck_dataset_projects_status": "status IN ('prepared','validating','ready','failed')",
            "ck_dataset_images_split": "split IN ('train','val','test')",
            "ck_dataset_images_status": "status IN ('valid','invalid','ignored')",
        }
        op.create_check_constraint(constraint, table, expressions[constraint])


def downgrade() -> None:
    for table, constraint in (
        ("dataset_images", "ck_dataset_images_status"),
        ("dataset_images", "ck_dataset_images_split"),
        ("dataset_projects", "ck_dataset_projects_status"),
        ("model_versions", "ck_model_versions_status"),
        ("training_tasks", "ck_training_tasks_progress"),
        ("training_tasks", "ck_training_tasks_status"),
        ("detection_results", "ck_detection_results_confidence"),
        ("detection_tasks", "ck_detection_tasks_iou"),
        ("detection_tasks", "ck_detection_tasks_conf"),
        ("detection_tasks", "ck_detection_tasks_status"),
        ("detection_tasks", "ck_detection_tasks_task_type"),
    ):
        op.drop_constraint(constraint, table, type_="check")
    for name, table in (
        ("ix_operation_logs_module_action", "operation_logs"),
        ("ix_operation_logs_user_created", "operation_logs"),
        ("ix_chat_sessions_user_updated", "chat_sessions"),
        ("ix_training_tasks_user_status_created", "training_tasks"),
        ("ix_detection_results_class_name_class_id", "detection_results"),
        ("ix_detection_tasks_user_status_created", "detection_tasks"),
        ("uq_model_versions_scene_default", "model_versions"),
    ):
        op.drop_index(name, table_name=table)
    op.drop_constraint("uq_model_versions_scene_version", "model_versions", type_="unique")
    op.drop_constraint("uq_training_metrics_task_epoch", "training_metrics", type_="unique")
    op.drop_constraint("uq_dataset_images_project_path", "dataset_images", type_="unique")
    op.drop_constraint("uq_dataset_projects_user_name", "dataset_projects", type_="unique")
    op.add_column("detection_scenes", sa.Column("default_model_version_id", sa.Integer(), nullable=True))
    op.create_foreign_key(None, "detection_scenes", "model_versions", ["default_model_version_id"], ["id"])
    op.add_column("detection_tasks", sa.Column("analyzed_at", sa.DateTime(), nullable=True))
    op.add_column("detection_tasks", sa.Column("risk_level", sa.String(20), nullable=True))
    op.add_column("detection_tasks", sa.Column("analysis_suggestion", sa.Text(), nullable=True))
    op.add_column("detection_tasks", sa.Column("analysis_report", sa.Text(), nullable=True))
    op.drop_index("ix_dashboard_snapshots_date_scene_user", table_name="dashboard_snapshots")
    op.drop_table("dashboard_snapshots")
    op.drop_index("ix_detection_reports_report_uuid", table_name="detection_reports")
    op.drop_table("detection_reports")
    op.drop_constraint("fk_detection_results_item_task", "detection_results", type_="foreignkey")
    op.drop_index("ix_detection_results_item_id", table_name="detection_results")
    op.alter_column("detection_results", "annotated_image_path", new_column_name="annotated_image_url")
    op.drop_column("detection_results", "item_id")
    op.drop_index("ix_detection_items_task_status", table_name="detection_items")
    op.drop_table("detection_items")
    op.drop_column("detection_tasks", "result_path")
    op.drop_column("detection_tasks", "input_path")
    op.drop_constraint("uq_role_permissions_role_permission", "role_permissions", type_="unique")
    op.drop_constraint("uq_user_roles_user_role", "user_roles", type_="unique")
