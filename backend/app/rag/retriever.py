"""串联文档加载、向量化和 Pgvector 检索的 RAG 管线。"""

from app.config.settings import settings
from app.core.logger import get_logger
from app.rag.document_loader import document_loader
from app.rag.embedding import embedding_service
from app.vectorstore.pgvector_client import pgvector_client

logger = get_logger(__name__)


class KnowledgeRetriever:
    """知识索引构建、查询、格式化和统计入口。"""

    def __init__(self):
        self._index_built = False

    def build_index(self, force_rebuild: bool = False) -> dict:
        """加载三份知识文档，分块、向量化并写入 Pgvector。"""
        if self._index_built and not force_rebuild:
            count = pgvector_client.count()
            if count > 0:
                logger.info("知识库索引已存在 (%d 条)，跳过构建", count)
                return self.get_stats()

        logger.info("开始构建知识库索引...")
        if not pgvector_client.init_table():
            return self.get_stats()

        existing_count = pgvector_client.count()
        if existing_count > 0 and not force_rebuild:
            self._index_built = True
            logger.info("知识库索引已存在 (%d 条)，跳过构建", existing_count)
            return self.get_stats()

        if force_rebuild and not pgvector_client.clear():
            return self.get_stats()

        documents = document_loader.load_documents()
        if not documents:
            logger.warning("知识库中没有文档")
            return self.get_stats()

        chunks = document_loader.split_documents(documents)
        if not chunks:
            logger.warning("文档分块后为空")
            return self.get_stats()

        texts = [chunk["content"] for chunk in chunks]
        metadatas = [chunk["metadata"] for chunk in chunks]
        embeddings = embedding_service.embed_texts(texts)
        valid_indices = [index for index, embedding in enumerate(embeddings) if embedding]
        if not valid_indices:
            logger.error("所有文本向量化均失败")
            return self.get_stats()

        inserted = pgvector_client.insert_embeddings(
            [texts[index] for index in valid_indices],
            [embeddings[index] for index in valid_indices],
            [metadatas[index] for index in valid_indices],
        )
        self._index_built = inserted > 0
        logger.info(
            "知识库索引构建完成: %d 个文档 → %d 个文本块 → %d 条向量",
            len(documents),
            len(chunks),
            inserted,
        )
        return self.get_stats()

    def search(self, query: str, top_k: int | None = None) -> list[dict]:
        """向量化查询文本并返回最相关的知识片段。"""
        if not self._index_built and pgvector_client.count() == 0:
            self.build_index()

        query_embedding = embedding_service.embed_query(query)
        if not query_embedding:
            logger.error("查询向量化失败: %s", query)
            return []

        return pgvector_client.search(
            query_embedding,
            top_k=top_k or settings.RAG_TOP_K,
        )

    @staticmethod
    def format_context(results: list[dict]) -> str:
        """将检索结果格式化为带来源与相似度的上下文。"""
        if not results:
            return "（知识库中暂无相关内容）"

        parts = []
        for index, result in enumerate(results, 1):
            source = result.get("metadata", {}).get("source", "未知")
            similarity = result.get("similarity", 0)
            parts.append(
                f"[知识片段 {index}] (来源: {source}, 相似度: {similarity:.2f})\n"
                f"{result['content']}"
            )
        return "\n\n---\n\n".join(parts)

    def get_stats(self) -> dict:
        """返回知识片段数量和索引状态。"""
        count = pgvector_client.count()
        return {
            "total_chunks": count,
            "index_built": self._index_built or count > 0,
        }


knowledge_retriever = KnowledgeRetriever()
