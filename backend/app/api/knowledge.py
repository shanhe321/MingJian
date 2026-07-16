"""知识库索引构建、统计和手动检索 API。"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.auth import get_current_user
from app.rag.retriever import knowledge_retriever

router = APIRouter(prefix="/api/knowledge", tags=["知识库管理"])


class SearchRequest(BaseModel):
    query: str
    top_k: int = 3


@router.post("/build", summary="构建知识库索引")
async def build_index(
    force_rebuild: bool = False,
    current_user=Depends(get_current_user),
):
    """构建或重建三份领域文档的 Pgvector 索引。"""
    del current_user
    stats = knowledge_retriever.build_index(force_rebuild=force_rebuild)
    return {"message": "知识库索引构建完成", "stats": stats}


@router.get("/stats", summary="知识库统计")
async def get_stats(current_user=Depends(get_current_user)):
    """获取知识向量片段数量和索引状态。"""
    del current_user
    return knowledge_retriever.get_stats()


@router.post("/search", summary="测试检索")
async def search_knowledge(
    request: SearchRequest,
    current_user=Depends(get_current_user),
):
    """手动验证知识库语义检索结果。"""
    del current_user
    results = knowledge_retriever.search(request.query, top_k=request.top_k)
    return {
        "query": request.query,
        "results": results,
        "count": len(results),
    }
