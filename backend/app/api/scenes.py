"""检测场景查询与管理员 CRUD。"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.auth import get_current_user, require_admin
from app.database.session import get_db
from app.entity.db_models import (
    DatasetProject,
    DetectionScene,
    DetectionTask,
    ModelVersion,
    TrainingTask,
)
from app.entity.schemas import SceneCreate, SceneUpdate
from app.services.audit_service import write_audit


router = APIRouter(prefix="/api/scenes", tags=["检测场景"])


def _validate_class_mapping(class_names: list[str], mapping: dict | None) -> None:
    mapping = mapping or {}
    unknown = set(mapping) - set(class_names)
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"中文类别映射包含未定义类别: {', '.join(sorted(unknown))}",
        )
    if any(not str(value).strip() for value in mapping.values()):
        raise HTTPException(status_code=400, detail="中文类别名称不能为空")


def _is_admin(user) -> bool:
    return bool(
        getattr(user, "is_superuser", False)
        or any(item.role.name == "admin" for item in getattr(user, "user_roles", []))
    )


def _payload(scene: DetectionScene) -> dict:
    return {
        "id": scene.id,
        "name": scene.name,
        "display_name": scene.display_name,
        "description": scene.description,
        "category": scene.category,
        "class_names": scene.class_names or [],
        "class_names_cn": scene.class_names_cn or {},
        "is_active": bool(scene.is_active),
        "created_by": scene.created_by,
        "created_at": scene.created_at,
        "updated_at": scene.updated_at,
    }


@router.get("")
async def list_scenes(
    include_inactive: bool = False,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if include_inactive and not _is_admin(user):
        raise HTTPException(status_code=403, detail="仅管理员可查看停用场景")
    query = db.query(DetectionScene)
    if not include_inactive:
        query = query.filter(DetectionScene.is_active.is_(True))
    rows = query.order_by(DetectionScene.created_at, DetectionScene.id).all()
    return {"total": len(rows), "items": [_payload(row) for row in rows]}


@router.get("/{scene_id}")
async def get_scene(
    scene_id: int,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    scene = db.get(DetectionScene, scene_id)
    if scene is None:
        raise HTTPException(status_code=404, detail="检测场景不存在")
    if not scene.is_active and not _is_admin(user):
        raise HTTPException(status_code=403, detail="无权查看停用场景")
    return _payload(scene)


@router.post("", status_code=201)
async def create_scene(
    payload: SceneCreate,
    request: Request,
    admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    if db.query(DetectionScene).filter(DetectionScene.name == payload.name).first():
        raise HTTPException(status_code=409, detail="场景标识已存在")
    if not payload.class_names or len(set(payload.class_names)) != len(payload.class_names):
        raise HTTPException(status_code=400, detail="缺陷类别不能为空或重复")
    _validate_class_mapping(payload.class_names, payload.class_names_cn)
    scene = DetectionScene(**payload.model_dump(), created_by=admin.id)
    db.add(scene)
    db.flush()
    write_audit(
        db, user=admin, module="scene", action="create",
        target_type="scene", target_id=scene.id, request=request,
    )
    db.commit()
    db.refresh(scene)
    return _payload(scene)


@router.put("/{scene_id}")
async def update_scene(
    scene_id: int,
    payload: SceneUpdate,
    request: Request,
    admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    scene = db.get(DetectionScene, scene_id)
    if scene is None:
        raise HTTPException(status_code=404, detail="检测场景不存在")
    changes = payload.model_dump(exclude_unset=True)
    if "class_names" in changes and (
        not changes["class_names"] or len(set(changes["class_names"])) != len(changes["class_names"])
    ):
        raise HTTPException(status_code=400, detail="缺陷类别不能为空或重复")
    next_classes = changes.get("class_names", scene.class_names or [])
    next_mapping = changes.get("class_names_cn", scene.class_names_cn or {})
    _validate_class_mapping(next_classes, next_mapping)
    if "class_names" in changes and changes["class_names"] != (scene.class_names or []):
        referenced = any(
            db.query(model).filter(model.scene_id == scene_id).first() is not None
            for model in (DatasetProject, DetectionTask, TrainingTask, ModelVersion)
        )
        if referenced:
            raise HTTPException(
                status_code=409,
                detail="场景已产生数据集、检测、训练或模型记录，不能修改类别集合",
            )
    for key, value in changes.items():
        setattr(scene, key, value)
    write_audit(
        db, user=admin, module="scene", action="update",
        target_type="scene", target_id=scene.id, details={"fields": sorted(changes)}, request=request,
    )
    db.commit()
    db.refresh(scene)
    return _payload(scene)


@router.delete("/{scene_id}")
async def delete_scene(
    scene_id: int,
    request: Request,
    admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    scene = db.get(DetectionScene, scene_id)
    if scene is None:
        raise HTTPException(status_code=404, detail="检测场景不存在")
    db.delete(scene)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="场景已被数据集、检测、训练或模型引用，不能删除") from exc
    write_audit(
        db, user=admin, module="scene", action="delete",
        target_type="scene", target_id=scene_id, request=request,
    )
    db.commit()
    return {"message": "检测场景已删除", "scene_id": scene_id}
