import zipfile
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from app.core.security import hash_password
from app.entity.db_models import (
    DetectionItem,
    DetectionScene,
    DetectionTask,
    ModelVersion,
    User,
)
from app.services.detection_service import DetectionService


class _ModelQuery:
    def __init__(self, rows):
        self.rows = list(rows)

    def filter(self, *criteria):
        # SQL expression evaluation is intentionally left to production SQLAlchemy;
        # these tests only exercise selector control flow and ordering.
        return self

    def order_by(self, *columns):
        self.rows.sort(key=lambda row: (not row.is_default, -row.id))
        return self

    def first(self):
        return self.rows[0] if self.rows else None


class _ModelDb:
    def __init__(self, rows):
        self.rows = rows

    def query(self, model):
        assert model is ModelVersion
        return _ModelQuery(self.rows)


def test_scene_model_selector_prefers_default_and_rejects_explicit_mismatch():
    latest = SimpleNamespace(id=2, scene_id=3, status="active", is_default=False)
    default = SimpleNamespace(id=1, scene_id=3, status="active", is_default=True)
    selected = DetectionService._select_model_version(_ModelDb([latest, default]), 3)
    assert selected.id == 1

    mismatch = SimpleNamespace(id=9, scene_id=4, status="active", is_default=True)
    with pytest.raises(ValueError, match="场景不匹配"):
        DetectionService._select_model_version(_ModelDb([mismatch]), 3, 9)


def test_invalid_zip_finishes_precreated_task_as_failed(tmp_path: Path, monkeypatch):
    archive = tmp_path / "empty.zip"
    with zipfile.ZipFile(archive, "w") as file:
        file.writestr("readme.txt", "not an image")
    failures = []
    service = DetectionService()
    monkeypatch.setattr(service, "_mark_task_failed", lambda task_id, message: failures.append((task_id, message)))

    result = service.detect_zip(str(archive), task_id=42)

    assert "error" in result
    assert failures == [(42, "ZIP 文件中没有找到图片")]


def test_video_open_failure_finishes_precreated_task(monkeypatch):
    service = DetectionService()
    failures = []
    monkeypatch.setattr(service, "_load_model", lambda db, scene_id, model_version_id=None: (object(), None))
    monkeypatch.setattr(service, "_mark_task_failed", lambda task_id, message: failures.append((task_id, message)))
    monkeypatch.setattr("app.services.detection_service.cv2.VideoCapture", lambda path: SimpleNamespace(isOpened=lambda: False, release=lambda: None))
    monkeypatch.setattr("app.services.detection_service.SessionLocal", lambda: SimpleNamespace(close=lambda: None))

    result = service.detect_video("broken.mp4", scene_id=1, task_id=8)

    assert "error" in result
    assert failures and failures[0][0] == 8


def test_detection_endpoints_expose_model_selection_and_async_progress(client):
    schema = client.get("/openapi.json").json()
    for path in ("/api/detection/single", "/api/detection/batch", "/api/detection/zip", "/api/detection/video"):
        request_body = schema["paths"][path]["post"]["requestBody"]["content"]
        media = next(iter(request_body.values()))
        reference = media["schema"]["$ref"].rsplit("/", 1)[-1]
        properties = schema["components"]["schemas"][reference]["properties"]
        assert "model_version_id" in properties
    status_schema = schema["paths"]["/api/detection/status/{task_id}"]["get"]
    assert status_schema["summary"]


def test_persisted_folder_inputs_still_upload_annotated_outputs(
    db_session, tmp_path: Path, monkeypatch
):
    module = __import__("app.services.detection_service", fromlist=["SessionLocal"])
    user = User(
        username="folder_output_owner",
        email="folder-output@example.com",
        hashed_password=hash_password("123456"),
    )
    db_session.add(user)
    db_session.flush()
    scene = DetectionScene(
        name="folder_output_scene",
        display_name="文件夹输出测试",
        category="industry",
        class_names=["defect"],
        created_by=user.id,
    )
    db_session.add(scene)
    db_session.flush()
    task = DetectionTask(
        user_id=user.id,
        scene_id=scene.id,
        task_type="folder",
        status="pending",
        total_images=1,
        conf_threshold=0.25,
        iou_threshold=0.45,
    )
    db_session.add(task)
    db_session.flush()
    item = DetectionItem(
        task_id=task.id,
        item_index=0,
        file_name="board.jpg",
        input_path=f"detections/{task.id}/input/00000_board.jpg",
        status="pending",
    )
    db_session.add(item)
    db_session.commit()
    task_id = task.id
    scene_id = scene.id
    user_id = user.id
    item_id = item.id

    image_path = tmp_path / "00000.jpg"
    image_path.write_bytes(b"local-placeholder")
    prediction = SimpleNamespace(
        boxes=[],
        speed={"inference": 2.5},
        plot=lambda: np.zeros((8, 8, 3), dtype=np.uint8),
    )

    class Model:
        names = {}

        def predict(self, **kwargs):
            return [prediction]

    uploaded = []

    class MinIO:
        def upload_file(self, *args, **kwargs):
            raise AssertionError("持久化输入不应重复上传")

        def upload_bytes(self, object_name, data, content_type):
            uploaded.append((object_name, content_type, len(data)))

    monkeypatch.setattr(module, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(module, "MinIOClient", MinIO)
    monkeypatch.setattr(
        DetectionService,
        "_load_model",
        staticmethod(lambda db, scene_id=None, model_version_id=None: (Model(), None)),
    )
    monkeypatch.setattr(
        module,
        "finalize_detection_task",
        lambda *args, **kwargs: SimpleNamespace(
            quality_conclusion="合格", risk_level=None, suggestion="正常流转"
        ),
    )

    result = DetectionService().detect_batch(
        [str(image_path)],
        scene_id=scene_id,
        user_id=user_id,
        mode="folder",
        task_id=task_id,
        inputs_persisted=True,
    )

    assert "error" not in result
    assert len(uploaded) == 1
    assert uploaded[0][0] == f"detections/{task_id}/output/00000_00000.jpg"
    assert uploaded[0][1] == "image/jpeg"
    assert uploaded[0][2] > 0
    db_session.expire_all()
    repaired_item = db_session.query(DetectionItem).filter(DetectionItem.id == item_id).first()
    assert repaired_item.result_path == f"detections/{task_id}/output/00000_00000.jpg"
