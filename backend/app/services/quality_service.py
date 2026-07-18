"""PCB 类别本地化、质检报告与看板快照。"""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, time, timedelta
from pathlib import Path
from uuid import uuid4

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.orm import Session

from app.core.logger import get_logger
from app.database.session import SessionLocal
from app.entity.db_models import (
    DashboardSnapshot,
    DetectionItem,
    DetectionReport,
    DetectionResult,
    DetectionTask,
    OperationLog,
)
from app.storage.minio_client import MinIOClient
from app.config.settings import settings
from app.services.report_service import persist_online_report, serialize_detection_task

logger = get_logger(__name__)

PCB_CLASS_NAMES_CN = {
    "missing_hole": "漏孔",
    "mouse_bite": "鼠咬",
    "open_circuit": "断路",
    "short": "短路",
    "spur": "毛刺",
    "spurious_copper": "多余铜",
}
HIGH_RISK = {"short", "open_circuit", "missing_hole"}


def class_name_cn(task: DetectionTask, class_name: str) -> str:
    mapping = task.scene.class_names_cn if task.scene and task.scene.class_names_cn else {}
    return mapping.get(class_name) or PCB_CLASS_NAMES_CN.get(class_name) or class_name


def _is_pcb_scene(task: DetectionTask | None) -> bool:
    if task is None:
        return True
    scene = task.scene
    if not scene:
        return False
    text = " ".join(
        str(value or "").lower()
        for value in (scene.name, scene.display_name, scene.category, scene.description)
    )
    return any(marker in text for marker in ("pcb", "printed circuit", "电路板"))


def _is_multi_image_task(task: DetectionTask | None) -> bool:
    """Return whether one task may contain multiple boards or multiple views."""
    return bool(task and getattr(task, "task_type", None) in {"batch", "folder", "zip"})


def evaluate_quality(results: list[DetectionResult], task: DetectionTask | None = None) -> dict:
    """Give deterministic scene-aware conclusions; PCB high-risk rules take priority."""
    if not _is_pcb_scene(task):
        if not results:
            return {
                "quality_conclusion": "未发现目标",
                "risk_level": None,
                "risk_reason": "未检测到达到当前置信度阈值的目标",
                "suggestion": "建议结合检测场景、图像质量和阈值设置进行复核；关键业务结果不应仅凭自动检测直接放行。",
            }
        low_confidence = any(result.confidence < 0.5 for result in results)
        return {
            "quality_conclusion": "发现目标，需复核",
            "risk_level": "low" if low_confidence else "medium",
            "risk_reason": f"检测到 {len(results)} 个目标" + ("，其中包含低置信度结果" if low_confidence else ""),
            "suggestion": "请按当前场景的业务规则核对目标类别、位置和置信度，并由人工确认后采取后续措施。",
        }

    multi_image = _is_multi_image_task(task)
    if not results:
        if multi_image:
            return {
                "quality_conclusion": "多图任务未检出疑似缺陷",
                "risk_level": None,
                "risk_reason": "成功处理的图像中未检出达到当前置信度阈值的缺陷候选",
                "suggestion": (
                    "当前结论仅适用于图像级自动筛查；建议按批次抽检规则复核后再决定流转，"
                    "不得将图像无检出率直接解释为 PCB 件数良率。"
                ),
            }
        return {
            "quality_conclusion": "合格",
            "risk_level": None,
            "risk_reason": "未检出达到当前置信度阈值的缺陷候选",
            "suggestion": "建议结合原图和业务规则复核后，再决定该图像对应检测对象是否继续流转。",
        }

    names = [result.class_name for result in results]
    if HIGH_RISK.intersection(names):
        high = sorted(
            {
                getattr(result, "class_name_cn", None)
                or PCB_CLASS_NAMES_CN.get(result.class_name)
                or result.class_name
                for result in results
                if result.class_name in HIGH_RISK
            }
        )
        if multi_image:
            return {
                "quality_conclusion": "多图任务筛查未通过",
                "risk_level": "high",
                "risk_reason": f"一个或多个检测项检出高风险缺陷候选：{', '.join(high)}",
                "suggestion": (
                    "隔离命中高风险缺陷候选的对应检测项并逐项人工复核；"
                    "其他检测项是否流转应按批次质检规则决定，不得据此认定整批 PCB 全部不合格。"
                ),
            }
        return {
            "quality_conclusion": "不合格",
            "risk_level": "high",
            "risk_reason": f"模型检出高风险缺陷候选：{', '.join(high)}",
            "suggestion": "建议暂缓该图像对应检测对象流转，人工确认后再决定返修、报废或继续流转。",
        }
    if "mouse_bite" in names or (not multi_image and len(results) > 1):
        return {
            "quality_conclusion": "多图任务需重点复核" if multi_image else "疑似缺陷",
            "risk_level": "medium",
            "risk_reason": (
                "一个或多个检测项检出鼠咬缺陷候选"
                if multi_image
                else "模型检出鼠咬或同一图像存在多处轻微缺陷候选"
            ),
            "suggestion": (
                "按检测项逐一人工复核，确认每张图像对应检测对象的缺陷范围后分别处置。"
                if multi_image
                else "转人工复检，确认缺陷范围后决定返修或继续流转。"
            ),
        }
    low_confidence = any(result.confidence < 0.5 for result in results)
    return {
        "quality_conclusion": "多图任务需人工复核" if multi_image else "疑似缺陷",
        "risk_level": "low",
        "risk_reason": (
            "一个或多个检测项检出毛刺、多余铜或低置信度缺陷候选"
            if multi_image and low_confidence
            else "一个或多个检测项检出一般风险缺陷候选"
            if multi_image
            else "模型检出毛刺、多余铜或低置信度缺陷候选"
            if low_confidence
            else "模型检出轻微缺陷候选"
        ),
        "suggestion": (
            "按检测项人工抽检并分别记录复核结论，不应把文件级检出直接换算为 PCB 件数良率。"
            if multi_image
            else "建议人工抽检并清理轻微缺陷，保留检测记录。"
        ),
    }


