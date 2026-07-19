"""Agent 可调用的检测统计、历史和用户查询工具。"""

import json
from datetime import datetime, timedelta

from langchain_core.tools import tool
from sqlalchemy import func
from sqlalchemy.orm import joinedload

from app.agent.tools.context import current_user_id, current_user_is_superuser
from app.core.logger import get_logger
from app.database.session import SessionLocal
from app.entity.db_models import (
    DetectionReport,
    DetectionResult,
    DetectionTask,
    ModelVersion,
    Permission,
    User,
    UserRole,
)

logger = get_logger(__name__)


def _personal_scope_error() -> str | None:
    if current_user_id.get() is None:
        return json.dumps({"error": "缺少当前用户上下文，无法查询个人数据"}, ensure_ascii=False)
    return None


def _bounded(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(int(value), maximum))


@tool
def query_detection_stats(days: int = 30) -> str:
    """查询当前用户最近 N 天的检测统计数据。

    当用户询问检测次数、目标数量、图片数量或平均推理耗时时使用。

    Args:
        days: 统计最近 N 天的数据，默认 30 天。

    Returns:
        JSON 字符串，包含任务数、目标数、图片数和平均推理耗时。
    """
    if error := _personal_scope_error():
        return error
    days = _bounded(days, 1, 365)
    db = SessionLocal()
    try:
        query = db.query(
            func.count(DetectionTask.id),
            func.coalesce(func.sum(DetectionTask.total_objects), 0),
            func.coalesce(func.sum(DetectionTask.total_images), 0),
            func.coalesce(func.avg(DetectionTask.total_inference_time), 0),
        ).filter(DetectionTask.created_at >= datetime.now() - timedelta(days=days))
        query = query.filter(DetectionTask.user_id == current_user_id.get())
        row = query.first()
        return json.dumps(
            {
                "period": f"最近 {days} 天",
                "total_tasks": row[0],
                "total_objects": int(row[1]),
                "total_images": int(row[2]),
                "avg_inference_time": round(float(row[3]), 2),
            },
            ensure_ascii=False,
        )
    except Exception as exc:
        logger.error("查询统计失败: %s", str(exc))
        return json.dumps({"error": f"查询失败: {str(exc)}"}, ensure_ascii=False)
    finally:
        db.close()


@tool
def query_detection_history(limit: int = 10) -> str:
    """查询当前用户最近的检测历史记录。

    当用户询问上次检测结果、最近检测内容或检测历史时使用。

    Args:
        limit: 返回最近 N 条记录，默认 10 条。

    Returns:
        JSON 字符串，包含任务类型、状态、目标数、图片数和创建时间。
    """
    if error := _personal_scope_error():
        return error
    limit = _bounded(limit, 1, 50)
    db = SessionLocal()
    try:
        query = db.query(DetectionTask).order_by(DetectionTask.created_at.desc())
        query = query.filter(DetectionTask.user_id == current_user_id.get())
        tasks = query.limit(limit).all()
        return json.dumps(
            {
                "history": [
                    {
                        "id": task.id,
                        "task_type": task.task_type,
                        "status": task.status,
                        "total_objects": task.total_objects or 0,
                        "total_images": task.total_images or 0,
                        "created_at": (
                            task.created_at.isoformat() if task.created_at else None
                        ),
                    }
                    for task in tasks
                ],
                "count": len(tasks),
            },
            ensure_ascii=False,
        )
    except Exception as exc:
        logger.error("查询历史失败: %s", str(exc))
        return json.dumps({"error": f"查询失败: {str(exc)}"}, ensure_ascii=False)
    finally:
        db.close()


@tool
def query_defect_distribution(days: int = 30) -> str:
    """查询当前用户最近 N 天的缺陷类别分布和平均置信度。"""
    if error := _personal_scope_error():
        return error
    days = _bounded(days, 1, 365)
    db = SessionLocal()
    try:
        rows = (
            db.query(
                DetectionResult.class_name,
                DetectionResult.class_name_cn,
                func.count(DetectionResult.id),
                func.avg(DetectionResult.confidence),
            )
            .join(DetectionTask, DetectionTask.id == DetectionResult.task_id)
            .filter(
                DetectionTask.user_id == current_user_id.get(),
                DetectionTask.created_at >= datetime.now() - timedelta(days=days),
            )
            .group_by(DetectionResult.class_name, DetectionResult.class_name_cn)
            .order_by(func.count(DetectionResult.id).desc())
            .all()
        )
        return json.dumps(
            {
                "period": f"最近 {days} 天",
                "distribution": [
                    {
                        "class_name": class_name,
                        "class_name_cn": class_name_cn,
                        "count": count,
                        "average_confidence": round(float(avg_confidence or 0), 4),
                    }
                    for class_name, class_name_cn, count, avg_confidence in rows
                ],
            },
            ensure_ascii=False,
        )
    except Exception as exc:
        logger.error("查询缺陷类别分布失败: %s", str(exc))
        return json.dumps({"error": f"查询失败: {str(exc)}"}, ensure_ascii=False)
    finally:
        db.close()


