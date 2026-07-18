"""PCB 类别本地化、质检报告与看板快照。"""

from __future__ import annotations

import json
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


def evaluate_quality(results: list[DetectionResult]) -> dict:
    """严格按需求报告给出质检结论；高风险规则优先。"""
    if not results:
        return {
            "quality_conclusion": "合格",
            "risk_level": None,
            "risk_reason": "未检测到缺陷",
            "suggestion": "PCB 可判定为合格，建议按正常流程流转。",
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
        return {
            "quality_conclusion": "不合格",
            "risk_level": "high",
            "risk_reason": f"检测到高风险缺陷：{', '.join(high)}",
            "suggestion": "立即隔离该 PCB，停止流转并安排返修或报废复核。",
        }
    if "mouse_bite" in names or len(results) > 1:
        return {
            "quality_conclusion": "疑似缺陷",
            "risk_level": "medium",
            "risk_reason": "检测到鼠咬或多处轻微缺陷",
            "suggestion": "转人工复检，确认缺陷范围后决定返修或继续流转。",
        }
    low_confidence = any(result.confidence < 0.5 for result in results)
    return {
        "quality_conclusion": "疑似缺陷",
        "risk_level": "low",
        "risk_reason": "检测到毛刺、多余铜或低置信度缺陷" if low_confidence else "检测到轻微缺陷",
        "suggestion": "建议人工抽检并清理轻微缺陷，保留检测记录。",
    }


def _highest_risk_defect(task: DetectionTask) -> str:
    """返回报告中可读的最高风险缺陷；同级时选择置信度最高者。"""
    if not task.results:
        return "无"

    def priority(result: DetectionResult) -> tuple[int, float]:
        if result.class_name in HIGH_RISK:
            level = 3
        elif result.class_name == "mouse_bite":
            level = 2
        else:
            level = 1
        return level, result.confidence

    result = max(task.results, key=priority)
    localized = result.class_name_cn or class_name_cn(task, result.class_name)
    return f"{localized}（置信度 {result.confidence:.2%}）"


def _report_markdown(task: DetectionTask, report: DetectionReport) -> str:
    model = (
        f"{task.model_version.model_name} / {task.model_version.version}"
        if task.model_version else "未记录"
    )
    items = sorted(task.items, key=lambda item: item.item_index)
    failed = [item for item in items if item.status == "failed"]
    lines = [
        f"# PCB 缺陷检测报告 {report.report_uuid}",
        "",
        f"- 检测任务：{task.id}",
        f"- 检测用户：{task.user.username if task.user else task.user_id}",
        f"- 开始时间：{task.created_at.isoformat(sep=' ', timespec='seconds') if task.created_at else '未记录'}",
        f"- 完成时间：{task.completed_at.isoformat(sep=' ', timespec='seconds') if task.completed_at else '未完成'}",
        f"- 检测模式：{task.task_type}",
        f"- 模型版本：{model}",
        f"- 处理数量：{task.total_images or len(items)}",
        f"- 失败项数：{len(failed)}",
        f"- 质检结论：{report.quality_conclusion}",
        f"- 风险等级：{report.risk_level or '无'}",
        f"- 缺陷总数：{report.defect_count}",
        f"- 最高风险缺陷：{_highest_risk_defect(task)}",
        f"- 风险原因：{report.risk_reason}",
        f"- 处理建议：{report.suggestion}",
        "",
        "## 检测文件",
        "",
    ]
    if items:
        lines.extend(
            f"- {item.file_name}：{item.status}，缺陷 {item.defect_count or 0} 个"
            + (f"，失败原因：{item.error_message}" if item.status == "failed" else "")
            for item in items
        )
    elif task.task_type == "camera":
        lines.append(f"- 浏览器摄像头会话：处理 {task.total_images or 0} 帧")
    elif task.input_path:
        lines.append(f"- {Path(task.input_path).name}")
    else:
        lines.append("- 未记录可恢复的输入文件")
    lines.extend(
        [
            "",
            "## 缺陷分布",
            "",
            "```json",
            json.dumps(report.defect_summary or {}, ensure_ascii=False, indent=2),
            "```",
        ]
    )
    return "\n".join(lines) + "\n"


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
        assessment = {
            "quality_conclusion": "检测失败",
            "risk_level": None,
            "risk_reason": f"{failed_count or task.total_images or 1} 个检测项均未成功处理",
            "suggestion": "请检查输入文件、模型和存储服务后重新检测，不应据此判定 PCB 合格。",
        }
    else:
        assessment = evaluate_quality(task.results)
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

    object_name = f"reports/{task.user_id}/{task.id}/{report.report_uuid}.md"
    try:
        MinIOClient().upload_bytes(
            object_name,
            _report_markdown(task, report).encode("utf-8"),
            "text/markdown; charset=utf-8",
        )
        report.report_path = object_name
    except Exception as exc:
        logger.warning("报告上传 MinIO 失败，保留数据库报告: %s", exc)

    for user_id, scene_id in (
        (task.user_id, task.scene_id),
        (task.user_id, None),
        (None, task.scene_id),
        (None, None),
    ):
        _upsert_snapshot(db, task, user_id, scene_id)

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
