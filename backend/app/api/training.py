from __future__ import annotations

import base64
import os
import tempfile

import cv2
import numpy as np
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.config.settings import settings
from app.core.logger import get_logger
from app.database.session import get_db
from app.entity.db_models import DatasetProject, DetectionScene, ModelVersion, TrainingTask
from app.entity.schemas import (
    ModelExportRequest,
    ModelValidateRequest,
    TrainingTaskCreate,
)
from app.training.training_service import training_service
from app.storage.minio_client import MinIOClient
from app.services.audit_service import write_audit

logger = get_logger(__name__)
router = APIRouter(prefix="/api/training", tags=["模型训练"])


def _is_admin(user) -> bool:
    return bool(getattr(user, "is_superuser", False) or any(item.role.name == "admin" for item in getattr(user, "user_roles", [])))


def _owned_task(db: Session, task_id: int, user) -> TrainingTask:
    task = db.query(TrainingTask).filter(TrainingTask.id == task_id).first()
    if task is None:
        raise HTTPException(status_code=404, detail="训练任务不存在")
    if task.user_id != user.id and not _is_admin(user):
        raise HTTPException(status_code=403, detail="无权访问该训练任务")
    return task


@router.post("/start", summary="启动训练任务")
async def start_training(
    request: TrainingTaskCreate,
    http_request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    scene = db.query(DetectionScene).filter(DetectionScene.id == request.scene_id).first()
    if scene is None:
        raise HTTPException(status_code=404, detail="检测场景不存在")

    if request.dataset_project_id is not None:
        project = db.query(DatasetProject).filter(DatasetProject.id == request.dataset_project_id).first()
        if project is None:
            raise HTTPException(status_code=404, detail="数据集项目不存在")
        if project.user_id != current_user.id and not _is_admin(current_user):
            raise HTTPException(status_code=403, detail="无权使用该数据集")
        if project.status != "ready":
            raise HTTPException(status_code=400, detail="数据集尚未通过校验")
        dataset_path = os.path.join(project.storage_path, "yolo_dataset")
        data_yaml = os.path.join(dataset_path, "data.yaml")
    else:
        api_dir = os.path.dirname(os.path.abspath(__file__))
        app_dir = os.path.dirname(api_dir)
        backend_dir = os.path.dirname(app_dir)
        dataset_path = os.path.join(backend_dir, "datasets", scene.name, "yolo_dataset")
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
        "dataset_project_id": request.dataset_project_id,
    }
    try:
        task = training_service.start_training(
            db=db,
            user_id=current_user.id,
            scene_id=request.scene_id,
            config=config,
        )
        write_audit(
            db, user=current_user, module="training", action="start",
            target_type="training_task", target_id=task.id,
            details={"dataset_project_id": request.dataset_project_id}, request=http_request,
        )
        db.commit()
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
    user_id: int | None = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    scoped_user_id = user_id if _is_admin(current_user) else current_user.id
    tasks = training_service.get_task_list(db, user_id=scoped_user_id)
    return {"total": len(tasks), "items": tasks}


def _model_payload(model: ModelVersion) -> dict:
    artifact_names = ("confusion_matrix.png", "PR_curve.png", "F1_curve.png", "results.png", "eval_report.json")
    artifacts = {}
    model_url = None
    if model.minio_url:
        root = model.minio_url.rsplit("/", 1)[0]
        try:
            client = MinIOClient()
            model_url = client.get_presigned_url(model.minio_url)
            existing = client.list_object_names(f"{root}/artifacts/")
            artifacts = {
                name: client.get_presigned_url(f"{root}/artifacts/{name}")
                for name in artifact_names
                if f"{root}/artifacts/{name}" in existing
            }
        except Exception:
            artifacts = {}
    return {
        "id": model.id, "scene_id": model.scene_id, "training_task_id": model.training_task_id,
        "version": model.version, "model_name": model.model_name, "model_type": model.model_type,
        "status": model.status, "model_path": model.model_path, "model_object_path": model.minio_url,
        "map50": model.map50, "map50_95": model.map50_95, "precision": model.precision,
        "recall": model.recall, "per_class_ap": model.per_class_ap,
        "description": model.description, "file_size": model.file_size,
        "is_default": model.is_default, "created_at": model.created_at,
        "model_url": model_url, "artifacts": artifacts,
        "artifact_status": {
            "available": sorted(artifacts),
            "missing": [name for name in artifact_names if name not in artifacts],
        },
    }


