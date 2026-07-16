"""通过通义千问或 OpenAI 兼容接口生成文本向量。"""

from typing import Optional

from app.config.settings import settings
from app.core.logger import get_logger

logger = get_logger(__name__)


class EmbeddingService:
    """支持批量处理的文本向量化服务。"""

    def __init__(self):
        self._client = None
        self._model = None

    def _init_client(self):
        """按需初始化 Embedding 客户端，避免模块导入时发起外部连接。"""
        if self._client is not None:
            return

        try:
            from openai import OpenAI

            qwen_api_key = settings.QWEN_API_KEY
            if qwen_api_key and qwen_api_key != "sk-your-qwen-api-key":
                api_key = qwen_api_key
                base_url = settings.QWEN_BASE_URL
            else:
                api_key = settings.OPENAI_API_KEY
                base_url = settings.OPENAI_BASE_URL

            if not api_key or api_key in {"sk-your-api-key-here", "sk-your-qwen-api-key"}:
                logger.warning("未配置可用的 Embedding API Key")
                return

            self._client = OpenAI(api_key=api_key, base_url=base_url)
            self._model = settings.EMBEDDING_MODEL
            logger.info("Embedding 服务初始化完成: model=%s", self._model)
        except Exception as exc:
            logger.error("Embedding 服务初始化失败: %s", str(exc))
            self._client = None

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """每批最多 10 条文本，兼容 Qwen Embedding 接口限制。"""
        if not texts:
            return []

        self._init_client()
        if not self._client:
            logger.error("Embedding 客户端未初始化")
            return [[] for _ in texts]

        try:
            all_embeddings = []
            batch_size = 10
            for start in range(0, len(texts), batch_size):
                batch = texts[start : start + batch_size]
                response = self._client.embeddings.create(
                    model=self._model,
                    input=batch,
                )
                all_embeddings.extend(item.embedding for item in response.data)
                logger.debug("向量化批次 %d: %d 条文本", start // batch_size + 1, len(batch))

            logger.info(
                "向量化完成: %d 条文本, 向量维度=%d",
                len(texts),
                len(all_embeddings[0]) if all_embeddings else 0,
            )
            return all_embeddings
        except Exception as exc:
            logger.error("文本向量化失败: %s", str(exc))
            return [[] for _ in texts]

    def embed_query(self, query: str) -> Optional[list[float]]:
        """将单条查询转换为向量，失败返回 None。"""
        results = self.embed_texts([query])
        return results[0] if results and results[0] else None


embedding_service = EmbeddingService()
