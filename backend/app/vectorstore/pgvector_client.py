"""基于 PostgreSQL Pgvector 扩展的知识向量存储。"""

import json
from typing import Optional

from sqlalchemy import text

from app.config.settings import settings
from app.core.logger import get_logger
from app.database.session import SessionLocal

logger = get_logger(__name__)


def _create_table_sql() -> str:
    return f"""
CREATE TABLE IF NOT EXISTS knowledge_embeddings (
    id SERIAL PRIMARY KEY,
    content TEXT NOT NULL,
    metadata JSONB DEFAULT '{{}}'::jsonb,
    embedding vector({settings.EMBEDDING_DIM}),
    created_at TIMESTAMP DEFAULT NOW()
);
"""


MIGRATE_INDEX_SQL = """
DO $$
DECLARE
    index_method TEXT;
BEGIN
    SELECT am.amname
    INTO index_method
    FROM pg_class AS cls
    JOIN pg_am AS am ON am.oid = cls.relam
    WHERE cls.relname = 'idx_knowledge_embeddings_vector'
      AND cls.relkind = 'i';

    IF index_method IS NOT NULL AND index_method <> 'hnsw' THEN
        DROP INDEX idx_knowledge_embeddings_vector;
    END IF;
END $$;
"""

CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_knowledge_embeddings_vector
ON knowledge_embeddings
USING hnsw (embedding vector_cosine_ops);
"""


class PgvectorClient:
    """负责知识向量表初始化、写入、检索和统计。"""

    def __init__(self):
        self._initialized = False

    def init_table(self) -> bool:
        """启用 vector 扩展并初始化知识向量表与余弦索引。"""
        if self._initialized:
            return True

        db = SessionLocal()
        try:
            db.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
            db.execute(text(_create_table_sql()))
            db.execute(text(MIGRATE_INDEX_SQL))
            db.execute(text(CREATE_INDEX_SQL))
            db.commit()
            self._initialized = True
            logger.info("Pgvector 表和索引初始化完成")
            return True
        except Exception as exc:
            db.rollback()
            logger.error("Pgvector 初始化失败: %s", str(exc))
            return False
        finally:
            db.close()

    def insert_embeddings(
        self,
        contents: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict] | None = None,
    ) -> int:
        """批量插入内容、元数据和对应向量，返回成功写入数量。"""
        if not contents or not embeddings:
            return 0
        if len(contents) != len(embeddings):
            raise ValueError("文本数量与向量数量不一致")

        db = SessionLocal()
        try:
            for index, content in enumerate(contents):
                metadata = metadatas[index] if metadatas and index < len(metadatas) else {}
                embedding = embeddings[index]
                if len(embedding) != settings.EMBEDDING_DIM:
                    raise ValueError(
                        f"向量维度不匹配: 期望 {settings.EMBEDDING_DIM}, 实际 {len(embedding)}"
                    )
                embedding_str = "[" + ",".join(str(value) for value in embedding) + "]"
                db.execute(
                    text(
                        "INSERT INTO knowledge_embeddings (content, metadata, embedding) "
                        "VALUES (:content, CAST(:metadata AS jsonb), CAST(:embedding AS vector))"
                    ),
                    {
                        "content": content,
                        "metadata": json.dumps(metadata, ensure_ascii=False),
                        "embedding": embedding_str,
                    },
                )

            db.commit()
            logger.info("插入 %d 条向量数据", len(contents))
            return len(contents)
        except Exception as exc:
            db.rollback()
            logger.error("插入向量数据失败: %s", str(exc))
            return 0
        finally:
            db.close()

    def search(
        self,
        query_embedding: list[float],
        top_k: int = 3,
        filter_metadata: Optional[dict] = None,
    ) -> list[dict]:
        """使用余弦距离检索最相似的前 K 个知识片段。"""
        del filter_metadata  # 讲义保留的扩展参数，本次不增加额外过滤行为。
        if not query_embedding or len(query_embedding) != settings.EMBEDDING_DIM:
            logger.error("查询向量为空或维度不匹配")
            return []

        db = SessionLocal()
        try:
            embedding_str = "[" + ",".join(str(value) for value in query_embedding) + "]"
            sql = """
                SELECT
                    content,
                    metadata,
                    1 - (embedding <=> CAST(:query AS vector)) AS similarity
                FROM knowledge_embeddings
                ORDER BY embedding <=> CAST(:query AS vector)
                LIMIT :top_k
            """
            rows = db.execute(
                text(sql),
                {"query": embedding_str, "top_k": top_k},
            ).fetchall()
            results = [
                {
                    "content": row[0],
                    "metadata": row[1] if isinstance(row[1], dict) else {},
                    "similarity": round(float(row[2]), 4),
                }
                for row in rows
            ]
            logger.info(
                "向量检索完成: top_k=%d, 最高相似度=%.4f",
                top_k,
                results[0]["similarity"] if results else 0,
            )
            return results
        except Exception as exc:
            logger.error("向量检索失败: %s", str(exc))
            return []
        finally:
            db.close()

    def count(self) -> int:
        """返回知识向量表记录数；表尚未初始化时返回 0。"""
        db = SessionLocal()
        try:
            return db.execute(
                text("SELECT COUNT(*) FROM knowledge_embeddings")
            ).scalar() or 0
        except Exception:
            return 0
        finally:
            db.close()

    def clear(self) -> bool:
        """清空知识向量表。"""
        db = SessionLocal()
        try:
            db.execute(text("DELETE FROM knowledge_embeddings"))
            db.commit()
            logger.info("向量表已清空")
            return True
        except Exception as exc:
            db.rollback()
            logger.error("清空向量表失败: %s", str(exc))
            return False
        finally:
            db.close()


pgvector_client = PgvectorClient()
