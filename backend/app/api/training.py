"""
训练相关 API 路由

接口列表：
  - POST   /api/training/create       创建训练任务
  - GET    /api/training/status/{id}  查询训练状态
  - GET    /api/training/list         列出训练任务
  - POST   /api/training/validate/{id} 模型评估
  - POST   /api/training/export/{id}  模型导出
  - GET    /api/training/download/{id} 下载模型权重
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.core.logger import get_logger
from app.database.session import get_db
from app.entity.schemas import (
    TrainingTaskCreate,
    TrainingTaskResponse,
    EvaluateRequest,
    EvaluateResponse,
    ModelExportResponse,
)
from app.training.training_service import training_service

logger = get_logger(__name__)

router = APIRouter(prefix="/api/training", tags=["模型训练"])


@router.post("/create", response_model=TrainingTaskResponse, summary="创建训练任务")
async def create_training(
    request: TrainingTaskCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """创建新的模型训练任务"""
    task = training_service.create_task(
        db=db,
        user_id=current_user.id,
        scene_id=request.scene_id,
        model_name=request.model_name,
        epochs=request.epochs,
        img_size=request.img_size,
        batch_size=request.batch_size,
        device=request.device,
        optimizer=request.optimizer,
        lr0=request.lr0,
        augment_config=request.augment_config,
        dataset_project_id=request.dataset_project_id,
    )

    return TrainingTaskResponse(
        id=task.id,
        user_id=task.user_id,
        scene_id=task.scene_id,
        dataset_project_id=task.dataset_project_id,
        task_uuid=task.task_uuid,
        status=task.status,
        model_name=task.model_name,
        epochs=task.epochs,
        current_epoch=task.current_epoch,
        progress=task.progress,
        img_size=task.img_size,
        batch_size=task.batch_size,
        device=task.device,
        dataset_size=task.dataset_size,
        error_message=task.error_message,
        created_at=task.created_at,
        started_at=task.started_at,
        completed_at=task.completed_at,
    )


@router.get("/status/{task_id}", summary="查询训练状态")
async def get_training_status(
    task_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """查询训练任务的状态、进度和指标"""
    result = training_service.get_status(db, task_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/list", summary="列出训练任务")
async def list_training_tasks(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """列出当前用户的训练任务列表"""
    return training_service.list_tasks(db, user_id=current_user.id)


@router.post("/validate/{task_id}", response_model=EvaluateResponse, summary="模型评估")
async def validate_model(
    task_id: int,
    request: EvaluateRequest = EvaluateRequest(),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """对已完成训练的模型执行评估（验证集或测试集）"""
    result = training_service.validate_model(
        db=db,
        task_id=task_id,
        split=request.split,
        conf=request.conf,
        iou=request.iou,
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return EvaluateResponse(
        task_id=result["task_id"],
        split=result["split"],
        overall=result["overall"],
        per_class=result["per_class"],
    )


@router.post("/export/{task_id}", response_model=ModelExportResponse, summary="模型导出")
async def export_model(
    task_id: int,
    version: str = "v1.0.0",
    description: str = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """将训练完成的 best.pt 导出为模型版本"""
    result = training_service.export_model(
        db=db,
        task_id=task_id,
        version=version,
        description=description,
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return ModelExportResponse(
        id=result["id"],
        version=result["version"],
        model_name=result["model_name"],
        model_path=result["model_path"],
        file_size=result["file_size"],
        map50=result.get("map50"),
        map50_95=result.get("map50_95"),
    )


@router.get("/download/{task_id}", summary="下载模型权重")
async def download_model(
    task_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """下载训练完成后的 best.pt 模型文件"""
    weights_path = training_service.get_model_path(db, task_id)
    if not weights_path:
        raise HTTPException(status_code=404, detail="模型权重文件不存在")

    return FileResponse(
        path=weights_path,
        filename="best.pt",
        media_type="application/octet-stream",
    )
