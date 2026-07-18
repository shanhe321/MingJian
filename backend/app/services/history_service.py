"""检测历史记录查询与管理服务。"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin

from sqlalchemy import desc, func
from sqlalchemy.orm import joinedload, selectinload

from app.core.logger import get_logger
from app.database.session import SessionLocal
from app.entity.db_models import (
    DetectionReport,
    DetectionResult,
    DetectionScene,
    DetectionTask,
)
from app.storage.minio_client import MinIOClient

logger = get_logger(__name__)


def _object_url(client: MinIOClient | None, object_path: str | None) -> str | None:
    """只为对象名生成同源签名 URL，不把服务器本地路径暴露给浏览器。"""
    if not client or not object_path:
        return None
    if object_path.startswith("/api/storage/"):
        return object_path
    if object_path.startswith(("http://", "https://")) or os.path.isabs(object_path):
        return None
    return client.get_presigned_url(object_path)


def _markdown_cell(value) -> str:
    return str(value if value not in (None, "") else "-").replace("|", "\\|").replace("\n", " ")


def _absolute_media_url(url: str | None, public_base_url: str | None) -> str | None:
    if not url or not public_base_url or not url.startswith("/"):
        return url
    return urljoin(f"{public_base_url.rstrip('/')}/", url.lstrip("/"))


def _format_bbox(bbox) -> str:
    if not isinstance(bbox, (list, tuple)):
        return "-"
    return ", ".join(f"{float(value):.1f}" for value in bbox)


def _format_percent(value) -> str:
    return f"{float(value):.2%}" if value is not None else "-"


def _format_ms(value) -> str:
    return f"{float(value):.2f} ms" if value is not None else "-"


def render_report_markdown(detail: dict, public_base_url: str | None = None) -> bytes:
    """从数据库详情实时渲染完整报告，兼容早期不完整的 MinIO 报告。"""
    task = detail["task"]
    report = detail["report"]
    model = detail.get("model_version") or {}
    items = detail.get("items") or []
    failed = [item for item in items if item.get("status") == "failed"]
    results = detail.get("results") or []
    risk_order = {"short": 3, "open_circuit": 3, "missing_hole": 3, "mouse_bite": 2}
    highest = max(
        results,
        key=lambda result: (risk_order.get(result["class_name"], 1), result["confidence"]),
        default=None,
    )
    highest_text = (
        f"{highest.get('class_name_cn') or highest['class_name']}（置信度 {highest['confidence']:.2%}）"
        if highest else "无"
    )
    model_text = (
        f"{model.get('model_name')} / {model.get('version')}" if model else "未记录"
    )
    risk_text = {"low": "低风险", "medium": "中风险", "high": "高风险"}.get(
        report.get("risk_level"), "无"
    )
    lines = [
        f"# PCB 缺陷检测报告 {report['report_uuid']}",
        "",
        "## 一、任务概览",
        "",
        "| 项目 | 内容 | 项目 | 内容 |",
        "|---|---|---|---|",
        f"| 检测任务 | {_markdown_cell(task['id'])} | 检测用户 | {_markdown_cell(task.get('username') or task.get('user_id'))} |",
        f"| 检测场景 | {_markdown_cell(task.get('scene_name'))} | 检测模式 | {_markdown_cell(task.get('task_type'))} |",
        f"| 开始时间 | {_markdown_cell(task.get('created_at') or '未记录')} | 完成时间 | {_markdown_cell(task.get('completed_at') or '未完成')} |",
        f"| 模型版本 | {_markdown_cell(model_text)} | 处理数量 | {_markdown_cell(task.get('total_images', 0))} |",
        f"| 置信度阈值 | {_markdown_cell(task.get('conf_threshold'))} | IoU 阈值 | {_markdown_cell(task.get('iou_threshold'))} |",
        f"| 推理总耗时 | {_markdown_cell(task.get('total_inference_time'))} ms | 失败项数 | {len(failed)} |",
        "",
        "## 二、质检结论",
        "",
        "| 结论项 | 内容 |",
        "|---|---|",
        f"| 质检结论 | **{_markdown_cell(report['quality_conclusion'])}** |",
        f"| 风险等级 | **{risk_text}** |",
        f"| 缺陷总数 | {report['defect_count']} |",
        f"| 最高风险缺陷 | {_markdown_cell(highest_text)} |",
        f"| 风险原因 | {_markdown_cell(report.get('risk_reason') or '无')} |",
        f"| 处理建议 | {_markdown_cell(report.get('suggestion') or '无')} |",
        "",
    ]
    lines.extend(["## 三、缺陷分布", "", "| 缺陷类别 | 数量 | 占比 |", "|---|---:|---:|"])
    distribution = report.get("defect_summary") or {}
    if distribution:
        total_defects = max(1, sum(int(count) for count in distribution.values()))
        lines.extend(
            f"| {_markdown_cell(name)} | {count} | {int(count) / total_defects:.1%} |"
            for name, count in distribution.items()
        )
    else:
        lines.append("| 无 | 0 | 0% |")

    display_items = items[:20]
    lines.extend(["", "## 四、逐文件检测明细", ""])
    if len(items) > len(display_items):
        lines.append(f"> 本任务共 {len(items)} 个文件，报告内展示前 {len(display_items)} 个；完整结构化结果请在历史详情中查看。")
        lines.append("")

    if not display_items and task.get("task_type") == "camera":
        lines.append(f"浏览器摄像头会话共处理 {task.get('total_images', 0)} 帧。")
    elif not display_items:
        display_items = [{
            "id": None,
            "file_name": os.path.basename(task.get("input_path") or "检测输入"),
            "input_path": task.get("input_path"),
            "input_url": task.get("input_url"),
            "result_url": task.get("result_url"),
            "status": task.get("status"),
            "defect_count": report.get("defect_count", 0),
            "average_confidence": None,
            "inference_time": task.get("total_inference_time"),
            "error_message": task.get("error_message"),
        }]

    for index, item in enumerate(display_items, start=1):
        item_results = [
            result for result in results
            if (item.get("id") is not None and result.get("item_id") == item.get("id"))
            or (
                item.get("input_path")
                and result.get("image_path") == item.get("input_path")
            )
        ]
        lines.extend([
            f"### 4.{index} {_markdown_cell(item.get('file_name') or f'文件 {index}')}",
            "",
            "| 状态 | 缺陷数 | 平均置信度 | 推理耗时 |",
            "|---|---:|---:|---:|",
            f"| {_markdown_cell(item.get('status'))} | {item.get('defect_count') or 0} | "
            f"{_format_percent(item.get('average_confidence'))} | "
            f"{_format_ms(item.get('inference_time'))} |",
            "",
        ])
        if item.get("error_message"):
            lines.extend([f"> 检测失败原因：{_markdown_cell(item['error_message'])}", ""])

        input_url = _absolute_media_url(item.get("input_url"), public_base_url)
        result_url = _absolute_media_url(item.get("result_url"), public_base_url)
        if input_url:
            lines.extend([
                "**原始图像**",
                "",
                f"![原始图像 {index}]({input_url})",
                "",
                f"[在新窗口打开原始图像]({input_url})",
                "",
            ])
        if result_url:
            lines.extend([
                "**检测标注图**",
                "",
                f"![检测标注图 {index}]({result_url})",
                "",
                f"[在新窗口打开检测标注图]({result_url})",
                "",
            ])

        if item_results:
            lines.extend([
                "**缺陷框明细**",
                "",
                "| # | 缺陷类别 | 英文类别 | 置信度 | 边界框 x1,y1,x2,y2 | 推理耗时 |",
                "|---:|---|---|---:|---|---:|",
            ])
            for result_index, result in enumerate(item_results, start=1):
                lines.append(
                    f"| {result_index} | {_markdown_cell(result.get('class_name_cn') or result.get('class_name'))} | "
                    f"{_markdown_cell(result.get('class_name'))} | {float(result.get('confidence') or 0):.2%} | "
                    f"{_format_bbox(result.get('bbox'))} | "
                    f"{_format_ms(result.get('inference_time'))} |"
                )
            lines.append("")
        elif item.get("status") == "completed":
            lines.extend(["未检测到缺陷。", ""])

    lines.extend([
        "## 五、报告说明",
        "",
        "- 本报告由检测任务、逐文件检测项和缺陷框数据实时生成。",
        "- 报告中的图片使用受签名保护的同源访问地址，超过有效期后需从系统重新下载报告。",
        "- 自动检测结果用于辅助质检，高风险或疑似缺陷应结合人工复核后处置。",
    ])
    return ("\n".join(lines) + "\n").encode("utf-8")


class HistoryService:
    """当前用户检测任务的分页、详情、删除和摘要服务。"""

    @staticmethod
    def list_tasks(
        user_id: int | None,
        page: int = 1,
        page_size: int = 10,
        task_type: Optional[str] = None,
        status: Optional[str] = None,
        scene_id: Optional[int] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        defect_class: Optional[str] = None,
        risk_level: Optional[str] = None,
    ) -> dict:
        db = SessionLocal()
        try:
            query = db.query(DetectionTask).options(
                joinedload(DetectionTask.scene),
                joinedload(DetectionTask.user),
                joinedload(DetectionTask.report),
                joinedload(DetectionTask.model_version),
            )
            if user_id is not None:
                query = query.filter(DetectionTask.user_id == user_id)
            if task_type:
                query = query.filter(DetectionTask.task_type == task_type)
            if status:
                query = query.filter(DetectionTask.status == status)
            if scene_id:
                query = query.filter(DetectionTask.scene_id == scene_id)
            if defect_class:
                query = query.filter(DetectionTask.results.any(DetectionResult.class_name == defect_class))
            if risk_level:
                query = query.filter(DetectionTask.report.has(DetectionReport.risk_level == risk_level))
            if start_date:
                try:
                    query = query.filter(DetectionTask.created_at >= datetime.strptime(start_date, "%Y-%m-%d"))
                except ValueError:
                    pass
            if end_date:
                try:
                    query = query.filter(
                        DetectionTask.created_at
                        <= datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
                    )
                except ValueError:
                    pass

            total = query.count()
            tasks = query.order_by(desc(DetectionTask.created_at)).offset((page - 1) * page_size).limit(page_size).all()
            return {
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": (total + page_size - 1) // page_size,
                "items": [
                    {
                        "id": task.id,
                        "user_id": task.user_id,
                        "username": task.user.username if task.user else None,
                        "task_type": task.task_type,
                        "status": task.status,
                        "scene_id": task.scene_id,
                        "scene_name": task.scene.display_name if task.scene else None,
                        "model_version_id": task.model_version_id,
                        "model_version": task.model_version.version if task.model_version else None,
                        "total_images": task.total_images or 0,
                        "total_objects": task.total_objects or 0,
                        "total_inference_time": round(task.total_inference_time or 0, 2),
                        "conf_threshold": task.conf_threshold,
                        "error_message": task.error_message,
                        "risk_level": task.report.risk_level if task.report else None,
                        "quality_conclusion": task.report.quality_conclusion if task.report else None,
                        "created_at": task.created_at.isoformat() if task.created_at else None,
                        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
                    }
                    for task in tasks
                ],
            }
        finally:
            db.close()

    @staticmethod
    def get_task_detail(user_id: int | None, task_id: int) -> Optional[dict]:
        db = SessionLocal()
        try:
            query = db.query(DetectionTask).options(
                joinedload(DetectionTask.scene),
                joinedload(DetectionTask.user),
                joinedload(DetectionTask.model_version),
                joinedload(DetectionTask.report),
                selectinload(DetectionTask.items),
                selectinload(DetectionTask.results),
            ).filter(DetectionTask.id == task_id)
            if user_id is not None:
                query = query.filter(DetectionTask.user_id == user_id)
            task = query.first()
            if not task:
                return None

            try:
                minio_client = MinIOClient()
            except Exception:
                minio_client = None

            task_result_path = task.result_path
            if not task_result_path and task.task_type == "video" and minio_client:
                candidate = f"detections/{task.id}/annotated_video.mp4"
                try:
                    if minio_client.object_exists(candidate):
                        task_result_path = candidate
                except Exception:
                    pass

            class_counts: dict[str, int] = {}
            result_items = []
            for result in task.results:
                class_counts[result.class_name] = class_counts.get(result.class_name, 0) + 1
                result_items.append(
                    {
                        "id": result.id,
                        "item_id": result.item_id,
                        "class_name": result.class_name,
                        "class_name_cn": result.class_name_cn,
                        "class_id": result.class_id,
                        "confidence": round(result.confidence, 4),
                        "bbox": result.bbox,
                        "image_path": result.image_path,
                        "image_url": _object_url(minio_client, result.image_path),
                        "annotated_image_path": result.annotated_image_path,
                        "annotated_image_url": _object_url(minio_client, result.annotated_image_path),
                        "inference_time": round(result.inference_time, 2) if result.inference_time else None,
                    }
                )

            detail = {
                "task": {
                    "id": task.id,
                    "user_id": task.user_id,
                    "username": task.user.username if task.user else None,
                    "task_type": task.task_type,
                    "status": task.status,
                    "scene_id": task.scene_id,
                    "scene_name": task.scene.display_name if task.scene else None,
                    "model_version_id": task.model_version_id,
                    "input_path": task.input_path,
                    "input_url": _object_url(minio_client, task.input_path),
                    "result_path": task_result_path,
                    "result_url": _object_url(minio_client, task_result_path),
                    "annotated_video_url": (
                        _object_url(minio_client, task_result_path) if task.task_type == "video" else None
                    ),
                    "total_images": task.total_images or 0,
                    "total_objects": task.total_objects or 0,
                    "total_inference_time": round(task.total_inference_time or 0, 2),
                    "conf_threshold": task.conf_threshold,
                    "iou_threshold": task.iou_threshold,
                    "error_message": task.error_message,
                    "created_at": task.created_at.isoformat() if task.created_at else None,
                    "completed_at": task.completed_at.isoformat() if task.completed_at else None,
                },
                "model_version": (
                    {
                        "id": task.model_version.id,
                        "version": task.model_version.version,
                        "model_name": task.model_version.model_name,
                        "model_type": task.model_version.model_type,
                    }
                    if task.model_version else None
                ),
                "class_counts": class_counts,
                "results": result_items,
                "items": [
                    {
                        "id": item.id,
                        "item_index": item.item_index,
                        "file_name": item.file_name,
                        "input_path": item.input_path,
                        "input_url": _object_url(minio_client, item.input_path),
                        "result_path": item.result_path,
                        "result_url": _object_url(minio_client, item.result_path),
                        "status": item.status,
                        "defect_count": item.defect_count,
                        "average_confidence": item.average_confidence,
                        "inference_time": item.inference_time,
                        "error_message": item.error_message,
                    }
                    for item in task.items
                ],
                "report": (
                    {
                        "report_uuid": task.report.report_uuid,
                        "quality_conclusion": task.report.quality_conclusion,
                        "risk_level": task.report.risk_level,
                        "defect_count": task.report.defect_count,
                        "defect_summary": task.report.defect_summary,
                        "risk_reason": task.report.risk_reason,
                        "suggestion": task.report.suggestion,
                        "report_path": task.report.report_path,
                        "report_url": _object_url(minio_client, task.report.report_path),
                    }
                    if task.report else None
                ),
            }
            return detail
        finally:
            db.close()

    @staticmethod
    def delete_task(user_id: int | None, task_id: int) -> bool:
        db = SessionLocal()
        try:
            query = db.query(DetectionTask).filter(DetectionTask.id == task_id)
            if user_id is not None:
                query = query.filter(DetectionTask.user_id == user_id)
            task = query.first()
            if not task:
                return False
            owner_id = task.user_id
            db.delete(task)
            db.commit()
            try:
                client = MinIOClient()
                client.delete_prefix(f"detections/{task_id}/")
                client.delete_prefix(f"reports/{owner_id}/{task_id}/")
            except Exception as exc:
                logger.warning("任务已删除，但 MinIO 对象清理失败: %s", exc)
            logger.info("用户 %s 删除检测任务 #%d", user_id, task_id)
            return True
        finally:
            db.close()

    @staticmethod
    def get_summary(user_id: int) -> dict:
        db = SessionLocal()
        try:
            today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            rows = db.query(DetectionTask.status, func.count(DetectionTask.id)).filter(
                DetectionTask.user_id == user_id
            ).group_by(DetectionTask.status).all()
            status_counts = {status: 0 for status in ["completed", "processing", "failed", "pending"]}
            status_counts.update({status: count for status, count in rows})
            total, today_count = db.query(
                func.count(DetectionTask.id),
                func.count(DetectionTask.id).filter(DetectionTask.created_at >= today_start),
            ).filter(DetectionTask.user_id == user_id).one()
            return {"total_tasks": total, "today_tasks": today_count, "status_counts": status_counts}
        finally:
            db.close()

    @staticmethod
    def list_scenes() -> list:
        db = SessionLocal()
        try:
            scenes = db.query(DetectionScene).filter(DetectionScene.is_active.is_(True)).all()
            return [
                {"id": scene.id, "name": scene.name, "display_name": scene.display_name, "category": scene.category}
                for scene in scenes
            ]
        finally:
            db.close()


history_service = HistoryService()