def _upsert_snapshot(
    db: Session,
    task: DetectionTask,
    user_id: int | None,
    scene_id: int | None,
    day: date | None = None,
) -> None:
    day = day or (task.created_at or datetime.now()).date()
    start = datetime.combine(day, time.min)
    end = datetime.combine(day, time.max)
    task_query = db.query(DetectionTask).filter(
        DetectionTask.created_at >= start,
        DetectionTask.created_at <= end,
    )
    item_query = (
        db.query(DetectionItem)
        .join(DetectionTask, DetectionItem.task_id == DetectionTask.id)
        .filter(
            DetectionTask.created_at >= start,
            DetectionTask.created_at <= end,
            DetectionTask.task_type != "camera",
        )
    )
    result_query = (
        db.query(DetectionResult)
        .join(DetectionTask, DetectionResult.task_id == DetectionTask.id)
        .filter(
            DetectionTask.created_at >= start,
            DetectionTask.created_at <= end,
        )
    )
    if user_id is not None:
        task_query = task_query.filter(DetectionTask.user_id == user_id)
        item_query = item_query.filter(DetectionTask.user_id == user_id)
        result_query = result_query.filter(DetectionTask.user_id == user_id)
    if scene_id is not None:
        task_query = task_query.filter(DetectionTask.scene_id == scene_id)
        item_query = item_query.filter(DetectionTask.scene_id == scene_id)
        result_query = result_query.filter(DetectionTask.scene_id == scene_id)

    completed_items = item_query.filter(DetectionItem.status == "completed")
    normal_passed = completed_items.filter(DetectionItem.defect_count == 0).count()
    normal_completed = completed_items.count()
    camera_tasks = task_query.filter(
        DetectionTask.task_type == "camera",
        DetectionTask.status == "completed",
    )
    camera_completed = camera_tasks.count()
    camera_passed = camera_tasks.filter(DetectionTask.total_objects == 0).count()
    passed = normal_passed + camera_passed
    successful_units = normal_completed + camera_completed
    defective = successful_units - passed
    distribution = {
        (cn or name): count
        for cn, name, count in result_query.with_entities(
            DetectionResult.class_name_cn,
            DetectionResult.class_name,
            func.count(DetectionResult.id),
        ).group_by(DetectionResult.class_name_cn, DetectionResult.class_name)
    }
    total_images = int(
        task_query.with_entities(func.coalesce(func.sum(DetectionTask.total_images), 0)).scalar() or 0
    )
    total_defects = int(
        task_query.with_entities(func.coalesce(func.sum(DetectionTask.total_objects), 0)).scalar() or 0
    )
    average_confidence = float(
        result_query.with_entities(func.coalesce(func.avg(DetectionResult.confidence), 0)).scalar() or 0
    )
    values = {
        "date_key": day,
        "user_id": user_id,
        "scene_id": scene_id,
        "total_tasks": task_query.count(),
        "total_images": total_images,
        "total_defects": total_defects,
        "pass_rate": round(100 * passed / successful_units, 2) if successful_units else 0,
        "defect_distribution": distribution,
        "trend_data": {
            "passed_items": passed,
            "defective_items": defective,
            "failed_items": item_query.filter(DetectionItem.status == "failed").count()
            + task_query.filter(
                DetectionTask.task_type == "camera",
                DetectionTask.status == "failed",
            ).count(),
            "average_confidence": round(average_confidence, 4),
        },
        "generated_at": datetime.now(),
    }

    bind = db.get_bind()
    if bind.dialect.name == "postgresql":
        statement = postgresql_insert(DashboardSnapshot).values(**values)
        statement = statement.on_conflict_do_update(
            constraint="uq_dashboard_snapshots_dimensions",
            set_={
                key: getattr(statement.excluded, key)
                for key in values
                if key not in {"date_key", "user_id", "scene_id"}
            },
        )
        db.execute(statement)
        return

    snapshot = db.query(DashboardSnapshot).filter(
        DashboardSnapshot.date_key == day,
        DashboardSnapshot.user_id.is_(user_id) if user_id is None else DashboardSnapshot.user_id == user_id,
        DashboardSnapshot.scene_id.is_(scene_id) if scene_id is None else DashboardSnapshot.scene_id == scene_id,
    ).first()
    if snapshot is None:
        snapshot = DashboardSnapshot(date_key=day, user_id=user_id, scene_id=scene_id)
        db.add(snapshot)
    for key, value in values.items():
        setattr(snapshot, key, value)
    db.flush()


