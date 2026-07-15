"""
检测 API 路由 — 快捷检测接口（跳过 LLM，直接调用 YOLO）

接口列表：
  - POST /api/detection/single     单图检测
  - POST /api/detection/batch      批量检测
  - POST /api/detection/zip        ZIP 文件检测
  - POST /api/detection/video      视频检测
  - GET  /api/detection/video/status/:id 查询视频任务进度
  - WS   /api/detection/camera     摄像头实时检测
  - GET  /api/detection/status/:id 查询任务状态
"""

import base64
import os
import tempfile
import threading
import time

import cv2
import numpy as np
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.responses import JSONResponse

from app.api.auth import get_current_user
from app.core.logger import get_logger
from app.database.session import SessionLocal
from app.entity.db_models import DetectionTask
from app.services.detection_service import detection_service
from app.storage.redis_client import redis_client

logger = get_logger(__name__)

router = APIRouter(prefix="/api/detection", tags=["快捷检测"])


@router.post("/single", summary="单图检测")
async def detect_single_api(
    file: UploadFile = File(..., description="检测图片"),
    conf: float = Form(0.25, description="置信度阈值"),
    scene_id: int = Form(None, description="场景 ID"),
    current_user=Depends(get_current_user),
):
    """快捷单图检测（跳过 LLM，直接调用 YOLO）。"""
    suffix = os.path.splitext(file.filename)[1] or ".jpg"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temporary_file:
        content = await file.read()
        temporary_file.write(content)
        temporary_path = temporary_file.name

    try:
        result = detection_service.detect_single(
            image_path=temporary_path,
            conf=conf,
            scene_id=scene_id,
            user_id=current_user.id,
        )
        result["filename"] = file.filename
        return result
    finally:
        os.unlink(temporary_path)


@router.post("/batch", summary="批量检测")
async def detect_batch_api(
    files: list[UploadFile] = File(..., description="多张图片"),
    conf: float = Form(0.25),
    scene_id: int = Form(None),
    current_user=Depends(get_current_user),
):
    """快捷批量检测。"""
    temporary_paths = []
    try:
        for file in files:
            suffix = os.path.splitext(file.filename)[1] or ".jpg"
            with tempfile.NamedTemporaryFile(
                suffix=suffix,
                delete=False,
            ) as temporary_file:
                content = await file.read()
                temporary_file.write(content)
                temporary_paths.append(temporary_file.name)

        return detection_service.detect_batch(
            image_paths=temporary_paths,
            conf=conf,
            scene_id=scene_id,
            user_id=current_user.id,
        )
    finally:
        for path in temporary_paths:
            try:
                os.unlink(path)
            except Exception:
                pass


@router.post("/zip", summary="ZIP 文件检测")
async def detect_zip_api(
    file: UploadFile = File(..., description="ZIP 压缩包"),
    conf: float = Form(0.25),
    scene_id: int = Form(None),
    current_user=Depends(get_current_user),
):
    """快捷 ZIP 检测：解压并检测其中所有图片。"""
    suffix = os.path.splitext(file.filename)[1] or ".zip"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temporary_file:
        content = await file.read()
        temporary_file.write(content)
        temporary_path = temporary_file.name

    try:
        return detection_service.detect_zip(
            zip_path=temporary_path,
            conf=conf,
            scene_id=scene_id,
            user_id=current_user.id,
        )
    finally:
        os.unlink(temporary_path)


@router.get("/status/{task_id}", summary="查询检测任务状态")
async def get_detection_status(
    task_id: int,
    current_user=Depends(get_current_user),
):
    """查询检测任务状态。"""
    db = SessionLocal()
    try:
        task = db.query(DetectionTask).filter(DetectionTask.id == task_id).first()
        if not task:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content={"error": "任务不存在"},
            )
        return {
            "task_id": task.id,
            "status": task.status,
            "task_type": task.task_type,
            "total_images": task.total_images,
            "total_objects": task.total_objects,
            "completed_at": (
                task.completed_at.isoformat() if task.completed_at else None
            ),
            "created_at": task.created_at.isoformat() if task.created_at else None,
        }
    finally:
        db.close()


