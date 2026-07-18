"""基于 Redis 的 API 速率限制中间件。"""

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.storage.redis_client import redis_client
from app.config.settings import settings


class RateLimiterMiddleware(BaseHTTPMiddleware):
    """为检测接口和其他 API 应用按 IP 限流。"""

    DEFAULT_LIMIT = 60
    DEFAULT_WINDOW = 60

    RATE_LIMITS = {
        "/api/detection/single": {"limit": 30, "window": 60},
        "/api/detection/batch": {"limit": 10, "window": 60},
        "/api/detection/video": {"limit": 5, "window": 60},
        "/api/detection/camera": {"limit": 10, "window": 60},
    }

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path.startswith("/docs") or path.startswith("/redoc"):
            return await call_next(request)

        limit_config = self.RATE_LIMITS.get(
            path,
            {"limit": self.DEFAULT_LIMIT, "window": self.DEFAULT_WINDOW},
        )
        client_ip = self._get_client_ip(request)
        key = f"rate_limit:{path}:{client_ip}"

        try:
            current = redis_client.increment_with_expiry(
                key, limit_config["window"]
            )

            if current > limit_config["limit"]:
                return Response(
                    content=(
                        '{"code":429,"message":"请求过于频繁，请稍后重试",'
                        '"data":null}'
                    ),
                    status_code=429,
                    media_type="application/json",
                )
        except Exception:
            pass

        return await call_next(request)

    @staticmethod
    def _get_client_ip(request: Request) -> str:
        if settings.TRUST_PROXY_HEADERS:
            forwarded_for = request.headers.get("x-forwarded-for")
            if forwarded_for:
                return forwarded_for.split(",")[0].strip()
            real_ip = request.headers.get("x-real-ip")
            if real_ip:
                return real_ip
        return request.client.host if request.client else "unknown"
