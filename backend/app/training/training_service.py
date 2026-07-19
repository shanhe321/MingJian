from __future__ import annotations

import csv
import json
import os
import re
import shutil
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.core.logger import get_logger
from app.database.session import SessionLocal
from app.entity.db_models import DetectionScene, ModelVersion, TrainingMetric, TrainingTask
from app.storage.redis_client import redis_client

logger = get_logger(__name__)

BACKEND_DIR = Path(__file__).resolve().parents[2]
EVALUATION_ARTIFACTS = (
    "confusion_matrix.png",
    "PR_curve.png",
    "F1_curve.png",
    "results.png",
    "eval_report.json",
)


class TrainingService:
    def __init__(self) -> None:
        self._running_tasks: dict[int, Any] = {}
        self._tasks_lock = threading.Lock()

    @staticmethod
    def _evaluation_lock_key(task_id: int) -> str:
        return f"training:evaluation:{task_id}"

    @staticmethod
    def _postprocess_key(task_id: int) -> str:
        return f"training:postprocess:{task_id}"

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
    def _artifact_inventory(directory: Path) -> dict[str, list[str]]:
        available = [name for name in EVALUATION_ARTIFACTS if (directory / name).is_file()]
        return {
            "available": available,
            "missing": [name for name in EVALUATION_ARTIFACTS if name not in available],
        }

    @staticmethod
    def _next_version(db: Session, scene_id: int) -> str:
        if db.get_bind().dialect.name == "postgresql":
            # 同一场景的自动版本分配串行化到当前短事务，避免并发 count/select 冲突。
            db.execute(
                text("SELECT pg_advisory_xact_lock(:lock_key)"),
                {"lock_key": 7_310_000 + int(scene_id)},
            )
        existing = {
            row[0] if isinstance(row, tuple) else getattr(row, "version", None)
            for row in db.query(ModelVersion.version).filter(ModelVersion.scene_id == scene_id).all()
        }
        major = 1
        while f"v{major}.0.0" in existing:
            major += 1
        return f"v{major}.0.0"

    @staticmethod
    def _upload_model_assets(
        model_version: ModelVersion,
        weights_path: Path,
        artifact_dir: Path,
    ) -> dict:
        """上传真实存在的权重和评估产物，并明确报告缺失项。"""
        from app.storage.minio_client import MinIOClient

        client = MinIOClient()
        object_root = f"models/scene_{model_version.scene_id}/{model_version.version}"
        weight_object = f"{object_root}/best.pt"
        client.upload_file(weight_object, str(weights_path))
        uploaded: dict[str, str] = {}
        for artifact_name in EVALUATION_ARTIFACTS:
            artifact = artifact_dir / artifact_name
            if artifact.is_file():
                object_name = f"{object_root}/artifacts/{artifact_name}"
                client.upload_file(object_name, str(artifact))
                uploaded[artifact_name] = object_name
        inventory = TrainingService._artifact_inventory(artifact_dir)
        return {
            "weight_object": weight_object,
            "uploaded": uploaded,
            "missing": inventory["missing"],
        }

    @classmethod
    def resolve_model_path(cls, model_version: ModelVersion) -> str | None:
        """返回可用本地权重；本地丢失时从 MinIO 恢复到持久化缓存。"""
        model_path = getattr(model_version, "model_path", None)
        if model_path:
            configured = cls._absolute_path(model_path)
            if configured.is_file():
                return str(configured)
        minio_url = getattr(model_version, "minio_url", None)
        if not minio_url:
            return None

        cache_dir = BACKEND_DIR / "models" / "cache" / f"model_{model_version.id}"
        cache_dir.mkdir(parents=True, exist_ok=True)
        cached = cache_dir / "best.pt"
        if cached.is_file() and cached.stat().st_size > 0:
            return str(cached)

        from app.storage.minio_client import MinIOClient

        content = MinIOClient().download_bytes(minio_url)
        if not content:
            raise RuntimeError(f"MinIO 模型对象为空: {minio_url}")
        temporary = cache_dir / f".{cached.name}.{uuid.uuid4().hex}.part"
        try:
            temporary.write_bytes(content)
            os.replace(temporary, cached)
        finally:
            temporary.unlink(missing_ok=True)
        logger.info("模型已从 MinIO 恢复到本地缓存: model_id=%s, path=%s", model_version.id, cached)
        return str(cached)

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

            resume_checkpoint = config.get("resume_checkpoint")
            model = YOLO(
                str(resume_checkpoint)
                if resume_checkpoint
                else self._model_checkpoint(config.get("model_name", "yolov11n"))
            )
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
                "workers": max(0, settings.TRAIN_WORKERS),
            }
            reserved_args = {
                "data", "epochs", "imgsz", "batch", "device", "optimizer",
                "lr0", "project", "name", "exist_ok", "plots", "verbose", "workers",
            }
            train_args.update(
                {
                    key: value
                    for key, value in (config.get("augment_config") or {}).items()
                    if key not in reserved_args
                }
            )
            if resume_checkpoint:
                train_args["resume"] = str(resume_checkpoint)
            model.train(**train_args)

            self._parse_final_results(db, task_id, self._task_output_dir(task_uuid) / "results.csv")
            db.refresh(task)
            if task.status != "cancelled":
                redis_client.set(
                    self._postprocess_key(task_id),
                    "1",
                    expire=settings.EVALUATION_LOCK_TTL_SECONDS,
                )
                task.status = "completed"
                task.current_epoch = task.epochs
                task.progress = 100
                task.completed_at = datetime.now()
                db.commit()
                logger.info("训练完成: task_id=%d", task_id)
                # 训练成功和模型后处理是两个独立阶段。评估/MinIO 故障不得把已经
                # 完成的训练反向标为 failed，但会在状态中留下可见原因，便于重试。
                try:
                    try:
                        finalization = self._finalize_completed_training(db, task_id)
                    except Exception as exc:
                        db.rollback()
                        finalization = {"error": str(exc)}
                        logger.error(
                            "训练完成后的模型后处理异常: task_id=%d, error=%s",
                            task_id,
                            exc,
                            exc_info=True,
                        )
                finally:
                    redis_client.delete(self._postprocess_key(task_id))
                postprocess_issue = finalization.get("error") or finalization.get("warning")
                if postprocess_issue:
                    task = db.query(TrainingTask).filter(TrainingTask.id == task_id).first()
                    if task is None:
                        return
                    task.status = "completed"
                    task.error_message = f"训练已完成，但模型后处理不完整: {postprocess_issue}"
                    db.commit()
                    logger.warning(
                        "训练完成后的模型后处理不完整: task_id=%d, error=%s",
                        task_id,
                        postprocess_issue,
                    )
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
            redis_client.delete(self._postprocess_key(task_id))
            with self._tasks_lock:
                self._running_tasks.pop(task_id, None)
            db.close()

    def _finalize_completed_training(self, db: Session, task_id: int) -> dict:
        """自动评估并发布模型版本；可安全重复调用。"""
        warnings: list[str] = []
        evaluation = self.validate_model(
            db, task_id, split="val", conf=0.001, iou=0.6,
            allow_postprocess=True,
        )
        if evaluation.get("error"):
            warnings.append(evaluation["error"])
            logger.warning("自动评估未完成: task_id=%d, error=%s", task_id, evaluation["error"])
        exported = self.export_model(db, task_id, upload_minio=True)
        if exported.get("error"):
            return {"error": exported["error"], "evaluation": evaluation}
        if exported.get("storage_error"):
            warnings.append(f"MinIO 上传失败: {exported['storage_error']}")
        missing = exported.get("artifacts", {}).get("missing", [])
        if missing:
            warnings.append(f"缺少真实评估产物: {', '.join(missing)}")
        return {
            "evaluation": evaluation,
            "model": exported,
            "warning": "; ".join(warnings) if warnings else None,
        }

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
                epoch = int(epoch_value)
                cls._upsert_metric(db, task_id, epoch if epoch >= 1 else 1, values)
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
        is_evaluating = redis_client.exists(self._evaluation_lock_key(task_id))
        is_postprocessing = redis_client.exists(self._postprocess_key(task_id))
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
                "error_message": getattr(task, "error_message", None),
            },
            "latest_metric": self._metric_dict(latest),
            "is_running": is_running,
            "is_evaluating": is_evaluating,
            "is_postprocessing": is_postprocessing,
            "failure_reason": getattr(task, "error_message", None) if task.status == "failed" else None,
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

    @staticmethod
    def validate_model(
        db: Session,
        task_id: int,
        split: str = "val",
        conf: float = 0.25,
        iou: float = 0.45,
        allow_postprocess: bool = False,
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

        if (
            not allow_postprocess
            and redis_client.exists(TrainingService._postprocess_key(task_id))
        ):
            return {
                "error": "模型正在执行训练后评估和产物整理，请等待当前后处理完成",
                "code": "evaluation_in_progress",
            }
        lock_key = TrainingService._evaluation_lock_key(task_id)
        lock_token = redis_client.acquire_lock(
            lock_key,
            expire=settings.EVALUATION_LOCK_TTL_SECONDS,
        )
        if not lock_token:
            return {
                "error": "模型正在评估或训练后处理中，请等待当前评估完成",
                "code": "evaluation_in_progress",
            }

        try:
            task = db.query(TrainingTask).filter(TrainingTask.id == task_id).first()
            if task is None:
                return {"error": "训练任务不存在"}
            if task.status != "completed":
                return {"error": f"训练任务状态为 {task.status}，只有已完成的任务才能评估"}

            model_version = (
                db.query(ModelVersion).filter(ModelVersion.training_task_id == task_id).first()
            )
            weights_path = TrainingService._weights_path(task.task_uuid)
            if not weights_path.exists() and model_version is not None:
                try:
                    restored_path = TrainingService.resolve_model_path(model_version)
                    weights_path = Path(restored_path) if restored_path else weights_path
                except Exception as exc:
                    return {"error": f"模型权重恢复失败: {exc}"}
            if not weights_path.exists():
                return {"error": f"模型权重不存在: {weights_path}"}
            data_yaml = Path(task.data_yaml) if task.data_yaml else Path(task.dataset_path or "") / "data.yaml"
            if not data_yaml.exists():
                return {"error": "data.yaml 不存在"}

            evaluation_device = task.device or "cpu"
            logger.info(
                "开始模型评估: task_id=%d, weights=%s, split=%s, device=%s",
                task_id,
                weights_path,
                split,
                evaluation_device,
            )

            evaluation_output = TrainingService._task_output_dir(task.task_uuid)
            # 防止重复评估时把上一次遗留的曲线误报为本次真实产物。
            for artifact_name in ("confusion_matrix.png", "PR_curve.png", "F1_curve.png"):
                (evaluation_output / artifact_name).unlink(missing_ok=True)
            model = YOLO(str(weights_path))
            results = model.val(
                data=str(data_yaml),
                split=split,
                conf=conf,
                iou=iou,
                imgsz=task.img_size,
                device=evaluation_device,
                save_json=True,
                plots=True,
                project=str(TrainingService._absolute_path(settings.TRAIN_OUTPUT_DIR)),
                name=f"task_{task.task_uuid}",
                exist_ok=True,
                verbose=False,
                workers=max(0, settings.EVAL_WORKERS),
            )
            overall = {
                "precision": float(results.box.mp),
                "recall": float(results.box.mr),
                "map50": float(results.box.map50),
                "map50_95": float(results.box.map),
            }
            per_class = {}
            if results.box.ap is not None:
                raw_class_indices = getattr(results.box, "ap_class_index", None)
                if raw_class_indices is None:
                    raw_class_indices = getattr(results.box, "ap_class", None)
                class_indices = (
                    list(raw_class_indices)
                    if raw_class_indices is not None
                    else list(range(len(results.box.ap)))
                )
                for offset, ap50 in enumerate(results.box.ap50):
                    class_id = int(class_indices[offset]) if offset < len(class_indices) else offset
                    class_name = model.names.get(class_id, f"class_{class_id}")
                    per_class[class_name] = {
                        "ap50": round(float(ap50), 4),
                        "ap50_95": round(
                            float(results.box.ap[offset])
                            if offset < len(results.box.ap)
                            else 0.0,
                            4,
                        ),
                    }

            scene_query = db.query(DetectionScene).filter(DetectionScene.id == task.scene_id)
            if hasattr(scene_query, "with_for_update"):
                scene_query = scene_query.with_for_update()
            scene = scene_query.first()
            if model_version is None:
                version = TrainingService._next_version(db, task.scene_id)
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

            result_save_dir = getattr(results, "save_dir", None)
            artifact_dir = Path(result_save_dir or TrainingService._task_output_dir(task.task_uuid))
            artifact_dir.mkdir(parents=True, exist_ok=True)
            inventory_before_report = TrainingService._artifact_inventory(artifact_dir)
            report_artifacts = {
                "available": list(dict.fromkeys(
                    [*inventory_before_report["available"], "eval_report.json"]
                )),
                "missing": [
                    name for name in inventory_before_report["missing"]
                    if name != "eval_report.json"
                ],
            }
            report = {
                "task_id": task_id,
                "task_uuid": task.task_uuid,
                "model_version_id": model_version.id,
                "model_version": model_version.version,
                "split": split,
                "overall": overall,
                "per_class": per_class,
                "artifacts": report_artifacts,
                "evaluated_at": datetime.now().isoformat(),
            }
            (artifact_dir / "eval_report.json").write_text(
                json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            artifact_status = TrainingService._artifact_inventory(artifact_dir)
            storage_error = None
            try:
                upload = TrainingService._upload_model_assets(
                    model_version, weights_path, artifact_dir
                )
                model_version.minio_url = upload["weight_object"]
                model_version.model_path = str(weights_path)
                model_version.file_size = weights_path.stat().st_size
                db.commit()
            except Exception as exc:
                storage_error = str(exc)
                logger.warning(
                    "评估产物上传 MinIO 失败: task_id=%d, error=%s", task_id, exc
                )
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
                "artifacts": artifact_status,
                "storage_error": storage_error,
            }
        except Exception as exc:
            db.rollback()
            logger.error("模型评估异常: task_id=%d, error=%s", task_id, exc, exc_info=True)
            return {"error": f"评估失败: {exc}"}
        finally:
            redis_client.release_lock(lock_key, lock_token)

    @staticmethod
    def export_model(
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
        weights_path = TrainingService._weights_path(task.task_uuid)
        if not weights_path.exists():
            return {"error": f"模型权重不存在: {weights_path}"}
        scene_query = db.query(DetectionScene).filter(DetectionScene.id == task.scene_id)
        if hasattr(scene_query, "with_for_update"):
            scene_query = scene_query.with_for_update()
        scene = scene_query.first()
        if scene is None:
            return {"error": "关联场景不存在"}

        existing = db.query(ModelVersion).filter(ModelVersion.training_task_id == task_id).first()
        if not version:
            version = existing.version if existing is not None else TrainingService._next_version(db, task.scene_id)
        if not re.fullmatch(r"v?\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)?", version):
            return {"error": "模型版本号格式无效"}

        export_dir = BACKEND_DIR / "models" / f"scene_{task.scene_id}_{version}"
        export_dir.mkdir(parents=True, exist_ok=True)
        exported_weight = export_dir / "best.pt"
        shutil.copy2(weights_path, exported_weight)
        logger.info("模型文件已复制: %s → %s", weights_path, exported_weight)

        task_output = TrainingService._task_output_dir(task.task_uuid)
        for name in EVALUATION_ARTIFACTS:
            (export_dir / name).unlink(missing_ok=True)
        for name in ("confusion_matrix.png", "PR_curve.png", "F1_curve.png", "results.png"):
            source = task_output / name
            if source.exists():
                shutil.copy2(source, export_dir / name)

        overall: dict[str, float | None] = {}
        per_class: dict = {}
        csv_path = task_output / "results.csv"
        if csv_path.exists():
            try:
                with csv_path.open("r", encoding="utf-8-sig", newline="") as file:
                    rows = list(csv.DictReader(file))
                if rows:
                    row = {str(key).strip(): value for key, value in rows[-1].items()}
                    overall = {
                        "precision": TrainingService._safe_float(
                            row.get("metrics/precision(B)")
                        ),
                        "recall": TrainingService._safe_float(row.get("metrics/recall(B)")),
                        "map50": TrainingService._safe_float(row.get("metrics/mAP50(B)")),
                        "map50_95": TrainingService._safe_float(
                            row.get("metrics/mAP50-95(B)")
                        ),
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

        report_inventory = TrainingService._artifact_inventory(export_dir)
        report_artifacts = {
            "available": list(dict.fromkeys(
                [*report_inventory["available"], "eval_report.json"]
            )),
            "missing": [
                name for name in report_inventory["missing"]
                if name != "eval_report.json"
            ],
        }
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
            "artifacts": report_artifacts,
            "exported_at": datetime.now().isoformat(),
        }
        (export_dir / "eval_report.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        artifact_status = TrainingService._artifact_inventory(export_dir)
        minio_url = existing.minio_url if existing is not None else None
        storage_error = None
        if upload_minio:
            try:
                from app.storage.minio_client import MinIOClient

                client = MinIOClient()
                object_root = f"models/scene_{task.scene_id}/{version}"
                weight_object = f"{object_root}/best.pt"
                client.upload_file(weight_object, str(exported_weight))
                for artifact_name in (
                    "confusion_matrix.png", "PR_curve.png", "F1_curve.png",
                    "results.png", "eval_report.json",
                ):
                    artifact = export_dir / artifact_name
                    if artifact.exists():
                        client.upload_file(f"{object_root}/artifacts/{artifact_name}", str(artifact))
                minio_url = weight_object
                logger.info("模型及评估产物已上传 MinIO: %s", object_root)
            except Exception as exc:
                storage_error = str(exc)
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
        model_version.model_name = f"{task.model_name}_{scene.name}_{version}"
        model_version.model_path = str(exported_weight)
        if minio_url:
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
            "artifacts": artifact_status,
            "storage_error": storage_error,
            "is_default": bool(model_version.is_default),
            "message": f"模型已导出为版本 {version}",
        }

    @staticmethod
    def get_model_download_path(db: Session, task_id: int) -> dict:
        """获取训练任务的模型权重文件路径（用于下载）"""
        task = db.query(TrainingTask).filter(TrainingTask.id == task_id).first()
        if task is None:
            return {"error": "训练任务不存在"}

        weights_dir = TrainingService._task_output_dir(task.task_uuid) / "weights"
        best_path = weights_dir / "best.pt"
        if best_path.exists():
            return {
                "file_path": str(best_path),
                "filename": f"best_{task.task_uuid}.pt",
                "file_size": best_path.stat().st_size,
            }

        last_path = weights_dir / "last.pt"
        if last_path.exists():
            return {
                "file_path": str(last_path),
                "filename": f"last_{task.task_uuid}.pt",
                "file_size": last_path.stat().st_size,
            }

        model_version = (
            db.query(ModelVersion)
            .filter(ModelVersion.training_task_id == task_id)
            .first()
        )
        if model_version is not None:
            try:
                restored = TrainingService.resolve_model_path(model_version)
            except Exception as exc:
                return {"error": f"模型权重恢复失败: {exc}"}
            if restored:
                restored_path = Path(restored)
                return {
                    "file_path": str(restored_path),
                    "filename": f"best_{task.task_uuid}.pt",
                    "file_size": restored_path.stat().st_size,
                }

        return {"error": "模型权重文件不存在"}

    @staticmethod
    def get_model_path(db: Session, task_id: int) -> str:
        """获取训练任务的模型权重路径"""
        task = db.query(TrainingTask).filter(TrainingTask.id == task_id).first()
        if not task:
            return None
        weights_path = TrainingService._weights_path(task.task_uuid)
        if weights_path.exists():
            return str(weights_path)
        model_version = (
            db.query(ModelVersion)
            .filter(ModelVersion.training_task_id == task_id)
            .first()
        )
        return TrainingService.resolve_model_path(model_version) if model_version else None

    def recover_incomplete_tasks(self) -> int:
        """应用启动时恢复 pending/running 训练；存在 last.pt 时从检查点续训。"""
        db = SessionLocal()
        recoverable: list[tuple[int, str, dict]] = []
        try:
            tasks = db.query(TrainingTask).filter(
                TrainingTask.status.in_(("pending", "running"))
            ).all()
            for task in tasks:
                if not task.data_yaml or not Path(task.data_yaml).exists():
                    task.status = "failed"
                    task.error_message = "服务重启后无法恢复：训练数据配置不存在"
                    task.completed_at = datetime.now()
                    continue
                config = {
                    "model_name": task.model_name,
                    "epochs": task.epochs,
                    "img_size": task.img_size,
                    "batch_size": task.batch_size,
                    "device": task.device,
                    "optimizer": task.optimizer,
                    "lr0": task.lr0,
                    "augment_config": task.augment_config or {},
                    "dataset_path": task.dataset_path,
                    "data_yaml": task.data_yaml,
                    "dataset_project_id": task.dataset_project_id,
                }
                checkpoint = self._task_output_dir(task.task_uuid) / "weights" / "last.pt"
                if checkpoint.exists():
                    config["resume_checkpoint"] = str(checkpoint)
                task.status = "pending"
                task.error_message = "服务重启后自动恢复训练"
                recoverable.append((task.id, task.task_uuid, config))
            db.commit()
        finally:
            db.close()
        for task_id, task_uuid, config in recoverable:
            threading.Thread(
                target=self._run_training,
                args=(task_id, task_uuid, config),
                daemon=True,
                name=f"train-recover-{task_uuid}",
            ).start()
        return len(recoverable)


training_service = TrainingService()
