"""
训练服务 — 封装 YOLOv11 训练全流程

职责：
  - 启动本地 CPU 训练（start_training）
  - 查询训练状态（get_training_status）
  - 模型验证评估（validate_model）
  - 模型导出（export_model）
  - 获取模型路径（get_model_path）
"""

import os
import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.config.settings import settings
from app.core.logger import get_logger
from app.entity.db_models import (
    ModelVersion,
    TrainingMetric,
    TrainingTask,
)

logger = get_logger(__name__)


class TrainingService:
    """训练服务"""

    @staticmethod
    def create_task(
        db: Session,
        user_id: int,
        scene_id: int,
        model_name: str = "yolov11n",
        epochs: int = 100,
        img_size: int = 640,
        batch_size: int = 16,
        device: str = "cpu",
        optimizer: str = "SGD",
        lr0: float = 0.01,
        augment_config: dict = None,
        dataset_project_id: int = None,
    ) -> TrainingTask:
        """创建训练任务"""
        task = TrainingTask(
            user_id=user_id,
            scene_id=scene_id,
            dataset_project_id=dataset_project_id,
            task_uuid=uuid.uuid4().hex[:16],
            status="pending",
            model_name=model_name,
            epochs=epochs,
            img_size=img_size,
            batch_size=batch_size,
            device=device,
            optimizer=optimizer,
            lr0=lr0,
            augment_config=augment_config,
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        logger.info("训练任务创建: task_id=%d, uuid=%s", task.id, task.task_uuid)
        return task

    @staticmethod
    def get_status(db: Session, task_id: int) -> dict:
        """查询训练任务状态"""
        task = db.query(TrainingTask).filter(TrainingTask.id == task_id).first()
        if not task:
            return {"error": "任务不存在"}

        metrics = (
            db.query(TrainingMetric)
            .filter(TrainingMetric.task_id == task_id)
            .order_by(TrainingMetric.epoch.desc())
            .all()
        )

        return {
            "task_id": task.id,
            "task_uuid": task.task_uuid,
            "status": task.status,
            "model_name": task.model_name,
            "epochs": task.epochs,
            "current_epoch": task.current_epoch,
            "progress": task.progress,
            "error_message": task.error_message,
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "started_at": task.started_at.isoformat() if task.started_at else None,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            "metrics": [
                {
                    "epoch": m.epoch,
                    "box_loss": m.box_loss,
                    "cls_loss": m.cls_loss,
                    "dfl_loss": m.dfl_loss,
                    "precision": m.precision,
                    "recall": m.recall,
                    "map50": m.map50,
                    "map50_95": m.map50_95,
                }
                for m in metrics
            ],
        }

    @staticmethod
    def list_tasks(db: Session, user_id: int = None) -> list[dict]:
        """列出训练任务"""
        query = db.query(TrainingTask)
        if user_id is not None:
            query = query.filter(TrainingTask.user_id == user_id)
        query = query.order_by(TrainingTask.created_at.desc())
        tasks = query.all()

        return [
            {
                "id": t.id,
                "user_id": t.user_id,
                "scene_id": t.scene_id,
                "task_uuid": t.task_uuid,
                "status": t.status,
                "model_name": t.model_name,
                "epochs": t.epochs,
                "current_epoch": t.current_epoch,
                "progress": t.progress,
                "created_at": t.created_at.isoformat() if t.created_at else None,
                "completed_at": t.completed_at.isoformat() if t.completed_at else None,
            }
            for t in tasks
        ]

    @staticmethod
    def validate_model(
        db: Session,
        task_id: int,
        split: str = "val",
        conf: float = 0.25,
        iou: float = 0.45,
    ) -> dict:
        """
        对已完成训练的模型执行验证集评估

        flow:
          1. 查找训练任务对应的 best.pt 路径
          2. 加载模型并运行 model.val()
          3. 解析评估结果
          4. 将评估指标写入 ModelVersion 表
          5. 返回结构化评估报告
        """
        from ultralytics import YOLO

        task = db.query(TrainingTask).filter(TrainingTask.id == task_id).first()
        if not task:
            return {"error": "训练任务不存在"}
        if task.status != "completed":
            return {"error": f"训练任务状态为 {task.status}，只有已完成的任务才能评估"}

        original_cwd = os.getcwd()
        weights_path = os.path.join(
            original_cwd,
            settings.TRAIN_OUTPUT_DIR,
            f"task_{task.task_uuid}",
            "weights",
            "best.pt",
        )

        if not os.path.exists(weights_path):
            return {"error": f"模型权重不存在: {weights_path}"}

        data_yaml = task.data_yaml
        if not data_yaml or not os.path.exists(data_yaml):
            if task.dataset_path:
                data_yaml = os.path.join(task.dataset_path, "data.yaml")
            if not data_yaml or not os.path.exists(data_yaml):
                return {"error": "data.yaml 不存在"}

        logger.info("开始模型评估: task_id=%d, weights=%s, split=%s", task_id, weights_path, split)

        try:
            model = YOLO(weights_path)
            results = model.val(
                data=data_yaml,
                split=split,
                conf=conf,
                iou=iou,
                imgsz=task.img_size,
                device="cpu",
                save_json=True,
                plots=True,
                project=os.path.join(original_cwd, settings.TRAIN_OUTPUT_DIR),
                name=f"task_{task.task_uuid}",
                exist_ok=True,
                verbose=False,
            )

            overall = {
                "precision": round(float(results.box.mp), 4),
                "recall": round(float(results.box.mr), 4),
                "map50": round(float(results.box.map50), 4),
                "map50_95": round(float(results.box.map), 4),
            }

            per_class = {}
            if results.box.ap is not None:
                for i, ap50 in enumerate(results.box.ap50):
                    class_name = model.names.get(i, f"class_{i}")
                    ap50_95 = results.box.ap[i] if i < len(results.box.ap) else 0.0
                    per_class[class_name] = {
                        "ap50": round(float(ap50), 4),
                        "ap50_95": round(float(ap50_95), 4),
                    }

            # 写入 ModelVersion 表
            model_version = (
                db.query(ModelVersion)
                .filter(ModelVersion.training_task_id == task_id)
                .first()
            )
            if model_version:
                model_version.map50 = overall["map50"]
                model_version.map50_95 = overall["map50_95"]
                model_version.precision = overall["precision"]
                model_version.recall = overall["recall"]
                model_version.per_class_ap = per_class
                db.commit()
                logger.info("模型评估指标已写入 ModelVersion id=%d", model_version.id)

            return {
                "task_id": task_id,
                "split": split,
                "overall": overall,
                "per_class": per_class,
            }

        except Exception as e:
            logger.error("模型评估异常: %s", str(e), exc_info=True)
            return {"error": f"评估失败: {str(e)}"}

    @staticmethod
    def export_model(
        db: Session,
        task_id: int,
        version: str = "v1.0.0",
        description: str = None,
    ) -> dict:
        """
        导出训练完成的模型为 ModelVersion

        flow:
          1. 查找训练任务
          2. 确认 best.pt 存在
          3. 创建或更新 ModelVersion 记录
          4. 返回模型版本信息
        """
        task = db.query(TrainingTask).filter(TrainingTask.id == task_id).first()
        if not task:
            return {"error": "训练任务不存在"}
        if task.status != "completed":
            return {"error": f"训练任务状态为 {task.status}"}

        weights_path = os.path.join(
            os.getcwd(),
            settings.TRAIN_OUTPUT_DIR,
            f"task_{task.task_uuid}",
            "weights",
            "best.pt",
        )

        if not os.path.exists(weights_path):
            return {"error": f"模型权重不存在: {weights_path}"}

        file_size = os.path.getsize(weights_path)

        # 查找已有的 model_version 或创建新的
        model_version = (
            db.query(ModelVersion)
            .filter(ModelVersion.training_task_id == task_id)
            .first()
        )

        if model_version:
            model_version.model_path = weights_path
            model_version.file_size = file_size
            model_version.description = description or model_version.description
            model_version.status = "active"
        else:
            model_version = ModelVersion(
                scene_id=task.scene_id,
                training_task_id=task_id,
                version=version,
                model_name=task.model_name,
                model_type=task.model_name,
                model_path=weights_path,
                file_size=file_size,
                description=description,
                status="active",
                is_default=False,
            )
            db.add(model_version)

        db.commit()
        db.refresh(model_version)

        logger.info("模型导出成功: version_id=%d, path=%s", model_version.id, weights_path)

        return {
            "id": model_version.id,
            "version": model_version.version,
            "model_name": model_version.model_name,
            "model_path": model_version.model_path,
            "file_size": model_version.file_size,
            "map50": model_version.map50,
            "map50_95": model_version.map50_95,
        }

    @staticmethod
    def get_model_path(db: Session, task_id: int) -> str:
        """获取训练任务的模型权重路径"""
        task = db.query(TrainingTask).filter(TrainingTask.id == task_id).first()
        if not task:
            return None

        weights_path = os.path.join(
            os.getcwd(),
            settings.TRAIN_OUTPUT_DIR,
            f"task_{task.task_uuid}",
            "weights",
            "best.pt",
        )

        if os.path.exists(weights_path):
            return weights_path
        return None


# 全局单例
training_service = TrainingService()
