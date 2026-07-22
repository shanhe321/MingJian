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
import time
import warnings
from datetime import datetime
from urllib.parse import urlsplit

import cv2
import numpy as np
from jose import JWTError
from starlette.concurrency import run_in_threadpool
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)

from app.api.auth import get_current_user
from app.config.settings import settings
from app.core.security import decode_access_token
from app.core.logger import get_logger
from app.database.session import SessionLocal
from app.entity.db_models import DetectionTask
from app.entity.db_models import (
    DetectionItem,
    DetectionResult,
    DetectionScene,
    ModelVersion,
    User,
)
from app.services.quality_service import finalize_detection_task, resolve_class_name_cn
from app.services.audit_service import write_audit
from app.services.detection_service import detection_service
from app.services.upload_service import read_valid_image
from app.storage.redis_client import redis_client
from app.storage.minio_client import MinIOClient

logger = get_logger(__name__)

# FastAPI 0.110 会为 multipart 端点动态生成 Pydantic 请求模型；外部字段名
# model_version_id 是既有 API 契约，但会触发 Pydantic 2 的保留命名空间提示。
# 仅屏蔽这一条已知且无行为影响的提示，保留 OpenAPI/Form 字段名不变。
warnings.filterwarnings(
    "ignore",
    message=r'Field "model_version_id" has conflict with protected namespace "model_"\.',
    category=UserWarning,
    module=r"pydantic\._internal\._fields",
)

router = APIRouter(prefix="/api/detection", tags=["快捷检测"])


def _admin_user(user) -> bool:
    return bool(getattr(user, "is_superuser", False) or any(item.role.name == "admin" for item in getattr(user, "user_roles", [])))


