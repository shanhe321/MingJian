"""基于 Redis 的对话历史存储。"""

import json
import time

from app.core.logger import get_logger
from app.storage.redis_client import redis_client

logger = get_logger(__name__)
MAX_HISTORY_MESSAGES = 20
SESSION_TTL = 3600
SESSION_INDEX_TTL = 86400


class ConversationMemory:
    def __init__(self, max_messages: int = MAX_HISTORY_MESSAGES, ttl: int = SESSION_TTL):
        self.max_messages = max_messages
        self.ttl = ttl
        self.redis = redis_client

    @staticmethod
    def _session_key(user_id: int, session_id: str) -> str:
        return f"chat:session:{user_id}:{session_id}"

    @staticmethod
    def _index_key(user_id: int) -> str:
        return f"chat:sessions:{user_id}"

    def save_message(self, user_id: int, session_id: str, role: str, content: str):
        key = self._session_key(user_id, session_id)
        message = {"role": role, "content": content, "timestamp": time.time()}
        self.redis.rpush(key, json.dumps(message, ensure_ascii=False))
        self.redis.expire(key, self.ttl)
        exists_key = f"chat:exists:{user_id}:{session_id}"
        if not self.redis.get(exists_key):
            self.redis.rpush(self._index_key(user_id), session_id)
            self.redis.set(exists_key, "1", expire=SESSION_INDEX_TTL)
            self.redis.expire(self._index_key(user_id), SESSION_INDEX_TTL)
        logger.debug("保存消息: user=%d, session=%s, role=%s", user_id, session_id, role)

    def load_history(self, user_id: int, session_id: str) -> list[dict]:
        messages = []
        for raw in self.redis.lrange(self._session_key(user_id, session_id), -self.max_messages, -1):
            try:
                item = json.loads(raw) if isinstance(raw, str) else raw
                messages.append({"role": item.get("role", "user"), "content": item.get("content", "")})
            except (json.JSONDecodeError, AttributeError):
                continue
        return messages

    def get_sessions(self, user_id: int) -> list[str]:
        return self.redis.lrange(self._index_key(user_id), 0, -1)

    def clear_session(self, user_id: int, session_id: str):
        self.redis.delete(self._session_key(user_id, session_id))
        logger.info("清空会话: user=%d, session=%s", user_id, session_id)


conversation_memory = ConversationMemory()
