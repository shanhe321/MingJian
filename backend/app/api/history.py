"""
检测历史记录 API 路由

接口列表：
  - GET    /api/history/tasks         检测任务分页列表
  - GET    /api/history/tasks/{id}    检测任务详情
  - DELETE /api/history/tasks/{id}    删除检测任务
  - GET    /api/history/summary       历史记录快速统计
  - GET    /api/history/scenes        获取检测场景列表
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from app.api.auth import get_current_user
from app.core.logger import get_logger
from app.services.history_service import history_service

logger = get_logger(__name__)

router = APIRouter(prefix="/api/history", tags=["检测历史"])


@router.get("/tasks", summary="检测任务分页列表")
async def list_detection_tasks(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(10, ge=1, le=100, description="每页数量"),
    task_type: Optional[str] = Query(None, description="任务类型筛选"),
    status: Optional[str] = Query(None, description="状态筛选"),
    scene_id: Optional[int] = Query(None, description="场景 ID 筛选"),
    start_date: Optional[str] = Query(None, description="起始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    keyword: Optional[str] = Query(None, description="关键词搜索（预留）"),
    current_user=Depends(get_current_user),
):
    """分页查询当前用户的检测任务列表。"""
    return history_service.list_tasks(
        user_id=current_user.id,
        page=page,
        page_size=page_size,
        task_type=task_type,
        status=status,
        scene_id=scene_id,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/tasks/{task_id}", summary="检测任务详情")
async def get_detection_task_detail(
    task_id: int,
    current_user=Depends(get_current_user),
):
    """获取任务基本信息及完整检测结果列表。"""
    result = history_service.get_task_detail(
        user_id=current_user.id,
        task_id=task_id,
    )
    if not result:
        return JSONResponse(
            status_code=404,
            content={"error": "任务不存在或无权访问"},
        )
    return result


@router.delete("/tasks/{task_id}", summary="删除检测任务")
async def delete_detection_task(
    task_id: int,
    current_user=Depends(get_current_user),
):
    """删除当前用户的检测任务及其关联结果。"""
    success = history_service.delete_task(
        user_id=current_user.id,
        task_id=task_id,
    )
    if not success:
        return JSONResponse(
            status_code=404,
            content={"error": "任务不存在或无权访问"},
        )
    logger.info("用户 %s 删除检测任务 #%d", current_user.username, task_id)
    return {"message": f"任务 #{task_id} 已删除", "task_id": task_id}


@router.get("/summary", summary="历史记录快速统计")
async def get_history_summary(current_user=Depends(get_current_user)):
    """获取当前用户的任务总数、今日任务数和各状态任务数。"""
    return history_service.get_summary(user_id=current_user.id)


@router.get("/scenes", summary="获取所有检测场景列表")
async def list_scenes(_current_user=Depends(get_current_user)):
    """获取所有可用检测场景。"""
    return {"scenes": history_service.list_scenes()}