def finalize_detection_task(
    db: Session,
    task: DetectionTask,
    input_paths: list[str] | None = None,
    failed_items: dict[str, str] | None = None,
) -> DetectionReport:
    """幂等生成检测项、报告和个人/全局快照。"""
    failed_items = failed_items or {}
    paths = (
        input_paths
        if input_paths is not None
        else []
        if task.task_type == "camera"
        else sorted({result.image_path for result in task.results})
    )
    existing = {item.input_path: item for item in task.items}
    for index, path in enumerate(paths):
        item = existing.get(path)
        if item is None:
            item = DetectionItem(
                task_id=task.id,
                item_index=index,
                file_name=Path(path).name,
                input_path=path,
            )
            db.add(item)
            db.flush()
        item_results = [result for result in task.results if result.image_path == path]
        for result in item_results:
            result.item_id = item.id
            result.class_name_cn = result.class_name_cn or class_name_cn(task, result.class_name)
        if path in failed_items:
            item.status = "failed"
            item.error_message = failed_items[path]
        else:
            item.status = "completed"
            item.defect_count = len(item_results)
            item.average_confidence = (
                sum(result.confidence for result in item_results) / len(item_results)
                if item_results else None
            )
            item.inference_time = max((result.inference_time or 0 for result in item_results), default=0)
            item.result_path = next(
                (result.annotated_image_path for result in item_results if result.annotated_image_path),
                item.result_path,
            )
            item.completed_at = task.completed_at or datetime.now()

    items = list(task.items)
    failed_count = sum(1 for item in items if item.status == "failed")
    completed_count = sum(1 for item in items if item.status == "completed")
    if task.status == "failed" or (failed_count and not completed_count):
        subject = "PCB" if _is_pcb_scene(task) else "检测对象"
        assessment = {
            "quality_conclusion": "检测失败",
            "risk_level": None,
            "risk_reason": f"{failed_count or task.total_images or 1} 个检测项均未成功处理",
            "suggestion": f"请检查输入文件、模型和存储服务后重新检测，不应据此判定 {subject} 合格。",
        }
    else:
        assessment = evaluate_quality(task.results, task)
        if failed_count:
            if not task.results:
                assessment["quality_conclusion"] = "疑似缺陷"
                assessment["risk_level"] = None
            assessment["risk_reason"] = (
                f"{assessment['risk_reason']}；另有 {failed_count} 个文件检测失败，结论仅覆盖成功项"
            )
            assessment["suggestion"] = (
                f"{assessment['suggestion']} 同时请重新检测失败文件，完整结果确认前不要作为整批放行依据。"
            )

    summary = Counter(result.class_name_cn or class_name_cn(task, result.class_name) for result in task.results)
    report = task.report
    if report is None:
        report = DetectionReport(task_id=task.id, report_uuid=str(uuid4()))
        db.add(report)
    report.quality_conclusion = assessment["quality_conclusion"]
    report.risk_level = assessment["risk_level"]
    report.defect_count = len(task.results)
    report.defect_summary = dict(summary)
    report.risk_reason = assessment["risk_reason"]
    report.suggestion = assessment["suggestion"]
    db.flush()

    try:
        client = MinIOClient()
        detail = serialize_detection_task(task, storage_client=client, report=report)
        _, object_name, _ = persist_online_report(
            detail,
            client,
            public_base_url=settings.PUBLIC_BASE_URL.strip().rstrip("/"),
        )
        report.report_path = object_name
    except Exception as exc:
        logger.warning("报告上传 MinIO 失败，保留数据库报告: %s", exc)

    # Dashboard APIs read current business tables directly. Snapshot refresh is
    # handled by the startup/hourly maintenance job so detection completion is
    # not delayed by four full-day aggregate queries.

    db.add(
        OperationLog(
            user_id=task.user_id,
            username=task.user.username if task.user else None,
            module="detection",
            action="failed" if task.status == "failed" else "complete",
            target_type="detection_task",
            target_id=str(task.id),
            description=(
                f"检测失败并生成失败报告 {report.report_uuid}"
                if task.status == "failed"
                else f"检测完成并生成报告 {report.report_uuid}"
            ),
            status="failed" if task.status == "failed" else "success",
            error_message=task.error_message if task.status == "failed" else None,
        )
    )
    db.commit()
    db.refresh(report)
    return report


