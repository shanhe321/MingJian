"""数据集项目 CRUD、四格式导入与校验。"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from PIL import Image
import yaml
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.api.auth import get_current_user
from app.config.settings import settings
from app.database.session import get_db
from app.entity.db_models import (
    DatasetAnnotation,
    DatasetImage,
    DatasetProject,
    DetectionScene,
)
from app.services.audit_service import write_audit
from app.training.data_converter import DataConverter

router = APIRouter(prefix="/api/datasets", tags=["数据集"])


def _is_admin(user) -> bool:
    return bool(getattr(user, "is_superuser", False) or any(item.role.name == "admin" for item in getattr(user, "user_roles", [])))


def _project(db: Session, project_id: int, user) -> DatasetProject:
    project = db.query(DatasetProject).filter(DatasetProject.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="数据集项目不存在")
    if project.user_id != user.id and not _is_admin(user):
        raise HTTPException(status_code=403, detail="无权访问该数据集")
    return project


def _serialize(project: DatasetProject, include_images: bool = False) -> dict:
    data = {
        "id": project.id, "user_id": project.user_id, "scene_id": project.scene_id,
        "name": project.name, "description": project.description,
        "storage_path": project.storage_path, "status": project.status,
        "total_images": project.total_images, "train_images": project.train_images,
        "val_images": project.val_images, "test_images": project.test_images,
        "created_at": project.created_at, "updated_at": project.updated_at,
    }
    if include_images:
        data["images"] = [
            {"id": image.id, "image_name": image.image_name, "image_path": image.image_path,
             "label_path": image.label_path, "split": image.split, "width": image.width,
             "height": image.height, "defect_count": image.defect_count, "status": image.status,
             "annotations": [
                 {"id": annotation.id, "class_id": annotation.class_id,
                  "class_name": annotation.class_name, "bbox": annotation.bbox,
                  "source": annotation.source}
                 for annotation in image.annotations
             ]}
            for image in project.images
        ]
    return data


@router.post("", status_code=201, summary="创建数据集项目")
async def create_dataset(
    request: Request,
    name: str = Form(...),
    scene_id: int = Form(...),
    description: str | None = Form(None),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not db.query(DetectionScene).filter(DetectionScene.id == scene_id).first():
        raise HTTPException(status_code=404, detail="检测场景不存在")
    if db.query(DatasetProject).filter(DatasetProject.user_id == current_user.id, DatasetProject.name == name).first():
        raise HTTPException(status_code=409, detail="数据集名称已存在")
    project = DatasetProject(user_id=current_user.id, scene_id=scene_id, name=name, description=description)
    db.add(project); db.flush()
    project.storage_path = str((Path(settings.DATASET_BASE_DIR) / "projects" / str(project.id)).resolve())
    write_audit(db, user=current_user, module="dataset", action="create", target_type="dataset", target_id=project.id, request=request)
    db.commit(); db.refresh(project)
    return _serialize(project)


@router.get("", summary="数据集项目列表")
async def list_datasets(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    query = db.query(DatasetProject)
    if not _is_admin(current_user):
        query = query.filter(DatasetProject.user_id == current_user.id)
    rows = query.order_by(DatasetProject.updated_at.desc()).all()
    return {"total": len(rows), "items": [_serialize(row) for row in rows]}


@router.get("/{project_id}", summary="数据集项目详情")
async def get_dataset(project_id: int, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    project = (
        db.query(DatasetProject)
        .options(
            selectinload(DatasetProject.images).selectinload(DatasetImage.annotations)
        )
        .filter(DatasetProject.id == project_id)
        .first()
    )
    if not project:
        raise HTTPException(status_code=404, detail="数据集项目不存在")
    if project.user_id != current_user.id and not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="无权访问该数据集")
    return _serialize(project, include_images=True)


@router.put("/{project_id}", summary="修改数据集项目")
async def update_dataset(
    project_id: int, request: Request, name: str | None = Form(None), description: str | None = Form(None),
    current_user=Depends(get_current_user), db: Session = Depends(get_db),
):
    project = _project(db, project_id, current_user)
    if name is not None:
        duplicate = db.query(DatasetProject).filter(
            DatasetProject.user_id == project.user_id,
            DatasetProject.name == name,
            DatasetProject.id != project.id,
        ).first()
        if duplicate:
            raise HTTPException(status_code=409, detail="数据集名称已存在")
        project.name = name
    if description is not None:
        project.description = description
    write_audit(db, user=current_user, module="dataset", action="update", target_type="dataset", target_id=project.id, request=request)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="数据集名称已存在") from exc
    db.refresh(project)
    return _serialize(project)


def _safe_extract(archive: zipfile.ZipFile, target: Path) -> None:
    members = [item for item in archive.infolist() if not item.is_dir()]
    if len(members) > settings.MAX_ZIP_FILES:
        raise HTTPException(status_code=400, detail="压缩包文件数量超过限制")
    if sum(item.file_size for item in members) > settings.MAX_ZIP_UNCOMPRESSED_MB * 1024 * 1024:
        raise HTTPException(status_code=400, detail="压缩包解压总体积超过限制")
    root = target.resolve()
    for item in members:
        destination = (target / item.filename).resolve()
        if os.path.commonpath([str(root), str(destination)]) != str(root):
            raise HTTPException(status_code=400, detail="压缩包包含非法路径")
        archive.extract(item, target)


def _source_split(image_path: Path) -> str | None:
    parts = {part.lower() for part in image_path.parts}
    if "test" in parts:
        return "test"
    if "val" in parts or "valid" in parts or "validation" in parts:
        return "val"
    if "train" in parts:
        return "train"
    return None


def _yolo_source_label(image_path: Path, source: Path) -> Path | None:
    relative = image_path.relative_to(source)
    parts = list(relative.parts)
    lowered = [part.lower() for part in parts]
    if "images" in lowered:
        index = lowered.index("images")
        candidate = source.joinpath(*parts[:index], "labels", *parts[index + 1:]).with_suffix(".txt")
        if candidate.exists():
            return candidate
    beside = image_path.with_suffix(".txt")
    if beside.exists():
        return beside
    matches = list(source.rglob(f"{image_path.stem}.txt"))
    return matches[0] if len(matches) == 1 else None


@router.post("/{project_id}/import", summary="导入并转换数据集")
async def import_dataset(
    project_id: int, request: Request, file: UploadFile = File(...),
    format: str = Form(..., pattern="^(yolo|voc|coco|labelme)$"),
    current_user=Depends(get_current_user), db: Session = Depends(get_db),
):
    project = _project(db, project_id, current_user)
    if Path(file.filename or "").suffix.lower() != ".zip":
        raise HTTPException(status_code=415, detail="数据集必须以 ZIP 上传")
    content = await file.read(200 * 1024 * 1024 + 1)
    if len(content) > 200 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="数据集压缩包不能超过 200MB")
    root = Path(project.storage_path)
    root.parent.mkdir(parents=True, exist_ok=True)
    scene_classes = list(project.scene.class_names or [])
    # 文件解压和转换不占用数据库事务。
    db.commit()
    staging = Path(tempfile.mkdtemp(prefix=f"dataset_{project.id}_", dir=str(root.parent)))
    source = staging / "source"
    converted_labels = staging / "converted_labels"
    output = staging / "yolo_dataset"
    source.mkdir(parents=True)
    converted_labels.mkdir(parents=True)
    archive_path = staging / "upload.zip"
    archive_path.write_bytes(content)
    try:
        with zipfile.ZipFile(archive_path) as archive:
            _safe_extract(archive, source)
    except zipfile.BadZipFile as exc:
        shutil.rmtree(staging, ignore_errors=True)
        raise HTTPException(status_code=400, detail="无效 ZIP 文件") from exc
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    finally:
        archive_path.unlink(missing_ok=True)

    mapping = {name: index for index, name in enumerate(scene_classes)}
    conversion = {"total": 0, "converted": 0, "skipped": 0, "errors": []}
    if format == "voc":
        xmls = list(source.rglob("*.xml"))
        if not xmls:
            shutil.rmtree(staging, ignore_errors=True)
            raise HTTPException(status_code=400, detail="VOC 数据集中未找到 XML 标注")
        conversion = DataConverter.voc_to_yolo(source, converted_labels, mapping)
    elif format == "coco":
        candidates = list(source.rglob("*.json"))
        coco_file = None
        for candidate in candidates:
            try:
                payload = json.loads(candidate.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                continue
            if all(key in payload for key in ("images", "annotations", "categories")):
                coco_file = candidate
                break
        if coco_file is None:
            shutil.rmtree(staging, ignore_errors=True)
            raise HTTPException(status_code=400, detail="COCO 数据集中未找到有效标注 JSON")
        conversion = DataConverter.coco_to_yolo(coco_file, converted_labels, mapping or None)
    elif format == "labelme":
        candidates = list(source.rglob("*.json"))
        if not candidates:
            shutil.rmtree(staging, ignore_errors=True)
            raise HTTPException(status_code=400, detail="LabelMe 数据集中未找到 JSON 标注")
        conversion = DataConverter.labelme_to_yolo(source, converted_labels, mapping)

    if format != "yolo" and conversion["total"] == 0:
        shutil.rmtree(staging, ignore_errors=True)
        raise HTTPException(status_code=400, detail="数据集标注为空，无法完成格式转换")

    image_paths = sorted(
        path for path in source.rglob("*")
        if path.is_file() and path.suffix.lower() in DataConverter.image_exts
    )
    assignments = [_source_split(path) for path in image_paths]
    if "val" not in assignments and len(image_paths) >= 2:
        assignments[-max(1, len(image_paths) // 5):] = ["val"] * max(1, len(image_paths) // 5)
    assignments = [split or "train" for split in assignments]

    counts = {"train": 0, "val": 0, "test": 0}
    rows = []
    for image_path, split in zip(image_paths, assignments):
        try:
            with Image.open(image_path) as image:
                width, height = image.size
        except OSError:
            continue
        checksum = hashlib.sha256(image_path.read_bytes()).hexdigest()
        output_name = f"{checksum[:12]}_{image_path.name}"
        image_target = output / "images" / split / output_name
        image_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(image_path, image_target)
        source_label = (
            _yolo_source_label(image_path, source)
            if format == "yolo"
            else converted_labels / f"{image_path.stem}.txt"
        )
        label_target = output / "labels" / split / f"{Path(output_name).stem}.txt"
        if source_label and source_label.exists():
            label_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_label, label_target)
            defect_count = len([line for line in label_target.read_text(encoding="utf-8").splitlines() if line.strip()])
        else:
            label_target = None
            defect_count = 0
        rows.append({
            "image_name": image_path.name,
            "image_relative": image_target.relative_to(staging),
            "label_relative": label_target.relative_to(staging) if label_target else None,
            "split": split,
            "width": width,
            "height": height,
            "defect_count": defect_count,
            "checksum": checksum,
        })
        counts[split] += 1

    backup = root.with_name(f"{root.name}.backup")
    if backup.exists():
        shutil.rmtree(backup)
    if root.exists():
        root.rename(backup)
    try:
        staging.rename(root)
        db.query(DatasetImage).filter(
            DatasetImage.dataset_project_id == project.id
        ).delete(synchronize_session=False)
        for row in rows:
            dataset_image = DatasetImage(
                dataset_project_id=project.id,
                image_name=row["image_name"],
                image_path=str(root / row["image_relative"]),
                label_path=str(root / row["label_relative"]) if row["label_relative"] else None,
                split=row["split"], width=row["width"], height=row["height"],
                defect_count=row["defect_count"], checksum=row["checksum"], status="valid",
            )
            db.add(dataset_image)
            db.flush()
            if row["label_relative"]:
                label_file = root / row["label_relative"]
                for line in label_file.read_text(encoding="utf-8").splitlines():
                    values = line.split()
                    if len(values) != 5:
                        continue
                    try:
                        class_id = int(values[0])
                        x_center, y_center, box_width, box_height = (
                            float(value) for value in values[1:]
                        )
                    except ValueError:
                        continue
                    if not 0 <= class_id < len(scene_classes):
                        continue
                    x1 = (x_center - box_width / 2) * row["width"]
                    y1 = (y_center - box_height / 2) * row["height"]
                    x2 = (x_center + box_width / 2) * row["width"]
                    y2 = (y_center + box_height / 2) * row["height"]
                    db.add(DatasetAnnotation(
                        image_id=dataset_image.id,
                        class_id=class_id,
                        class_name=scene_classes[class_id],
                        bbox=[round(x1, 2), round(y1, 2), round(x2, 2), round(y2, 2)],
                        source="import",
                        created_by=current_user.id,
                    ))
        project = _project(db, project_id, current_user)
        project.total_images = sum(counts.values()); project.train_images = counts["train"]
        project.val_images = counts["val"]; project.test_images = counts["test"]
        project.status = "prepared" if project.total_images else "failed"
        write_audit(db, user=current_user, module="dataset", action="import", target_type="dataset", target_id=project.id, details={"format": format}, request=request)
        db.commit()
    except Exception:
        db.rollback()
        if root.exists():
            shutil.rmtree(root)
        if backup.exists():
            backup.rename(root)
        raise
    finally:
        if backup.exists():
            shutil.rmtree(backup)
    return {"project": _serialize(project), "format": format, "conversion": conversion}


@router.post("/{project_id}/validate", summary="校验 YOLO 数据集")
async def validate_dataset(project_id: int, request: Request, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    project = _project(db, project_id, current_user); project.status = "validating"; db.flush()
    errors = []
    scene_classes = list(project.scene.class_names or [])
    if project.train_images < 1:
        errors.append("训练集至少需要 1 张图片")
    if project.val_images < 1:
        errors.append("验证集至少需要 1 张图片")
    for image in project.images:
        if not Path(image.image_path).exists():
            image.status = "invalid"; errors.append(f"图片不存在: {image.image_name}"); continue
        if not image.label_path:
            image.status = "invalid"; errors.append(f"图片缺少标签文件: {image.image_name}"); continue
        if image.label_path and not Path(image.label_path).exists():
            image.status = "invalid"; errors.append(f"标签不存在: {image.image_name}"); continue
        if image.label_path:
            for line_number, line in enumerate(Path(image.label_path).read_text(encoding="utf-8").splitlines(), 1):
                try:
                    values = line.split()
                    if len(values) != 5:
                        raise ValueError
                    class_id = int(values[0]); coords = [float(value) for value in values[1:5]]
                    if not 0 <= class_id < len(scene_classes) or not all(0 <= value <= 1 for value in coords):
                        raise ValueError
                except (TypeError, ValueError):
                    image.status = "invalid"; errors.append(f"{image.image_name}:{line_number} 标注非法")
        if image.status != "invalid":
            image.status = "valid"
    project.status = "ready" if not errors and project.total_images else "failed"
    if project.status == "ready":
        scene = project.scene
        dataset_root = (Path(project.storage_path) / "yolo_dataset").resolve()
        data_yaml = {
            "path": str(dataset_root),
            "train": "images/train",
            "val": "images/val",
            "names": {index: name for index, name in enumerate(scene.class_names or [])},
        }
        if project.test_images:
            data_yaml["test"] = "images/test"
        (dataset_root / "data.yaml").write_text(
            yaml.safe_dump(data_yaml, allow_unicode=True, sort_keys=False), encoding="utf-8"
        )
    write_audit(db, user=current_user, module="dataset", action="validate", target_type="dataset", target_id=project.id, details={"errors": len(errors)}, request=request)
    db.commit()
    return {"project_id": project.id, "status": project.status, "valid": not errors, "errors": errors[:100]}


@router.delete("/{project_id}", summary="删除数据集项目")
async def delete_dataset(project_id: int, request: Request, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    project = _project(db, project_id, current_user); path = Path(project.storage_path) if project.storage_path else None
    db.delete(project)
    write_audit(db, user=current_user, module="dataset", action="delete", target_type="dataset", target_id=project_id, request=request)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="数据集已被训练任务引用，不能删除") from exc
    if path and path.exists():
        shutil.rmtree(path)
    return {"message": "数据集已删除", "project_id": project_id}