@router.post("/video", summary="视频检测")
async def detect_video_api(
    file: UploadFile = File(..., description="视频文件（mp4/avi/mov）"),
    conf: float = Form(0.25, description="置信度阈值"),
    frame_sample_rate: int = Form(5, description="帧采样间隔（每 N 帧取 1 帧）"),
    max_frames: int = Form(50, description="最多处理的关键帧数量"),
    scene_id: int = Form(None, description="场景 ID"),
    current_user=Depends(get_current_user),
):
    """上传视频并在后台线程中执行检测。"""
    allowed_video_types = {".mp4", ".avi", ".mov", ".mkv", ".wmv", ".flv"}
    suffix = os.path.splitext(file.filename)[1].lower()
    if suffix not in allowed_video_types:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": (
                    f"不支持的视频格式: {suffix}，"
                    f"支持的格式: {', '.join(allowed_video_types)}"
                )
            },
        )

    content = await file.read()
    if len(content) > 50 * 1024 * 1024:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "视频文件不能超过 50MB"},
        )

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temporary_file:
        temporary_file.write(content)
        temporary_path = temporary_file.name

    logger.info(
        "视频文件已保存: %s (%.2f MB), 用户: %s",
        temporary_path,
        len(content) / (1024 * 1024),
        current_user.username,
    )

    db = SessionLocal()
    try:
        task = DetectionTask(
            user_id=current_user.id,
            scene_id=scene_id or 1,
            task_type="video",
            status="processing",
            conf_threshold=conf,
        )
        db.add(task)
        db.flush()
        task_id = task.id
        db.commit()
    finally:
        db.close()

    redis_client.set_json(
        f"video_task:{task_id}",
        {
            "status": "processing",
            "progress": 0,
            "message": "视频处理中...",
        },
        expire=3600,
    )
    user_id = current_user.id

    def run_video_detection():
        try:
            result = detection_service.detect_video(
                video_path=temporary_path,
                conf=conf,
                frame_sample_rate=frame_sample_rate,
                max_frames=max_frames,
                scene_id=scene_id,
                user_id=user_id,
                task_id=task_id,
            )
            if "error" in result:
                progress = {
                    "status": "failed",
                    "progress": 0,
                    "message": result["error"],
                }
            else:
                progress = {
                    "status": "completed",
                    "progress": 100,
                    "message": (
                        f"检测完成，共处理 {result['processed_frames']} 帧，"
                        f"发现 {result['total_objects']} 个目标"
                    ),
                    "result": result,
                }
            redis_client.set_json(
                f"video_task:{task_id}",
                progress,
                expire=3600,
            )
        except Exception as exc:
            logger.error("视频后台检测异常: %s", str(exc), exc_info=True)
            redis_client.set_json(
                f"video_task:{task_id}",
                {
                    "status": "failed",
                    "progress": 0,
                    "message": f"视频检测异常: {str(exc)}",
                },
                expire=3600,
            )
        finally:
            try:
                os.unlink(temporary_path)
            except Exception:
                pass

    threading.Thread(target=run_video_detection, daemon=True).start()
    return {
        "task_id": task_id,
        "status": "processing",
        "message": "视频已上传，正在后台处理中，请通过 status 接口轮询进度",
        "filename": file.filename,
    }


@router.get("/video/status/{task_id}", summary="查询视频检测进度")
async def get_video_detection_status(
    task_id: int,
    current_user=Depends(get_current_user),
):
    """优先从 Redis 查询视频任务进度，未命中时回退数据库。"""
    progress_info = redis_client.get_json(f"video_task:{task_id}")
    if progress_info:
        return {"task_id": task_id, **progress_info}

    db = SessionLocal()
    try:
        task = db.query(DetectionTask).filter(DetectionTask.id == task_id).first()
        if not task:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content={"error": "任务不存在"},
            )
        result = {
            "task_id": task.id,
            "status": task.status,
            "task_type": task.task_type,
            "total_images": task.total_images,
            "total_objects": task.total_objects or 0,
        }
        if task.status == "completed":
            from app.entity.db_models import DetectionResult

            detection_results = (
                db.query(DetectionResult)
                .filter(DetectionResult.task_id == task_id)
                .all()
            )
            class_counts = {}
            for detection_result in detection_results:
                class_name = detection_result.class_name
                class_counts[class_name] = class_counts.get(class_name, 0) + 1
            result["class_counts"] = class_counts
            result["total_inference_time"] = task.total_inference_time
        return result
    finally:
        db.close()


_camera_frame_buffer = {}