def _refresh_snapshots(db: Session, tasks: list[DetectionTask]) -> int:
    dimensions: dict[tuple[date, int | None, int | None], DetectionTask] = {}
    for task in tasks:
        day = (task.created_at or datetime.now()).date()
        for user_id, scene_id in (
            (task.user_id, task.scene_id),
            (task.user_id, None),
            (None, task.scene_id),
            (None, None),
        ):
            dimensions[(day, user_id, scene_id)] = task
    for (day, user_id, scene_id), task in dimensions.items():
        _upsert_snapshot(db, task, user_id, scene_id, day=day)
    db.commit()
    return len(dimensions)


def refresh_recent_snapshots() -> int:
    """幂等补算最近两天快照，供每小时后台维护调用。"""
    db = SessionLocal()
    try:
        tasks = db.query(DetectionTask).filter(
            DetectionTask.created_at >= datetime.now() - timedelta(days=2),
        ).all()
        _refresh_snapshots(db, tasks)
        return len(tasks)
    finally:
        db.close()


def refresh_all_snapshots() -> int:
    """补算数据库内全部历史日期的个人/场景/全局四种维度。"""
    db = SessionLocal()
    try:
        tasks = db.query(DetectionTask).filter(DetectionTask.created_at.isnot(None)).all()
        return _refresh_snapshots(db, tasks)
    finally:
        db.close()
