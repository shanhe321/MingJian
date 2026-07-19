"""知识库索引构建、统计和手动检索 API。"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator

from app.api.auth import get_current_user, require_admin
from app.rag.retriever import knowledge_retriever

router = APIRouter(prefix="/api/knowledge", tags=["知识库管理"])


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    top_k: int = Field(default=3, ge=1, le=20)

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("检索内容不能为空")
        return normalized


@router.post("/build", summary="构建知识库索引")
async def build_index(
    force_rebuild: bool = False,
    _admin=Depends(require_admin),
):
    """构建或重建三份领域文档的 Pgvector 索引。"""
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
