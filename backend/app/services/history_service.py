"""检测历史记录查询与管理服务。"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import desc, func, or_
from sqlalchemy.orm import joinedload, selectinload

from app.core.logger import get_logger
from app.database.session import SessionLocal
from app.entity.db_models import (
    DetectionReport,
    DetectionResult,
    DetectionScene,
    DetectionTask,
    User,
)
from app.storage.minio_client import MinIOClient
from app.services.report_service import (
    render_report_markdown,
    serialize_detection_task,
)

logger = get_logger(__name__)


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
        keyword: Optional[str] = None,
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
            if keyword and keyword.strip():
                pattern = f"%{keyword.strip()}%"
                query = query.filter(
                    or_(
                        DetectionTask.input_path.ilike(pattern),
                        DetectionTask.error_message.ilike(pattern),
                        DetectionTask.user.has(User.username.ilike(pattern)),
                        DetectionTask.scene.has(DetectionScene.display_name.ilike(pattern)),
                    )
                )
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

            return serialize_detection_task(
                task,
                storage_client=minio_client,
                task_result_path=task_result_path,
            )
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
