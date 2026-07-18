"""
全局配置模块
使用 pydantic-settings 管理所有配置项，支持从 .env 文件和环境变量读取
加载优先级：环境变量（系统级别）> .env 文件 > 代码中的默认值
"""

from urllib.parse import quote_plus

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """应用全局配置"""

    # ── 应用基础配置 ──────────────────────────────────
    APP_NAME: str = "RSOD Agent Platform"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = True
    # 本地调试默认由 FastAPI 提供媒体代理；公网部署时通过 .env 覆盖。
    PUBLIC_BASE_URL: str = "http://127.0.0.1:8000"
    TRUSTED_HOSTS: str = "*"
    TRUST_PROXY_HEADERS: bool = False

    # ── 数据库配置 ────────────────────────────────────
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_NAME: str = "rsod_agent"
    DB_USER: str = "rsod_admin"
    DB_PASSWORD: str = "rsod_admin"

    @property
    def DATABASE_URL(self) -> str:
        """构造 PostgreSQL 连接字符串"""
        return (
            f"postgresql://{quote_plus(self.DB_USER)}:{quote_plus(self.DB_PASSWORD)}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )

    # ── Redis 配置 ────────────────────────────────────
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str = ""
    REDIS_DB: int = 0

    @property
    def REDIS_URL(self) -> str:
        """构造 Redis 连接字符串"""
        credentials = f":{quote_plus(self.REDIS_PASSWORD)}@" if self.REDIS_PASSWORD else ""
        return f"redis://{credentials}{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    # ── MinIO 配置 ────────────────────────────────────
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET: str = "rsod-agent-images"
    MINIO_SECURE: bool = False
    # 兼容旧部署配置；浏览器对象地址统一由同源 /api/storage 代理生成。
    MINIO_PUBLIC_ENDPOINT: str = ""
    STORAGE_URL_EXPIRE_SECONDS: int = 7 * 24 * 3600

    # 可选的首次部署初始化；仅在系统不存在管理员时生效。
    BOOTSTRAP_ADMIN_USERNAME: str = ""
    BOOTSTRAP_ADMIN_EMAIL: str = ""
    BOOTSTRAP_ADMIN_PASSWORD: str = ""

    # ── 上传与临时文件安全 ───────────────────────────
    MAX_IMAGE_SIZE_MB: int = 20
    MAX_VIDEO_SIZE_MB: int = 200
    MAX_ZIP_FILES: int = 500
    MAX_ZIP_UNCOMPRESSED_MB: int = 1024
    TEMP_MAX_AGE_HOURS: int = 24
    CAMERA_DEFECT_KEYFRAME_LIMIT: int = 20

    # ── JWT 认证配置 ──────────────────────────────────
    JWT_SECRET_KEY: str = "your-super-secret-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # ── CORS 配置 ────────────────────────────────────
    ALLOWED_ORIGINS: str = (
        "http://localhost:3000,http://localhost:5173,http://localhost:8080"
    )

    @property
    def cors_origins_list(self) -> list:
        """将 CORS 配置字符串转为列表"""
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",") if origin.strip()]

    @property
    def trusted_hosts_list(self) -> list[str]:
        """反向代理转发后的合法 Host；云部署必须显式配置站点域名。"""
        return [host.strip() for host in self.TRUSTED_HOSTS.split(",") if host.strip()]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    # ── 日志配置 ──────────────────────────────────────
    LOG_LEVEL: str = "INFO"           # 日志级别
    LOG_DIR: str = "logs"             # 日志目录（相对于 backend/）
    LOG_MAX_BYTES: int = 10 * 1024 * 1024  # 单文件最大 10MB
    LOG_BACKUP_COUNT: int = 5         # 保留 5 份历史日志

    # ── 训练配置 ──────────────────────────────────────
    TRAIN_OUTPUT_DIR: str = "runs/train"      # 训练输出根目录
    DATASET_BASE_DIR: str = "datasets"         # 数据集根目录
    # Windows 下 Ultralytics 多进程 worker 会重复导入 FastAPI/Agent 模块；
    # 云端 Linux 可按 CPU 和内存情况通过环境变量调大。
    TRAIN_WORKERS: int = 0
    EVAL_WORKERS: int = 0
    EVALUATION_LOCK_TTL_SECONDS: int = 3600

    # ── LLM 配置 ──────────────────────────────────────
    OPENAI_API_KEY: str = "sk-your-api-key-here"
    OPENAI_MODEL: str = "gpt-4o-mini"
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"

    # 通义千问（推荐，国内访问快）
    QWEN_API_KEY: str = "sk-your-qwen-api-key"
    QWEN_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    QWEN_MODEL: str = "qwen-plus"
    SUPERVISOR_ENABLE_THINKING: bool = False

    # ── 本地 LLM 配置（可选）──────────────────────────
    USE_LOCAL_LLM: bool = False
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen2.5:7b"

    # ── RAG / Embedding 配置 ──────────────────────────
    EMBEDDING_MODEL: str = "text-embedding-v3"
    EMBEDDING_DIM: int = 1024
    RAG_CHUNK_SIZE: int = 500
    RAG_CHUNK_OVERLAP: int = 50
    RAG_TOP_K: int = 3


# 创建全局单例，其他模块直接 import 使用
settings = Settings()
