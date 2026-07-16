import base64
import importlib
import zipfile
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from app.agent.detection_agent import DETECTION_TOOLS, detection_agent
from app.api.auth import get_current_user
from app.config.settings import Settings
from app.services.detection_service import DetectionService, detection_service
from main import app


def test_chat_and_detection_routes_match_guide():
    routes = {
        (method, route.path)
        for route in app.routes
        if route.path.startswith("/api/chat")
        or route.path.startswith("/api/detection")
        for method in getattr(route, "methods", set())
    }
    assert routes == {
        ("POST", "/api/chat/upload"),
        ("POST", "/api/chat/stream"),
        ("POST", "/api/detection/single"),
        ("POST", "/api/detection/batch"),
        ("POST", "/api/detection/zip"),
        ("POST", "/api/detection/video"),
        ("GET", "/api/detection/status/{task_id}"),
        ("GET", "/api/detection/video/status/{task_id}"),
    }
    websocket_routes = {
        route.path for route in app.routes if route.__class__.__name__ == "APIWebSocketRoute"
    }
    assert "/api/detection/camera" in websocket_routes


def test_detection_agent_binds_documented_tools():
    assert {tool.name for tool in DETECTION_TOOLS} == {
        "detect_single_image",
        "detect_batch_images",
        "detect_zip_images_file",
        "detect_video_file",
    }
    assert detection_agent.executor.max_iterations == 5


def test_llm_settings_match_guide_defaults():
    assert Settings.model_fields["OPENAI_MODEL"].default == "gpt-4o-mini"
    assert Settings.model_fields["OPENAI_BASE_URL"].default == (
        "https://api.openai.com/v1"
    )
    assert Settings.model_fields["QWEN_MODEL"].default == "qwen-plus"
    assert Settings.model_fields["QWEN_BASE_URL"].default == (
        "https://dashscope.aliyuncs.com/compatible-mode/v1"
    )
    assert Settings.model_fields["OLLAMA_MODEL"].default == "qwen2.5:7b"


def test_detect_single_returns_annotations_and_statistics(monkeypatch):
    service_module = importlib.import_module("app.services.detection_service")

    class Database:
        closed = False

        def close(self):
            self.closed = True

    database = Database()
    box = SimpleNamespace(
        cls=[0],
        conf=[0.91234],
        xyxy=[np.array([1.0, 2.0, 30.0, 40.0])],
    )
    prediction = SimpleNamespace(
        boxes=[box],
        speed={"inference": 12.345},
        plot=lambda: np.zeros((8, 8, 3), dtype=np.uint8),
    )

    class Model:
        names = {0: "defect"}

        def predict(self, **kwargs):
            assert kwargs["conf"] == 0.3
            assert kwargs["iou"] == 0.5
            return [prediction]

    monkeypatch.setattr(service_module, "SessionLocal", lambda: database)
    monkeypatch.setattr(
        DetectionService,
        "_get_model",
        staticmethod(lambda scene_id=None: Model()),
    )

    result = DetectionService().detect_single(
        "sample.jpg",
        conf=0.3,
        iou=0.5,
    )

    assert result["total_objects"] == 1
    assert result["class_counts"] == {"defect": 1}
    assert result["detections"] == [
        {
            "class_name": "defect",
            "class_id": 0,
            "confidence": 0.9123,
            "bbox": [1.0, 2.0, 30.0, 40.0],
        }
    ]
    assert base64.b64decode(result["annotated_image_base64"])
    assert result["inference_time"] == 12.35
    assert result["task_id"] is None
    assert database.closed is True


def test_detect_single_uses_default_scene_for_history(monkeypatch):
    service_module = importlib.import_module("app.services.detection_service")
    captured = {}

    class Query:
        def first(self):
            return SimpleNamespace(id=4)

    class Database:
        closed = False

        def query(self, model):
            return Query()

        def close(self):
            self.closed = True

    database = Database()
    prediction = SimpleNamespace(
        boxes=[],
        speed={"inference": 2.0},
        plot=lambda: np.zeros((8, 8, 3), dtype=np.uint8),
    )

    class Model:
        names = {}

        def predict(self, **kwargs):
            return [prediction]

    def fake_get_model(scene_id=None):
        captured["model_scene_id"] = scene_id
        return Model()

    def fake_save(**kwargs):
        captured.update(kwargs)
        return {"task_id": 15, "annotated_image_url": "http://minio/result.jpg"}

    monkeypatch.setattr(service_module, "SessionLocal", lambda: database)
    monkeypatch.setattr(DetectionService, "_get_model", staticmethod(fake_get_model))
    monkeypatch.setattr(DetectionService, "_save_task_and_results", staticmethod(fake_save))

    result = DetectionService().detect_single("sample.jpg", user_id=7)

    assert captured["model_scene_id"] == 4
    assert captured["scene_id"] == 4
    assert captured["user_id"] == 7
    assert result["task_id"] == 15
    assert database.closed is True


