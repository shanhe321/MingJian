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
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.api.auth import get_current_user
from app.config.settings import settings
from app.database.session import get_db
from app.core.logger import get_logger
from app.entity.db_models import DetectionReport
from app.services.history_service import history_service, render_report_markdown
from app.services.report_service import build_report_archive, persist_online_report
from app.services.report_narrative_service import (
    AIGC_ANALYSIS_VERSION,
    generate_report_ai_content,
)
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


async def _ensure_report_ai_content(detail: dict, db: Session) -> dict:
    report_data = detail.get("report") or {}
    if (
        report_data.get("statistics_explanation")
        and report_data.get("aigc_analysis", {}).get("version") == AIGC_ANALYSIS_VERSION
    ):
        return detail
    try:
        allow_agent = db.get_bind().dialect.name != "sqlite"
    except Exception:
        allow_agent = True
    content = await run_in_threadpool(
        generate_report_ai_content,
        detail,
        allow_agent=allow_agent,
    )
    report_data.update({
        "statistics_explanation": content.statistics_explanation,
        "statistics_explanation_source": content.source,
        "statistics_explanation_generated_at": content.generated_at.isoformat(),
        "aigc_analysis": content.analysis,
        "aigc_analysis_source": content.source,
        "aigc_analysis_generated_at": content.generated_at.isoformat(),
    })
    report_record = db.query(DetectionReport).filter(
        DetectionReport.task_id == detail.get("task", {}).get("id")
    ).first()
    if report_record is not None:
        report_record.statistics_explanation = content.statistics_explanation
        report_record.statistics_explanation_source = content.source
        report_record.statistics_explanation_generated_at = content.generated_at
        report_record.aigc_analysis = content.analysis
        report_record.aigc_analysis_source = content.source
        report_record.aigc_analysis_generated_at = content.generated_at
        db.flush()
    return detail


@router.get("/tasks", summary="检测任务分页列表")
def list_detection_tasks(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(10, ge=1, le=100, description="每页数量"),
    task_type: Optional[str] = Query(None, description="任务类型筛选"),
    status: Optional[str] = Query(None, description="状态筛选"),
    scene_id: Optional[int] = Query(None, description="场景 ID 筛选"),
    start_date: Optional[str] = Query(None, description="起始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    keyword: Optional[str] = Query(None, min_length=1, max_length=100, description="用户名、场景、输入路径或错误信息关键词"),
    defect_class: Optional[str] = Query(None, description="缺陷类别"),
    risk_level: Optional[str] = Query(None, description="风险等级"),
    user_id: Optional[int] = Query(None, description="管理员用户筛选"),
    current_user=Depends(get_current_user),
):
    """分页查询当前用户的检测任务列表。"""
    for field_name, value in (("start_date", start_date), ("end_date", end_date)):
        if value:
            try:
                datetime.strptime(value, "%Y-%m-%d")
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=f"{field_name} 必须是有效的 YYYY-MM-DD 日期") from exc
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
    if keyword is not None:
        query_args["keyword"] = keyword
    return history_service.list_tasks(**query_args)


@router.get("/tasks/{task_id}", summary="检测任务详情")
def get_detection_task_detail(
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
def delete_detection_task(
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
    detail = await _ensure_report_ai_content(detail, db)
    # 始终按当前数据库内容渲染，旧任务也能获得新增的时间、文件、模型和失败项信息。
    public_base_url = settings.PUBLIC_BASE_URL.strip().rstrip("/")
    try:
        client = MinIOClient()
        content, _, _ = await run_in_threadpool(
            persist_online_report, detail, client, public_base_url
        )
    except Exception as exc:
        logger.warning("报告图表持久化失败，返回无图表 Markdown: %s", exc)
        content = render_report_markdown(detail, public_base_url=public_base_url)
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


@router.get("/tasks/{task_id}/report.zip", summary="下载可离线保存的检测报告归档")
async def download_detection_report_archive(
    task_id: int,
    request: Request,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    detail = history_service.get_task_detail(_scope_user(current_user), task_id)
    if not detail or not detail.get("report"):
        raise HTTPException(status_code=404, detail="报告不存在或无权访问")
    detail = await _ensure_report_ai_content(detail, db)
    try:
        try:
            storage_client = MinIOClient()
        except Exception as storage_exc:
            logger.warning("对象存储不可用，ZIP 将只包含报告、图表和结构化结果: %s", storage_exc)
            storage_client = None
        content = await run_in_threadpool(
            build_report_archive,
            detail,
            storage_client,
            settings.REPORT_ARCHIVE_MAX_MEDIA_MB * 1024 * 1024,
        )
    except Exception as exc:
        logger.exception("生成报告 ZIP 失败: task_id=%s", task_id)
        raise HTTPException(status_code=502, detail=f"报告归档生成失败: {exc}") from exc
    write_audit(
        db, user=current_user, module="report", action="download_archive",
        target_type="detection_task", target_id=task_id, request=request,
    )
    db.commit()
    return Response(
        content=content,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="detection-report-{task_id}.zip"'},
    )


@router.post("/tasks/{task_id}/redetect", summary="使用原输入重新检测")
def redetect_task(
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
def get_history_summary(current_user=Depends(get_current_user)):
    """获取当前用户的任务总数、今日任务数和各状态任务数。"""
    return history_service.get_summary(user_id=current_user.id)


@router.get("/scenes", summary="获取所有检测场景列表")
def list_scenes(_current_user=Depends(get_current_user)):
    """获取所有可用检测场景。"""
    return {"scenes": history_service.list_scenes()}
