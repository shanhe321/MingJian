"""数据看板聚合统计服务。"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import case, func
from sqlalchemy.orm import joinedload

from app.database.session import SessionLocal
from app.entity.db_models import (
    DetectionItem,
    DetectionReport,
    DetectionResult,
    DetectionScene,
    DetectionTask,
)


def _user_scope(query, user_id: int | None):
    return query.filter(DetectionTask.user_id == user_id) if user_id is not None else query


class DashboardService:
    """个人或管理员全局检测数据看板统计。"""

    @staticmethod
    def get_overview(user_id: int | None, days: int = 30) -> dict:
        db = SessionLocal()
        try:
            start = datetime.now() - timedelta(days=days)
            today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            period_tasks = _user_scope(
                db.query(DetectionTask).filter(DetectionTask.created_at >= start), user_id
            )
            all_tasks = _user_scope(db.query(DetectionTask), user_id)

            all_image_count = all_tasks.with_entities(
                func.coalesce(func.sum(DetectionTask.total_images), 0)
            ).scalar()

            # 普通检测按成功检测项计 PCB；摄像头按一次成功会话计一个统计单元，
            # 避免“无缺陷摄像头不保存关键帧，因此完全不进入合格率”的偏差。
            item_units = _user_scope(
                db.query(
                    func.count(DetectionItem.id).label("total"),
                    func.coalesce(
                        func.sum(case((DetectionItem.defect_count == 0, 1), else_=0)), 0
                    ).label("passed"),
                )
                .join(DetectionTask, DetectionItem.task_id == DetectionTask.id)
                .filter(
                    DetectionTask.created_at >= start,
                    DetectionTask.task_type != "camera",
                    DetectionItem.status == "completed",
                ),
                user_id,
            ).one()
            camera_units = _user_scope(
                db.query(
                    func.count(DetectionTask.id).label("total"),
                    func.coalesce(
                        func.sum(case((DetectionTask.total_objects == 0, 1), else_=0)), 0
                    ).label("passed"),
                ).filter(
                    DetectionTask.created_at >= start,
                    DetectionTask.task_type == "camera",
                    DetectionTask.status == "completed",
                ),
                user_id,
            ).one()
            successful = int(item_units.total or 0) + int(camera_units.total or 0)
            passed = int(item_units.passed or 0) + int(camera_units.passed or 0)
            defective = successful - passed

            results = _user_scope(
                db.query(DetectionResult)
                .join(DetectionTask, DetectionResult.task_id == DetectionTask.id)
                .filter(DetectionTask.created_at >= start),
                user_id,
            )
            reports = _user_scope(
                db.query(DetectionReport)
                .join(DetectionTask, DetectionReport.task_id == DetectionTask.id)
                .filter(DetectionTask.created_at >= start),
                user_id,
            )
            class_rows = results.with_entities(
                DetectionResult.class_name_cn,
                DetectionResult.class_name,
                func.count(DetectionResult.id),
                func.avg(DetectionResult.confidence),
            ).group_by(DetectionResult.class_name_cn, DetectionResult.class_name).all()
            risk_rows = reports.with_entities(
                DetectionReport.risk_level, func.count(DetectionReport.id)
            ).group_by(DetectionReport.risk_level).all()
            average_confidence = results.with_entities(
                func.coalesce(func.avg(DetectionResult.confidence), 0)
            ).scalar()

            day_col = func.date(DetectionTask.created_at)
            trend_rows = period_tasks.with_entities(
                day_col,
                func.count(DetectionTask.id),
                func.coalesce(func.sum(DetectionTask.total_images), 0),
                func.coalesce(func.sum(DetectionTask.total_objects), 0),
            ).group_by(day_col).order_by(day_col).all()
            scene_rows = period_tasks.with_entities(
                DetectionScene.display_name, func.count(DetectionTask.id)
            ).join(DetectionScene, DetectionTask.scene_id == DetectionScene.id).group_by(
                DetectionScene.display_name
            ).order_by(func.count(DetectionTask.id).desc()).all()
            recent = period_tasks.options(joinedload(DetectionTask.report)).order_by(
                DetectionTask.created_at.desc()
            ).limit(10).all()
            return {
                "scope": "global" if user_id is None else "personal",
                "today_detections": period_tasks.filter(DetectionTask.created_at >= today).count(),
                "total_detections": all_tasks.count(),
                "today_items": int(
                    period_tasks.filter(DetectionTask.created_at >= today).with_entities(
                        func.coalesce(func.sum(DetectionTask.total_images), 0)
                    ).scalar() or 0
                ),
                "total_items": int(all_image_count or 0),
                "qualified_pcbs": passed,
                "defective_pcbs": defective,
                "pass_rate": round(100 * passed / successful, 2) if successful else 0,
                "average_confidence": round(float(average_confidence or 0), 4),
                "class_distribution": [
                    {
                        "name": cn or name,
                        "value": count,
                        "average_confidence": round(float(confidence or 0), 4),
                    }
                    for cn, name, count, confidence in class_rows
                ],
                "risk_distribution": [
                    {"name": risk or "none", "value": count} for risk, count in risk_rows
                ],
                "trend": [
                    {
                        "date": str(day),
                        "task_count": task_count,
                        "image_count": int(image_count),
                        "defect_count": int(defect_count),
                    }
                    for day, task_count, image_count, defect_count in trend_rows
                ],
                "scene_distribution": [{"name": name, "value": count} for name, count in scene_rows],
                "recent_records": [
                    {
                        "task_id": task.id,
                        "user_id": task.user_id,
                        "task_type": task.task_type,
                        "status": task.status,
                        "total_images": task.total_images,
                        "total_objects": task.total_objects,
                        "risk_level": task.report.risk_level if task.report else None,
                        "quality_conclusion": task.report.quality_conclusion if task.report else None,
                        "created_at": task.created_at,
                    }
                    for task in recent
                ],
                "period_days": days,
            }
        finally:
            db.close()

    @staticmethod
    def get_statistics(user_id: int | None, days: int = 30) -> dict:
        db = SessionLocal()
        try:
            now = datetime.now()
            start_date = now - timedelta(days=days)
            prev_start = now - timedelta(days=days * 2)

            def aggregate(start_at, end_at=None):
                query = _user_scope(
                    db.query(
                        func.count(DetectionTask.id).label("total_tasks"),
                        func.coalesce(func.sum(DetectionTask.total_images), 0).label("total_images"),
                        func.coalesce(func.sum(DetectionTask.total_objects), 0).label("total_objects"),
                        func.coalesce(func.avg(DetectionTask.total_inference_time), 0).label("avg_inference_time"),
                    ).filter(DetectionTask.created_at >= start_at),
                    user_id,
                )
                if end_at is not None:
                    query = query.filter(DetectionTask.created_at < end_at)
                return query.one()

            current_stats = aggregate(start_date)
            prev_stats = aggregate(prev_start, start_date)

            def calc_growth(current, previous):
                if previous == 0:
                    return 100.0 if current > 0 else 0.0
                return round((current - previous) / previous * 100, 1)

            return {
                "scope": "global" if user_id is None else "personal",
                "total_tasks": current_stats.total_tasks,
                "total_images": int(current_stats.total_images),
                "total_objects": int(current_stats.total_objects),
                "avg_inference_time": round(float(current_stats.avg_inference_time), 2),
                "growth": {
                    "tasks": calc_growth(current_stats.total_tasks, prev_stats.total_tasks),
                    "images": calc_growth(int(current_stats.total_images), int(prev_stats.total_images)),
                    "objects": calc_growth(int(current_stats.total_objects), int(prev_stats.total_objects)),
                    "inference_time": calc_growth(
                        float(current_stats.avg_inference_time), float(prev_stats.avg_inference_time)
                    ),
                },
                "period_days": days,
            }
        finally:
            db.close()

    @staticmethod
    def get_trend(user_id: int | None, days: int = 30) -> dict:
        db = SessionLocal()
        try:
            start_date = datetime.now() - timedelta(days=days)
            day_column = func.date(DetectionTask.created_at)
            daily_stats = _user_scope(
                db.query(
                    day_column.label("date"),
                    func.count(DetectionTask.id).label("task_count"),
                    func.coalesce(func.sum(DetectionTask.total_objects), 0).label("object_count"),
                    func.coalesce(func.sum(DetectionTask.total_images), 0).label("image_count"),
                ).filter(DetectionTask.created_at >= start_date),
                user_id,
            ).group_by(day_column).order_by(day_column).all()
            date_map = {
                str(row.date): {
                    "date": str(row.date),
                    "task_count": row.task_count,
                    "object_count": int(row.object_count),
                    "image_count": int(row.image_count),
                }
                for row in daily_stats
            }
            trend = []
            for i in range(days):
                date = (datetime.now() - timedelta(days=days - 1 - i)).strftime("%Y-%m-%d")
                trend.append(
                    date_map.get(
                        date,
                        {"date": date, "task_count": 0, "object_count": 0, "image_count": 0},
                    )
                )
            return {"scope": "global" if user_id is None else "personal", "trend": trend, "period_days": days}
        finally:
            db.close()

    @staticmethod
    def get_class_distribution(user_id: int | None, days: int = 30) -> dict:
        db = SessionLocal()
        try:
            start_date = datetime.now() - timedelta(days=days)
            rows = _user_scope(
                db.query(
                    DetectionResult.class_name_cn,
                    DetectionResult.class_name,
                    func.count(DetectionResult.id).label("count"),
                ).join(DetectionTask, DetectionResult.task_id == DetectionTask.id).filter(
                    DetectionTask.created_at >= start_date
                ),
                user_id,
            ).group_by(DetectionResult.class_name_cn, DetectionResult.class_name).order_by(
                func.count(DetectionResult.id).desc()
            ).all()
            return {
                "scope": "global" if user_id is None else "personal",
                "distribution": [{"name": row.class_name_cn or row.class_name, "value": row.count} for row in rows],
                "period_days": days,
            }
        finally:
            db.close()

    @staticmethod
    def get_scene_distribution(user_id: int | None, days: int = 30) -> dict:
        db = SessionLocal()
        try:
            start_date = datetime.now() - timedelta(days=days)
            rows = _user_scope(
                db.query(DetectionScene.display_name, func.count(DetectionTask.id).label("count"))
                .join(DetectionScene, DetectionTask.scene_id == DetectionScene.id)
                .filter(DetectionTask.created_at >= start_date),
                user_id,
            ).group_by(DetectionScene.display_name).order_by(func.count(DetectionTask.id).desc()).all()
            return {
                "scope": "global" if user_id is None else "personal",
                "distribution": [{"name": row.display_name, "value": row.count} for row in rows],
                "period_days": days,
            }
        finally:
            db.close()

    @staticmethod
    def get_type_distribution(user_id: int | None, days: int = 30) -> dict:
        db = SessionLocal()
        try:
            start_date = datetime.now() - timedelta(days=days)
            rows = _user_scope(
                db.query(DetectionTask.task_type, func.count(DetectionTask.id).label("count")).filter(
                    DetectionTask.created_at >= start_date
                ),
                user_id,
            ).group_by(DetectionTask.task_type).order_by(func.count(DetectionTask.id).desc()).all()
            type_names = {
                "single": "单图检测",
                "batch": "批量检测",
                "folder": "文件夹检测",
                "zip": "ZIP检测",
                "video": "视频检测",
                "camera": "摄像头检测",
            }
            return {
                "scope": "global" if user_id is None else "personal",
                "distribution": [{"name": type_names.get(row.task_type, row.task_type), "value": row.count} for row in rows],
                "period_days": days,
            }
        finally:
            db.close()


dashboard_service = DashboardService()