def test_detect_batch_returns_aggregate_results(monkeypatch):
    service_module = importlib.import_module("app.services.detection_service")

    class Query:
        def first(self):
            return SimpleNamespace(id=3)

    class Database:
        def __init__(self):
            self.added = []
            self.closed = False

        def query(self, model):
            return Query()

        def add(self, item):
            self.added.append(item)

        def flush(self):
            self.added[0].id = 12

        def commit(self):
            pass

        def close(self):
            self.closed = True

    database = Database()
    box = SimpleNamespace(
        cls=[0],
        conf=[0.8],
        xyxy=[np.array([1.0, 2.0, 10.0, 20.0])],
    )
    prediction = SimpleNamespace(
        boxes=[box],
        speed={"inference": 5.0},
        plot=lambda: np.zeros((8, 8, 3), dtype=np.uint8),
    )

    class Model:
        names = {0: "defect"}

        def predict(self, **kwargs):
            return [prediction]

    monkeypatch.setattr(service_module, "SessionLocal", lambda: database)
    monkeypatch.setattr(
        DetectionService,
        "_get_model",
        staticmethod(lambda scene_id=None: Model()),
    )

    result = DetectionService().detect_batch(
        ["one.jpg", "two.jpg"],
        conf=0.3,
        user_id=7,
    )

    assert result["task_id"] == 12
    assert result["total_images"] == 2
    assert result["total_objects"] == 2
    assert result["class_counts"] == {"defect": 2}
    assert result["total_inference_time"] == 10.0
    assert len(result["detections"]) == 2
    assert len(result["annotated_images"]) == 2
    assert database.added[0].scene_id == 3
    assert database.added[0].status == "completed"
    assert database.closed is True


def test_detect_zip_filters_images_and_returns_batch_metadata(tmp_path: Path, monkeypatch):
    zip_path = tmp_path / "images.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("one.jpg", b"image-one")
        archive.writestr("nested/two.png", b"image-two")
        archive.writestr("notes.txt", b"ignored")

    captured_paths = []

    def fake_detect_batch(image_paths, conf, scene_id, user_id):
        captured_paths.extend(image_paths)
        assert all(Path(path).exists() for path in image_paths)
        return {"total_images": len(image_paths), "total_objects": 0}

    service = DetectionService()
    monkeypatch.setattr(service, "detect_batch", fake_detect_batch)

    result = service.detect_zip(
        str(zip_path),
        conf=0.3,
        scene_id=2,
        user_id=7,
    )

    assert {Path(path).suffix for path in captured_paths} == {".jpg", ".png"}
    assert result == {
        "total_images": 2,
        "total_objects": 0,
        "source": "zip",
        "zip_filename": "images.zip",
        "total_images_in_zip": 2,
    }
    assert all(not Path(path).exists() for path in captured_paths)


