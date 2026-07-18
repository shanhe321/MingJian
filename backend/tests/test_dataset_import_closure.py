import io
import json
import zipfile
from uuid import uuid4

import pytest
from PIL import Image

from app.api.auth import get_current_user
from app.config.settings import settings
from app.entity.db_models import DetectionScene, User
from main import app


def _image_bytes() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (20, 10), "white").save(output, format="JPEG")
    return output.getvalue()


def _archive(dataset_format: str) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name in ("a", "b"):
            archive.writestr(f"images/{name}.jpg", _image_bytes())
        if dataset_format == "yolo":
            archive.writestr("labels/a.txt", "0 0.5 0.5 0.4 0.4\n")
            archive.writestr("labels/b.txt", "0 0.5 0.5 0.2 0.2\n")
        elif dataset_format == "voc":
            xml = """<annotation><size><width>20</width><height>10</height></size>
            <object><name>short</name><bndbox><xmin>2</xmin><ymin>1</ymin>
            <xmax>10</xmax><ymax>8</ymax></bndbox></object></annotation>"""
            archive.writestr("annotations/a.xml", xml)
            archive.writestr("annotations/b.xml", xml)
        elif dataset_format == "coco":
            archive.writestr(
                "annotations.json",
                json.dumps(
                    {
                        "images": [
                            {"id": 1, "file_name": "a.jpg", "width": 20, "height": 10},
                            {"id": 2, "file_name": "b.jpg", "width": 20, "height": 10},
                        ],
                        "categories": [{"id": 1, "name": "short"}],
                        "annotations": [
                            {"id": 1, "image_id": 1, "category_id": 1, "bbox": [2, 1, 8, 7]},
                            {"id": 2, "image_id": 2, "category_id": 1, "bbox": [3, 2, 5, 5]},
                        ],
                    }
                ),
            )
        else:
            for name in ("a", "b"):
                archive.writestr(
                    f"labels/{name}.json",
                    json.dumps(
                        {
                            "imageWidth": 20,
                            "imageHeight": 10,
                            "shapes": [
                                {"label": "short", "points": [[2, 1], [10, 8]]}
                            ],
                        }
                    ),
                )
    return output.getvalue()


@pytest.mark.parametrize("dataset_format", ["yolo", "voc", "coco", "labelme"])
def test_four_dataset_formats_reach_ready_and_persist_annotations(
    dataset_format, tmp_path, monkeypatch, client, db_session
):
    suffix = uuid4().hex[:8]
    user = User(
        username=f"dataset_{suffix}",
        email=f"dataset-{suffix}@example.com",
        hashed_password="x",
        is_active=True,
    )
    scene = DetectionScene(
        name=f"dataset_scene_{suffix}",
        display_name="数据集测试场景",
        category="industry",
        class_names=["short"],
        class_names_cn={"short": "短路"},
        is_active=True,
    )
    db_session.add_all([user, scene])
    db_session.commit()
    db_session.refresh(user)
    db_session.refresh(scene)
    monkeypatch.setattr(settings, "DATASET_BASE_DIR", str(tmp_path / "datasets"))
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        created = client.post(
            "/api/datasets",
            data={"name": f"dataset_{dataset_format}_{suffix}", "scene_id": str(scene.id)},
        )
        assert created.status_code == 201, created.text
        project_id = created.json()["id"]
        imported = client.post(
            f"/api/datasets/{project_id}/import",
            data={"format": dataset_format},
            files={"file": ("dataset.zip", _archive(dataset_format), "application/zip")},
        )
        assert imported.status_code == 200, imported.text
        validated = client.post(f"/api/datasets/{project_id}/validate")
        assert validated.status_code == 200, validated.text
        assert validated.json()["status"] == "ready"

        detail = client.get(f"/api/datasets/{project_id}").json()
        assert detail["total_images"] == 2
        assert sum(len(image["annotations"]) for image in detail["images"]) == 2
        assert all(image["label_path"] for image in detail["images"])
    finally:
        app.dependency_overrides.pop(get_current_user, None)
