"""align schema comments and remove redundant report index

Revision ID: e9f0a1b2c3d4
Revises: d8e9f0a1b2c3
Create Date: 2026-07-17 11:42:00
"""

from typing import Sequence, Union

from alembic import op

revision: str = "e9f0a1b2c3d4"
down_revision: Union[str, None] = "d8e9f0a1b2c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


COMMENTS = {
    "dashboard_snapshots": {
        "user_id": "统计所属用户", "scene_id": "所属场景", "date_key": "统计日期",
        "total_tasks": "当日检测任务数", "total_images": "当日处理图片数",
        "total_defects": "当日缺陷总数", "pass_rate": "合格率",
        "defect_distribution": "缺陷类别分布", "trend_data": "趋势数据", "generated_at": "生成时间",
    },
    "detection_reports": {
        "task_id": "所属任务", "report_uuid": "报告唯一标识", "quality_conclusion": "质检结论",
        "risk_level": "风险等级：low/medium/high", "defect_count": "缺陷总数",
        "defect_summary": "缺陷类别统计", "risk_reason": "风险原因", "suggestion": "处理建议",
        "report_path": "报告文件路径", "created_at": "创建时间",
    },
    "detection_results": {"item_id": "所属检测项", "annotated_image_path": "标注图路径"},
    "detection_tasks": {"input_path": "输入文件或目录路径", "result_path": "结果文件路径"},
    "training_tasks": {"dataset_path": "兼容数据集目录", "data_yaml": "YOLO data.yaml 路径"},
    "users": {"avatar": "头像地址"},
}


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_detection_reports_report_uuid")
    op.execute("CREATE INDEX IF NOT EXISTS ix_detection_reports_task_id ON detection_reports (task_id)")
    for table, columns in COMMENTS.items():
        for column, comment in columns.items():
            escaped = comment.replace("'", "''")
            op.execute(f"COMMENT ON COLUMN {table}.{column} IS '{escaped}'")


def downgrade() -> None:
    for table, columns in COMMENTS.items():
        for column in columns:
            op.execute(f"COMMENT ON COLUMN {table}.{column} IS NULL")
    op.drop_index("ix_detection_reports_task_id", table_name="detection_reports")
    op.create_index("ix_detection_reports_report_uuid", "detection_reports", ["report_uuid"])
