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
import tempfile
import zipfile
from datetime import datetime

import cv2
from sqlalchemy.orm import Session
from ultralytics import YOLO

from app.config.settings import settings
from app.core.logger import get_logger
from app.database.session import SessionLocal
from app.entity.db_models import (
    DetectionResult,
    DetectionScene,
    DetectionTask,
    ModelVersion,
)
from app.storage.minio_client import MinIOClient

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

    @staticmethod
    def _get_default_model_path() -> str:
        """获取默认模型权重路径。"""
        db = SessionLocal()
        try:
            default_model = (
                db.query(ModelVersion).filter(ModelVersion.is_default == True).first()
            )
            if default_model and os.path.exists(default_model.model_path):
                return default_model.model_path

            from app.entity.db_models import TrainingTask

            latest_task = (
                db.query(TrainingTask)
                .filter(TrainingTask.status == "completed")
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
        model_path = None

        if scene_id:
            db = SessionLocal()
            try:
                default_model = (
                    db.query(ModelVersion)
                    .filter(
                        ModelVersion.scene_id == scene_id,
                        ModelVersion.is_default == True,
                    )
                    .first()
                )
                if default_model and os.path.exists(default_model.model_path):
                    model_path = default_model.model_path
            finally:
                db.close()

        if not model_path:
            model_path = DetectionService._get_default_model_path()

        logger.info("加载检测模型: %s", model_path)
        return YOLO(model_path)

    @staticmethod
    def _save_task_and_results(
        db: Session,
        user_id: int,
        scene_id: int,
        task_type: str,
        detections: list,
        annotated_image: bytes,
        original_filename: str,
        inference_time: float,
        conf: float,
        iou: float,
    ) -> dict:
        """保存检测任务、检测结果和标注图。"""
        task = DetectionTask(
            user_id=user_id,
            scene_id=scene_id,
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

        annotated_image_url = None
        try:
            minio_client = MinIOClient()
            object_name = f"detections/{task.id}/{original_filename}"
            annotated_image_url = minio_client.upload_bytes(
                object_name,
                annotated_image,
                "image/jpeg",
            )
        except Exception as exc:
            logger.warning("MinIO 上传失败（不影响检测结果）: %s", str(exc))

        for detection in detections:
            result = DetectionResult(
                task_id=task.id,
                image_path=original_filename,
                annotated_image_url=annotated_image_url,
                class_name=detection["class_name"],
                class_name_cn=detection.get("class_name_cn"),
                class_id=detection["class_id"],
                confidence=detection["confidence"],
                bbox=detection["bbox"],
                inference_time=inference_time,
            )
            db.add(result)

        db.commit()
        return {"task_id": task.id, "annotated_image_url": annotated_image_url}

    def detect_single(
        self,
        image_path: str,
        conf: float = 0.25,
        iou: float = 0.45,
        scene_id: int = None,
        user_id: int = None,
    ) -> dict:
        """检测单张图片。"""
        db = SessionLocal()
        try:
            model = self._get_model(scene_id)
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
            if user_id and scene_id:
                save_result = self._save_task_and_results(
                    db=db,
                    user_id=user_id,
                    scene_id=scene_id,
                    task_type="single",
                    detections=detections,
                    annotated_image=buffer.tobytes(),
                    original_filename=os.path.basename(image_path),
                    inference_time=float(result.speed.get("inference", 0)),
                    conf=conf,
                    iou=iou,
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
        scene_id: int = None,
        user_id: int = None,
    ) -> dict:
        """批量检测多张图片。"""
        db = SessionLocal()
        try:
            model = self._get_model(scene_id)

            if not scene_id:
                default_scene = db.query(DetectionScene).first()
                if default_scene:
                    scene_id = default_scene.id
                else:
                    return {"error": "数据库中没有可用的检测场景，请先创建检测场景"}

            task = DetectionTask(
                user_id=user_id or 0,
                scene_id=scene_id,
                task_type="batch",
                status="processing",
                total_images=len(image_paths),
                conf_threshold=conf,
            )
            db.add(task)
            db.flush()

            all_detections = []
            annotated_images = []
            total_objects = 0
            total_inference_time = 0
            class_counts = {}

            for image_path in image_paths:
                results = model.predict(
                    source=image_path,
                    conf=conf,
                    iou=0.45,
                    imgsz=640,
                    device="cpu",
                    save=False,
                    verbose=False,
                )
                result = results[0]
                inference_time = float(result.speed.get("inference", 0))
                total_inference_time += inference_time

                annotated_image = result.plot()
                _, buffer = cv2.imencode(
                    ".jpg",
                    annotated_image,
                    [cv2.IMWRITE_JPEG_QUALITY, 85],
                )
                annotated_images.append(
                    {
                        "image_path": os.path.basename(image_path),
                        "annotated_image_base64": base64.b64encode(buffer).decode(
                            "utf-8"
                        ),
                    }
                )

                if result.boxes is not None and len(result.boxes) > 0:
                    for box in result.boxes:
                        class_id = int(box.cls[0])
                        class_name = model.names.get(class_id, f"class_{class_id}")
                        confidence = float(box.conf[0])
                        x1, y1, x2, y2 = box.xyxy[0].tolist()

                        detection = {
                            "image_path": image_path,
                            "class_name": class_name,
                            "class_id": class_id,
                            "confidence": round(confidence, 4),
                            "bbox": [
                                round(x1, 1),
                                round(y1, 1),
                                round(x2, 1),
                                round(y2, 1),
                            ],
                            "inference_time": inference_time,
                        }
                        all_detections.append(detection)
                        total_objects += 1
                        class_counts[class_name] = class_counts.get(class_name, 0) + 1

                    for detection in all_detections:
                        if detection["image_path"] == image_path:
                            db_result = DetectionResult(
                                task_id=task.id,
                                image_path=image_path,
                                class_name=detection["class_name"],
                                class_id=detection["class_id"],
                                confidence=detection["confidence"],
                                bbox=detection["bbox"],
                                inference_time=inference_time,
                            )
                            db.add(db_result)

            task.status = "completed"
            task.total_objects = total_objects
            task.total_inference_time = total_inference_time
            task.completed_at = datetime.now()
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
            }

        except Exception as exc:
            logger.error("批量检测异常: %s", str(exc), exc_info=True)
            return {"error": f"批量检测失败: {str(exc)}"}
        finally:
            db.close()

    def detect_zip(
        self,
        zip_path: str,
        conf: float = 0.25,
        scene_id: int = None,
        user_id: int = None,
    ) -> dict:
        """解压 ZIP 文件并批量检测其中所有图片。"""
        temp_dir = None
        try:
            temp_dir = tempfile.mkdtemp(prefix="rsod_zip_")
            logger.info("解压 ZIP 文件: %s → %s", zip_path, temp_dir)

            with zipfile.ZipFile(zip_path, "r") as zip_file:
                zip_file.extractall(temp_dir)

            image_files = []
            for root, _, files in os.walk(temp_dir):
                for filename in files:
                    extension = os.path.splitext(filename)[1].lower()
                    if extension in {".jpg", ".jpeg", ".png", ".bmp", ".webp"}:
                        image_files.append(os.path.join(root, filename))

            if not image_files:
                return {"error": "ZIP 文件中没有找到图片"}

            logger.info("ZIP 中包含 %d 张图片，开始批量检测", len(image_files))
            batch_result = self.detect_batch(
                image_paths=image_files,
                conf=conf,
                scene_id=scene_id,
                user_id=user_id,
            )
            batch_result["source"] = "zip"
            batch_result["zip_filename"] = os.path.basename(zip_path)
            batch_result["total_images_in_zip"] = len(image_files)
            return batch_result

        except zipfile.BadZipFile:
            return {"error": f"无效的 ZIP 文件: {zip_path}"}
        except Exception as exc:
            logger.error("ZIP 检测异常: %s", str(exc), exc_info=True)
            return {"error": f"ZIP 检测失败: {str(exc)}"}
        finally:
            if temp_dir and os.path.exists(temp_dir):
                import shutil

                shutil.rmtree(temp_dir, ignore_errors=True)


detection_service = DetectionService()