def test_detect_video_returns_sampled_results(tmp_path: Path, monkeypatch):
    service_module = importlib.import_module("app.services.detection_service")
    task = SimpleNamespace(
        id=12,
        status="processing",
        total_images=0,
        total_objects=0,
        total_inference_time=0,
        completed_at=None,
        error_message=None,
    )

    class Query:
        def filter(self, *args):
            return self

        def first(self):
            return task

    class Database:
        closed = False

        def query(self, model):
            return Query()

        def add(self, item):
            pass

        def commit(self):
            pass

        def close(self):
            self.closed = True

    database = Database()
    frames = [
        np.zeros((8, 8, 3), dtype=np.uint8),
        np.full((8, 8, 3), 255, dtype=np.uint8),
    ]

    class Capture:
        released = False

        def isOpened(self):
            return True

        def get(self, prop):
            values = {
                service_module.cv2.CAP_PROP_FRAME_COUNT: 2,
                service_module.cv2.CAP_PROP_FPS: 2.0,
                service_module.cv2.CAP_PROP_FRAME_WIDTH: 8,
                service_module.cv2.CAP_PROP_FRAME_HEIGHT: 8,
            }
            return values[prop]

        def read(self):
            return (True, frames.pop(0)) if frames else (False, None)

        def release(self):
            self.released = True

    class Writer:
        def write(self, frame):
            pass

        def release(self):
            pass

    prediction = SimpleNamespace(boxes=[], speed={"inference": 4.0})

    class Model:
        names = {0: "defect"}

        def predict(self, **kwargs):
            return [prediction]

    class MinIO:
        def upload_file(self, object_name, file_path):
            assert object_name == "detections/12/annotated_video.mp4"
            assert Path(file_path).exists()
            return "http://minio/annotated_video.mp4"

    def fake_run(command, **kwargs):
        Path(command[-1]).write_bytes(b"h264")

    monkeypatch.setattr(service_module, "SessionLocal", lambda: database)
    monkeypatch.setattr(service_module.cv2, "VideoCapture", lambda path: Capture())
    monkeypatch.setattr(service_module.cv2, "VideoWriter", lambda *args: Writer())
    monkeypatch.setattr(service_module.cv2, "VideoWriter_fourcc", lambda *args: 0)
    monkeypatch.setattr(service_module, "MinIOClient", MinIO)
    monkeypatch.setattr(service_module.subprocess, "run", fake_run)
    monkeypatch.setattr(service_module.shutil, "which", lambda name: "ffmpeg")
    monkeypatch.setattr(
        DetectionService,
        "_get_model",
        staticmethod(lambda scene_id=None: Model()),
    )

    result = DetectionService().detect_video(
        str(tmp_path / "video.mp4"),
        frame_sample_rate=1,
        max_frames=2,
        task_id=12,
    )

    assert result["processed_frames"] == 2
    assert result["total_frames"] == 2
    assert result["fps"] == 2.0
    assert result["annotated_video_url"] == "http://minio/annotated_video.mp4"
    assert task.status == "completed"
    assert database.closed is True


def test_single_detection_api_uses_uploaded_file(client, monkeypatch):
    captured = {}

    def fake_detect_single(**kwargs):
        captured.update(kwargs)
        assert Path(kwargs["image_path"]).exists()
        return {"total_objects": 0, "detections": []}

    monkeypatch.setattr(detection_service, "detect_single", fake_detect_single)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=9)
    try:
        response = client.post(
            "/api/detection/single",
            files={"file": ("sample.jpg", b"image", "image/jpeg")},
            data={"conf": "0.4", "scene_id": "3"},
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    assert response.json() == {
        "total_objects": 0,
        "detections": [],
        "filename": "sample.jpg",
    }
    assert captured["conf"] == 0.4
    assert captured["scene_id"] == 3
    assert captured["user_id"] == 9
    assert not Path(captured["image_path"]).exists()


def test_chat_stream_returns_sse_events(client, monkeypatch):
    async def fake_chat_stream(message, image_path):
        assert message == "你好"
        assert image_path is None
        yield {"type": "text_chunk", "content": "你好"}

    monkeypatch.setattr(detection_agent, "chat_stream", fake_chat_stream)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=9,
        username="tester",
    )
    try:
        response = client.post("/api/chat/stream", json={"message": "你好"})
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert 'data: {"type": "text_chunk", "content": "你好"}\n\n' in response.text
    assert response.text.endswith("data: [DONE]\n\n")


def test_camera_websocket_processes_frame(client, monkeypatch):
    prediction = SimpleNamespace(
        boxes=[],
        speed={"inference": 5.0},
        plot=lambda: np.zeros((8, 8, 3), dtype=np.uint8),
    )

    class Model:
        names = {0: "defect"}

        def predict(self, **kwargs):
            return [prediction]

    monkeypatch.setattr(detection_service, "_get_model", lambda scene_id=None: Model())
    _, image_buffer = importlib.import_module("cv2").imencode(
        ".jpg",
        np.zeros((8, 8, 3), dtype=np.uint8),
    )
    frame_base64 = base64.b64encode(image_buffer).decode("utf-8")

    with client.websocket_connect("/api/detection/camera") as websocket:
        websocket.send_json({"type": "config", "mode": "cpu", "conf": 0.25})
        config = websocket.receive_json()
        assert config["type"] == "config_ok"

        websocket.send_json({"type": "frame", "data": frame_base64})
        result = websocket.receive_json()
        assert result["type"] == "result"
        assert result["object_count"] == 0
        assert result["inference_time"] == 5.0
        assert base64.b64decode(result["annotated_frame"])
        websocket.send_json({"type": "close"})