@tool
def query_detection_trend(days: int = 30) -> str:
    """查询当前用户最近 N 天按日汇总的检测和缺陷趋势。"""
    if error := _personal_scope_error():
        return error
    days = _bounded(days, 1, 365)
    db = SessionLocal()
    try:
        rows = (
            db.query(
                func.date(DetectionTask.created_at).label("date_key"),
                func.count(DetectionTask.id),
                func.coalesce(func.sum(DetectionTask.total_images), 0),
                func.coalesce(func.sum(DetectionTask.total_objects), 0),
            )
            .filter(
                DetectionTask.user_id == current_user_id.get(),
                DetectionTask.created_at >= datetime.now() - timedelta(days=days),
            )
            .group_by(func.date(DetectionTask.created_at))
            .order_by(func.date(DetectionTask.created_at))
            .all()
        )
        return json.dumps(
            {
                "period": f"最近 {days} 天",
                "trend": [
                    {
                        "date": str(date_key),
                        "task_count": task_count,
                        "image_count": int(image_count),
                        "defect_count": int(defect_count),
                    }
                    for date_key, task_count, image_count, defect_count in rows
                ],
            },
            ensure_ascii=False,
        )
    except Exception as exc:
        logger.error("查询检测趋势失败: %s", str(exc))
        return json.dumps({"error": f"查询失败: {str(exc)}"}, ensure_ascii=False)
    finally:
        db.close()


@tool
def query_risk_distribution(days: int = 30) -> str:
    """查询当前用户最近 N 天质检报告的风险等级分布。"""
    if error := _personal_scope_error():
        return error
    days = _bounded(days, 1, 365)
    db = SessionLocal()
    try:
        rows = (
            db.query(DetectionReport.risk_level, func.count(DetectionReport.id))
            .join(DetectionTask, DetectionTask.id == DetectionReport.task_id)
            .filter(
                DetectionTask.user_id == current_user_id.get(),
                DetectionTask.created_at >= datetime.now() - timedelta(days=days),
            )
            .group_by(DetectionReport.risk_level)
            .all()
        )
        return json.dumps(
            {
                "period": f"最近 {days} 天",
                "distribution": {
                    risk_level or "none": count for risk_level, count in rows
                },
            },
            ensure_ascii=False,
        )
    except Exception as exc:
        logger.error("查询风险分布失败: %s", str(exc))
        return json.dumps({"error": f"查询失败: {str(exc)}"}, ensure_ascii=False)
    finally:
        db.close()


@tool
def query_user_list(limit: int = 20) -> str:
    """查询系统用户列表，仅管理员可使用。

    当管理员询问系统用户、管理员或用户列表时使用。

    Args:
        limit: 返回最多 N 个用户，默认 20 个。

    Returns:
        JSON 字符串，包含用户名、邮箱、角色和启用状态。
    """
    if not current_user_is_superuser.get():
        return json.dumps({"error": "仅管理员可以查询用户列表"}, ensure_ascii=False)

    limit = _bounded(limit, 1, 100)
    db = SessionLocal()
    try:
        users = (
            db.query(User)
            .options(joinedload(User.user_roles).joinedload(UserRole.role))
            .order_by(User.created_at.desc())
            .limit(limit)
            .all()
        )
        return json.dumps(
            {
                "users": [
                    {
                        "id": user.id,
                        "username": user.username,
                        "email": user.email,
                        "roles": [role.role.name for role in user.user_roles],
                        "is_active": user.is_active,
                    }
                    for user in users
                ],
                "count": len(users),
            },
            ensure_ascii=False,
        )
    except Exception as exc:
        logger.error("查询用户列表失败: %s", str(exc))
        return json.dumps({"error": f"查询失败: {str(exc)}"}, ensure_ascii=False)
    finally:
        db.close()


@tool
def query_permissions() -> str:
    """管理员只读查询系统权限编码。"""
    if not current_user_is_superuser.get():
        return json.dumps({"error": "仅管理员可以查询权限"}, ensure_ascii=False)
    db = SessionLocal()
    try:
        rows = db.query(Permission).order_by(Permission.module, Permission.code).all()
        return json.dumps({"permissions": [{"code": row.code, "name": row.name, "module": row.module} for row in rows]}, ensure_ascii=False)
    finally:
        db.close()


@tool
def query_system_detection_total() -> str:
    """管理员只读查询全系统检测任务和图片总量。"""
    if not current_user_is_superuser.get():
        return json.dumps({"error": "仅管理员可以查询系统检测量"}, ensure_ascii=False)
    db = SessionLocal()
    try:
        task_count, image_count = db.query(
            func.count(DetectionTask.id), func.coalesce(func.sum(DetectionTask.total_images), 0)
        ).first()
        return json.dumps({"total_tasks": task_count, "total_images": int(image_count)}, ensure_ascii=False)
    finally:
        db.close()


@tool
def query_model_versions(limit: int = 20) -> str:
    """管理员只读查询模型版本。"""
    if not current_user_is_superuser.get():
        return json.dumps({"error": "仅管理员可以查询模型版本"}, ensure_ascii=False)
    limit = _bounded(limit, 1, 100)
    db = SessionLocal()
    try:
        rows = db.query(ModelVersion).order_by(ModelVersion.created_at.desc()).limit(limit).all()
        return json.dumps({"models": [{"id": row.id, "version": row.version, "scene_id": row.scene_id, "status": row.status, "is_default": row.is_default} for row in rows]}, ensure_ascii=False)
    finally:
        db.close()


ANALYSIS_TOOLS = [
    query_detection_stats,
    query_detection_history,
    query_defect_distribution,
    query_detection_trend,
    query_risk_distribution,
]

MANAGEMENT_TOOLS = [
    query_user_list,
    query_permissions,
    query_system_detection_total,
    query_model_versions,
]
