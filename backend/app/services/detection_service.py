"""
目标检测服务 — 封装 YOLOv11 推理逻辑

职责：
  - 单图检测（detect_single）
  - 批量检测（detect_batch）
  - ZIP 解压 + 批量检测（detect_zip）
  - 结果持久化（MinIO 存储标注图 + PostgreSQL 存储检测结果）
"""

import base64
import os
import shutil
import subprocess
import tempfile
import threading
import zipfile
from datetime import datetime
from pathlib import Path

import cv2
from sqlalchemy.orm import Session
from ultralytics import YOLO

from app.config.settings import settings
from app.core.logger import get_logger
from app.database.session import SessionLocal
from app.entity.db_models import (
    DetectionItem,
    DetectionResult,
    DetectionScene,
    DetectionTask,
    ModelVersion,
    OperationLog,
)
from app.services.quality_service import finalize_detection_task
from app.storage.minio_client import MinIOClient
from app.storage.redis_client import redis_client

logger = get_logger(__name__)

ALLOWED_IMAGE_TYPES = {
    "image/jpeg",
    "image/png",
    "image/bmp",
    "image/webp",
    ".jpg",
    ".jpeg",
    ".png",
    ".bmp",
    ".webp",
}


class DetectionService:
    """目标检测服务 — 封装 YOLOv11 推理全流程。"""

    _background_task_ids: set[int] = set()
    _background_task_lock = threading.Lock()

    @staticmethod
    def _model_cache_dir() -> Path:
        """返回持久化模型缓存目录（Docker 中位于 /app/data）。"""
        training_root = Path(settings.TRAIN_OUTPUT_DIR)
        if not training_root.is_absolute():
            training_root = Path.cwd() / training_root
        resolved = training_root.resolve()
        data_root = resolved.parents[1] if len(resolved.parents) > 1 else resolved.parent
        cache_dir = data_root / "models" / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir

    @staticmethod
    def _select_model_version(
        db: Session,
        scene_id: int | None,
        model_version_id: int | None = None,
    ) -> ModelVersion | None:
        query = db.query(ModelVersion).filter(ModelVersion.status == "active")
        if model_version_id is not None:
            model = query.filter(ModelVersion.id == model_version_id).first()
            if model is None:
                raise ValueError("指定的模型版本不存在或已归档")
            if scene_id is not None and model.scene_id != scene_id:
                raise ValueError("模型版本与检测场景不匹配")
            return model
        if scene_id is None:
            return None
        return (
            query.filter(ModelVersion.scene_id == scene_id)
            .order_by(ModelVersion.is_default.desc(), ModelVersion.created_at.desc())
            .first()
        )

    @staticmethod
    def _ensure_model_local(model: ModelVersion) -> str:
        local_path = Path(model.model_path)
        if local_path.exists():
            return str(local_path)
        if not model.minio_url:
            raise FileNotFoundError(f"模型文件不存在: {model.model_path}")
        suffix = Path(model.minio_url).suffix or ".pt"
        target = DetectionService._model_cache_dir() / f"model_{model.id}{suffix}"
        if not target.exists():
            temporary = target.with_suffix(target.suffix + ".part")
            try:
                MinIOClient().download_file(model.minio_url, str(temporary))
                os.replace(temporary, target)
            finally:
                if temporary.exists():
                    temporary.unlink(missing_ok=True)
        return str(target)

    @staticmethod
    def _get_default_model_path(scene_id: int | None = None) -> str:
        """获取场景内默认/最新模型，禁止跨场景随机取默认模型。"""
        db = SessionLocal()
        try:
            default_model = DetectionService._select_model_version(db, scene_id)
            if default_model:
                return DetectionService._ensure_model_local(default_model)

            from app.entity.db_models import TrainingTask

            latest_task = (
                db.query(TrainingTask)
                .filter(
                    TrainingTask.status == "completed",
                    TrainingTask.scene_id == scene_id if scene_id is not None else True,
                )
                .order_by(TrainingTask.completed_at.desc())
                .first()
            )
            if latest_task:
                weights_path = os.path.join(
                    os.getcwd(),
                    settings.TRAIN_OUTPUT_DIR,
                    f"task_{latest_task.task_uuid}",
                    "weights",
                    "best.pt",
                )
                if os.path.exists(weights_path):
                    return weights_path
        finally:
            db.close()

        return "yolo11n.pt"

    @staticmethod
    def _get_model(scene_id: int = None) -> YOLO:
        """优先加载场景默认模型，否则加载全局默认模型。"""
        model_path = DetectionService._get_default_model_path(scene_id)

        logger.info("加载检测模型: %s", model_path)
        return YOLO(model_path)

    @staticmethod
    def _load_model(
        db: Session,
        scene_id: int | None,
        model_version_id: int | None = None,
    ) -> tuple[YOLO, ModelVersion | None]:
        model_version = DetectionService._select_model_version(
            db, scene_id, model_version_id
        )
        if model_version is None:
            return DetectionService._get_model(scene_id), None
        model_path = DetectionService._ensure_model_local(model_version)
        logger.info("加载检测模型版本 %s: %s", model_version.version, model_path)
        return YOLO(model_path), model_version

    @staticmethod
    def _mark_task_failed(task_id: int | None, message: str) -> None:
        if not task_id:
            return
        db = SessionLocal()
        try:
            task = db.query(DetectionTask).filter(DetectionTask.id == task_id).first()
            if task:
                task.status = "failed"
                task.error_message = message[:2000]
                task.completed_at = datetime.now()
                db.add(OperationLog(
                    user_id=task.user_id,
                    username=task.user.username if task.user else None,
                    module="detection",
                    action="failed",
                    target_type="detection_task",
                    target_id=str(task.id),
                    description="检测任务失败",
                    status="failed",
                    error_message=message[:2000],
                ))
                db.commit()
        except Exception:
            db.rollback()
            logger.exception("更新检测任务失败状态异常: task_id=%s", task_id)
        finally:
            db.close()

    @staticmethod
    def _save_task_and_results(
        db: Session,
        user_id: int,
        scene_id: int,
        task_type: str,
        detections: list,
        annotated_image: bytes,
        original_path: str,
        original_filename: str,
        inference_time: float,
        conf: float,
        iou: float,
        model_version_id: int | None = None,
        image_width: int | None = None,
        image_height: int | None = None,
    ) -> dict:
        """保存检测任务、检测结果和标注图。"""
        task = DetectionTask(
            user_id=user_id,
            scene_id=scene_id,
            model_version_id=model_version_id,
            task_type=task_type,
            status="completed",
            total_images=1,
            total_objects=len(detections),
            total_inference_time=inference_time,
            conf_threshold=conf,
            iou_threshold=iou,
            completed_at=datetime.now(),
        )
        db.add(task)
        db.flush()

        input_object = f"detections/{task.id}/input/{original_filename}"
        annotated_object = f"detections/{task.id}/output/{original_filename}"
        annotated_image_url = None
        try:
            minio_client = MinIOClient()
            annotated_image_url = minio_client.upload_bytes(
                annotated_object,
                annotated_image,
                "image/jpeg",
            )
            minio_client.upload_file(input_object, original_path)
            task.input_path = input_object
            task.result_path = annotated_object
        except Exception as exc:
            logger.warning("MinIO 上传失败（不影响检测结果）: %s", str(exc))
            input_object = original_filename
            annotated_object = None

        item = DetectionItem(
            task_id=task.id,
            item_index=0,
            file_name=original_filename,
            input_path=input_object,
            result_path=annotated_object,
            status="completed",
            defect_count=len(detections),
            average_confidence=(
                sum(item["confidence"] for item in detections) / len(detections)
                if detections else None
            ),
            inference_time=inference_time,
            completed_at=task.completed_at,
        )
        db.add(item)
        db.flush()

        for detection in detections:
            result = DetectionResult(
                task_id=task.id,
                item_id=item.id,
                image_path=input_object,
                annotated_image_path=annotated_object,
                class_name=detection["class_name"],
                class_name_cn=detection.get("class_name_cn"),
                class_id=detection["class_id"],
                confidence=detection["confidence"],
                bbox=detection["bbox"],
                inference_time=inference_time,
                image_width=image_width,
                image_height=image_height,
            )
            db.add(result)

        db.flush()
        report = finalize_detection_task(db, task, input_paths=[input_object])
        return {
            "task_id": task.id,
            "annotated_image_url": annotated_image_url,
            "input_path": input_object,
            "result_path": annotated_object,
            "quality_conclusion": report.quality_conclusion,
            "risk_level": report.risk_level,
            "suggestion": report.suggestion,
        }

    def detect_single(
        self,
        image_path: str,
        conf: float = 0.25,
        iou: float = 0.45,
        scene_id: int = None,
        user_id: int = None,
        model_version_id: int | None = None,
    ) -> dict:
        """检测单张图片。"""
        db = SessionLocal()
        try:
            if user_id and not scene_id:
                default_scene = db.query(DetectionScene).first()
                if default_scene:
                    scene_id = default_scene.id
                else:
                    logger.warning("数据库中没有可用的检测场景")

            model, model_version = self._load_model(db, scene_id, model_version_id)
            results = model.predict(
                source=image_path,
                conf=conf,
                iou=iou,
                imgsz=640,
                device="cpu",
                save=False,
                verbose=False,
            )

            result = results[0]
            detections = []
            total_objects = 0

            if result.boxes is not None and len(result.boxes) > 0:
                for box in result.boxes:
                    class_id = int(box.cls[0])
                    class_name = model.names.get(class_id, f"class_{class_id}")
                    confidence = float(box.conf[0])
                    x1, y1, x2, y2 = box.xyxy[0].tolist()

                    detections.append(
                        {
                            "class_name": class_name,
                            "class_id": class_id,
                            "confidence": round(confidence, 4),
                            "bbox": [
                                round(x1, 1),
                                round(y1, 1),
                                round(x2, 1),
                                round(y2, 1),
                            ],
                        }
                    )
                    total_objects += 1

            annotated_image = result.plot()
            image_height, image_width = getattr(result, "orig_shape", annotated_image.shape[:2])
            _, buffer = cv2.imencode(
                ".jpg",
                annotated_image,
                [cv2.IMWRITE_JPEG_QUALITY, 85],
            )
            annotated_base64 = base64.b64encode(buffer).decode("utf-8")

            class_counts = {}
            for detection in detections:
                name = detection["class_name"]
                class_counts[name] = class_counts.get(name, 0) + 1

            task_id = None
            annotated_image_url = None
            save_result = {}
            if user_id and scene_id:
                save_result = self._save_task_and_results(
                    db=db,
                    user_id=user_id,
                    scene_id=scene_id,
                    task_type="single",
                    detections=detections,
                    annotated_image=buffer.tobytes(),
                    original_path=image_path,
                    original_filename=os.path.basename(image_path),
                    inference_time=float(result.speed.get("inference", 0)),
                    conf=conf,
                    iou=iou,
                    model_version_id=model_version.id if model_version else None,
                    image_width=int(image_width),
                    image_height=int(image_height),
                )
                task_id = save_result["task_id"]
                annotated_image_url = save_result.get("annotated_image_url")

            logger.info(
                "单图检测完成: %s, 检测到 %d 个目标, 耗时 %.2fms",
                image_path,
                total_objects,
                float(result.speed.get("inference", 0)),
            )

            return {
                "total_objects": total_objects,
                "class_counts": class_counts,
                "detections": detections,
                "annotated_image_base64": annotated_base64,
                "annotated_image_url": annotated_image_url,
                "inference_time": round(float(result.speed.get("inference", 0)), 2),
                "task_id": task_id,
                "quality_conclusion": save_result.get("quality_conclusion") if task_id else None,
                "risk_level": save_result.get("risk_level") if task_id else None,
                "suggestion": save_result.get("suggestion") if task_id else None,
            }

        except Exception as exc:
            logger.error("单图检测异常: %s", str(exc), exc_info=True)
            return {"error": f"检测失败: {str(exc)}"}
        finally:
            db.close()

    def detect_batch(
        self,
        image_paths: list[str],
        conf: float = 0.25,
        iou: float = 0.45,
        scene_id: int = None,
        user_id: int = None,
        mode: str = "batch",
        task_id: int | None = None,
        model_version_id: int | None = None,
        inputs_persisted: bool = False,
    ) -> dict:
        """批量检测多张图片。"""
        db = SessionLocal()
        task = None
        try:
            if not scene_id:
                default_scene = db.query(DetectionScene).filter(
                    DetectionScene.is_active.is_(True)
                ).first()
                if default_scene:
                    scene_id = default_scene.id
                else:
                    return {"error": "数据库中没有可用的检测场景，请先创建检测场景"}

            model, model_version = self._load_model(db, scene_id, model_version_id)

            task = db.query(DetectionTask).filter(DetectionTask.id == task_id).first() if task_id else None
            if task is None:
                task = DetectionTask(
                    user_id=user_id or 0,
                    scene_id=scene_id,
                    model_version_id=model_version.id if model_version else None,
                    task_type=mode if mode in {"batch", "folder", "zip"} else "batch",
                    status="processing",
                    total_images=len(image_paths),
                    conf_threshold=conf,
                    iou_threshold=iou,
                )
                db.add(task)
                db.flush()
            else:
                task.status = "processing"
                task.total_images = len(image_paths)
                task.iou_threshold = iou
                if model_version:
                    task.model_version_id = model_version.id
                db.commit()

            all_detections = []
            annotated_images = []
            total_objects = 0
            total_inference_time = 0
            class_counts = {}

            failed_items = {}
            item_paths = []
            minio_client = None
            try:
                minio_client = MinIOClient()
            except Exception as exc:
                logger.warning("MinIO 不可用，检测仍继续: %s", exc)

            for index, image_path in enumerate(image_paths):
                filename = os.path.basename(image_path)
                existing_item = next(
                    (entry for entry in task.items if entry.item_index == index), None
                )
                input_object = (
                    existing_item.input_path
                    if existing_item and existing_item.input_path
                    else f"detections/{task.id}/input/{index:05d}_{filename}"
                )
                output_object = f"detections/{task.id}/output/{index:05d}_{filename}"
                item = existing_item or DetectionItem(
                    task_id=task.id,
                    item_index=index,
                    file_name=filename,
                )
                item.input_path = input_object
                item.status = "processing"
                item.error_message = None
                if existing_item is None:
                    db.add(item)
                db.flush()
                if existing_item is not None:
                    db.query(DetectionResult).filter(
                        DetectionResult.item_id == item.id
                    ).delete(synchronize_session=False)
                item_paths.append(input_object)
                try:
                    results = model.predict(
                        source=image_path, conf=conf, iou=iou, imgsz=640,
                        device="cpu", save=False, verbose=False,
                    )
                    result = results[0]
                    inference_time = float(result.speed.get("inference", 0))
                    total_inference_time += inference_time
                    annotated_image = result.plot()
                    image_height, image_width = getattr(result, "orig_shape", annotated_image.shape[:2])
                    _, buffer = cv2.imencode(".jpg", annotated_image, [cv2.IMWRITE_JPEG_QUALITY, 85])
                    annotated_images.append({
                        "image_path": filename,
                        "annotated_image_base64": base64.b64encode(buffer).decode("utf-8"),
                    })
                    if minio_client:
                        try:
                            if not inputs_persisted:
                                minio_client.upload_file(input_object, image_path)
                            minio_client.upload_bytes(output_object, buffer.tobytes(), "image/jpeg")
                            item.result_path = output_object
                        except Exception as exc:
                            logger.warning("批量检测对象上传失败，保留检测结果: %s", exc)
                            output_object = None
                            item.result_path = None
                            if not inputs_persisted:
                                input_object = image_path
                                item.input_path = image_path
                                item_paths[-1] = image_path
                    if not minio_client:
                        output_object = None
                        item.result_path = None
                        if not inputs_persisted:
                            input_object = image_path
                            item.input_path = image_path
                            item_paths[-1] = image_path

                    item_detections = []
                    if result.boxes is not None and len(result.boxes) > 0:
                        for box in result.boxes:
                            class_id = int(box.cls[0])
                            class_name = model.names.get(class_id, f"class_{class_id}")
                            confidence = round(float(box.conf[0]), 4)
                            x1, y1, x2, y2 = box.xyxy[0].tolist()
                            detection = {
                                "image_path": input_object,
                                "class_name": class_name,
                                "class_id": class_id,
                                "confidence": confidence,
                                "bbox": [round(x1, 1), round(y1, 1), round(x2, 1), round(y2, 1)],
                                "inference_time": inference_time,
                            }
                            item_detections.append(detection)
                            all_detections.append(detection)
                            class_counts[class_name] = class_counts.get(class_name, 0) + 1
                            db.add(DetectionResult(
                                task_id=task.id,
                                item_id=item.id,
                                image_path=input_object,
                                annotated_image_path=output_object,
                                class_name=class_name,
                                class_id=class_id,
                                confidence=confidence,
                                bbox=detection["bbox"],
                                inference_time=inference_time,
                                image_width=int(image_width),
                                image_height=int(image_height),
                            ))
                    total_objects += len(item_detections)
                    item.status = "completed"
                    item.defect_count = len(item_detections)
                    item.average_confidence = (
                        sum(entry["confidence"] for entry in item_detections) / len(item_detections)
                        if item_detections else None
                    )
                    item.inference_time = inference_time
                    item.completed_at = datetime.now()
                except Exception as exc:
                    logger.warning("批量检测单项失败 %s: %s", filename, exc)
                    item.status = "failed"
                    item.error_message = str(exc)
                    item.completed_at = datetime.now()
                    failed_items[item.input_path] = str(exc)
                db.commit()

            task.status = "failed" if len(failed_items) == len(image_paths) else "completed"
            task.error_message = (
                f"全部 {len(image_paths)} 个检测项处理失败"
                if task.status == "failed"
                else f"{len(failed_items)} 个检测项处理失败"
                if failed_items
                else None
            )
            task.total_objects = total_objects
            task.total_inference_time = total_inference_time
            task.completed_at = datetime.now()
            db.flush()
            report = None
            query_probe = db.query(DetectionItem)
            if hasattr(query_probe, "join"):
                report = finalize_detection_task(db, task, input_paths=item_paths, failed_items=failed_items)
            else:
                db.commit()

            logger.info(
                "批量检测完成: %d 张图, 共 %d 个目标, 总耗时 %.2fms",
                len(image_paths),
                total_objects,
                total_inference_time,
            )

            return {
                "task_id": task.id,
                "total_images": len(image_paths),
                "total_objects": total_objects,
                "class_counts": class_counts,
                "total_inference_time": round(total_inference_time, 2),
                "detections": all_detections,
                "annotated_images": annotated_images,
                "failed_items": [
                    {"input_path": path, "error_message": error}
                    for path, error in failed_items.items()
                ],
                "quality_conclusion": report.quality_conclusion if report else None,
                "risk_level": report.risk_level if report else None,
                "suggestion": report.suggestion if report else None,
            }

        except Exception as exc:
            db.rollback()
            logger.error("批量检测异常: %s", str(exc), exc_info=True)
            self._mark_task_failed(task.id if task is not None else task_id, str(exc))
            return {"error": f"批量检测失败: {str(exc)}"}
        finally:
            db.close()

    def detect_zip(
        self,
        zip_path: str,
        conf: float = 0.25,
        iou: float = 0.45,
        scene_id: int = None,
        user_id: int = None,
        task_id: int | None = None,
        model_version_id: int | None = None,
    ) -> dict:
        """解压 ZIP 文件并批量检测其中所有图片。"""
        temp_dir = None
        try:
            temp_dir = tempfile.mkdtemp(prefix="rsod_zip_")
            logger.info("解压 ZIP 文件: %s → %s", zip_path, temp_dir)

            with zipfile.ZipFile(zip_path, "r") as zip_file:
                members = [entry for entry in zip_file.infolist() if not entry.is_dir()]
                if len(members) > settings.MAX_ZIP_FILES:
                    message = f"ZIP 文件数量超过限制（{settings.MAX_ZIP_FILES}）"
                    self._mark_task_failed(task_id, message)
                    return {"error": message}
                total_size = sum(entry.file_size for entry in members)
                if total_size > settings.MAX_ZIP_UNCOMPRESSED_MB * 1024 * 1024:
                    message = "ZIP 解压总体积超过限制"
                    self._mark_task_failed(task_id, message)
                    return {"error": message}
                root = os.path.realpath(temp_dir)
                for entry in members:
                    target = os.path.realpath(os.path.join(temp_dir, entry.filename))
                    if os.path.commonpath([root, target]) != root:
                        message = "ZIP 包含非法路径"
                        self._mark_task_failed(task_id, message)
                        return {"error": message}
                    zip_file.extract(entry, temp_dir)

            image_files = []
            for root, _, files in os.walk(temp_dir):
                for filename in files:
                    extension = os.path.splitext(filename)[1].lower()
                    if extension in {".jpg", ".jpeg", ".png", ".bmp", ".webp"}:
                        image_files.append(os.path.join(root, filename))

            if not image_files:
                message = "ZIP 文件中没有找到图片"
                self._mark_task_failed(task_id, message)
                return {"error": message}

            logger.info("ZIP 中包含 %d 张图片，开始批量检测", len(image_files))
            batch_kwargs = {
                "image_paths": image_files,
                "conf": conf,
                "iou": iou,
                "scene_id": scene_id,
                "user_id": user_id,
                "mode": "zip",
                "model_version_id": model_version_id,
            }
            if task_id is not None:
                batch_kwargs["task_id"] = task_id
            batch_result = self.detect_batch(**batch_kwargs)
            batch_result["source"] = "zip"
            batch_result["zip_filename"] = os.path.basename(zip_path)
            batch_result["total_images_in_zip"] = len(image_files)
            return batch_result

        except zipfile.BadZipFile:
            message = f"无效的 ZIP 文件: {zip_path}"
            self._mark_task_failed(task_id, message)
            return {"error": message}
        except Exception as exc:
            logger.error("ZIP 检测异常: %s", str(exc), exc_info=True)
            message = f"ZIP 检测失败: {str(exc)}"
            self._mark_task_failed(task_id, message)
            return {"error": message}
        finally:
            if temp_dir and os.path.exists(temp_dir):
                import shutil

                shutil.rmtree(temp_dir, ignore_errors=True)

    def detect_video(
        self,
        video_path: str,
        conf: float = 0.25,
        iou: float = 0.45,
        frame_sample_rate: int = 5,
        max_frames: int = 50,
        scene_id: int = None,
        user_id: int = None,
        task_id: int = None,
        model_version_id: int | None = None,
    ) -> dict:
        """对视频进行场景变化检测、帧采样和 YOLO 推理。"""
        db = SessionLocal()
        capture = None
        video_writer = None
        output_video_path = None
        try:
            if not scene_id:
                default_scene = db.query(DetectionScene).filter(
                    DetectionScene.is_active.is_(True)
                ).first()
                if default_scene:
                    scene_id = default_scene.id
            model, model_version = self._load_model(db, scene_id, model_version_id)
            capture = cv2.VideoCapture(video_path)
            if not capture.isOpened():
                message = f"无法打开视频文件: {video_path}"
                self._mark_task_failed(task_id, message)
                return {"error": message}

            total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
            width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
            duration_seconds = total_frames / fps if fps > 0 else 0

            logger.info(
                "视频信息: %d×%d, %.1ffps, %d 帧, %.1f 秒",
                width,
                height,
                fps,
                total_frames,
                duration_seconds,
            )

            if not task_id:
                task = DetectionTask(
                    user_id=user_id or 0,
                    scene_id=scene_id or 1,
                    model_version_id=model_version.id if model_version else None,
                    task_type="video",
                    status="processing",
                    total_images=0,
                    conf_threshold=conf,
                    iou_threshold=iou,
                )
                db.add(task)
                db.flush()
                task_id = task.id
            else:
                task = (
                    db.query(DetectionTask)
                    .filter(DetectionTask.id == task_id)
                    .first()
                )
                if task and model_version:
                    task.model_version_id = model_version.id

            sample_limit = max(1, max_frames)
            effective_interval = max(
                1,
                frame_sample_rate,
                total_frames // sample_limit,
            )
            sample_indices = list(range(0, total_frames, effective_interval))[
                :sample_limit
            ]
            sample_set = set(sample_indices)

            if task:
                task.total_images = len(sample_indices)
                db.commit()

            key_frames = []
            total_objects = 0
            total_inference_time = 0.0
            class_counts = {}
            sampled_count = 0
            last_detections = []
            last_frame = None

            class_colors = {
                "person": (0, 255, 0),
                "car": (255, 0, 0),
                "truck": (0, 0, 255),
                "bus": (255, 255, 0),
                "bicycle": (255, 0, 255),
                "motorcycle": (0, 255, 255),
            }

            def draw_detections_on_frame(frame, detections):
                annotated = frame.copy()
                for detection in detections:
                    x1, y1, x2, y2 = detection["bbox"]
                    color = class_colors.get(
                        detection["class_name"],
                        (255, 128, 0),
                    )
                    cv2.rectangle(
                        annotated,
                        (int(x1), int(y1)),
                        (int(x2), int(y2)),
                        color,
                        2,
                    )
                    label = (
                        f"{detection['class_name']} "
                        f"{detection['confidence']:.2f}"
                    )
                    cv2.putText(
                        annotated,
                        label,
                        (int(x1), int(y1) - 10),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.5,
                        color,
                        2,
                    )
                return annotated

            output_file = tempfile.NamedTemporaryFile(
                prefix="rsod_video_output_", suffix=".mp4", delete=False
            )
            output_video_path = output_file.name
            output_file.close()
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            video_writer = cv2.VideoWriter(
                output_video_path,
                fourcc,
                fps,
                (width, height),
            )

            frame_index = 0
            while True:
                success, frame = capture.read()
                if not success:
                    break

                current_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                current_gray = cv2.resize(current_gray, (100, 100))
                if last_frame is None:
                    scene_changed = True
                else:
                    scene_changed = cv2.absdiff(last_frame, current_gray).mean() > 10
                last_frame = current_gray.copy()

                should_detect = frame_index in sample_set and (
                    scene_changed or not last_detections
                )
                if should_detect:
                    results = model.predict(
                        source=frame,
                        conf=conf,
                        iou=iou,
                        imgsz=640,
                        device="cpu",
                        save=False,
                        verbose=False,
                    )
                    result = results[0]
                    frame_detections = []
                    if result.boxes is not None and len(result.boxes) > 0:
                        for box in result.boxes:
                            class_id = int(box.cls[0])
                            class_name = model.names.get(
                                class_id,
                                f"class_{class_id}",
                            )
                            confidence = float(box.conf[0])
                            x1, y1, x2, y2 = box.xyxy[0].tolist()
                            detection = {
                                "class_name": class_name,
                                "class_id": class_id,
                                "confidence": round(confidence, 4),
                                "bbox": [
                                    round(x1, 1),
                                    round(y1, 1),
                                    round(x2, 1),
                                    round(y2, 1),
                                ],
                            }
                            frame_detections.append(detection)
                            total_objects += 1
                            class_counts[class_name] = (
                                class_counts.get(class_name, 0) + 1
                            )

                    last_detections = frame_detections
                    sampled_count += 1
                    inference_time = float(result.speed.get("inference", 0))
                    total_inference_time += inference_time
                    annotated_frame = draw_detections_on_frame(
                        frame,
                        frame_detections,
                    )
                    video_writer.write(annotated_frame)

                    annotated_base64 = None
                    _, buffer = cv2.imencode(
                        ".jpg",
                        annotated_frame,
                        [cv2.IMWRITE_JPEG_QUALITY, 70],
                    )
                    if len(key_frames) < 6:
                        annotated_base64 = base64.b64encode(buffer).decode("utf-8")

                    frame_name = f"frame_{frame_index}.jpg"
                    input_object = f"detections/{task_id}/input/{frame_name}"
                    output_object = f"detections/{task_id}/output/{frame_name}"
                    try:
                        frame_client = MinIOClient()
                        raw_ok, raw_buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                        if raw_ok:
                            frame_client.upload_bytes(input_object, raw_buffer.tobytes(), "image/jpeg")
                        frame_client.upload_bytes(output_object, buffer.tobytes(), "image/jpeg")
                    except Exception as exc:
                        logger.warning("视频关键帧上传失败: %s", exc)
                        input_object = frame_name
                        output_object = None
                    frame_item = DetectionItem(
                        task_id=task_id,
                        item_index=len(key_frames),
                        file_name=frame_name,
                        input_path=input_object,
                        result_path=output_object,
                        status="completed",
                        defect_count=len(frame_detections),
                        average_confidence=(
                            sum(entry["confidence"] for entry in frame_detections) / len(frame_detections)
                            if frame_detections else None
                        ),
                        inference_time=inference_time,
                        completed_at=datetime.now(),
                    )
                    can_persist_items = hasattr(db, "flush")
                    if can_persist_items:
                        db.add(frame_item)
                        db.flush()

                    key_frames.append(
                        {
                            "frame_index": frame_index,
                            "timestamp": round(frame_index / fps, 2),
                            "annotated_image_base64": annotated_base64,
                            "object_count": len(frame_detections),
                            "detections": frame_detections,
                            "inference_time": round(inference_time, 2),
                        }
                    )

                    for detection in frame_detections:
                        if not can_persist_items:
                            continue
                        db.add(
                            DetectionResult(
                                task_id=task_id,
                                item_id=frame_item.id,
                                image_path=input_object,
                                annotated_image_path=output_object,
                                class_name=detection["class_name"],
                                class_id=detection["class_id"],
                                confidence=detection["confidence"],
                                bbox=detection["bbox"],
                                inference_time=inference_time,
                                image_width=width,
                                image_height=height,
                            )
                        )

                    if task:
                        task.total_objects = total_objects
                        db.commit()
                    logger.debug(
                        "视频检测进度: %d 场景, 帧号 %d, 检测到 %d 个目标",
                        sampled_count,
                        frame_index,
                        len(frame_detections),
                    )
                else:
                    video_writer.write(
                        draw_detections_on_frame(frame, last_detections)
                        if last_detections
                        else frame
                    )

                frame_index += 1
                if task_id and (
                    frame_index == total_frames
                    or frame_index % max(1, total_frames // 100) == 0
                ):
                    redis_client.set_json(
                        f"video_task:{task_id}",
                        {
                            "status": "processing",
                            "progress": min(95, round(frame_index * 95 / max(total_frames, 1), 2)),
                            "message": f"视频处理中：{frame_index}/{total_frames} 帧",
                        },
                        expire=3600,
                    )

            capture.release()
            capture = None
            video_writer.release()
            video_writer = None

            h264_video_path = output_video_path.replace(".mp4", "_h264.mp4")
            try:
                subprocess.run(
                    [
                        shutil.which("ffmpeg") or "ffmpeg",
                        "-y",
                        "-i",
                        output_video_path,
                        "-c:v",
                        "libx264",
                        "-preset",
                        "fast",
                        "-crf",
                        "23",
                        "-pix_fmt",
                        "yuv420p",
                        "-movflags",
                        "+faststart",
                        h264_video_path,
                    ],
                    capture_output=True,
                    timeout=300,
                    check=True,
                )
                os.replace(h264_video_path, output_video_path)
                logger.info("视频已转码为 H.264 格式")
            except Exception as exc:
                logger.warning("ffmpeg 转码失败，使用原始 mp4v 视频: %s", str(exc))
                try:
                    os.unlink(h264_video_path)
                except Exception:
                    pass

            annotated_video_url = None
            object_name = None
            try:
                candidate_object = f"detections/{task_id}/annotated_video.mp4"
                annotated_video_url = MinIOClient().upload_file(
                    candidate_object,
                    output_video_path,
                )
                object_name = candidate_object
                logger.info("标注视频已上传: %s", object_name)
            except Exception as exc:
                logger.warning("标注视频上传 MinIO 失败: %s", str(exc))

            report = None
            if task:
                task.status = "completed"
                task.total_objects = total_objects
                task.total_inference_time = total_inference_time
                task.completed_at = datetime.now()
                task.total_images = len(key_frames)
                task.result_path = object_name
                if hasattr(db, "flush"):
                    db.flush()
                    report = finalize_detection_task(db, task)
                else:
                    db.commit()

            logger.info(
                "视频检测完成: %d 帧处理, %d 关键帧采样, 共 %d 个目标, 总耗时 %.2fms",
                frame_index,
                len(key_frames),
                total_objects,
                total_inference_time,
            )
            return {
                "task_id": task_id,
                "total_frames": total_frames,
                "processed_frames": len(key_frames),
                "frame_sample_rate": frame_sample_rate,
                "fps": round(fps, 2),
                "duration_seconds": round(duration_seconds, 2),
                "video_resolution": {"width": width, "height": height},
                "total_objects": total_objects,
                "class_counts": class_counts,
                "key_frames": key_frames,
                "annotated_video_url": annotated_video_url,
                "quality_conclusion": report.quality_conclusion if report else None,
                "risk_level": report.risk_level if report else None,
                "suggestion": report.suggestion if report else None,
                "total_inference_time": round(total_inference_time, 2),
            }

        except Exception as exc:
            logger.error("视频检测异常: %s", str(exc), exc_info=True)
            if task_id:
                task = (
                    db.query(DetectionTask)
                    .filter(DetectionTask.id == task_id)
                    .first()
                )
                if task:
                    task.status = "failed"
                    task.error_message = str(exc)
                    db.commit()
            return {"error": f"视频检测失败: {str(exc)}"}
        finally:
            if capture is not None:
                capture.release()
            if video_writer is not None:
                video_writer.release()
            if output_video_path and os.path.exists(output_video_path):
                try:
                    os.unlink(output_video_path)
                except Exception:
                    pass
            db.close()

    def _run_persisted_task(self, task_id: int) -> None:
        """从 PostgreSQL + Redis + MinIO 恢复并执行一个异步检测任务。"""
        db = SessionLocal()
        try:
            task = db.query(DetectionTask).filter(DetectionTask.id == task_id).first()
            if task is None or task.status in {"completed", "failed"}:
                return
            persisted_items = list(task.items)
            db.expunge_all()
            db.close()
            config = redis_client.get_json(f"detection:task:{task_id}:config") or {}
            if not config:
                self._mark_task_failed(task_id, "异步任务恢复信息不存在，请重新提交检测")
                return
            client = MinIOClient()
            with tempfile.TemporaryDirectory(prefix=f"rsod_resume_{task_id}_") as workdir:
                if task.task_type in {"batch", "folder"}:
                    items = sorted(persisted_items, key=lambda entry: entry.item_index)
                    paths = []
                    for item in items:
                        suffix = Path(item.file_name).suffix or ".jpg"
                        local_path = Path(workdir) / f"{item.item_index:05d}{suffix}"
                        client.download_file(item.input_path, str(local_path))
                        paths.append(str(local_path))
                    result = self.detect_batch(
                        paths,
                        conf=task.conf_threshold,
                        iou=task.iou_threshold,
                        scene_id=task.scene_id,
                        user_id=task.user_id,
                        mode=task.task_type,
                        task_id=task.id,
                        model_version_id=task.model_version_id,
                        inputs_persisted=True,
                    )
                elif task.task_type == "zip":
                    local_path = Path(workdir) / "input.zip"
                    client.download_file(task.input_path, str(local_path))
                    result = self.detect_zip(
                        str(local_path),
                        conf=task.conf_threshold,
                        iou=task.iou_threshold,
                        scene_id=task.scene_id,
                        user_id=task.user_id,
                        task_id=task.id,
                        model_version_id=task.model_version_id,
                    )
                elif task.task_type == "video":
                    suffix = Path(task.input_path or "input.mp4").suffix or ".mp4"
                    local_path = Path(workdir) / f"input{suffix}"
                    client.download_file(task.input_path, str(local_path))
                    result = self.detect_video(
                        str(local_path),
                        conf=task.conf_threshold,
                        iou=task.iou_threshold,
                        frame_sample_rate=int(config.get("frame_sample_rate", 5)),
                        max_frames=int(config.get("max_frames", 50)),
                        scene_id=task.scene_id,
                        user_id=task.user_id,
                        task_id=task.id,
                        model_version_id=task.model_version_id,
                    )
                else:
                    result = {"error": f"任务类型 {task.task_type} 不支持后台恢复"}
                if result.get("error"):
                    self._mark_task_failed(task_id, result["error"])
                    if task.task_type == "video":
                        redis_client.set_json(
                            f"video_task:{task_id}",
                            {"status": "failed", "progress": 0, "message": result["error"]},
                            expire=3600,
                        )
                else:
                    redis_client.delete(f"detection:task:{task_id}:config")
                    if task.task_type == "video":
                        redis_client.set_json(
                            f"video_task:{task_id}",
                            {
                                "status": "completed",
                                "progress": 100,
                                "message": (
                                    f"检测完成，共处理 {result.get('processed_frames', 0)} 帧，"
                                    f"发现 {result.get('total_objects', 0)} 个目标"
                                ),
                                "result": result,
                            },
                            expire=3600,
                        )
        except Exception as exc:
            logger.error("异步检测任务执行失败: task_id=%s", task_id, exc_info=True)
            self._mark_task_failed(task_id, f"异步检测执行失败: {exc}")
        finally:
            db.close()
            with self._background_task_lock:
                self._background_task_ids.discard(task_id)

    def enqueue_persisted_task(self, task_id: int) -> bool:
        """幂等提交后台任务；任务输入必须已写入 MinIO。"""
        with self._background_task_lock:
            if task_id in self._background_task_ids:
                return False
            self._background_task_ids.add(task_id)
        threading.Thread(
            target=self._run_persisted_task,
            args=(task_id,),
            daemon=True,
            name=f"detection-{task_id}",
        ).start()
        return True

    def recover_incomplete_tasks(self) -> int:
        """应用启动时恢复有持久化配置的异步检测，缺配置任务明确失败。"""
        db = SessionLocal()
        try:
            tasks = db.query(DetectionTask).filter(
                DetectionTask.task_type.in_(("batch", "folder", "zip", "video")),
                DetectionTask.status.in_(("pending", "processing")),
            ).all()
            task_ids = [task.id for task in tasks]
            for task in tasks:
                task.status = "pending"
            db.commit()
        finally:
            db.close()
        for task_id in task_ids:
            self.enqueue_persisted_task(task_id)
        return len(task_ids)


detection_service = DetectionService()
