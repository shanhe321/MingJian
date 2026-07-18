"""基于 Redis 的对话历史存储。"""

import json
import time
from datetime import datetime

from app.core.logger import get_logger
from app.storage.redis_client import redis_client
from app.database.session import SessionLocal
from app.entity.db_models import ChatMessage, ChatSession

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

    @staticmethod
    def _build_title(content: str | None, fallback: str = "新会话") -> str:
        normalized = " ".join((content or "").strip().split())
        if not normalized:
            return fallback
        return normalized[:36] + ("…" if len(normalized) > 36 else "")

    def save_message(
        self,
        user_id: int,
        session_id: str,
        role: str,
        content: str,
        agent_used: str | None = None,
    ):
        key = self._session_key(user_id, session_id)
        message = {
            "role": role,
            "content": content,
            "timestamp": time.time(),
            "agent_used": agent_used,
        }
        self.redis.rpush(key, json.dumps(message, ensure_ascii=False))
        self.redis.expire(key, self.ttl)
        exists_key = f"chat:exists:{user_id}:{session_id}"
        if not self.redis.get(exists_key):
            self.redis.rpush(self._index_key(user_id), session_id)
            self.redis.set(exists_key, "1", expire=SESSION_INDEX_TTL)
            self.redis.expire(self._index_key(user_id), SESSION_INDEX_TTL)
        logger.debug("保存消息: user=%d, session=%s, role=%s", user_id, session_id, role)
        db = SessionLocal()
        try:
            session = db.query(ChatSession).filter(
                ChatSession.user_id == user_id,
                ChatSession.session_uuid == session_id,
            ).first()
            if session is None:
                session = ChatSession(
                    user_id=user_id,
                    session_uuid=session_id,
                    title=self._build_title(content) if role == "user" else None,
                )
                db.add(session)
                db.flush()
            else:
                session.status = "active"
                if role == "user" and not session.title:
                    session.title = self._build_title(content)
            db.add(ChatMessage(
                session_id=session.id,
                role="assistant" if role == "ai" else role,
                content=content,
                agent_used=agent_used,
            ))
            session.message_count = (session.message_count or 0) + 1
            session.last_message_at = datetime.now()
            session.updated_at = datetime.now()
            db.commit()
        except Exception as exc:
            db.rollback()
            logger.warning("PostgreSQL 会话持久化失败，已保留 Redis 缓存: %s", exc)
        finally:
            db.close()

    def load_history(self, user_id: int, session_id: str) -> list[dict]:
        messages = []
        for raw in self.redis.lrange(self._session_key(user_id, session_id), -self.max_messages, -1):
            try:
                item = json.loads(raw) if isinstance(raw, str) else raw
                messages.append({"role": item.get("role", "user"), "content": item.get("content", "")})
            except (json.JSONDecodeError, AttributeError):
                continue
        if messages:
            return messages
        db = SessionLocal()
        try:
            session = db.query(ChatSession).filter(
                ChatSession.user_id == user_id,
                ChatSession.session_uuid == session_id,
            ).first()
            if session is None:
                return []
            rows = db.query(ChatMessage).filter(ChatMessage.session_id == session.id).order_by(ChatMessage.created_at.desc()).limit(self.max_messages).all()
            messages = [
                {"role": "ai" if row.role == "assistant" else row.role, "content": row.content}
                for row in reversed(rows)
            ]
            key = self._session_key(user_id, session_id)
            for message in messages:
                cached = {**message, "timestamp": time.time()}
                self.redis.rpush(key, json.dumps(cached, ensure_ascii=False))
            self.redis.expire(key, self.ttl)
            return messages
        finally:
            db.close()

    def get_sessions(self, user_id: int) -> list[str]:
        db = SessionLocal()
        try:
            sessions = [row.session_uuid for row in db.query(ChatSession).filter(
                ChatSession.user_id == user_id,
                ChatSession.status == "active",
            ).order_by(ChatSession.updated_at.desc()).all()]
            return sessions or self.redis.lrange(self._index_key(user_id), 0, -1)
        except Exception:
            return self.redis.lrange(self._index_key(user_id), 0, -1)
        finally:
            db.close()

    def get_session_summaries(self, user_id: int) -> list[dict]:
        """返回带标题的会话摘要；旧会话标题为空时由首条用户消息补齐。"""
        db = SessionLocal()
        try:
            rows = db.query(ChatSession).filter(
                ChatSession.user_id == user_id,
                ChatSession.status == "active",
            ).order_by(ChatSession.updated_at.desc()).all()
            summaries = []
            changed = False
            for session in rows:
                title = session.title
                if not title:
                    first_user_message = db.query(ChatMessage).filter(
                        ChatMessage.session_id == session.id,
                        ChatMessage.role == "user",
                    ).order_by(ChatMessage.created_at.asc()).first()
                    title = self._build_title(
                        first_user_message.content if first_user_message else None,
                        fallback=f"会话 {session.session_uuid}",
                    )
                    session.title = title
                    changed = True
                summaries.append({
                    "session_id": session.session_uuid,
                    "title": title,
                    "message_count": session.message_count or 0,
                    "updated_at": (
                        session.updated_at.isoformat() if session.updated_at else None
                    ),
                })
            if changed:
                db.commit()
            if summaries:
                return summaries
        except Exception as exc:
            db.rollback()
            logger.warning("读取会话摘要失败，回退 Redis 索引: %s", exc)
        finally:
            db.close()

        return [
            {
                "session_id": session_id,
                "title": f"会话 {session_id}",
                "message_count": None,
                "updated_at": None,
            }
            for session_id in self.redis.lrange(self._index_key(user_id), 0, -1)
        ]

    def get_session_history(self, user_id: int, session_id: str) -> list[dict]:
        db = SessionLocal()
        try:
            session = db.query(ChatSession).filter(
                ChatSession.user_id == user_id,
                ChatSession.session_uuid == session_id,
            ).first()
            if session is None:
                return []
            return [
                {"id": row.id, "role": row.role, "content": row.content,
                 "agent_used": row.agent_used, "created_at": row.created_at}
                for row in db.query(ChatMessage).filter(ChatMessage.session_id == session.id).order_by(ChatMessage.created_at).all()
            ]
        finally:
            db.close()

    def clear_session(self, user_id: int, session_id: str):
        self.redis.delete(self._session_key(user_id, session_id))
        self.redis.delete(f"chat:exists:{user_id}:{session_id}")
        index_key = self._index_key(user_id)
        remaining = [
            item for item in self.redis.lrange(index_key, 0, -1)
            if item != session_id
        ]
        self.redis.delete(index_key)
        if remaining:
            self.redis.rpush(index_key, *remaining)
            self.redis.expire(index_key, SESSION_INDEX_TTL)
        db = SessionLocal()
        try:
            session = db.query(ChatSession).filter(
                ChatSession.user_id == user_id,
                ChatSession.session_uuid == session_id,
            ).first()
            if session:
                db.query(ChatMessage).filter(ChatMessage.session_id == session.id).delete(synchronize_session=False)
                session.message_count = 0
                session.last_message_at = None
                session.status = "archived"
                db.commit()
        finally:
            db.close()
        logger.info("清空会话: user=%d, session=%s", user_id, session_id)


conversation_memory = ConversationMemory()
