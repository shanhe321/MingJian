from __future__ import annotations

import base64
import os
import tempfile

import cv2
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.config.settings import settings
from app.core.logger import get_logger
from app.database.session import get_db
from app.entity.db_models import DetectionScene, TrainingTask
from app.entity.schemas import (
    ModelExportRequest,
    ModelValidateRequest,
    TrainingTaskCreate,
)
from app.training.training_service import training_service

logger = get_logger(__name__)
router = APIRouter(prefix="/api/training", tags=["模型训练"])


@router.post("/start", summary="启动训练任务")
async def start_training(
    request: TrainingTaskCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    scene = db.query(DetectionScene).filter(DetectionScene.id == request.scene_id).first()
    if scene is None:
        raise HTTPException(status_code=404, detail="检测场景不存在")

    api_dir = os.path.dirname(os.path.abspath(__file__))
    app_dir = os.path.dirname(api_dir)
    backend_dir = os.path.dirname(app_dir)
    dataset_path = os.path.join(
        backend_dir,
        "datasets",
        scene.name,
        "yolo_dataset",
    )
    data_yaml = os.path.join(dataset_path, "data.yaml")
    if not os.path.exists(data_yaml):
        raise HTTPException(
            status_code=400,
            detail=f"data.yaml 不存在：{data_yaml}，请先完成数据集准备",
        )

    config = {
        "model_name": request.model_name,
        "epochs": request.epochs,
        "img_size": request.img_size,
        "batch_size": request.batch_size,
        "device": request.device,
        "optimizer": request.optimizer,
        "lr0": request.lr0,
        "augment_config": request.augment_config,
        "dataset_path": dataset_path,
        "data_yaml": data_yaml,
    }
    try:
        task = training_service.start_training(
            db=db,
            user_id=current_user.id,
            scene_id=request.scene_id,
            config=config,
        )
    except Exception as exc:
        logger.error("启动训练失败：%s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"启动训练失败：{exc}") from exc

    return {
        "id": task.id,
        "task_uuid": task.task_uuid,
        "status": task.status,
        "model_name": task.model_name,
        "epochs": task.epochs,
        "message": "训练任务已创建，正在后台启动",
    }


@router.get("/tasks", summary="获取训练任务列表")
async def list_training_tasks(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    tasks = training_service.get_task_list(db, user_id=current_user.id)
    return {"total": len(tasks), "items": tasks}


@router.get("/status/{task_id}", summary="获取训练状态")
async def get_training_status(
    task_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    status = training_service.get_training_status(db, task_id)
    if "error" in status:
        raise HTTPException(status_code=404, detail=status["error"])
    return status


@router.get("/metrics/{task_id}", summary="获取训练指标历史")
async def get_training_metrics(
    task_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    metrics = training_service.get_training_metrics(db, task_id)
    return {"task_id": task_id, "total": len(metrics), "metrics": metrics}


@router.post("/stop/{task_id}", summary="停止训练任务")
async def stop_training(
    task_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    result = training_service.stop_training(db, task_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/results/{task_uuid}", summary="下载 results.csv")
async def get_results_csv(
    task_uuid: str,
    current_user=Depends(get_current_user),
):
    results_path = os.path.join(
        settings.TRAIN_OUTPUT_DIR,
        f"task_{task_uuid}",
        "results.csv",
    )
    if not os.path.exists(results_path):
        raise HTTPException(status_code=404, detail="results.csv 文件不存在")
    return FileResponse(
        path=results_path,
        media_type="text/csv",
        filename=f"training_results_{task_uuid}.csv",
    )


@router.post("/validate/{task_id}", summary="模型评估")
async def validate_model(
    task_id: int,
    request: ModelValidateRequest | None = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    request = request or ModelValidateRequest()
    result = training_service.validate_model(
        db=db,
        task_id=task_id,
        split=request.split,
        conf=request.conf,
        iou=request.iou,
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/export/{task_id}", summary="模型导出与版本管理")
async def export_model(
    task_id: int,
    request: ModelExportRequest | None = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    request = request or ModelExportRequest()
    result = training_service.export_model(
        db=db,
        task_id=task_id,
        version=request.version,
        description=request.description,
        set_default=request.set_default,
        upload_minio=request.upload_minio,
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/download/{task_id}", summary="下载模型权重")
async def download_model(
    task_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    result = training_service.get_model_download_path(db, task_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return FileResponse(
        path=result["file_path"],
        media_type="application/octet-stream",
        filename=result["filename"],
    )


@router.post("/predict", summary="上传测试图验证模型")
async def predict_test_image(
    file: UploadFile = File(..., description="测试图片"),
    task_id: int = Form(..., description="训练任务 ID（使用哪个模型）"),
    conf: float = Form(0.25, description="置信度阈值"),
    iou: float = Form(0.45, description="NMS IoU 阈值"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    allowed_types = {"image/jpeg", "image/png", "image/bmp", "image/webp"}
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型: {file.content_type}，支持: {', '.join(allowed_types)}",
        )

    task = db.query(TrainingTask).filter(TrainingTask.id == task_id).first()
    if task is None:
        raise HTTPException(status_code=404, detail="训练任务不存在")
    if task.status != "completed":
        raise HTTPException(status_code=400, detail="训练任务未完成，无法进行预测")
    weights_path = os.path.join(
        os.getcwd(),
        settings.TRAIN_OUTPUT_DIR,
        f"task_{task.task_uuid}",
        "weights",
        "best.pt",
    )
    if not os.path.exists(weights_path):
        raise HTTPException(status_code=404, detail="模型权重文件不存在")

    tmp_path = None
    try:
        content = await file.read()
        with tempfile.NamedTemporaryFile(
            suffix=os.path.splitext(file.filename)[1] or ".jpg",
            delete=False,
        ) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        from ultralytics import YOLO

        model = YOLO(weights_path)
        result = model.predict(
            source=tmp_path,
            conf=conf,
            iou=iou,
            imgsz=task.img_size,
            device="cpu",
            save=False,
            verbose=False,
        )[0]
        detections = []
        if result.boxes is not None:
            for box in result.boxes:
                class_id = int(box.cls[0])
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                detections.append(
                    {
                        "class_name": model.names.get(class_id, f"class_{class_id}"),
                        "class_id": class_id,
                        "confidence": round(float(box.conf[0]), 4),
                        "bbox": [round(value, 1) for value in (x1, y1, x2, y2)],
                    }
                )

        _, buffer = cv2.imencode(
            ".jpg", result.plot(), [cv2.IMWRITE_JPEG_QUALITY, 85]
        )
        class_counts: dict[str, int] = {}
        for detection in detections:
            name = detection["class_name"]
            class_counts[name] = class_counts.get(name, 0) + 1
        return {
            "task_id": task_id,
            "task_uuid": task.task_uuid,
            "filename": file.filename,
            "total_objects": len(detections),
            "detections": detections,
            "class_counts": class_counts,
            "annotated_image": base64.b64encode(buffer).decode("utf-8"),
            "inference_time": round(float(result.speed.get("inference", 0)), 2),
        }
    finally:
        await file.close()
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
