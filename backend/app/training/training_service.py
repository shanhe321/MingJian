from __future__ import annotations

import csv
import json
import os
import shutil
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.config.settings import settings
from app.core.logger import get_logger
from app.database.session import SessionLocal
from app.entity.db_models import DetectionScene, ModelVersion, TrainingMetric, TrainingTask

logger = get_logger(__name__)

BACKEND_DIR = Path(__file__).resolve().parents[2]


class TrainingService:
    def __init__(self) -> None:
        self._running_tasks: dict[int, Any] = {}
        self._tasks_lock = threading.Lock()

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
    def _absolute_path(path: str | os.PathLike[str]) -> Path:
        value = Path(path)
        return value.resolve() if value.is_absolute() else (BACKEND_DIR / value).resolve()

    @classmethod
    def _task_output_dir(cls, task_uuid: str) -> Path:
        return cls._absolute_path(settings.TRAIN_OUTPUT_DIR) / f"task_{task_uuid}"

    @classmethod
    def _weights_path(cls, task_uuid: str) -> Path:
        return cls._task_output_dir(task_uuid) / "weights" / "best.pt"

    @staticmethod
    def _safe_float(value: Any) -> float | None:
        try:
            if value is None or str(value).strip() == "":
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _model_checkpoint(model_name: str) -> str:
        if model_name.endswith(".pt") or Path(model_name).exists():
            return model_name
        normalized = model_name
        if normalized.startswith("yolov11"):
            normalized = "yolo11" + normalized[len("yolov11") :]
        return f"{normalized}.pt"

    @staticmethod
    def _count_dataset_images(dataset_path: str) -> int:
        image_root = Path(dataset_path) / "images"
        image_exts = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
        if not image_root.exists():
            return 0
        return sum(1 for path in image_root.rglob("*") if path.is_file() and path.suffix.lower() in image_exts)

    def start_training(
        self,
        db: Session,
        user_id: int,
        scene_id: int,
        config: dict,
    ) -> TrainingTask:
        task_uuid = uuid.uuid4().hex[:8]
        dataset_path = str(Path(config["dataset_path"]).resolve())
        data_yaml = str(Path(config["data_yaml"]).resolve())
        task = TrainingTask(
            user_id=user_id,
            scene_id=scene_id,
            dataset_project_id=config.get("dataset_project_id"),
            task_uuid=task_uuid,
            status="pending",
            model_name=config.get("model_name", "yolov11n"),
            epochs=config.get("epochs", 100),
            img_size=config.get("img_size", 640),
            batch_size=config.get("batch_size", 16),
            device=config.get("device", "cpu"),
            optimizer=config.get("optimizer", "SGD"),
            lr0=config.get("lr0", 0.01),
            augment_config=config.get("augment_config"),
            dataset_path=dataset_path,
            data_yaml=data_yaml,
            dataset_size=self._count_dataset_images(dataset_path),
        )
        db.add(task)
        db.commit()
        db.refresh(task)

        thread = threading.Thread(
            target=self._run_training,
            args=(task.id, task.task_uuid, config.copy()),
            daemon=True,
            name=f"train-{task.task_uuid}",
        )
        thread.start()
        logger.info("训练任务已创建: task_id=%d, uuid=%s", task.id, task.task_uuid)
        return task

    def _run_training(self, task_id: int, task_uuid: str, config: dict) -> None:
        db = SessionLocal()
        try:
            from ultralytics import YOLO

            task = db.query(TrainingTask).filter(TrainingTask.id == task_id).first()
            if task is None:
                logger.error("后台训练启动失败，任务不存在: %d", task_id)
                return
            if task.status == "cancelled":
                logger.info("训练任务在后台启动前已取消: task_id=%d", task_id)
                return

            task.status = "running"
            task.started_at = datetime.now()
            task.error_message = None
            db.commit()

            model = YOLO(self._model_checkpoint(config.get("model_name", "yolov11n")))
            with self._tasks_lock:
                self._running_tasks[task_id] = model

            def on_train_epoch_end(trainer) -> None:
                epoch = int(getattr(trainer, "epoch", 0)) + 1
                metrics = dict(getattr(trainer, "metrics", {}) or {})
                losses = getattr(trainer, "tloss", None)
                if hasattr(losses, "tolist"):
                    losses = losses.tolist()
                losses = list(losses or [])
                values = {
                    "box_loss": self._safe_float(losses[0] if len(losses) > 0 else None),
                    "cls_loss": self._safe_float(losses[1] if len(losses) > 1 else None),
                    "dfl_loss": self._safe_float(losses[2] if len(losses) > 2 else None),
                    "precision": self._safe_float(metrics.get("metrics/precision(B)")),
                    "recall": self._safe_float(metrics.get("metrics/recall(B)")),
                    "map50": self._safe_float(metrics.get("metrics/mAP50(B)")),
                    "map50_95": self._safe_float(metrics.get("metrics/mAP50-95(B)")),
                    "lr": self._safe_float((getattr(trainer, "lr", {}) or {}).get("lr/pg0")),
                }
                self._upsert_metric(db, task_id, epoch, values)
                task.current_epoch = epoch
                task.progress = min(100, round(epoch / max(task.epochs, 1) * 100))
                db.commit()

            model.add_callback("on_train_epoch_end", on_train_epoch_end)
            train_args = {
                "data": str(Path(config["data_yaml"]).resolve()),
                "epochs": config.get("epochs", 100),
                "imgsz": config.get("img_size", 640),
                "batch": config.get("batch_size", 16),
                "device": config.get("device", "cpu"),
                "optimizer": config.get("optimizer", "SGD"),
                "lr0": config.get("lr0", 0.01),
                "project": str(self._absolute_path(settings.TRAIN_OUTPUT_DIR)),
                "name": f"task_{task_uuid}",
                "exist_ok": True,
                "plots": True,
                "verbose": True,
            }
            reserved_args = {
                "data", "epochs", "imgsz", "batch", "device", "optimizer",
                "lr0", "project", "name", "exist_ok",
            }
            train_args.update(
                {
                    key: value
                    for key, value in (config.get("augment_config") or {}).items()
                    if key not in reserved_args
                }
            )
            model.train(**train_args)

            self._parse_final_results(db, task_id, self._task_output_dir(task_uuid) / "results.csv")
            db.refresh(task)
            if task.status != "cancelled":
                task.status = "completed"
                task.current_epoch = task.epochs
                task.progress = 100
                task.completed_at = datetime.now()
                db.commit()
                logger.info("训练完成: task_id=%d", task_id)
        except Exception as exc:
            db.rollback()
            task = db.query(TrainingTask).filter(TrainingTask.id == task_id).first()
            if task is not None and task.status != "cancelled":
                task.status = "failed"
                task.error_message = str(exc)
                task.completed_at = datetime.now()
                db.commit()
            logger.error("训练失败: task_id=%d, error=%s", task_id, exc, exc_info=True)
        finally:
            with self._tasks_lock:
                self._running_tasks.pop(task_id, None)
            db.close()

    @classmethod
    def _upsert_metric(cls, db: Session, task_id: int, epoch: int, values: dict) -> None:
        metric = (
            db.query(TrainingMetric)
            .filter(TrainingMetric.task_id == task_id, TrainingMetric.epoch == epoch)
            .first()
        )
        if metric is None:
            metric = TrainingMetric(task_id=task_id, epoch=epoch)
            db.add(metric)
        for field, value in values.items():
            if value is not None:
                setattr(metric, field, value)

    @classmethod
    def _parse_final_results(cls, db: Session, task_id: int, csv_path: Path) -> None:
        if not csv_path.exists():
            return
        with csv_path.open("r", encoding="utf-8-sig", newline="") as file:
            for row in csv.DictReader(file):
                row = {str(key).strip(): value for key, value in row.items()}
                epoch_value = cls._safe_float(row.get("epoch"))
                if epoch_value is None:
                    continue
                values = {
                    "box_loss": cls._safe_float(row.get("train/box_loss")),
                    "cls_loss": cls._safe_float(row.get("train/cls_loss")),
                    "dfl_loss": cls._safe_float(row.get("train/dfl_loss")),
                    "precision": cls._safe_float(row.get("metrics/precision(B)")),
                    "recall": cls._safe_float(row.get("metrics/recall(B)")),
                    "map50": cls._safe_float(row.get("metrics/mAP50(B)")),
                    "map50_95": cls._safe_float(row.get("metrics/mAP50-95(B)")),
                    "lr": cls._safe_float(row.get("lr/pg0")),
                }
                cls._upsert_metric(db, task_id, int(epoch_value) + 1, values)
        db.commit()

    @staticmethod
    def _metric_dict(metric: TrainingMetric | None) -> dict | None:
        if metric is None:
            return None
        return {
            "epoch": metric.epoch,
            "box_loss": metric.box_loss,
            "cls_loss": metric.cls_loss,
            "dfl_loss": metric.dfl_loss,
            "precision": metric.precision,
            "recall": metric.recall,
            "map50": metric.map50,
            "map50_95": metric.map50_95,
            "lr": metric.lr,
        }

    def get_training_status(self, db: Session, task_id: int) -> dict:
        task = db.query(TrainingTask).filter(TrainingTask.id == task_id).first()
        if task is None:
            return {"error": "训练任务不存在"}
        latest = (
            db.query(TrainingMetric)
            .filter(TrainingMetric.task_id == task_id)
            .order_by(TrainingMetric.epoch.desc())
            .first()
        )
        with self._tasks_lock:
            is_running = task.id in self._running_tasks
        return {
            "task": {
                "id": task.id,
                "task_uuid": task.task_uuid,
                "status": task.status,
                "model_name": task.model_name,
                "epochs": task.epochs,
                "current_epoch": task.current_epoch,
                "progress": task.progress,
                "device": task.device,
            },
            "latest_metric": self._metric_dict(latest),
            "is_running": is_running,
        }

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
                    "epoch": metric.epoch,
                    "box_loss": metric.box_loss,
                    "cls_loss": metric.cls_loss,
                    "dfl_loss": metric.dfl_loss,
                    "precision": metric.precision,
                    "recall": metric.recall,
                    "map50": metric.map50,
                    "map50_95": metric.map50_95,
                }
                for metric in metrics
            ],
        }

    @staticmethod
    def get_task_list(db: Session, user_id: int | None = None) -> list[dict]:
        query = db.query(TrainingTask)
        if user_id is not None:
            query = query.filter(TrainingTask.user_id == user_id)
        tasks = query.order_by(TrainingTask.created_at.desc()).all()
        return [
            {
                "id": task.id,
                "task_uuid": task.task_uuid,
                "scene_id": task.scene_id,
                "status": task.status,
                "model_name": task.model_name,
                "epochs": task.epochs,
                "current_epoch": task.current_epoch,
                "progress": task.progress,
                "img_size": task.img_size,
                "batch_size": task.batch_size,
                "device": task.device,
                "error_message": task.error_message,
                "created_at": task.created_at.isoformat() if task.created_at else None,
                "started_at": task.started_at.isoformat() if task.started_at else None,
                "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            }
            for task in tasks
        ]

    @staticmethod
    def list_tasks(db: Session, user_id: int = None) -> list[dict]:
        """列出训练任务"""
        query = db.query(TrainingTask)
        if user_id is not None:
            query = query.filter(TrainingTask.user_id == user_id)
        tasks = query.order_by(TrainingTask.created_at.desc()).all()
        return [
            {
                "id": task.id,
                "user_id": task.user_id,
                "scene_id": task.scene_id,
                "task_uuid": task.task_uuid,
                "status": task.status,
                "model_name": task.model_name,
                "epochs": task.epochs,
                "current_epoch": task.current_epoch,
                "progress": task.progress,
                "created_at": task.created_at.isoformat() if task.created_at else None,
                "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            }
            for task in tasks
        ]

    def get_training_metrics(self, db: Session, task_id: int) -> list[dict]:
        metrics = (
            db.query(TrainingMetric)
            .filter(TrainingMetric.task_id == task_id)
            .order_by(TrainingMetric.epoch.asc())
            .all()
        )
        return [self._metric_dict(metric) for metric in metrics]

    def stop_training(self, db: Session, task_id: int) -> dict:
        task = db.query(TrainingTask).filter(TrainingTask.id == task_id).first()
        if task is None:
            return {"error": "训练任务不存在"}
        if task.status not in {"pending", "running"}:
            return {"error": f"训练任务状态为 {task.status}，无法停止"}
        with self._tasks_lock:
            model = self._running_tasks.get(task_id)
        trainer = getattr(model, "trainer", None) if model is not None else None
        if trainer is not None:
            stop = getattr(trainer, "stop", None)
            if callable(stop):
                stop()
            else:
                setattr(trainer, "stop", True)
        task.status = "cancelled"
        task.completed_at = datetime.now()
        db.commit()
        return {"task_id": task_id, "status": "cancelled", "message": "训练任务已停止"}

    def validate_model(
        self,
        db: Session,
        task_id: int,
        split: str = "val",
        conf: float = 0.25,
        iou: float = 0.45,
    ) -> dict:
        """
        对已完成训练的模型执行验证集评估

        流程：
          1. 查找训练任务对应的 best.pt 路径
          2. 加载模型并运行 model.val()
          3. 解析评估结果
          4. 将评估指标写入 ModelVersion 表
          5. 返回结构化评估报告
        """
        from ultralytics import YOLO

        task = db.query(TrainingTask).filter(TrainingTask.id == task_id).first()
        if task is None:
            return {"error": "训练任务不存在"}
        if task.status != "completed":
            return {"error": f"训练任务状态为 {task.status}，只有已完成的任务才能评估"}

        weights_path = self._weights_path(task.task_uuid)
        if not weights_path.exists():
            return {"error": f"模型权重不存在: {weights_path}"}
        data_yaml = Path(task.data_yaml) if task.data_yaml else Path(task.dataset_path or "") / "data.yaml"
        if not data_yaml.exists():
            return {"error": "data.yaml 不存在"}

        logger.info(
            "开始模型评估: task_id=%d, weights=%s, split=%s",
            task_id,
            weights_path,
            split,
        )

        try:
            model = YOLO(str(weights_path))
            results = model.val(
                data=str(data_yaml),
                split=split,
                conf=conf,
                iou=iou,
                imgsz=task.img_size,
                device="cpu",
                save_json=True,
                plots=True,
                project=str(self._absolute_path(settings.TRAIN_OUTPUT_DIR)),
                name=f"task_{task.task_uuid}",
                exist_ok=True,
                verbose=False,
            )
            overall = {
                "precision": float(results.box.mp),
                "recall": float(results.box.mr),
                "map50": float(results.box.map50),
                "map50_95": float(results.box.map),
            }
            per_class = {}
            if results.box.ap is not None:
                for index, ap50 in enumerate(results.box.ap50):
                    class_name = model.names.get(index, f"class_{index}")
                    per_class[class_name] = {
                        "ap50": round(float(ap50), 4),
                        "ap50_95": round(
                            float(results.box.ap[index])
                            if index < len(results.box.ap)
                            else 0.0,
                            4,
                        ),
                    }

            scene = db.query(DetectionScene).filter(DetectionScene.id == task.scene_id).first()
            model_version = (
                db.query(ModelVersion).filter(ModelVersion.training_task_id == task_id).first()
            )
            if model_version is None:
                count = db.query(ModelVersion).filter(ModelVersion.scene_id == task.scene_id).count()
                version = f"v{count + 1}.0.0"
                scene_name = scene.name if scene else f"scene_{task.scene_id}"
                model_version = ModelVersion(
                    scene_id=task.scene_id,
                    training_task_id=task_id,
                    version=version,
                    model_name=f"{task.model_name}_{scene_name}_{version}",
                    model_type=task.model_name,
                    model_path=str(weights_path),
                    file_size=weights_path.stat().st_size,
                    description=f"训练任务 {task.task_uuid} 自动产出",
                )
                db.add(model_version)
            model_version.map50 = overall["map50"]
            model_version.map50_95 = overall["map50_95"]
            model_version.precision = overall["precision"]
            model_version.recall = overall["recall"]
            model_version.per_class_ap = per_class
            db.commit()
            db.refresh(model_version)
            logger.info(
                "模型评估完成: task_id=%d, mAP50=%.4f, mAP50-95=%.4f",
                task_id,
                overall["map50"],
                overall["map50_95"],
            )
            return {
                "task_id": task_id,
                "task_uuid": task.task_uuid,
                "split": split,
                "overall": overall,
                "per_class": per_class,
                "model_version_id": model_version.id,
                "model_version": model_version.version,
            }
        except Exception as exc:
            logger.error("模型评估异常: task_id=%d, error=%s", task_id, exc, exc_info=True)
            return {"error": f"评估失败: {exc}"}

    def export_model(
        self,
        db: Session,
        task_id: int,
        version: str | None = None,
        description: str | None = None,
        set_default: bool = False,
        upload_minio: bool = True,
    ) -> dict:
        """
        导出训练好的模型为正式版本

        流程：
          1. 复制 best.pt 到 models/ 目录
          2. 运行评估获取最终指标
          3. 保存评估报告 JSON
          4. 创建 ModelVersion 记录
          5. 可选上传到 MinIO
        """
        task = db.query(TrainingTask).filter(TrainingTask.id == task_id).first()
        if task is None:
            return {"error": "训练任务不存在"}
        if task.status != "completed":
            return {"error": f"训练任务状态为 {task.status}，只有已完成的任务才能导出"}
        weights_path = self._weights_path(task.task_uuid)
        if not weights_path.exists():
            return {"error": f"模型权重不存在: {weights_path}"}
        scene = db.query(DetectionScene).filter(DetectionScene.id == task.scene_id).first()
        if scene is None:
            return {"error": "关联场景不存在"}

        if not version:
            count = db.query(ModelVersion).filter(ModelVersion.scene_id == task.scene_id).count()
            version = f"v{count + 1}.0.0"

        export_dir = BACKEND_DIR / "models" / f"{scene.name}_{version}"
        export_dir.mkdir(parents=True, exist_ok=True)
        exported_weight = export_dir / "best.pt"
        shutil.copy2(weights_path, exported_weight)
        logger.info("模型文件已复制: %s → %s", weights_path, exported_weight)

        task_output = self._task_output_dir(task.task_uuid)
        for name in ("confusion_matrix.png", "PR_curve.png", "F1_curve.png", "results.png"):
            source = task_output / name
            if source.exists():
                shutil.copy2(source, export_dir / name)

        overall: dict[str, float | None] = {}
        per_class: dict = {}
        existing = db.query(ModelVersion).filter(ModelVersion.training_task_id == task_id).first()
        csv_path = task_output / "results.csv"
        if csv_path.exists():
            try:
                with csv_path.open("r", encoding="utf-8-sig", newline="") as file:
                    rows = list(csv.DictReader(file))
                if rows:
                    row = {str(key).strip(): value for key, value in rows[-1].items()}
                    overall = {
                        "precision": self._safe_float(row.get("metrics/precision(B)")),
                        "recall": self._safe_float(row.get("metrics/recall(B)")),
                        "map50": self._safe_float(row.get("metrics/mAP50(B)")),
                        "map50_95": self._safe_float(row.get("metrics/mAP50-95(B)")),
                    }
                    if existing and existing.per_class_ap:
                        per_class = existing.per_class_ap
                    logger.info(
                        "从 results.csv 读取评估指标: task_id=%d, mAP50=%.4f",
                        task_id,
                        overall.get("map50") or 0,
                    )
            except Exception as exc:
                logger.warning("从 results.csv 读取指标失败: %s", exc)

        if (not overall or overall.get("map50") is None) and existing is not None:
            overall = {
                "precision": existing.precision,
                "recall": existing.recall,
                "map50": existing.map50,
                "map50_95": existing.map50_95,
            }
            per_class = existing.per_class_ap or {}
            logger.info(
                "使用已有 ModelVersion 指标: task_id=%d, mAP50=%.4f",
                task_id,
                existing.map50 or 0,
            )

        report = {
            "version": version,
            "model_name": task.model_name,
            "scene": scene.name,
            "training_task": task.task_uuid,
            "evaluation": {"split": "val", "overall": overall, "per_class": per_class},
            "training_config": {
                "epochs": task.epochs,
                "batch_size": task.batch_size,
                "img_size": task.img_size,
                "optimizer": task.optimizer,
                "lr0": task.lr0,
                "device": task.device,
            },
            "exported_at": datetime.now().isoformat(),
        }
        (export_dir / "eval_report.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        minio_url = None
        if upload_minio:
            try:
                from app.storage.minio_client import MinIOClient

                minio_url = MinIOClient().upload_file(
                    f"models/{scene.name}/{version}/best.pt", str(exported_weight)
                )
                logger.info("模型已上传 MinIO: %s", minio_url)
            except Exception as exc:
                logger.warning("MinIO 上传失败（不影响本地导出）: %s", exc)

        model_version = existing
        if model_version is None:
            model_version = ModelVersion(
                scene_id=task.scene_id,
                training_task_id=task_id,
                version=version,
                model_name=f"{task.model_name}_{scene.name}_{version}",
                model_type=task.model_name,
                model_path=str(exported_weight),
            )
            db.add(model_version)
        model_version.version = version
        model_version.model_path = str(exported_weight)
        model_version.minio_url = minio_url
        model_version.map50 = overall.get("map50")
        model_version.map50_95 = overall.get("map50_95")
        model_version.precision = overall.get("precision")
        model_version.recall = overall.get("recall")
        model_version.per_class_ap = per_class
        model_version.file_size = exported_weight.stat().st_size
        model_version.description = description or f"训练任务 {task.task_uuid} 导出"
        db.flush()
        if set_default:
            db.query(ModelVersion).filter(
                ModelVersion.scene_id == task.scene_id,
                ModelVersion.id != model_version.id,
            ).update({"is_default": False})
            model_version.is_default = True
        db.commit()
        db.refresh(model_version)
        logger.info(
            "模型导出完成: scene=%s, version=%s, mAP50=%.4f",
            scene.name,
            version,
            overall.get("map50") or 0,
        )

        return {
            "model_version_id": model_version.id,
            "version": version,
            "model_name": model_version.model_name,
            "model_path": str(exported_weight),
            "export_dir": str(export_dir),
            "minio_url": minio_url,
            "file_size": model_version.file_size,
            "evaluation": {
                "map50": overall.get("map50"),
                "map50_95": overall.get("map50_95"),
                "precision": overall.get("precision"),
                "recall": overall.get("recall"),
                "per_class": per_class,
            },
            "is_default": bool(model_version.is_default),
            "message": f"模型已导出为版本 {version}",
        }

    def get_model_download_path(self, db: Session, task_id: int) -> dict:
        task = db.query(TrainingTask).filter(TrainingTask.id == task_id).first()
        if task is None:
            return {"error": "训练任务不存在"}
        if task.status != "completed":
            return {"error": "训练任务未完成"}
        weights_path = self._weights_path(task.task_uuid)
        if not weights_path.exists():
            return {"error": "模型权重文件不存在"}
        return {
            "file_path": str(weights_path),
            "filename": f"{task.model_name}_{task.task_uuid}_best.pt",
        }

    @staticmethod
    def get_model_path(db: Session, task_id: int) -> str:
        """获取训练任务的模型权重路径"""
        task = db.query(TrainingTask).filter(TrainingTask.id == task_id).first()
        if not task:
            return None
        weights_path = TrainingService._weights_path(task.task_uuid)
        return str(weights_path) if weights_path.exists() else None


training_service = TrainingService()
