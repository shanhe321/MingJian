"""
数据库模型定义

表结构总览：
  用户权限：users, roles, permissions, user_roles, role_permissions
  检测业务：detection_scenes, detection_tasks, detection_results, detection_reports
  数据看板：dashboard_snapshots
  模型管理：training_tasks, training_metrics, model_versions
  数据集：  dataset_projects, dataset_images, dataset_annotations
  智能体：  chat_sessions, chat_messages
  系统运维：operation_logs
"""
from datetime import date, datetime

from sqlalchemy import (
    Column, Integer, String, Float, DateTime, ForeignKey, ForeignKeyConstraint, Date,
    Text, Boolean, BigInteger, JSON, UniqueConstraint, CheckConstraint, Index, text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.database.session import Base


# PostgreSQL 使用 JSONB；SQLite 测试库回退到标准 JSON。
JSONType = JSON().with_variant(JSONB, "postgresql")


# ══════════════════════════════════════════════════════════════
# 一、用户与权限（RBAC）
# ══════════════════════════════════════════════════════════════

class User(Base):
    """用户表"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False, index=True, comment="用户名")
    email = Column(String(100), unique=True, nullable=False, index=True, comment="邮箱")
    hashed_password = Column(String(255), nullable=False, comment="加密密码")
    phone = Column(String(20), nullable=True, comment="手机号")
    avatar = Column(String(500), nullable=True, comment="头像地址")
    is_active = Column(Boolean, default=True, comment="是否启用")
    is_superuser = Column(Boolean, default=False, comment="是否超级管理员")
    last_login_at = Column(DateTime, nullable=True, comment="最后登录时间")
    created_at = Column(DateTime, default=datetime.now, index=True, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")

    # 关联
    user_roles = relationship("UserRole", back_populates="user", cascade="all, delete-orphan")
    detection_tasks = relationship("DetectionTask", back_populates="user")
    training_tasks = relationship("TrainingTask", back_populates="user")
    chat_sessions = relationship("ChatSession", back_populates="user")
    operation_logs = relationship("OperationLog", back_populates="user")
    dataset_projects = relationship("DatasetProject", back_populates="user")


class Role(Base):
    """角色表"""
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), unique=True, nullable=False, comment="角色标识，如 admin/operator/viewer")
    display_name = Column(String(100), nullable=False, comment="角色显示名，如 管理员/操作员/访客")
    description = Column(String(500), nullable=True, comment="角色描述")
    is_system = Column(Boolean, default=False, comment="是否系统内置角色（不可删除）")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")

    # 关联
    user_roles = relationship("UserRole", back_populates="role", cascade="all, delete-orphan")
    role_permissions = relationship("RolePermission", back_populates="role", cascade="all, delete-orphan")


class Permission(Base):
    """权限表"""
    __tablename__ = "permissions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(100), unique=True, nullable=False, comment="权限编码，如 detection:task:create")
    name = Column(String(100), nullable=False, comment="权限名称")
    module = Column(String(50), nullable=False, comment="所属模块：auth/detection/training/agent/system")
    description = Column(String(500), nullable=True, comment="权限描述")

    # 关联
    role_permissions = relationship("RolePermission", back_populates="permission", cascade="all, delete-orphan")


class UserRole(Base):
    """用户-角色关联表（多对多）"""
    __tablename__ = "user_roles"
    __table_args__ = (
        UniqueConstraint("user_id", "role_id", name="uq_user_roles_user_role"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role_id = Column(Integer, ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.now)

    user = relationship("User", back_populates="user_roles")
    role = relationship("Role", back_populates="user_roles")


class RolePermission(Base):
    """角色-权限关联表（多对多）"""
    __tablename__ = "role_permissions"
    __table_args__ = (
        UniqueConstraint("role_id", "permission_id", name="uq_role_permissions_role_permission"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    role_id = Column(Integer, ForeignKey("roles.id"), nullable=False, index=True)
    permission_id = Column(Integer, ForeignKey("permissions.id"), nullable=False, index=True)

    role = relationship("Role", back_populates="role_permissions")
    permission = relationship("Permission", back_populates="role_permissions")


# ══════════════════════════════════════════════════════════════
# 二、检测业务
# ══════════════════════════════════════════════════════════════

class DetectionScene(Base):
    """检测场景配置表
    每个小组/业务方向一个场景，如：遥感检测、工业缺陷、农业病害等
    场景决定了使用哪个模型、检测哪些类别
    """
    __tablename__ = "detection_scenes"
    __table_args__ = (
        Index(
            "ix_detection_scenes_created_by", "created_by",
            postgresql_where=text("created_by IS NOT NULL"),
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), unique=True, nullable=False, comment="场景标识，如 remote_sensing")
    display_name = Column(String(100), nullable=False, comment="场景显示名，如 遥感目标检测")
    description = Column(Text, nullable=True, comment="场景描述")
    category = Column(String(50), nullable=False, comment="场景分类：agriculture/industry/remote_sensing/medical/traffic")
    class_names = Column(JSONType, nullable=False, comment="类别列表，如 [\"airplane\",\"storage-tank\"]")
    class_names_cn = Column(JSONType, nullable=True, comment="类别中文名映射，如 {\"airplane\":\"飞机\"}")
    is_active = Column(Boolean, default=True, comment="是否启用")
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True, comment="创建人")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    # 关联
    detection_tasks = relationship("DetectionTask", back_populates="scene")
    model_versions = relationship(
        "ModelVersion",
        back_populates="scene",
        foreign_keys="[ModelVersion.scene_id]",
    )
    training_tasks = relationship("TrainingTask", back_populates="scene")


class DatasetProject(Base):
    """数据集项目表"""
    __tablename__ = "dataset_projects"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_dataset_projects_user_name"),
        CheckConstraint("status IN ('prepared','validating','ready','failed')", name="ck_dataset_projects_status"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True, comment="创建者")
    scene_id = Column(Integer, ForeignKey("detection_scenes.id", ondelete="RESTRICT"), nullable=False, index=True, comment="所属场景")
    name = Column(String(200), nullable=False, comment="数据集名称")
    description = Column(Text, nullable=True, comment="数据集说明")
    storage_path = Column(String(500), nullable=True, comment="数据集存储路径")
    total_images = Column(Integer, default=0, comment="图片总数")
    train_images = Column(Integer, default=0, comment="训练集图片数")
    val_images = Column(Integer, default=0, comment="验证集图片数")
    test_images = Column(Integer, default=0, comment="测试集图片数")
    status = Column(String(20), nullable=False, default="prepared", index=True, comment="状态：prepared/validating/ready/failed")
    created_at = Column(DateTime, default=datetime.now, index=True, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")

    # 关联
    user = relationship("User", back_populates="dataset_projects")
    scene = relationship("DetectionScene")
    images = relationship("DatasetImage", back_populates="dataset", cascade="all, delete-orphan")
    training_tasks = relationship("TrainingTask", back_populates="dataset_project")


class DatasetImage(Base):
    """数据集图片表"""
    __tablename__ = "dataset_images"
    __table_args__ = (
        UniqueConstraint("dataset_project_id", "image_path", name="uq_dataset_images_project_path"),
        CheckConstraint("split IN ('train','val','test')", name="ck_dataset_images_split"),
        CheckConstraint("status IN ('valid','invalid','ignored')", name="ck_dataset_images_status"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    dataset_project_id = Column(Integer, ForeignKey("dataset_projects.id", ondelete="CASCADE"), nullable=False, index=True, comment="所属数据集")
    image_name = Column(String(255), nullable=False, comment="图片文件名")
    image_path = Column(String(500), nullable=False, comment="图片路径")
    label_path = Column(String(500), nullable=True, comment="标注文件路径")
    split = Column(String(20), nullable=False, index=True, comment="数据划分：train/val/test")
    width = Column(Integer, nullable=True, comment="图像宽")
    height = Column(Integer, nullable=True, comment="图像高")
    defect_count = Column(Integer, default=0, comment="图片中缺陷数量")
    checksum = Column(String(128), nullable=True, index=True, comment="文件校验码")
    status = Column(String(20), nullable=False, default="valid", index=True, comment="状态：valid/invalid/ignored")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")

    # 关联
    dataset = relationship("DatasetProject", back_populates="images")
    annotations = relationship("DatasetAnnotation", back_populates="image", cascade="all, delete-orphan")


class DatasetAnnotation(Base):
    """数据集标注表"""
    __tablename__ = "dataset_annotations"
    __table_args__ = (
        Index(
            "ix_dataset_annotations_created_by", "created_by",
            postgresql_where=text("created_by IS NOT NULL"),
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    image_id = Column(Integer, ForeignKey("dataset_images.id", ondelete="CASCADE"), nullable=False, index=True, comment="所属图片")
    class_id = Column(Integer, nullable=False, index=True, comment="缺陷类别ID")
    class_name = Column(String(50), nullable=False, index=True, comment="缺陷类别名称")
    bbox = Column(JSONType, nullable=False, comment="边界框 [x1, y1, x2, y2]")
    confidence = Column(Float, nullable=True, comment="标注置信度")
    source = Column(String(20), nullable=False, default="import", comment="来源：manual/auto/import")
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True, comment="标注创建者")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")

    # 关联
    image = relationship("DatasetImage", back_populates="annotations")


class DetectionTask(Base):
    """检测任务表 — 每次检测操作生成一条任务记录"""
    __tablename__ = "detection_tasks"
    __table_args__ = (
        Index("ix_detection_tasks_user_status_created", "user_id", "status", "created_at"),
        Index(
            "ix_detection_tasks_model_version_id", "model_version_id",
            postgresql_where=text("model_version_id IS NOT NULL"),
        ),
        CheckConstraint(
            "status IN ('pending', 'processing', 'completed', 'failed')",
            name="ck_detection_tasks_status",
        ),
        CheckConstraint(
            "task_type IN ('single', 'batch', 'folder', 'zip', 'video', 'camera')",
            name="ck_detection_tasks_task_type",
        ),
        CheckConstraint("conf_threshold >= 0 AND conf_threshold <= 1", name="ck_detection_tasks_conf"),
        CheckConstraint("iou_threshold >= 0 AND iou_threshold <= 1", name="ck_detection_tasks_iou"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True, comment="操作用户")
    scene_id = Column(Integer, ForeignKey("detection_scenes.id", ondelete="RESTRICT"), nullable=False, index=True, comment="使用的检测场景")
    model_version_id = Column(Integer, ForeignKey("model_versions.id"), nullable=True, comment="使用的模型版本")
    task_type = Column(String(20), nullable=False, comment="检测类型：single/batch/folder/zip/video/camera")
    status = Column(String(20), default="pending", comment="状态：pending/processing/completed/failed")

    # 输入输出路径
    input_path = Column(String(500), nullable=True, comment="输入文件或目录路径")
    result_path = Column(String(500), nullable=True, comment="结果文件路径")

    # 检测统计
    total_images = Column(Integer, default=0, comment="处理图像总数")
    total_objects = Column(Integer, default=0, comment="检测到目标总数")
    total_inference_time = Column(Float, default=0, comment="总推理耗时（ms）")

    # 检测参数
    conf_threshold = Column(Float, default=0.25, comment="置信度阈值")
    iou_threshold = Column(Float, default=0.45, comment="NMS IoU 阈值")
    image_size = Column(Integer, default=640, comment="推理图像尺寸")

    # 错误信息
    error_message = Column(Text, nullable=True, comment="失败时的错误信息")

    created_at = Column(DateTime, default=datetime.now, index=True, comment="创建时间")
    completed_at = Column(DateTime, nullable=True, comment="完成时间")

    # 关联
    user = relationship("User", back_populates="detection_tasks")
    scene = relationship("DetectionScene", back_populates="detection_tasks")
    model_version = relationship("ModelVersion", back_populates="detection_tasks")
    results = relationship("DetectionResult", back_populates="task", cascade="all, delete-orphan")
    items = relationship("DetectionItem", back_populates="task", cascade="all, delete-orphan", order_by="DetectionItem.item_index")
    report = relationship("DetectionReport", back_populates="task", uselist=False, cascade="all, delete-orphan")


class DetectionItem(Base):
    """单图、批量文件或视频关键帧的逐项处理记录。"""
    __tablename__ = "detection_items"
    __table_args__ = (
        UniqueConstraint("task_id", "item_index", name="uq_detection_items_task_index"),
        UniqueConstraint("id", "task_id", name="uq_detection_items_id_task"),
        CheckConstraint("status IN ('pending','processing','completed','failed')", name="ck_detection_items_status"),
        CheckConstraint("average_confidence IS NULL OR (average_confidence >= 0 AND average_confidence <= 1)", name="ck_detection_items_confidence"),
        Index("ix_detection_items_task_status", "task_id", "status"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey("detection_tasks.id", ondelete="CASCADE"), nullable=False)
    item_index = Column(Integer, nullable=False)
    file_name = Column(String(255), nullable=False)
    input_path = Column(String(500), nullable=True)
    result_path = Column(String(500), nullable=True)
    status = Column(String(20), nullable=False, default="pending")
    defect_count = Column(Integer, nullable=False, default=0)
    average_confidence = Column(Float, nullable=True)
    inference_time = Column(Float, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    completed_at = Column(DateTime, nullable=True)

    task = relationship("DetectionTask", back_populates="items")
    results = relationship("DetectionResult", back_populates="item", overlaps="results,task")


class DetectionResult(Base):
    """检测结果表 — 每张图像中每个检测到的目标一条记录"""
    __tablename__ = "detection_results"
    __table_args__ = (
        Index("ix_detection_results_class_name_class_id", "class_name", "class_id"),
        Index(
            "ix_detection_results_item_task", "item_id", "task_id",
            postgresql_where=text("item_id IS NOT NULL"),
        ),
        ForeignKeyConstraint(
            ["item_id", "task_id"],
            ["detection_items.id", "detection_items.task_id"],
            name="fk_detection_results_item_task",
            ondelete="CASCADE",
        ),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_detection_results_confidence"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey("detection_tasks.id", ondelete="CASCADE"), nullable=False, index=True, comment="所属检测任务")
    item_id = Column(Integer, nullable=True, index=True, comment="所属检测项")
    image_path = Column(String(500), nullable=False, comment="原始图像路径")
    annotated_image_path = Column(String(500), nullable=True, comment="标注图路径")

    # 单个目标信息
    class_name = Column(String(50), nullable=False, index=True, comment="类别名称")
    class_name_cn = Column(String(50), nullable=True, comment="类别中文名")
    class_id = Column(Integer, nullable=False, comment="类别 ID")
    confidence = Column(Float, nullable=False, comment="置信度 0~1")
    bbox = Column(JSONType, nullable=False, comment="边界框 [x1, y1, x2, y2]")

    # 图像级信息（冗余存储，方便查询）
    inference_time = Column(Float, nullable=True, comment="该图推理耗时（ms）")
    image_width = Column(Integer, nullable=True, comment="图像宽度")
    image_height = Column(Integer, nullable=True, comment="图像高度")

    created_at = Column(DateTime, default=datetime.now, index=True)

    # 关联
    task = relationship("DetectionTask", back_populates="results", overlaps="item,results")
    item = relationship("DetectionItem", back_populates="results", overlaps="task,results")

    @property
    def annotated_image_url(self):
        """兼容旧响应字段；数据库只保存对象路径。"""
        return self.annotated_image_path

    @annotated_image_url.setter
    def annotated_image_url(self, value):
        self.annotated_image_path = value


class DetectionReport(Base):
    """检测报告表 — 每次检测任务可生成一份质检报告"""
    __tablename__ = "detection_reports"
    __table_args__ = (
        CheckConstraint(
            "risk_level IS NULL OR risk_level IN ('low', 'medium', 'high')",
            name="ck_detection_reports_risk_level",
        ),
        UniqueConstraint("task_id", name="uq_detection_reports_task"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey("detection_tasks.id", ondelete="CASCADE"), nullable=False, index=True, comment="所属任务")
    report_uuid = Column(String(100), unique=True, nullable=False, comment="报告唯一标识")
    quality_conclusion = Column(String(50), nullable=True, comment="质检结论")
    risk_level = Column(String(20), nullable=True, comment="风险等级：low/medium/high")
    defect_count = Column(Integer, nullable=False, default=0, comment="缺陷总数")
    defect_summary = Column(JSONType, nullable=True, comment="缺陷类别统计")
    risk_reason = Column(Text, nullable=True, comment="风险原因")
    suggestion = Column(Text, nullable=True, comment="处理建议")
    report_path = Column(String(500), nullable=True, comment="报告文件路径")
    created_at = Column(DateTime, default=datetime.now, nullable=False, comment="创建时间")

    # 关联
    task = relationship("DetectionTask", back_populates="report")


# ══════════════════════════════════════════════════════════════
# 三、数据分析与看板
# ══════════════════════════════════════════════════════════════


class DashboardSnapshot(Base):
    """看板统计快照表 — 预聚合每日检测统计数据"""
    __tablename__ = "dashboard_snapshots"
    __table_args__ = (
        Index("ix_dashboard_snapshots_date_scene_user", "date_key", "scene_id", "user_id"),
        Index("ix_dashboard_snapshots_scene_id", "scene_id"),
        Index("ix_dashboard_snapshots_user_id", "user_id"),
        CheckConstraint("pass_rate >= 0 AND pass_rate <= 100", name="ck_dashboard_snapshots_pass_rate"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, comment="统计所属用户")
    scene_id = Column(Integer, ForeignKey("detection_scenes.id", ondelete="CASCADE"), nullable=True, comment="所属场景")
    date_key = Column(Date, nullable=False, default=date.today, comment="统计日期")
    total_tasks = Column(Integer, nullable=False, default=0, comment="当日检测任务数")
    total_images = Column(Integer, nullable=False, default=0, comment="当日处理图片数")
    total_defects = Column(Integer, nullable=False, default=0, comment="当日缺陷总数")
    pass_rate = Column(Float, nullable=False, default=0, comment="合格率")
    defect_distribution = Column(JSONType, nullable=True, comment="缺陷类别分布")
    trend_data = Column(JSONType, nullable=True, comment="趋势数据")
    generated_at = Column(DateTime, default=datetime.now, nullable=False, comment="生成时间")

    # 关联
    user = relationship("User")
    scene = relationship("DetectionScene")


# ══════════════════════════════════════════════════════════════
# 四、模型管理
# ══════════════════════════════════════════════════════════════

class TrainingTask(Base):
    """模型训练任务表"""
    __tablename__ = "training_tasks"
    __table_args__ = (
        Index("ix_training_tasks_user_status_created", "user_id", "status", "created_at"),
        Index(
            "ix_training_tasks_dataset_project_id", "dataset_project_id",
            postgresql_where=text("dataset_project_id IS NOT NULL"),
        ),
        CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed', 'cancelled')",
            name="ck_training_tasks_status",
        ),
        CheckConstraint("progress >= 0 AND progress <= 100", name="ck_training_tasks_progress"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True, comment="操作用户")
    scene_id = Column(Integer, ForeignKey("detection_scenes.id"), nullable=False, index=True, comment="关联场景")
    dataset_project_id = Column(Integer, ForeignKey("dataset_projects.id"), nullable=True, comment="训练数据集")
    task_uuid = Column(String(100), unique=True, nullable=False, index=True, comment="任务唯一标识")
    status = Column(String(20), default="pending", comment="状态：pending/running/completed/failed/cancelled")

    # 训练配置
    model_name = Column(String(50), default="yolov11n", comment="基础模型：yolov11n/s/m/l/x")
    epochs = Column(Integer, default=100, comment="训练轮数")
    img_size = Column(Integer, default=640, comment="图像尺寸")
    batch_size = Column(Integer, default=16, comment="批次大小")
    device = Column(String(20), default="cpu", comment="训练设备：0/1/cpu")
    optimizer = Column(String(20), default="SGD", comment="优化器：SGD/Adam/AdamW")
    lr0 = Column(Float, default=0.01, comment="初始学习率")
    augment_config = Column(JSONType, nullable=True, comment="数据增强配置")

    # 训练进度
    current_epoch = Column(Integer, default=0, comment="当前轮数")
    progress = Column(Integer, default=0, comment="进度百分比 0~100")

    # 兼容既有目录训练，并支持 dataset_project_id 逐步替代目录参数。
    dataset_path = Column(String(500), nullable=True, comment="兼容数据集目录")
    dataset_size = Column(Integer, nullable=True, comment="数据集图像数量")
    data_yaml = Column(String(500), nullable=True, comment="YOLO data.yaml 路径")

    # 错误信息
    error_message = Column(Text, nullable=True, comment="失败错误信息")

    created_at = Column(DateTime, default=datetime.now, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")
    started_at = Column(DateTime, nullable=True, comment="开始训练时间")
    completed_at = Column(DateTime, nullable=True, comment="训练完成时间")

    # 关联
    user = relationship("User", back_populates="training_tasks")
    scene = relationship("DetectionScene", back_populates="training_tasks")
    dataset_project = relationship("DatasetProject", back_populates="training_tasks")
    metrics = relationship("TrainingMetric", back_populates="task", cascade="all, delete-orphan")
    model_versions = relationship("ModelVersion", back_populates="training_task")


class TrainingMetric(Base):
    """训练指标表 — 每个 epoch 记录一条，用于绘制训练曲线"""
    __tablename__ = "training_metrics"
    __table_args__ = (
        UniqueConstraint("task_id", "epoch", name="uq_training_metrics_task_epoch"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey("training_tasks.id", ondelete="CASCADE"), nullable=False, index=True, comment="所属训练任务")
    epoch = Column(Integer, nullable=False, comment="当前轮数")

    # 损失值
    box_loss = Column(Float, nullable=True, comment="边界框损失")
    cls_loss = Column(Float, nullable=True, comment="分类损失")
    dfl_loss = Column(Float, nullable=True, comment="DFL 损失")

    # 评估指标
    precision = Column(Float, nullable=True, comment="精确率")
    recall = Column(Float, nullable=True, comment="召回率")
    map50 = Column(Float, nullable=True, comment="mAP@0.50")
    map50_95 = Column(Float, nullable=True, comment="mAP@0.50:0.95")

    # 学习率
    lr = Column(Float, nullable=True, comment="当前学习率")

    created_at = Column(DateTime, default=datetime.now)

    # 关联
    task = relationship("TrainingTask", back_populates="metrics")


class ModelVersion(Base):
    """模型版本管理表 — 每次训练产出或手动上传的模型版本"""
    __tablename__ = "model_versions"
    __table_args__ = (
        UniqueConstraint("scene_id", "version", name="uq_model_versions_scene_version"),
        CheckConstraint("status IN ('active','archived','deleted')", name="ck_model_versions_status"),
        Index(
            "uq_model_versions_scene_default",
            "scene_id",
            unique=True,
            postgresql_where=text("status = 'active' AND is_default IS TRUE"),
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    scene_id = Column(Integer, ForeignKey("detection_scenes.id"), nullable=False, index=True, comment="所属场景")
    training_task_id = Column(Integer, ForeignKey("training_tasks.id", ondelete="SET NULL"), nullable=True, index=True, comment="来源训练任务（可为空，支持手动上传）")

    version = Column(String(50), nullable=False, comment="版本号，如 v1.0.0")
    model_name = Column(String(100), nullable=False, comment="模型名称")
    model_type = Column(String(50), default="yolov11n", comment="模型类型：yolov11n/s/m/l/x")
    status = Column(String(20), default="active", index=True, comment="状态：active/archived/deleted")

    # 模型文件
    model_path = Column(String(500), nullable=False, comment="本地模型文件路径")
    minio_url = Column(String(500), nullable=True, comment="MinIO 存储 URL")

    # 评估指标（训练完成后写入）
    map50 = Column(Float, nullable=True, comment="mAP@0.50")
    map50_95 = Column(Float, nullable=True, comment="mAP@0.50:0.95")
    precision = Column(Float, nullable=True, comment="精确率")
    recall = Column(Float, nullable=True, comment="召回率")
    per_class_ap = Column(JSONType, nullable=True, comment="各类别 AP，如 {\"airplane\":0.85,\"tank\":0.72}")

    # 元信息
    description = Column(Text, nullable=True, comment="版本描述/变更说明")
    file_size = Column(BigInteger, nullable=True, comment="模型文件大小（字节）")
    is_default = Column(Boolean, default=False, comment="是否为该场景的默认模型")

    created_at = Column(DateTime, default=datetime.now, comment="创建时间")

    # 关联
    scene = relationship(
        "DetectionScene",
        back_populates="model_versions",
        foreign_keys=[scene_id],
    )
    training_task = relationship("TrainingTask", back_populates="model_versions")
    detection_tasks = relationship("DetectionTask", back_populates="model_version")


# ══════════════════════════════════════════════════════════════
# 五、智能体对话
# ══════════════════════════════════════════════════════════════

class ChatSession(Base):
    """对话会话表 — 每次对话创建一个会话"""
    __tablename__ = "chat_sessions"
    __table_args__ = (
        Index("ix_chat_sessions_user_updated", "user_id", "updated_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True, comment="所属用户")
    session_uuid = Column(String(100), unique=True, nullable=False, index=True, comment="会话唯一标识")
    title = Column(String(200), nullable=True, comment="会话标题（取第一条消息摘要）")
    status = Column(String(20), default="active", comment="状态：active/archived")
    message_count = Column(Integer, default=0, comment="消息数量")
    last_message_at = Column(DateTime, nullable=True, comment="最后消息时间")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    # 关联
    user = relationship("User", back_populates="chat_sessions")
    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan",
                            order_by="ChatMessage.created_at")


class ChatMessage(Base):
    """对话消息表 — 每条消息（用户/AI/工具调用）一条记录"""
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False, index=True, comment="所属会话")
    role = Column(String(20), nullable=False, comment="消息角色：user/assistant/tool/system")
    content = Column(Text, nullable=False, comment="消息内容")

    # 智能体路由信息
    agent_used = Column(String(50), nullable=True, comment="处理的 Agent：supervisor/detection/analysis/qa")
    tool_calls = Column(JSONType, nullable=True, comment="工具调用记录，如 [{\"tool\":\"detect_objects\",\"args\":{...}}]")
    tool_result = Column(Text, nullable=True, comment="工具调用返回结果")

    # 元信息
    tokens_used = Column(Integer, nullable=True, comment="Token 消耗量")
    latency_ms = Column(Integer, nullable=True, comment="响应耗时（毫秒）")

    created_at = Column(DateTime, default=datetime.now, index=True, comment="创建时间")

    # 关联
    session = relationship("ChatSession", back_populates="messages")


# ══════════════════════════════════════════════════════════════
# 六、系统运维
# ══════════════════════════════════════════════════════════════

class OperationLog(Base):
    """操作审计日志表 — 记录用户关键操作"""
    __tablename__ = "operation_logs"
    __table_args__ = (
        Index("ix_operation_logs_user_created", "user_id", "created_at"),
        Index("ix_operation_logs_module_action", "module", "action"),
        CheckConstraint(
            "status IN ('success','failed')", name="ck_operation_logs_status"
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True, comment="操作用户（可为空表示系统操作）")
    username = Column(String(50), nullable=True, comment="冗余用户名，方便查询")

    # 操作信息
    module = Column(String(50), nullable=False, comment="操作模块：auth/detection/training/agent/system")
    action = Column(String(50), nullable=False, comment="操作类型：create/update/delete/login/export")
    target_type = Column(String(50), nullable=True, comment="操作对象类型：user/task/model/session")
    target_id = Column(String(100), nullable=True, comment="操作对象 ID")
    description = Column(String(500), nullable=True, comment="操作描述")

    # 请求信息
    ip_address = Column(String(50), nullable=True, comment="客户端 IP")
    user_agent = Column(String(500), nullable=True, comment="客户端 User-Agent")
    request_method = Column(String(10), nullable=True, comment="HTTP 方法")
    request_path = Column(String(500), nullable=True, comment="请求路径")

    # 结果
    status = Column(String(20), default="success", comment="操作结果：success/failed")
    error_message = Column(Text, nullable=True, comment="失败时的错误信息")

    created_at = Column(DateTime, default=datetime.now, index=True, comment="创建时间")

    # 关联
    user = relationship("User", back_populates="operation_logs")
