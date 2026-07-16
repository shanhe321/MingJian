"""Agent 可调用的 RAG 领域知识检索工具。"""

import json

from langchain_core.tools import tool

from app.core.logger import get_logger
from app.rag.retriever import knowledge_retriever

logger = get_logger(__name__)


@tool
def search_knowledge(query: str, top_k: int = 3) -> str:
    """搜索遥感目标检测知识库，获取专业领域知识。

    当用户询问 IoU、YOLOv11、mAP、遥感图像特点或 NMS 等专业问题时使用。

    Args:
        query: 用户的问题或关键词。
        top_k: 返回最相关的前 K 条知识片段，默认 3 条。

    Returns:
        JSON 字符串，包含知识片段内容、来源和相似度。
    """
    try:
        results = knowledge_retriever.search(query, top_k=top_k)
        if not results:
            return json.dumps(
                {"answer": "知识库中暂无相关内容", "sources": []},
                ensure_ascii=False,
            )

        knowledge = [
            {
                "content": result["content"][:300],
                "source": result.get("metadata", {}).get("source", "未知"),
                "similarity": result.get("similarity", 0),
            }
            for result in results
        ]
        return json.dumps(
            {"knowledge": knowledge, "count": len(knowledge)},
            ensure_ascii=False,
        )
    except Exception as exc:
        logger.error("知识检索失败: %s", str(exc))
        return json.dumps({"error": f"检索失败: {str(exc)}"}, ensure_ascii=False)


KNOWLEDGE_TOOLS = [search_knowledge]