@router.get("/models", summary="模型版本列表")
async def list_model_versions(
    scene_id: int | None = None,
    include_archived: bool = False,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(ModelVersion)
    if scene_id is not None:
        query = query.filter(ModelVersion.scene_id == scene_id)
    if not include_archived or not _is_admin(current_user):
        query = query.filter(ModelVersion.status == "active")
    rows = query.order_by(ModelVersion.created_at.desc()).all()
    return {"total": len(rows), "items": [_model_payload(row) for row in rows]}


@router.get("/models/{model_id}", summary="模型版本详情")
async def get_model_version(model_id: int, user=Depends(get_current_user), db: Session = Depends(get_db)):
    model = db.query(ModelVersion).filter(ModelVersion.id == model_id).first()
    if not model:
        raise HTTPException(status_code=404, detail="模型版本不存在")
    if model.status != "active" and not _is_admin(user):
        raise HTTPException(status_code=404, detail="模型版本不存在")
    return _model_payload(model)


@router.put("/models/{model_id}/default", summary="切换默认模型")
async def set_default_model(
    model_id: int, request: Request,
    current_user=Depends(get_current_user), db: Session = Depends(get_db),
):
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="仅管理员可切换默认模型")
    model = db.query(ModelVersion).filter(ModelVersion.id == model_id).first()
    if not model or model.status != "active":
        raise HTTPException(status_code=404, detail="可用模型版本不存在")
    db.query(ModelVersion).filter(ModelVersion.scene_id == model.scene_id).update({ModelVersion.is_default: False})
    model.is_default = True
    write_audit(db, user=current_user, module="model", action="set_default", target_type="model", target_id=model.id, request=request)
    db.commit()
    return _model_payload(model)


@router.delete("/models/{model_id}", summary="逻辑归档模型")
async def archive_model(
    model_id: int, request: Request,
    current_user=Depends(get_current_user), db: Session = Depends(get_db),
):
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="仅管理员可归档模型")
    model = db.query(ModelVersion).filter(ModelVersion.id == model_id).first()
    if not model or model.status != "active":
        raise HTTPException(status_code=404, detail="模型版本不存在")
    replacement = (
        db.query(ModelVersion)
        .filter(
            ModelVersion.scene_id == model.scene_id,
            ModelVersion.status == "active",
            ModelVersion.id != model.id,
        )
        .order_by(ModelVersion.created_at.desc())
        .first()
    )
    if replacement is None:
        raise HTTPException(status_code=409, detail="每个场景至少保留一个可用模型，无法归档")
    if model.is_default:
        replacement.is_default = True
    model.status = "archived"
    model.is_default = False
    write_audit(db, user=current_user, module="model", action="archive", target_type="model", target_id=model.id, request=request)
    db.commit()
    return {"message": "模型已归档", "model_id": model.id}