def _audit_detection(
    user_id: int,
    action: str,
    task_id: int | None,
    request: Request | None = None,
    details: dict | None = None,
    audit_status: str = "success",
    error_message: str | None = None,
) -> None:
    """检测服务使用独立事务，审计失败不能回滚已经完成的检测。"""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        write_audit(
            db,
            user=user,
            module="detection",
            action=action,
            target_type="detection_task",
            target_id=task_id,
            details=details,
            request=request,
            status=audit_status,
            error_message=error_message,
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.warning("检测审计写入失败: %s", exc)
    finally:
        db.close()


def _scene_id_or_default(db, scene_id: int | None) -> int:
    scene = db.query(DetectionScene).filter(DetectionScene.id == scene_id).first() if scene_id else db.query(DetectionScene).filter(DetectionScene.is_active == True).first()
    if not scene:
        raise ValueError("数据库中没有可用检测场景")
    return scene.id


def _create_async_task(
    user_id: int,
    scene_id: int | None,
    task_type: str,
    total: int,
    conf: float,
    iou: float = 0.45,
    model_version_id: int | None = None,
) -> int:
    db = SessionLocal()
    try:
        resolved_scene_id = _scene_id_or_default(db, scene_id)
        if model_version_id is not None:
            model = db.query(ModelVersion).filter(
                ModelVersion.id == model_version_id,
                ModelVersion.status == "active",
            ).first()
            if model is None:
                raise ValueError("指定的模型版本不存在或已归档")
            if model.scene_id != resolved_scene_id:
                raise ValueError("模型版本与检测场景不匹配")
        task = DetectionTask(
            user_id=user_id,
            scene_id=resolved_scene_id,
            model_version_id=model_version_id,
            task_type=task_type,
            status="pending",
            total_images=total,
            conf_threshold=conf,
            iou_threshold=iou,
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        return task.id
    finally:
        db.close()


def _persist_batch_inputs(
    task_id: int,
    paths: list[str],
    filenames: list[str],
    config: dict,
) -> None:
    """异步返回前将输入写入 MinIO 和检测项，使服务重启后可恢复。"""
    client = MinIOClient()
    db = SessionLocal()
    try:
        for index, (path, filename) in enumerate(zip(paths, filenames)):
            safe_name = os.path.basename(filename) or f"image_{index}.jpg"
            object_name = f"detections/{task_id}/input/{index:05d}_{safe_name}"
            client.upload_file(object_name, path)
            db.add(DetectionItem(
                task_id=task_id,
                item_index=index,
                file_name=safe_name,
                input_path=object_name,
                status="pending",
            ))
        db.commit()
        redis_client.set_json(
            f"detection:task:{task_id}:config", config, expire=7 * 24 * 3600
        )
        if not settings.DEBUG and (
            not redis_client.ensure_available()
            or redis_client.get_json(f"detection:task:{task_id}:config") is None
        ):
            raise RuntimeError("Redis 不可用，无法保证异步任务恢复")
    except Exception:
        db.rollback()
        detection_service._mark_task_failed(task_id, "异步输入持久化失败")
        try:
            client.delete_prefix(f"detections/{task_id}/")
        except Exception:
            pass
        raise
    finally:
        db.close()


def _persist_single_async_input(task_id: int, path: str, filename: str, config: dict) -> str:
    client = MinIOClient()
    safe_name = os.path.basename(filename) or "input.bin"
    object_name = f"detections/{task_id}/input/{safe_name}"
    try:
        client.upload_file(object_name, path)
        db = SessionLocal()
        try:
            task = db.query(DetectionTask).filter(DetectionTask.id == task_id).first()
            if task:
                task.input_path = object_name
                db.commit()
        finally:
            db.close()
        redis_client.set_json(
            f"detection:task:{task_id}:config", config, expire=7 * 24 * 3600
        )
        if not settings.DEBUG and (
            not redis_client.ensure_available()
            or redis_client.get_json(f"detection:task:{task_id}:config") is None
        ):
            raise RuntimeError("Redis 不可用，无法保证异步任务恢复")
        return object_name
    except Exception:
        detection_service._mark_task_failed(task_id, "异步输入持久化失败")
        try:
            client.delete_prefix(f"detections/{task_id}/")
        except Exception:
            pass
        raise


@router.post("/single", summary="单图检测")
async def detect_single_api(
    request: Request,
    file: UploadFile = File(..., description="检测图片"),
    conf: float = Form(0.25, ge=0, le=1, description="置信度阈值"),
    iou: float = Form(0.45, ge=0, le=1, description="NMS IoU 阈值"),
    scene_id: int = Form(None, description="场景 ID"),
    model_version_id: int | None = Form(None, description="指定模型版本 ID"),
    current_user=Depends(get_current_user),
):
    """快捷单图检测（跳过 LLM，直接调用 YOLO）。"""
    suffix = os.path.splitext(file.filename)[1] or ".jpg"
    with tempfile.NamedTemporaryFile(prefix="rsod_single_", suffix=suffix, delete=False) as temporary_file:
        content = await read_valid_image(file)
        temporary_file.write(content)
        temporary_path = temporary_file.name

    try:
        result = await run_in_threadpool(
            detection_service.detect_single,
            image_path=temporary_path,
            conf=conf,
            iou=iou,
            scene_id=scene_id,
            user_id=current_user.id,
            model_version_id=model_version_id,
        )
        if "error" in result:
            _audit_detection(
                current_user.id, "single", result.get("task_id"), request,
                audit_status="failed", error_message=result["error"],
            )
            raise HTTPException(status_code=500, detail=result["error"])
        result["filename"] = file.filename
        _audit_detection(current_user.id, "single", result.get("task_id"), request)
        return result
    finally:
        os.unlink(temporary_path)


@router.post("/batch", summary="批量检测")
async def detect_batch_api(
    request: Request,
    files: list[UploadFile] = File(..., description="多张图片"),
    conf: float = Form(0.25, ge=0, le=1),
    iou: float = Form(0.45, ge=0, le=1),
    scene_id: int = Form(None),
    model_version_id: int | None = Form(None),
    async_mode: bool = Form(False),
    mode: str = Form("batch"),
    current_user=Depends(get_current_user),
):
    """快捷批量检测。"""
    if mode not in {"batch", "folder"}:
        raise HTTPException(status_code=400, detail="mode 只能是 batch 或 folder")
    temporary_paths = []
    try:
        for file in files:
            suffix = os.path.splitext(file.filename)[1] or ".jpg"
            with tempfile.NamedTemporaryFile(
                prefix="rsod_batch_",
                suffix=suffix,
                delete=False,
            ) as temporary_file:
                content = await read_valid_image(file)
                temporary_file.write(content)
                temporary_paths.append(temporary_file.name)

        if async_mode:
            user_id = current_user.id
            task_id = _create_async_task(
                user_id, scene_id, mode, len(temporary_paths), conf, iou,
                model_version_id,
            )
            paths = list(temporary_paths)
            _persist_batch_inputs(
                task_id,
                paths,
                [file.filename or os.path.basename(path) for file, path in zip(files, paths)],
                {"task_type": mode},
            )
            detection_service.enqueue_persisted_task(task_id)
            for path in paths:
                try:
                    os.unlink(path)
                except OSError:
                    pass
            temporary_paths = []
            _audit_detection(
                current_user.id,
                f"start_{mode}",
                task_id,
                request,
                {"total_items": len(paths)},
            )
            return {"task_id": task_id, "status": "pending", "total_items": len(paths)}

        result = await run_in_threadpool(
            detection_service.detect_batch,
            image_paths=temporary_paths,
            conf=conf,
            iou=iou,
            scene_id=scene_id,
            user_id=current_user.id,
            mode=mode,
            model_version_id=model_version_id,
        )
        if "error" in result:
            _audit_detection(
                current_user.id, mode, result.get("task_id"), request,
                audit_status="failed", error_message=result["error"],
            )
            raise HTTPException(status_code=500, detail=result["error"])
        _audit_detection(current_user.id, mode, result.get("task_id"), request)
        return result
    finally:
        for path in temporary_paths:
            try:
                os.unlink(path)
            except Exception:
                pass


@router.post("/zip", summary="ZIP 文件检测")
async def detect_zip_api(
    request: Request,
    file: UploadFile = File(..., description="ZIP 压缩包"),
    conf: float = Form(0.25, ge=0, le=1),
    iou: float = Form(0.45, ge=0, le=1),
    scene_id: int = Form(None),
    model_version_id: int | None = Form(None),
    async_mode: bool = Form(False),
    current_user=Depends(get_current_user),
):
    """快捷 ZIP 检测：解压并检测其中所有图片。"""
    suffix = os.path.splitext(file.filename)[1].lower() or ".zip"
    if suffix != ".zip" or file.content_type not in {"application/zip", "application/x-zip-compressed", "application/octet-stream"}:
        raise HTTPException(status_code=415, detail="仅支持 ZIP 文件")
    content = await file.read(100 * 1024 * 1024 + 1)
    if len(content) > 100 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="ZIP 文件不能超过 100MB")
    with tempfile.NamedTemporaryFile(prefix="rsod_zip_", suffix=suffix, delete=False) as temporary_file:
        temporary_file.write(content)
        temporary_path = temporary_file.name

    if async_mode:
        user_id = current_user.id
        task_id = _create_async_task(
            user_id, scene_id, "zip", 0, conf, iou, model_version_id
        )
        _persist_single_async_input(
            task_id,
            temporary_path,
            file.filename or "input.zip",
            {"task_type": "zip"},
        )
        detection_service.enqueue_persisted_task(task_id)
        try:
            os.unlink(temporary_path)
        except OSError:
            pass
        _audit_detection(current_user.id, "start_zip", task_id, request)
        return {"task_id": task_id, "status": "pending"}

    try:
        result = await run_in_threadpool(
            detection_service.detect_zip,
            zip_path=temporary_path,
            conf=conf,
            iou=iou,
            scene_id=scene_id,
            user_id=current_user.id,
            model_version_id=model_version_id,
        )
        if "error" in result:
            _audit_detection(
                current_user.id, "zip", result.get("task_id"), request,
                audit_status="failed", error_message=result["error"],
            )
            raise HTTPException(status_code=400, detail=result["error"])
        _audit_detection(current_user.id, "zip", result.get("task_id"), request)
        return result
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
            raise HTTPException(status_code=404, detail="任务不存在")
        if task.user_id != current_user.id and not _admin_user(current_user):
            raise HTTPException(status_code=403, detail="无权访问该任务")
        items = db.query(DetectionItem).filter(DetectionItem.task_id == task.id).order_by(DetectionItem.item_index).all()
        processed = sum(item.status in {"completed", "failed"} for item in items)
        failed = [
            {"item_id": item.id, "file_name": item.file_name, "error_message": item.error_message}
            for item in items if item.status == "failed"
        ]
        total = len(items) or task.total_images
        return {
            "task_id": task.id,
            "status": task.status,
            "task_type": task.task_type,
            "model_version_id": task.model_version_id,
            "total_images": task.total_images,
            "total_objects": task.total_objects,
            "total_items": total,
            "processed_items": processed,
            "failed_items": len(failed),
            "failures": failed,
            "error_message": task.error_message,
            "progress": round(processed * 100 / total, 2) if total else (100 if task.status == "completed" else 0),
            "completed_at": (
                task.completed_at.isoformat() if task.completed_at else None
            ),
            "created_at": task.created_at.isoformat() if task.created_at else None,
        }
    finally:
        db.close()


@router.post("/video", summary="视频检测")
async def detect_video_api(
    request: Request,
    file: UploadFile = File(..., description="视频文件（mp4/avi/mov）"),
    conf: float = Form(0.25, ge=0, le=1, description="置信度阈值"),
    iou: float = Form(0.45, ge=0, le=1, description="NMS IoU 阈值"),
    frame_sample_rate: int = Form(5, ge=1, le=1000, description="帧采样间隔（每 N 帧取 1 帧）"),
    max_frames: int = Form(50, ge=1, le=1000, description="最多处理的关键帧数量"),
    scene_id: int = Form(None, description="场景 ID"),
    model_version_id: int | None = Form(None, description="指定模型版本 ID"),
    current_user=Depends(get_current_user),
):
    """上传视频并在后台线程中执行检测。"""
    allowed_video_types = {".mp4", ".avi", ".mov", ".mkv", ".wmv", ".flv"}
    suffix = os.path.splitext(file.filename)[1].lower()
    if suffix not in allowed_video_types:
        raise HTTPException(
            status_code=400,
            detail=(
                f"不支持的视频格式: {suffix}，"
                f"支持的格式: {', '.join(allowed_video_types)}"
            ),
        )

    content = await file.read()
    if len(content) > settings.MAX_VIDEO_SIZE_MB * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail=f"视频文件不能超过 {settings.MAX_VIDEO_SIZE_MB}MB",
        )

    with tempfile.NamedTemporaryFile(prefix="rsod_video_", suffix=suffix, delete=False) as temporary_file:
        temporary_file.write(content)
        temporary_path = temporary_file.name

    logger.info(
        "视频文件已保存: %s (%.2f MB), 用户: %s",
        temporary_path,
        len(content) / (1024 * 1024),
        current_user.username,
    )

    try:
        task_id = _create_async_task(
            current_user.id,
            scene_id,
            "video",
            0,
            conf,
            iou,
            model_version_id,
        )
        _persist_single_async_input(
            task_id,
            temporary_path,
            file.filename or f"input{suffix}",
            {
                "task_type": "video",
                "frame_sample_rate": frame_sample_rate,
                "max_frames": max_frames,
            },
        )
    except Exception:
        try:
            os.unlink(temporary_path)
        except OSError:
            pass
        raise

    redis_client.set_json(
        f"video_task:{task_id}",
        {
            "status": "pending",
            "progress": 0,
            "message": "视频处理中...",
        },
        expire=3600,
    )
    detection_service.enqueue_persisted_task(task_id)
    try:
        os.unlink(temporary_path)
    except OSError:
        pass
    _audit_detection(current_user.id, "start_video", task_id, request)
    return {
        "task_id": task_id,
        "status": "pending",
        "message": "视频已上传，正在后台处理中，请通过 status 接口轮询进度",
        "filename": file.filename,
    }


