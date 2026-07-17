# =============================================================================
# RSOD Web Platform - 后端 Dockerfile
# 基础镜像: python:3.11-slim + PyTorch CPU 版本（减小体积）
# =============================================================================

FROM python:3.11-slim

# 设置环境变量
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# 设置工作目录
WORKDIR /app

# ------------------------- 系统依赖 -------------------------
# 安装编译 PyTorch 所需的系统库及运行时依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    # 编译工具链
    build-essential \
    # OpenCV / 图像处理依赖
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    # 其他运行时依赖
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# ------------------------- Python 依赖 -------------------------
# 先复制 requirements 文件以利用 Docker 层缓存
COPY requirements.txt .

# 安装 PyTorch CPU 版本（显著减小镜像体积，避免下载 CUDA 库）
# 使用官方 CPU-only 索引源
RUN pip install --upgrade pip && \
    pip install --index-url https://download.pytorch.org/whl/cpu \
    torch torchvision torchaudio && \
    pip install --no-cache-dir -r requirements.txt

# ------------------------- 应用代码 -------------------------
# 复制应用源代码
COPY . .

# 创建非 root 用户运行应用（安全最佳实践）
RUN groupadd -r appuser && useradd -r -g appuser -s /bin/false appuser \
    && chown -R appuser:appuser /app

# 切换到非 root 用户
USER appuser

# 暴露端口
EXPOSE 8000

# 健康检查（每 30 秒检查一次，超时 5 秒）
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

# 启动 FastAPI 服务（使用 uvicorn）
# 生产环境建议: workers 数量根据 CPU 核数调整，通常为 2-4
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4", "--proxy-headers", "--forwarded-allow-ips", "*"]
