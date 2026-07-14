"""
Pydantic 请求/响应模型
用于 API 接口的数据验证和序列化

分层原则：
  - Create 模型：创建资源时的请求体
  - Update 模型：更新资源时的请求体（所有字段可选）
  - Response 模型：API 返回的响应体（过滤敏感字段）
  - List 模型：分页列表查询的参数和响应
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class _ModelFieldsBase(BaseModel):
    """允许模型业务字段使用 ``model_`` 前缀。"""

    model_config = ConfigDict(protected_namespaces=())


# ══════════════════════════════════════════════════════════════
# 一、用户与权限
# ══════════════════════════════════════════════════════════════

# --- 认证相关 ---

class UserRegister(BaseModel):
    """用户注册请求"""
    username: str = Field(..., min_length=3, max_length=50, description="用户名")
    email: str = Field(..., description="邮箱")
    password: str = Field(..., min_length=6, max_length=100, description="密码")


class UserLogin(BaseModel):
    """用户登录请求"""
    username: str = Field(..., description="用户名或邮箱")
    password: str = Field(..., description="密码")


class UserBrief(BaseModel):
    """用户简要信息（嵌入在 Token 响应中）"""
    id: int
    username: str
    email: str
    avatar: Optional[str] = None
    roles: list[str] = []

    model_config = {
        "from_attributes": True,
    }


class TokenResponse(BaseModel):
    """登录成功响应"""
    access_token: str
    token_type: str = "bearer"
    user: UserBrief


# --- 用户管理 ---

class UserResponse(BaseModel):
    """用户详情响应"""
    id: int
    username: str
    email: str
    phone: Optional[str] = None
    avatar: Optional[str] = None
    is_active: bool
    is_superuser: bool
    roles: list[str] = []
    last_login_at: Optional[datetime] = None
    created_at: datetime

    model_config = {
        "from_attributes": True,
    }


class UserUpdate(BaseModel):
    """用户信息更新"""
    phone: Optional[str] = None
    avatar: Optional[str] = None
    email: Optional[str] = None


class ChangePassword(BaseModel):
    """修改密码"""
    old_password: str = Field(..., description="旧密码")
    new_password: str = Field(..., min_length=6, max_length=100, description="新密码")


# --- 角色权限 ---

class RoleResponse(BaseModel):
    """角色响应"""
    id: int
    name: str
    display_name: str
    description: Optional[str] = None
    is_system: bool
    permissions: list[str] = []  # 权限编码列表
    created_at: datetime

    class Config:
        from_attributes = True


class RoleCreate(BaseModel):
    """创建角色"""
    name: str = Field(..., min_length=2, max_length=50, description="角色标识")
    display_name: str = Field(..., description="角色显示名")
    description: Optional[str] = None
    permission_codes: list[str] = Field(default=[], description="权限编码列表")


class PermissionResponse(BaseModel):
    """权限响应"""
    id: int
    code: str
    name: str
    module: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


# ══════════════════════════════════════════════════════════════
# 二、检测业务
# ══════════════════════════════════════════════════════════════

# --- 检测场景 ---

class SceneCreate(BaseModel):
    """创建检测场景"""
    name: str = Field(..., description="场景标识，如 remote_sensing")
    display_name: str = Field(..., description="场景显示名，如 遥感目标检测")
    description: Optional[str] = None
    category: str = Field(..., description="分类：agriculture/industry/remote_sensing/medical/traffic")
    class_names: list[str] = Field(..., description="类别列表")
    class_names_cn: Optional[dict[str, str]] = Field(None, description="中文名映射")


class SceneResponse(BaseModel):
    """检测场景响应"""
    id: int
    name: str
    display_name: str
    description: Optional[str] = None
    category: str
    class_names: list
    class_names_cn: Optional[dict] = None
    is_active: bool
    default_model: Optional["ModelVersionBrief"] = None
    created_at: datetime

    class Config:
        from_attributes = True


# --- 数据集管理 ---

class DatasetProjectCreate(BaseModel):
    """创建数据集项目"""
    scene_id: int = Field(..., description="所属场景ID")
    name: str = Field(..., min_length=1, max_length=200, description="数据集名称")
    description: Optional[str] = Field(None, description="数据集说明")


class DatasetProjectResponse(BaseModel):
    """数据集项目响应"""
    id: int
    user_id: int
    scene_id: int
    name: str
    description: Optional[str] = None
    storage_path: Optional[str] = None
    total_images: int
    train_images: int
    val_images: int
    test_images: int
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class DatasetImageResponse(BaseModel):
    """数据集图片响应"""
    id: int
    dataset_project_id: int
    image_name: str
    image_path: str
    label_path: Optional[str] = None
    split: str
    width: Optional[int] = None
    height: Optional[int] = None
    defect_count: int
    checksum: Optional[str] = None
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class DatasetAnnotationResponse(BaseModel):
    """数据集标注响应"""
    id: int
    image_id: int
    class_id: int
    class_name: str
    bbox: list
    confidence: Optional[float] = None
    source: str
    created_by: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True


class DatasetProjectDetail(BaseModel):
    """数据集项目详情（含图片和标注列表）"""
    project: DatasetProjectResponse
    images: list[DatasetImageResponse] = []
    stats: Optional[dict] = None  # 各类别统计


# --- 检测任务 ---

class DetectionTaskResponse(_ModelFieldsBase):
    """检测任务响应"""
    id: int
    user_id: int
    scene_id: int
    scene_name: Optional[str] = None
    model_version_id: Optional[int] = None
    task_type: str
    status: str
    total_images: int
    total_objects: int
    total_inference_time: float
    conf_threshold: float
    iou_threshold: float
    error_message: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class DetectionResultResponse(BaseModel):
    """单条检测结果响应"""
    id: int
    task_id: int
    image_path: str
    annotated_image_url: Optional[str] = None
    class_name: str
    class_name_cn: Optional[str] = None
    class_id: int
    confidence: float
    bbox: list  # [x1, y1, x2, y2]
    inference_time: Optional[float] = None
    image_width: Optional[int] = None
    image_height: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True


class DetectionTaskDetail(BaseModel):
    """检测任务详情（含结果列表）"""
    task: DetectionTaskResponse
    results: list[DetectionResultResponse] = []


# --- 检测统计 ---

class DetectionStatistics(BaseModel):
    """检测统计数据"""
    total_tasks: int
    total_images: int
    total_objects: int
    avg_inference_time: float
    class_distribution: dict[str, int]  # 各类别检测次数
    daily_trend: list[dict]             # 每日检测趋势
    scene_distribution: dict[str, int]  # 各场景检测次数


# ══════════════════════════════════════════════════════════════
# 三、模型管理
# ══════════════════════════════════════════════════════════════

# --- 训练任务 ---

class TrainingTaskCreate(_ModelFieldsBase):
    """创建训练任务"""
    scene_id: int = Field(..., description="关联场景 ID")
    dataset_project_id: Optional[int] = Field(None, description="训练数据集项目ID")
    model_name: str = Field(default="yolov11n", description="基础模型")
    epochs: int = Field(default=100, ge=1, le=500, description="训练轮数")
    img_size: int = Field(default=640, description="图像尺寸")
    batch_size: int = Field(default=16, ge=1, le=64, description="批次大小")
    device: str = Field(default="0", description="训练设备")
    optimizer: str = Field(default="SGD", description="优化器")
    lr0: float = Field(default=0.01, description="初始学习率")
    augment_config: Optional[dict] = Field(None, description="数据增强配置")


class TrainingTaskResponse(_ModelFieldsBase):
    """训练任务响应"""
    id: int
    user_id: int
    scene_id: int
    scene_name: Optional[str] = None
    dataset_project_id: Optional[int] = None
    task_uuid: str
    status: str
    model_name: str
    epochs: int
    current_epoch: int
    progress: int
    img_size: int
    batch_size: int
    device: str
    dataset_size: Optional[int] = None
    error_message: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class TrainingMetricResponse(BaseModel):
    """训练指标响应（单 epoch）"""
    epoch: int
    box_loss: Optional[float] = None
    cls_loss: Optional[float] = None
    dfl_loss: Optional[float] = None
    precision: Optional[float] = None
    recall: Optional[float] = None
    map50: Optional[float] = None
    map50_95: Optional[float] = None
    lr: Optional[float] = None

    class Config:
        from_attributes = True


# --- 模型版本 ---

class ModelVersionBrief(_ModelFieldsBase):
    """模型版本简要信息"""
    id: int
    version: str
    model_name: str
    model_type: str
    map50: Optional[float] = None
    is_default: bool
    created_at: datetime

    class Config:
        from_attributes = True


class ModelVersionResponse(_ModelFieldsBase):
    """模型版本详情"""
    id: int
    scene_id: int
    scene_name: Optional[str] = None
    training_task_id: Optional[int] = None
    version: str
    model_name: str
    model_type: str
    status: str
    model_path: str
    minio_url: Optional[str] = None
    map50: Optional[float] = None
    map50_95: Optional[float] = None
    precision: Optional[float] = None
    recall: Optional[float] = None
    per_class_ap: Optional[dict] = None
    description: Optional[str] = None
    file_size: Optional[int] = None
    is_default: bool
    created_at: datetime

    class Config:
        from_attributes = True


class ModelVersionCreate(_ModelFieldsBase):
    """手动上传模型版本"""
    scene_id: int
    version: str = Field(..., description="版本号")
    model_name: str = Field(..., description="模型名称")
    model_type: str = Field(default="yolov11n", description="模型类型")
    description: Optional[str] = None


# --- 模型评估与导出 ---

class ModelValidateRequest(BaseModel):
    """模型评估请求"""
    split: str = Field(default="val", description="评估数据集划分: val / test / train")
    conf: float = Field(default=0.001, description="置信度阈值")
    iou: float = Field(default=0.6, description="NMS IoU 阈值")


class ModelValidateResponse(_ModelFieldsBase):
    """模型评估响应"""
    task_id: int
    task_uuid: str
    split: str
    overall: dict
    per_class: dict
    model_version_id: Optional[int] = None
    model_version: Optional[str] = None


class EvaluateRequest(BaseModel):
    """模型评估请求"""
    split: str = Field(default="val", description="评估数据集划分：val/test")
    conf: float = Field(default=0.25, ge=0.001, le=1.0, description="置信度阈值")
    iou: float = Field(default=0.45, ge=0.1, le=1.0, description="NMS IoU 阈值")


class EvaluateResponse(BaseModel):
    """模型评估响应"""
    task_id: int
    split: str
    overall: dict
    per_class: dict


class ModelExportRequest(BaseModel):
    """模型导出请求"""
    version: Optional[str] = Field(None, description="版本号（如 v1.0.0，不传则自动生成）")
    description: Optional[str] = Field(None, description="版本描述/变更说明")
    set_default: bool = Field(default=False, description="是否设为该场景的默认模型")
    upload_minio: bool = Field(default=True, description="是否上传到 MinIO")


class ModelExportResponse(_ModelFieldsBase):
    """模型导出响应"""
    model_version_id: int
    version: str
    model_name: str
    model_path: str
    export_dir: str
    minio_url: Optional[str] = None
    file_size: Optional[int] = None
    evaluation: dict
    is_default: bool
    message: str


class LegacyModelExportResponse(_ModelFieldsBase):
    """模型导出响应"""
    id: int
    version: str
    model_name: str
    model_path: str
    file_size: Optional[int] = None
    map50: Optional[float] = None
    map50_95: Optional[float] = None

# ══════════════════════════════════════════════════════════════
# 四、智能体对话
# ══════════════════════════════════════════════════════════════

class ChatSessionCreate(BaseModel):
    """创建对话会话"""
    title: Optional[str] = None


class ChatSessionResponse(BaseModel):
    """对话会话响应"""
    id: int
    session_uuid: str
    title: Optional[str] = None
    status: str
    message_count: int
    last_message_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class ChatMessageRequest(BaseModel):
    """发送消息请求"""
    session_id: Optional[int] = Field(None, description="会话 ID（为空则自动创建新会话）")
    content: str = Field(..., min_length=1, max_length=5000, description="消息内容")


class ChatMessageResponse(BaseModel):
    """对话消息响应"""
    id: int
    session_id: int
    role: str
    content: str
    agent_used: Optional[str] = None
    tool_calls: Optional[list] = None
    tool_result: Optional[str] = None
    tokens_used: Optional[int] = None
    latency_ms: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True


class ChatHistoryResponse(BaseModel):
    """对话历史响应（含会话信息和消息列表）"""
    session: ChatSessionResponse
    messages: list[ChatMessageResponse] = []


# ══════════════════════════════════════════════════════════════
# 五、系统运维
# ══════════════════════════════════════════════════════════════

class OperationLogResponse(BaseModel):
    """操作日志响应"""
    id: int
    user_id: Optional[int] = None
    username: Optional[str] = None
    module: str
    action: str
    target_type: Optional[str] = None
    target_id: Optional[str] = None
    description: Optional[str] = None
    ip_address: Optional[str] = None
    request_method: Optional[str] = None
    request_path: Optional[str] = None
    status: str
    error_message: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ══════════════════════════════════════════════════════════════
# 六、通用模型
# ══════════════════════════════════════════════════════════════

class ApiResponse(BaseModel):
    """统一 API 响应"""
    code: int = 200
    message: str = "success"
    data: Optional[dict | list] = None


class PageParams(BaseModel):
    """分页查询参数"""
    page: int = Field(default=1, ge=1, description="页码")
    page_size: int = Field(default=20, ge=1, le=100, description="每页数量")


class PageResponse(BaseModel):
    """分页响应"""
    total: int
    page: int
    page_size: int
    total_pages: int
    items: list


class HealthResponse(BaseModel):
    """健康检查响应"""
    status: str = "healthy"
    app_name: str
    version: str
    database: Optional[str] = None
    redis: Optional[str] = None
    minio: Optional[str] = None