@router.get("/video/status/{task_id}", summary="查询视频检测进度")
async def get_video_detection_status(
    task_id: int,
    current_user=Depends(get_current_user),
):
    """先校验任务所有权，再从 Redis 查询视频进度。"""
    db = SessionLocal()
    try:
        task = db.query(DetectionTask).filter(DetectionTask.id == task_id).first()
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")
        if task.user_id != current_user.id and not _admin_user(current_user):
            raise HTTPException(status_code=403, detail="无权访问该任务")
        progress_info = redis_client.get_json(f"video_task:{task_id}")
        if progress_info:
            return {"task_id": task_id, **progress_info}
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
    origin = websocket.headers.get("origin")
    request_host = websocket.headers.get("host", "").split(":", 1)[0].lower()
    if origin:
        origin_host = (urlsplit(origin).hostname or "").lower()
        if not origin_host or origin_host != request_host:
            await websocket.close(code=1008, reason="摄像头连接仅允许同源网页")
            return
    token = websocket.query_params.get("token")
    if not settings.DEBUG and not redis_client.ensure_available():
        await websocket.close(code=1013, reason="认证缓存暂时不可用")
        return
    db = SessionLocal()
    try:
        payload = decode_access_token(token or "")
        if redis_client.exists(f"jwt:blacklist:{payload.get('jti')}"):
            raise ValueError("token revoked")
        camera_user = db.query(User).filter(User.id == int(payload.get("sub"))).first()
        if camera_user is None or not camera_user.is_active:
            raise ValueError("inactive user")
        camera_user_id = camera_user.id
    except (JWTError, ValueError, TypeError):
        await websocket.close(code=1008, reason="无效或已退出的 Token")
        return
    finally:
        db.close()
    camera_attempts = redis_client.increment_with_expiry(
        f"rate_limit:camera:{camera_user_id}", 60
    )
    if camera_attempts > 10:
        await websocket.close(code=1008, reason="摄像头连接过于频繁，请稍后重试")
        return
    await websocket.accept()
    connection_id = id(websocket)
    logger.info("摄像头 WebSocket 连接建立: connection_id=%d", connection_id)

    mode = "cpu"
    conf = 0.25
    iou = 0.45
    scene_id = None
    model_version_id = None
    model = None
    last_frame_time = 0.0
    frame_count = 0
    fps_start_time = time.time()
    fps_frame_count = 0
    camera_task_id = None
    camera_class_names_cn = {}
    saved_keyframes = 0
    total_objects = 0
    total_inference_time = 0.0
    camera_error_message = None

    try:
        while True:
            data = await websocket.receive_json()
            message_type = data.get("type")

            if message_type == "config":
                try:
                    mode = data.get("mode", "cpu")
                    conf = float(data.get("conf", 0.25))
                    iou = float(data.get("iou", 0.45))
                    scene_id = int(data["scene_id"]) if data.get("scene_id") is not None else None
                    model_version_id = (
                        int(data["model_version_id"])
                        if data.get("model_version_id") is not None
                        else None
                    )
                    if mode not in {"cpu", "gpu"}:
                        raise ValueError("推理模式只能是 cpu 或 gpu")
                    if not 0 <= conf <= 1 or not 0 <= iou <= 1:
                        raise ValueError("conf 和 iou 必须位于 0 到 1")
                except (TypeError, ValueError) as exc:
                    await websocket.send_json({"type": "error", "message": str(exc)})
                    continue
                if camera_task_id is None:
                    try:
                        camera_task_id = _create_async_task(
                            camera_user_id,
                            scene_id,
                            "camera",
                            0,
                            conf,
                            iou,
                            model_version_id,
                        )
                        _audit_detection(camera_user_id, "start_camera", camera_task_id)
                    except ValueError as exc:
                        await websocket.send_json({"type": "error", "message": str(exc)})
                        continue
                device = "cpu" if mode == "cpu" else "0"
                try:
                    model_db = SessionLocal()
                    try:
                        camera_task = model_db.query(DetectionTask).filter(
                            DetectionTask.id == camera_task_id
                        ).first()
                        camera_class_names_cn = (
                            camera_task.scene.class_names_cn
                            if camera_task and camera_task.scene and camera_task.scene.class_names_cn
                            else {}
                        )
                        model, _model_version = detection_service._load_model(
                            model_db,
                            camera_task.scene_id,
                            camera_task.model_version_id,
                        )
                    finally:
                        model_db.close()
                    dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
                    await run_in_threadpool(
                        model.predict,
                        source=dummy_frame,
                        conf=conf,
                        iou=iou,
                        imgsz=640,
                        device=device,
                        save=False,
                        verbose=False,
                    )
                    logger.info("摄像头模型预热完成, 模式: %s", mode)
                    camera_error_message = None
                except Exception as exc:
                    logger.error("模型加载失败: %s", str(exc))
                    model = None
                    camera_error_message = f"模型加载失败: {str(exc)}"
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
                    max_frame_bytes = settings.MAX_IMAGE_SIZE_MB * 1024 * 1024
                    if len(frame_base64) > ((max_frame_bytes + 2) // 3) * 4:
                        raise ValueError("摄像头帧超过大小限制")
                    image_bytes = base64.b64decode(frame_base64, validate=True)
                    if len(image_bytes) > max_frame_bytes:
                        raise ValueError("摄像头帧超过大小限制")
                    image_array = np.frombuffer(image_bytes, np.uint8)
                    frame = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
                    if frame is None:
                        raise ValueError("摄像头帧无法读取")

                    device = "cpu" if mode == "cpu" else "0"
                    image_size = 416 if mode == "cpu" else 640
                    prediction_results = await run_in_threadpool(
                        model.predict,
                        source=frame,
                        conf=conf,
                        iou=iou,
                        imgsz=image_size,
                        device=device,
                        save=False,
                        verbose=False,
                        half=False,
                    )
                    result = prediction_results[0]
                    inference_time = float(result.speed.get("inference", 0))
                    total_inference_time += inference_time
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
                                    "class_name_cn": resolve_class_name_cn(
                                        class_name, camera_class_names_cn
                                    ),
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
                    total_objects += len(detections)
                    if detections and saved_keyframes < settings.CAMERA_DEFECT_KEYFRAME_LIMIT and camera_task_id:
                        frame_name = f"camera_{frame_count:06d}.jpg"
                        input_object = f"detections/{camera_task_id}/input/{frame_name}"
                        result_object = f"detections/{camera_task_id}/output/{frame_name}"
                        try:
                            client = MinIOClient()
                            client.upload_bytes(input_object, image_bytes, "image/jpeg")
                            client.upload_bytes(result_object, buffer.tobytes(), "image/jpeg")
                        except Exception as exc:
                            logger.warning("摄像头关键帧上传失败: %s", exc)
                            input_object = frame_name
                            result_object = None
                        frame_db = SessionLocal()
                        try:
                            item = DetectionItem(
                                task_id=camera_task_id, item_index=saved_keyframes,
                                file_name=frame_name, input_path=input_object,
                                result_path=result_object, status="completed",
                                defect_count=len(detections),
                                average_confidence=sum(entry["confidence"] for entry in detections) / len(detections),
                                inference_time=inference_time, completed_at=datetime.now(),
                            )
                            frame_db.add(item); frame_db.flush()
                            for detection in detections:
                                frame_db.add(DetectionResult(
                                    task_id=camera_task_id, item_id=item.id,
                                    image_path=input_object, annotated_image_path=result_object,
                                    class_name=detection["class_name"],
                                    class_name_cn=detection["class_name_cn"],
                                    class_id=detection["class_id"],
                                    confidence=detection["confidence"], bbox=detection["bbox"],
                                    inference_time=inference_time,
                                ))
                            frame_db.commit(); saved_keyframes += 1
                        finally:
                            frame_db.close()
                    elif detections and camera_task_id:
                        # 超过关键帧上限后仍持久化结构化检测框，报告和统计保持完整；
                        # 不再保存图像对象，避免突破最多 20 张关键帧的存储约束。
                        result_db = SessionLocal()
                        try:
                            for detection in detections:
                                result_db.add(DetectionResult(
                                    task_id=camera_task_id,
                                    item_id=None,
                                    image_path=f"camera-live-frame:{frame_count}",
                                    annotated_image_path=None,
                                    class_name=detection["class_name"],
                                    class_name_cn=detection["class_name_cn"],
                                    class_id=detection["class_id"],
                                    confidence=detection["confidence"],
                                    bbox=detection["bbox"],
                                    inference_time=inference_time,
                                ))
                            result_db.commit()
                        finally:
                            result_db.close()

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
        if camera_task_id:
            final_db = SessionLocal()
            try:
                task = final_db.query(DetectionTask).filter(DetectionTask.id == camera_task_id).first()
                if task:
                    task.total_images = frame_count
                    task.total_objects = total_objects
                    task.total_inference_time = total_inference_time
                    task.completed_at = datetime.now()
                    if camera_error_message or frame_count == 0:
                        task.status = "failed"
                        task.error_message = camera_error_message or "摄像头会话未处理任何有效帧"
                        final_db.commit()
                    else:
                        task.status = "completed"
                        final_db.flush()
                        finalize_detection_task(final_db, task)
            except Exception as exc:
                final_db.rollback()
                logger.error("摄像头任务收尾失败: %s", exc, exc_info=True)
            finally:
                final_db.close()
        _camera_frame_buffer.pop(connection_id, None)
        logger.info(
            "摄像头 WebSocket 关闭, 共处理 %d 帧: connection_id=%d",
            frame_count,
            connection_id,
        )
