"""
数据看板 API 路由 — 聚合统计查询接口

接口列表：
  - GET /api/dashboard/statistics    汇总统计
  - GET /api/dashboard/trend         每日检测趋势
  - GET /api/dashboard/class-dist    类别分布统计
  - GET /api/dashboard/scene-dist    场景分布统计
  - GET /api/dashboard/type-dist     任务类型分布统计
"""

from fastapi import APIRouter, Depends, Query, HTTPException

from app.api.auth import get_current_user
from app.services.dashboard_service import dashboard_service

router = APIRouter(prefix="/api/dashboard", tags=["数据看板"])


def _dashboard_user(current_user, scope: str) -> int | None:
    if scope == "personal":
        return current_user.id
    is_admin = getattr(current_user, "is_superuser", False) or any(item.role.name == "admin" for item in getattr(current_user, "user_roles", []))
    if not is_admin:
        raise HTTPException(status_code=403, detail="全局看板仅管理员可用")
    return None


@router.get("/overview", summary="需求指标完整看板")
def get_overview(
    days: int = Query(30, ge=1, le=365),
    scope: str = Query("personal", pattern="^(personal|global)$"),
    current_user=Depends(get_current_user),
):
    return dashboard_service.get_overview(_dashboard_user(current_user, scope), days)


@router.get("/statistics", summary="汇总统计")
def get_statistics(
    days: int = Query(30, ge=1, le=365, description="统计最近 N 天"),
    scope: str = Query("personal", pattern="^(personal|global)$"),
    current_user=Depends(get_current_user),
):
    """获取检测汇总统计数据及与上一同等时段的环比增长率。"""
    return dashboard_service.get_statistics(user_id=_dashboard_user(current_user, scope), days=days)


@router.get("/trend", summary="每日检测趋势")
def get_trend(
    days: int = Query(30, ge=1, le=365, description="统计最近 N 天"),
    scope: str = Query("personal", pattern="^(personal|global)$"),
    current_user=Depends(get_current_user),
):
    """获取每天的检测任务数、目标数和图片数。"""
    return dashboard_service.get_trend(user_id=_dashboard_user(current_user, scope), days=days)


@router.get("/class-dist", summary="类别分布统计")
def get_class_distribution(
    days: int = Query(30, ge=1, le=365),
    scope: str = Query("personal", pattern="^(personal|global)$"),
    current_user=Depends(get_current_user),
):
    """获取各类别检测次数分布。"""
    return dashboard_service.get_class_distribution(
        user_id=_dashboard_user(current_user, scope),
        days=days,
    )


@router.get("/scene-dist", summary="场景分布统计")
def get_scene_distribution(
    days: int = Query(30, ge=1, le=365),
    scope: str = Query("personal", pattern="^(personal|global)$"),
    current_user=Depends(get_current_user),
):
    """获取各检测场景的任务分布。"""
    return dashboard_service.get_scene_distribution(
        user_id=_dashboard_user(current_user, scope),
        days=days,
    )


@router.get("/type-dist", summary="任务类型分布统计")
def get_type_distribution(
    days: int = Query(30, ge=1, le=365),
    scope: str = Query("personal", pattern="^(personal|global)$"),
    current_user=Depends(get_current_user),
):
    """获取各任务类型的分布。"""
    return dashboard_service.get_type_distribution(
        user_id=_dashboard_user(current_user, scope),
        days=days,
    )