@router.get("/status/{task_id}", summary="获取训练状态")
async def get_training_status(
    task_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    _owned_task(db, task_id, current_user)
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
    _owned_task(db, task_id, current_user)
    metrics = training_service.get_training_metrics(db, task_id)
    return {"task_id": task_id, "total": len(metrics), "metrics": metrics}


@router.post("/stop/{task_id}", summary="停止训练任务")
async def stop_training(
    task_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    _owned_task(db, task_id, current_user)
    result = training_service.stop_training(db, task_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    write_audit(
        db, user=current_user, module="training", action="stop",
        target_type="training_task", target_id=task_id, request=request,
    )
    db.commit()
    return result


@router.get("/results/{task_uuid}", summary="下载 results.csv")
async def get_results_csv(
    task_uuid: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    task = db.query(TrainingTask).filter(TrainingTask.task_uuid == task_uuid).first()
    if task is None:
        raise HTTPException(status_code=404, detail="训练任务不存在")
    _owned_task(db, task.id, current_user)
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
def validate_model(
    task_id: int,
    http_request: Request,
    request: ModelValidateRequest | None = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    对已完成训练的模型执行评估

    - 在验证集或测试集上运行 model.val()
    - 返回 mAP、Precision、Recall 等指标
    - 返回每类 AP 分析
    - 自动创建/更新 ModelVersion 记录
    """
    request = request or ModelValidateRequest()
    _owned_task(db, task_id, current_user)
    result = training_service.validate_model(
        db=db,
        task_id=task_id,
        split=request.split,
        conf=request.conf,
        iou=request.iou,
    )
    if "error" in result:
        status_code = 409 if result.get("code") == "evaluation_in_progress" else 400
        raise HTTPException(status_code=status_code, detail=result["error"])
    write_audit(db, user=current_user, module="training", action="evaluate", target_type="training_task", target_id=task_id, request=http_request)
    db.commit()
    logger.info(
        "用户 %s 评估模型: task_id=%d, mAP50=%.4f",
        current_user.username,
        task_id,
        result.get("overall", {}).get("map50", 0),
    )
    return result


@router.post("/export/{task_id}", summary="模型导出与版本管理")
def export_model(
    task_id: int,
    http_request: Request,
    request: ModelExportRequest | None = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    导出训练好的模型为正式版本

    - 复制 best.pt 到 models/ 目录
    - 运行评估获取最终指标
    - 保存评估报告 JSON
    - 创建 ModelVersion 记录
    - 可选上传到 MinIO
    """
    request = request or ModelExportRequest()
    _owned_task(db, task_id, current_user)
    if request.set_default and not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="仅管理员可切换默认模型")
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
    write_audit(db, user=current_user, module="model", action="export", target_type="training_task", target_id=task_id, details={"version": result.get("version")}, request=http_request)
    db.commit()
    logger.info(
        "用户 %s 导出模型: task_id=%d, version=%s",
        current_user.username,
        task_id,
        result.get("version"),
    )
    return result


@router.get("/download/{task_id}", summary="下载模型权重")
async def download_model(
    task_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    下载训练好的模型权重文件（best.pt）

    返回文件下载响应，浏览器直接保存文件
    """
    _owned_task(db, task_id, current_user)
    result = training_service.get_model_download_path(db, task_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    logger.info(
        "用户 %s 下载模型: task_id=%d, file=%s",
        current_user.username,
        task_id,
        result["filename"],
    )
    write_audit(
        db, user=current_user, module="model", action="download",
        target_type="training_task", target_id=task_id,
        details={"filename": result["filename"]}, request=request,
    )
    db.commit()
    return FileResponse(
        path=result["file_path"],
        media_type="application/octet-stream",
        filename=result["filename"],
    )


@router.post("/predict", summary="上传测试图验证模型")
async def predict_test_image(
    request: Request,
    file: UploadFile = File(..., description="测试图片"),
    task_id: int = Form(..., description="训练任务 ID（使用哪个模型）"),
    conf: float = Form(0.25, ge=0, le=1, description="置信度阈值"),
    iou: float = Form(0.45, gt=0, le=1, description="NMS IoU 阈值"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    上传测试图片，使用训练好的模型进行预测

    用于快速验证模型训练效果：
    1. 上传一张不在训练集/验证集中的测试图片
    2. 使用 best.pt 进行推理
    3. 返回检测结果（标注图 + 检测统计）
    """
    allowed_types = {"image/jpeg", "image/png", "image/bmp", "image/webp"}
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型: {file.content_type}，支持: {', '.join(allowed_types)}",
        )

    task = _owned_task(db, task_id, current_user)
    if task.status != "completed":
        raise HTTPException(status_code=400, detail="训练任务未完成，无法进行预测")
    try:
        weights_path = training_service.get_model_path(db, task_id)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"模型权重恢复失败: {exc}") from exc
    if not weights_path:
        raise HTTPException(status_code=404, detail="模型权重文件不存在")

    tmp_path = None
    try:
        content = await file.read(settings.MAX_IMAGE_SIZE_MB * 1024 * 1024 + 1)
        if len(content) > settings.MAX_IMAGE_SIZE_MB * 1024 * 1024:
            raise HTTPException(status_code=413, detail=f"图片不能超过 {settings.MAX_IMAGE_SIZE_MB}MB")
        decoded = cv2.imdecode(np.frombuffer(content, dtype=np.uint8), cv2.IMREAD_COLOR)
        if decoded is None:
            raise HTTPException(status_code=400, detail="上传文件不是可读取的图片")
        with tempfile.NamedTemporaryFile(
            prefix="rsod_training_predict_",
            suffix={
                "image/jpeg": ".jpg",
                "image/png": ".png",
                "image/bmp": ".bmp",
                "image/webp": ".webp",
            }[file.content_type],
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
        response = {
            "task_id": task_id,
            "task_uuid": task.task_uuid,
            "filename": file.filename,
            "total_objects": len(detections),
            "detections": detections,
            "class_counts": class_counts,
            "annotated_image": base64.b64encode(buffer).decode("utf-8"),
            "inference_time": round(float(result.speed.get("inference", 0)), 2),
        }
        write_audit(
            db, user=current_user, module="model", action="predict",
            target_type="training_task", target_id=task_id,
            details={"filename": file.filename, "total_objects": len(detections)},
            request=request,
        )
        db.commit()
        return response
    finally:
        await file.close()
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
