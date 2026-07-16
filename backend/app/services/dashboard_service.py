"""数据看板聚合统计服务。"""

from datetime import datetime, timedelta

from sqlalchemy import func

from app.database.session import SessionLocal
from app.entity.db_models import DetectionResult, DetectionScene, DetectionTask


class DashboardService:
    """当前用户检测任务的数据看板统计。"""

    @staticmethod
    def get_statistics(user_id: int, days: int = 30) -> dict:
        db = SessionLocal()
        try:
            now = datetime.now()
            start_date = now - timedelta(days=days)
            prev_start = now - timedelta(days=days * 2)

            current_stats = (
                db.query(
                    func.count(DetectionTask.id).label("total_tasks"),
                    func.coalesce(func.sum(DetectionTask.total_images), 0).label(
                        "total_images"
                    ),
                    func.coalesce(func.sum(DetectionTask.total_objects), 0).label(
                        "total_objects"
                    ),
                    func.coalesce(func.avg(DetectionTask.total_inference_time), 0).label(
                        "avg_inference_time"
                    ),
                )
                .filter(
                    DetectionTask.user_id == user_id,
                    DetectionTask.created_at >= start_date,
                )
                .first()
            )
            prev_stats = (
                db.query(
                    func.count(DetectionTask.id).label("total_tasks"),
                    func.coalesce(func.sum(DetectionTask.total_images), 0).label(
                        "total_images"
                    ),
                    func.coalesce(func.sum(DetectionTask.total_objects), 0).label(
                        "total_objects"
                    ),
                    func.coalesce(func.avg(DetectionTask.total_inference_time), 0).label(
                        "avg_inference_time"
                    ),
                )
                .filter(
                    DetectionTask.user_id == user_id,
                    DetectionTask.created_at >= prev_start,
                    DetectionTask.created_at < start_date,
                )
                .first()
            )

            def calc_growth(current, previous):
                if previous == 0:
                    return 100.0 if current > 0 else 0.0
                return round((current - previous) / previous * 100, 1)

            return {
                "total_tasks": current_stats.total_tasks,
                "total_images": int(current_stats.total_images),
                "total_objects": int(current_stats.total_objects),
                "avg_inference_time": round(float(current_stats.avg_inference_time), 2),
                "growth": {
                    "tasks": calc_growth(
                        current_stats.total_tasks,
                        prev_stats.total_tasks,
                    ),
                    "images": calc_growth(
                        int(current_stats.total_images),
                        int(prev_stats.total_images),
                    ),
                    "objects": calc_growth(
                        int(current_stats.total_objects),
                        int(prev_stats.total_objects),
                    ),
                    "inference_time": calc_growth(
                        float(current_stats.avg_inference_time),
                        float(prev_stats.avg_inference_time),
                    ),
                },
                "period_days": days,
            }
        finally:
            db.close()

    @staticmethod
    def get_trend(user_id: int, days: int = 30) -> dict:
        db = SessionLocal()
        try:
            start_date = datetime.now() - timedelta(days=days)
            day_column = func.date(DetectionTask.created_at)
            daily_stats = (
                db.query(
                    day_column.label("date"),
                    func.count(DetectionTask.id).label("task_count"),
                    func.coalesce(func.sum(DetectionTask.total_objects), 0).label(
                        "object_count"
                    ),
                    func.coalesce(func.sum(DetectionTask.total_images), 0).label(
                        "image_count"
                    ),
                )
                .filter(
                    DetectionTask.user_id == user_id,
                    DetectionTask.created_at >= start_date,
                )
                .group_by(day_column)
                .order_by(day_column)
                .all()
            )

            date_map = {}
            for row in daily_stats:
                date_str = str(row.date)
                date_map[date_str] = {
                    "date": date_str,
                    "task_count": row.task_count,
                    "object_count": int(row.object_count),
                    "image_count": int(row.image_count),
                }

            trend = []
            for i in range(days):
                date = (datetime.now() - timedelta(days=days - 1 - i)).strftime(
                    "%Y-%m-%d"
                )
                trend.append(
                    date_map.get(
                        date,
                        {
                            "date": date,
                            "task_count": 0,
                            "object_count": 0,
                            "image_count": 0,
                        },
                    )
                )
            return {"trend": trend, "period_days": days}
        finally:
            db.close()

    @staticmethod
    def get_class_distribution(user_id: int, days: int = 30) -> dict:
        db = SessionLocal()
        try:
            start_date = datetime.now() - timedelta(days=days)
            rows = (
                db.query(
                    DetectionResult.class_name,
                    func.count(DetectionResult.id).label("count"),
                )
                .join(DetectionTask, DetectionResult.task_id == DetectionTask.id)
                .filter(
                    DetectionTask.user_id == user_id,
                    DetectionTask.created_at >= start_date,
                )
                .group_by(DetectionResult.class_name)
                .order_by(func.count(DetectionResult.id).desc())
                .all()
            )
            return {
                "distribution": [
                    {"name": row.class_name, "value": row.count} for row in rows
                ],
                "period_days": days,
            }
        finally:
            db.close()

    @staticmethod
    def get_scene_distribution(user_id: int, days: int = 30) -> dict:
        db = SessionLocal()
        try:
            start_date = datetime.now() - timedelta(days=days)
            rows = (
                db.query(
                    DetectionScene.display_name,
                    func.count(DetectionTask.id).label("count"),
                )
                .join(DetectionScene, DetectionTask.scene_id == DetectionScene.id)
                .filter(
                    DetectionTask.user_id == user_id,
                    DetectionTask.created_at >= start_date,
                )
                .group_by(DetectionScene.display_name)
                .order_by(func.count(DetectionTask.id).desc())
                .all()
            )
            return {
                "distribution": [
                    {"name": row.display_name, "value": row.count} for row in rows
                ],
                "period_days": days,
            }
        finally:
            db.close()

    @staticmethod
    def get_type_distribution(user_id: int, days: int = 30) -> dict:
        db = SessionLocal()
        try:
            start_date = datetime.now() - timedelta(days=days)
            rows = (
                db.query(
                    DetectionTask.task_type,
                    func.count(DetectionTask.id).label("count"),
                )
                .filter(
                    DetectionTask.user_id == user_id,
                    DetectionTask.created_at >= start_date,
                )
                .group_by(DetectionTask.task_type)
                .order_by(func.count(DetectionTask.id).desc())
                .all()
            )
            type_names = {
                "single": "单图检测",
                "batch": "批量检测",
                "zip": "ZIP检测",
                "video": "视频检测",
                "camera": "摄像头检测",
            }
            return {
                "distribution": [
                    {
                        "name": type_names.get(row.task_type, row.task_type),
                        "value": row.count,
                    }
                    for row in rows
                ],
                "period_days": days,
            }
        finally:
            db.close()


dashboard_service = DashboardService()
