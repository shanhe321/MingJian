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
import os
import tempfile

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.config.settings import settings
from app.database.session import get_db
from app.core.logger import get_logger
from app.services.history_service import history_service, render_report_markdown
from app.storage.minio_client import MinIOClient
from app.services.detection_service import detection_service
from app.services.audit_service import write_audit

logger = get_logger(__name__)

router = APIRouter(prefix="/api/history", tags=["检测历史"])


def _scope_user(current_user, requested_user_id: int | None = None) -> int | None:
    is_admin = getattr(current_user, "is_superuser", False) or any(
        item.role.name == "admin" for item in getattr(current_user, "user_roles", [])
    )
    return requested_user_id if is_admin else current_user.id


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
    defect_class: Optional[str] = Query(None, description="缺陷类别"),
    risk_level: Optional[str] = Query(None, description="风险等级"),
    user_id: Optional[int] = Query(None, description="管理员用户筛选"),
    current_user=Depends(get_current_user),
):
    """分页查询当前用户的检测任务列表。"""
    query_args = dict(
        user_id=_scope_user(current_user, user_id),
        page=page,
        page_size=page_size,
        task_type=task_type,
        status=status,
        scene_id=scene_id,
        start_date=start_date,
        end_date=end_date,
    )
    if defect_class is not None:
        query_args["defect_class"] = defect_class
    if risk_level is not None:
        query_args["risk_level"] = risk_level
    return history_service.list_tasks(**query_args)


@router.get("/tasks/{task_id}", summary="检测任务详情")
async def get_detection_task_detail(
    task_id: int,
    current_user=Depends(get_current_user),
):
    """获取任务基本信息及完整检测结果列表。"""
    result = history_service.get_task_detail(
        user_id=_scope_user(current_user),
        task_id=task_id,
    )
    if not result:
        raise HTTPException(status_code=404, detail="任务不存在或无权访问")
    return result


@router.delete("/tasks/{task_id}", summary="删除检测任务")
async def delete_detection_task(
    task_id: int,
    request: Request,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """删除当前用户的检测任务及其关联结果。"""
    success = history_service.delete_task(
        user_id=_scope_user(current_user),
        task_id=task_id,
    )
    if not success:
        raise HTTPException(status_code=404, detail="任务不存在或无权访问")
    logger.info("用户 %s 删除检测任务 #%d", current_user.username, task_id)
    write_audit(
        db, user=current_user, module="detection", action="delete",
        target_type="detection_task", target_id=task_id, request=request,
    )
    db.commit()
    return {"message": f"任务 #{task_id} 已删除", "task_id": task_id}


@router.get("/tasks/{task_id}/report.md", summary="下载 Markdown 检测报告")
async def download_detection_report(
    task_id: int,
    request: Request,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    detail = history_service.get_task_detail(_scope_user(current_user), task_id)
    if not detail or not detail.get("report"):
        raise HTTPException(status_code=404, detail="报告不存在或无权访问")
    # 始终按当前数据库内容渲染，旧任务也能获得新增的时间、文件、模型和失败项信息。
    content = render_report_markdown(
        detail,
        # 不使用 request.base_url，避免反向代理配置不完整时把
        # 127.0.0.1/localhost 写进下载后的报告。
        public_base_url=settings.PUBLIC_BASE_URL.strip().rstrip("/"),
    )
    write_audit(
        db, user=current_user, module="report", action="download",
        target_type="detection_task", target_id=task_id, request=request,
    )
    db.commit()
    return Response(
        content=content,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="detection-report-{task_id}.md"'},
    )


@router.post("/tasks/{task_id}/redetect", summary="使用原输入重新检测")
async def redetect_task(
    task_id: int,
    request: Request,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    detail = history_service.get_task_detail(_scope_user(current_user), task_id)
    if not detail:
        raise HTTPException(status_code=404, detail="任务不存在或无权访问")
    task = detail["task"]
    task_type = task["task_type"]
    if task_type in {"video", "camera"}:
        raise HTTPException(
            status_code=409,
            detail=f"{task_type} 检测依赖原始流媒体输入，历史任务不支持直接重新检测",
        )
    if task_type not in {"single", "batch", "folder", "zip"}:
        raise HTTPException(status_code=409, detail=f"不支持重新检测的任务类型: {task_type}")
    paths = [item["input_path"] for item in detail.get("items", []) if item.get("input_path")]
    if not paths:
        raise HTTPException(status_code=409, detail="历史输入不可恢复，无法重新检测")
    temp_paths = []
    try:
        client = MinIOClient()
        for object_path in paths:
            data = client.download_bytes(object_path)
            suffix = os.path.splitext(object_path)[1] or ".jpg"
            with tempfile.NamedTemporaryFile(prefix="rsod_redetect_", suffix=suffix, delete=False) as file:
                file.write(data); temp_paths.append(file.name)
        if task_type == "single":
            if len(temp_paths) != 1:
                raise HTTPException(status_code=409, detail="单图任务的历史输入数量异常，无法重新检测")
            result = detection_service.detect_single(
                temp_paths[0], conf=task["conf_threshold"], iou=task["iou_threshold"],
                scene_id=task["scene_id"], user_id=current_user.id,
                model_version_id=task.get("model_version_id"),
            )
        else:
            result = detection_service.detect_batch(
                temp_paths, conf=task["conf_threshold"], iou=task["iou_threshold"],
                scene_id=task["scene_id"], user_id=current_user.id, mode=task_type,
                model_version_id=task.get("model_version_id"),
            )
        if "error" in result:
            raise HTTPException(status_code=409, detail=result["error"])
        write_audit(
            db, user=current_user, module="detection", action="redetect",
            target_type="detection_task", target_id=result.get("task_id"),
            details={"source_task_id": task_id}, request=request,
        )
        db.commit()
        return result
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=409, detail=f"历史输入读取失败: {exc}") from exc
    finally:
        for path in temp_paths:
            try:
                os.unlink(path)
            except OSError:
                pass


@router.get("/summary", summary="历史记录快速统计")
async def get_history_summary(current_user=Depends(get_current_user)):
    """获取当前用户的任务总数、今日任务数和各状态任务数。"""
    return history_service.get_summary(user_id=current_user.id)


@router.get("/scenes", summary="获取所有检测场景列表")
async def list_scenes(_current_user=Depends(get_current_user)):
    """获取所有可用检测场景。"""
    return {"scenes": history_service.list_scenes()}
