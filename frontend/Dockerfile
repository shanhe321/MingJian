# =============================================================================
# RSOD Web Platform - 前端 Dockerfile
# 多阶段构建: Node (构建) → Nginx Alpine (运行)
# =============================================================================

# ------------------------- 阶段 1: 构建阶段 -------------------------
FROM node:20-alpine AS builder

# 设置工作目录
WORKDIR /app

# 利用 Docker 缓存层：先复制依赖描述文件
COPY package.json package-lock.json* yarn.lock* pnpm-lock.yaml* ./

# 安装依赖（优先使用 npm ci 以保证可复现构建）
RUN if [ -f yarn.lock ]; then \
        yarn install --frozen-lockfile --production=false; \
    elif [ -f pnpm-lock.yaml ]; then \
        corepack enable && pnpm install --frozen-lockfile; \
    else \
        npm ci; \
    fi

# 复制全部源代码
COPY . .

# 执行 Vue 3 生产构建
RUN npm run build

# ------------------------- 阶段 2: 运行阶段 -------------------------
FROM nginx:1.27-alpine AS runner

# 删除默认 Nginx 配置
RUN rm -rf /etc/nginx/conf.d/default.conf /usr/share/nginx/html/*

# 复制自定义 Nginx 配置
COPY nginx.conf /etc/nginx/conf.d/default.conf

# 从构建阶段复制静态产物
COPY --from=builder /app/dist /usr/share/nginx/html

# 创建非 root 用户运行 Nginx（安全最佳实践）
RUN addgroup -S appgroup && adduser -S appuser -G appgroup \
    && chown -R appuser:appgroup /usr/share/nginx/html \
    && chown -R appuser:appgroup /var/cache/nginx \
    && chown -R appuser:appgroup /var/log/nginx \
    && touch /var/run/nginx.pid \
    && chown -R appuser:appgroup /var/run/nginx.pid

# 切换到非 root 用户
USER appuser

# 暴露 80 端口
EXPOSE 80

# 启动 Nginx（前台运行）
CMD ["nginx", "-g", "daemon off;"]
