"""
Redis 客户端 — 封装连接池和常用操作。

Redis 不可用时自动降级到进程内字典，保证开发环境中的任务进度查询可用。
"""

import json
import time
from typing import Any, Optional

import redis
from redis.exceptions import RedisError

from app.config.settings import settings


class RedisClient:
    """Redis 客户端封装。"""

    _instance = None
    _pool = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._connect()
        return cls._instance

    def _connect(self):
        self._memory_cache = getattr(self, "_memory_cache", {})
        try:
            self._pool = redis.ConnectionPool(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                db=0,
                decode_responses=True,
                socket_timeout=5,
                socket_connect_timeout=5,
                max_connections=20,
            )
            self._client = redis.Redis(connection_pool=self._pool)
            self._client.ping()
            self._use_redis = True
            print(f"Redis 连接成功: {settings.REDIS_HOST}:{settings.REDIS_PORT}")
        except Exception as exc:
            self._use_redis = False
            self._client = None
            print(f"Redis 连接失败，降级到内存存储: {exc}")

    def _retry_on_fail(self, operation, max_retries=3, delay=0.5):
        if not self._use_redis:
            return operation()
        for retry in range(max_retries):
            try:
                if not self._client:
                    self._connect()
                    if not self._use_redis:
                        return operation()
                return operation()
            except RedisError:
                if retry < max_retries - 1:
                    time.sleep(delay)
                    self._connect()
                    if not self._use_redis:
                        return operation()
                else:
                    self._use_redis = False
                    return operation()

    def set(self, key: str, value: str, expire: Optional[int] = None) -> Any:
        def operation():
            if self._use_redis:
                return self._client.set(key, value, ex=expire)
            self._memory_cache[key] = value
            return True

        return self._retry_on_fail(operation)

    def get(self, key: str) -> Optional[str]:
        return self._retry_on_fail(
            lambda: self._client.get(key)
            if self._use_redis
            else self._memory_cache.get(key)
        )

    def delete(self, key: str) -> Any:
        return self._retry_on_fail(
            lambda: self._client.delete(key)
            if self._use_redis
            else self._memory_cache.pop(key, None)
        )

    def exists(self, key: str) -> bool:
        return self._retry_on_fail(
            lambda: bool(self._client.exists(key))
            if self._use_redis
            else key in self._memory_cache
        )

    def set_json(self, key: str, data: dict, expire: Optional[int] = None) -> Any:
        return self.set(key, json.dumps(data, ensure_ascii=False), expire)

    def get_json(self, key: str) -> Optional[dict]:
        value = self.get(key)
        return json.loads(value) if value else None

    def hset(self, name: str, mapping: dict) -> Any:
        def operation():
            if self._use_redis:
                return self._client.hset(name, mapping=mapping)
            self._memory_cache.setdefault(name, {}).update(mapping)
            return True

        return self._retry_on_fail(operation)

    def hgetall(self, name: str) -> Optional[dict]:
        return self._retry_on_fail(
            lambda: self._client.hgetall(name)
            if self._use_redis
            else self._memory_cache.get(name, {})
        )

    def lpush(self, name: str, *values: Any) -> Any:
        def operation():
            if self._use_redis:
                return self._client.lpush(name, *values)
            items = self._memory_cache.setdefault(name, [])
            for value in values:
                items.insert(0, value)
            return len(items)

        return self._retry_on_fail(operation)

    def rpop(self, name: str) -> Optional[Any]:
        return self._retry_on_fail(
            lambda: self._client.rpop(name)
            if self._use_redis
            else self._memory_cache.get(name, []).pop()
            if self._memory_cache.get(name)
            else None
        )

    def flushall(self) -> Any:
        return self._retry_on_fail(
            lambda: self._client.flushall()
            if self._use_redis
            else self._memory_cache.clear()
        )

    def keys(self, pattern: str = "*") -> list:
        return self._retry_on_fail(
            lambda: self._client.keys(pattern)
            if self._use_redis
            else [
                key
                for key in self._memory_cache
                if pattern == "*" or key.startswith(pattern.replace("*", ""))
            ]
        )

    def get_all_data(self) -> dict:
        data = {}
        if self._use_redis:
            for key in self.keys():
                try:
                    data[key] = self.get(key)
                except Exception:
                    data[key] = "无法解析"
        else:
            data = dict(self._memory_cache)
        return data

    def info(self) -> dict:
        return {
            "use_redis": self._use_redis,
            "redis_host": settings.REDIS_HOST,
            "redis_port": settings.REDIS_PORT,
            "key_count": len(self.keys()),
            "memory_usage": (
                self._client.info("memory")
                if self._use_redis and self._client
                else None
            ),
        }


redis_client = RedisClient()
