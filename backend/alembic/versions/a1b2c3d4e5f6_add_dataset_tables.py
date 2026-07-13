"""add dataset tables and missing fields

Revision ID: a1b2c3d4e5f6
Revises: 735387d83f86
Create Date: 2026-07-13 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '735387d83f86'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # === 1. 创建 dataset_projects（数据集项目表）===
    op.create_table(
        'dataset_projects',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False, comment='创建者'),
        sa.Column('scene_id', sa.Integer(), sa.ForeignKey('detection_scenes.id'), nullable=False, comment='所属场景'),
        sa.Column('name', sa.String(length=200), nullable=False, comment='数据集名称'),
        sa.Column('description', sa.Text(), nullable=True, comment='数据集说明'),
        sa.Column('storage_path', sa.String(length=500), nullable=True, comment='数据集存储路径'),
        sa.Column('total_images', sa.Integer(), server_default='0', comment='图片总数'),
        sa.Column('train_images', sa.Integer(), server_default='0', comment='训练集图片数'),
        sa.Column('val_images', sa.Integer(), server_default='0', comment='验证集图片数'),
        sa.Column('test_images', sa.Integer(), server_default='0', comment='测试集图片数'),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='prepared', comment='状态：prepared/validating/ready/failed'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), comment='创建时间'),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), comment='更新时间'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_dataset_projects_user_id'), 'dataset_projects', ['user_id'])
    op.create_index(op.f('ix_dataset_projects_scene_id'), 'dataset_projects', ['scene_id'])
    op.create_index(op.f('ix_dataset_projects_status'), 'dataset_projects', ['status'])
    op.create_index(op.f('ix_dataset_projects_created_at'), 'dataset_projects', ['created_at'])

    # === 2. 创建 dataset_images（数据集图片表）===
    op.create_table(
        'dataset_images',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('dataset_project_id', sa.Integer(), sa.ForeignKey('dataset_projects.id'), nullable=False, comment='所属数据集'),
        sa.Column('image_name', sa.String(length=255), nullable=False, comment='图片文件名'),
        sa.Column('image_path', sa.String(length=500), nullable=False, comment='图片路径'),
        sa.Column('label_path', sa.String(length=500), nullable=True, comment='标注文件路径'),
        sa.Column('split', sa.String(length=20), nullable=False, comment='数据划分：train/val/test'),
        sa.Column('width', sa.Integer(), nullable=True, comment='图像宽'),
        sa.Column('height', sa.Integer(), nullable=True, comment='图像高'),
        sa.Column('defect_count', sa.Integer(), server_default='0', comment='图片中缺陷数量'),
        sa.Column('checksum', sa.String(length=128), nullable=True, comment='文件校验码'),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='valid', comment='状态：valid/invalid/ignored'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), comment='创建时间'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_dataset_images_dataset_project_id'), 'dataset_images', ['dataset_project_id'])
    op.create_index(op.f('ix_dataset_images_split'), 'dataset_images', ['split'])
    op.create_index(op.f('ix_dataset_images_status'), 'dataset_images', ['status'])

    # === 3. 创建 dataset_annotations（数据集标注表）===
    op.create_table(
        'dataset_annotations',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('image_id', sa.Integer(), sa.ForeignKey('dataset_images.id'), nullable=False, comment='所属图片'),
        sa.Column('class_id', sa.Integer(), nullable=False, comment='缺陷类别ID'),
        sa.Column('class_name', sa.String(length=50), nullable=False, comment='缺陷类别名称'),
        sa.Column('bbox', sa.JSON(), nullable=False, comment='边界框 [x1, y1, x2, y2]'),
        sa.Column('confidence', sa.Float(), nullable=True, comment='标注置信度'),
        sa.Column('source', sa.String(length=20), nullable=False, server_default='import', comment='来源：manual/auto/import'),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True, comment='标注创建者'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), comment='创建时间'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_dataset_annotations_image_id'), 'dataset_annotations', ['image_id'])
    op.create_index(op.f('ix_dataset_annotations_class_id'), 'dataset_annotations', ['class_id'])
    op.create_index(op.f('ix_dataset_annotations_class_name'), 'dataset_annotations', ['class_name'])

    # === 4. 给 detection_scenes 添加 default_model_version_id ===
    op.add_column(
        'detection_scenes',
        sa.Column('default_model_version_id', sa.Integer(), sa.ForeignKey('model_versions.id'), nullable=True, comment='默认模型版本'),
    )

    # === 5. 给 training_tasks 添加 dataset_project_id ===
    op.add_column(
        'training_tasks',
        sa.Column('dataset_project_id', sa.Integer(), sa.ForeignKey('dataset_projects.id'), nullable=True, comment='训练数据集'),
    )


def downgrade() -> None:
    # === 回滚 5：删除 training_tasks.dataset_project_id ===
    op.drop_column('training_tasks', 'dataset_project_id')

    # === 回滚 4：删除 detection_scenes.default_model_version_id ===
    op.drop_constraint(None, 'detection_scenes', type_='foreignkey')  # type: ignore
    op.drop_column('detection_scenes', 'default_model_version_id')

    # === 回滚 3：删除 dataset_annotations ===
    op.drop_index(op.f('ix_dataset_annotations_class_name'), table_name='dataset_annotations')
    op.drop_index(op.f('ix_dataset_annotations_class_id'), table_name='dataset_annotations')
    op.drop_index(op.f('ix_dataset_annotations_image_id'), table_name='dataset_annotations')
    op.drop_table('dataset_annotations')

    # === 回滚 2：删除 dataset_images ===
    op.drop_index(op.f('ix_dataset_images_status'), table_name='dataset_images')
    op.drop_index(op.f('ix_dataset_images_split'), table_name='dataset_images')
    op.drop_index(op.f('ix_dataset_images_dataset_project_id'), table_name='dataset_images')
    op.drop_table('dataset_images')

    # === 回滚 1：删除 dataset_projects ===
    op.drop_index(op.f('ix_dataset_projects_created_at'), table_name='dataset_projects')
    op.drop_index(op.f('ix_dataset_projects_status'), table_name='dataset_projects')
    op.drop_index(op.f('ix_dataset_projects_scene_id'), table_name='dataset_projects')
    op.drop_index(op.f('ix_dataset_projects_user_id'), table_name='dataset_projects')
    op.drop_table('dataset_projects')