@router.websocket("/camera")
async def camera_detection_ws(websocket: WebSocket):
    """摄像头实时检测 WebSocket 接口。"""
    await websocket.accept()
    connection_id = id(websocket)
    logger.info("摄像头 WebSocket 连接建立: connection_id=%d", connection_id)

    mode = "cpu"
    conf = 0.25
    iou = 0.45
    scene_id = None
    model = None
    last_frame_time = 0.0
    frame_count = 0
    fps_start_time = time.time()
    fps_frame_count = 0

    try:
        while True:
            data = await websocket.receive_json()
            message_type = data.get("type")

            if message_type == "config":
                mode = data.get("mode", "cpu")
                conf = data.get("conf", 0.25)
                iou = data.get("iou", 0.45)
                scene_id = data.get("scene_id")
                device = "cpu" if mode == "cpu" else "0"
                try:
                    model = detection_service._get_model(scene_id)
                    dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
                    model.predict(
                        source=dummy_frame,
                        conf=conf,
                        iou=iou,
                        imgsz=640,
                        device=device,
                        save=False,
                        verbose=False,
                    )
                    logger.info("摄像头模型预热完成, 模式: %s", mode)
                except Exception as exc:
                    logger.error("模型加载失败: %s", str(exc))
                    model = None
                    await websocket.send_json(
                        {"type": "error", "message": f"模型加载失败: {str(exc)}"}
                    )
                    continue

                await websocket.send_json(
                    {
                        "type": "config_ok",
                        "mode": mode,
                        "message": f"配置成功，模式: {mode}",
                    }
                )

            elif message_type == "frame":
                if model is None:
                    await websocket.send_json(
                        {"type": "error", "message": "请先发送 config 消息初始化模型"}
                    )
                    continue

                current_time = time.time()
                if mode == "cpu" and current_time - last_frame_time < 0.3:
                    continue
                last_frame_time = current_time

                frame_base64 = data.get("data", "")
                if not frame_base64:
                    continue
                try:
                    image_bytes = base64.b64decode(frame_base64)
                    image_array = np.frombuffer(image_bytes, np.uint8)
                    frame = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
                    if frame is None:
                        continue

                    device = "cpu" if mode == "cpu" else "0"
                    image_size = 416 if mode == "cpu" else 640
                    result = model.predict(
                        source=frame,
                        conf=conf,
                        iou=iou,
                        imgsz=image_size,
                        device=device,
                        save=False,
                        verbose=False,
                        half=False,
                    )[0]
                    inference_time = float(result.speed.get("inference", 0))
                    annotated_image = result.plot()
                    _, buffer = cv2.imencode(
                        ".jpg",
                        annotated_image,
                        [cv2.IMWRITE_JPEG_QUALITY, 70],
                    )
                    annotated_base64 = base64.b64encode(buffer).decode("utf-8")

                    detections = []
                    if result.boxes is not None and len(result.boxes) > 0:
                        for box in result.boxes:
                            class_id = int(box.cls[0])
                            class_name = model.names.get(
                                class_id,
                                f"class_{class_id}",
                            )
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

                    fps_frame_count += 1
                    elapsed = time.time() - fps_start_time
                    if elapsed >= 1.0:
                        current_fps = fps_frame_count / elapsed
                        fps_frame_count = 0
                        fps_start_time = time.time()
                    else:
                        current_fps = 0
                    frame_count += 1
                    await websocket.send_json(
                        {
                            "type": "result",
                            "annotated_frame": annotated_base64,
                            "detections": detections,
                            "object_count": len(detections),
                            "inference_time": round(inference_time, 2),
                            "fps": round(current_fps, 1),
                            "frame_count": frame_count,
                        }
                    )
                except Exception as exc:
                    logger.error("摄像头帧处理异常: %s", str(exc))
                    await websocket.send_json(
                        {"type": "error", "message": f"帧处理失败: {str(exc)}"}
                    )

            elif message_type == "close":
                logger.info(
                    "摄像头 WebSocket 主动关闭: connection_id=%d",
                    connection_id,
                )
                break

    except WebSocketDisconnect:
        logger.info("摄像头 WebSocket 断开: connection_id=%d", connection_id)
    except Exception as exc:
        logger.error("摄像头 WebSocket 异常: %s", str(exc), exc_info=True)
    finally:
        _camera_frame_buffer.pop(connection_id, None)
        logger.info(
            "摄像头 WebSocket 关闭, 共处理 %d 帧: connection_id=%d",
            frame_count,
            connection_id,
        )
