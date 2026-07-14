from pathlib import Path
from types import SimpleNamespace

import yaml

from app.entity.schemas import ModelExportRequest, ModelValidateRequest, TrainingTaskCreate
from app.training.dataset_splitter import DatasetSplitter
from app.training.training_service import TrainingService
from main import app
from tools.verify_dataset import verify_dataset


def test_training_router_exposes_documented_ten_endpoints():
    routes = {
        (method, route.path)
        for route in app.routes
        if route.path.startswith("/api/training")
        for method in route.methods
    }
    assert routes == {
        ("POST", "/api/training/start"),
        ("GET", "/api/training/tasks"),
        ("GET", "/api/training/status/{task_id}"),
        ("GET", "/api/training/metrics/{task_id}"),
        ("POST", "/api/training/stop/{task_id}"),
        ("GET", "/api/training/results/{task_uuid}"),
        ("POST", "/api/training/validate/{task_id}"),
        ("POST", "/api/training/export/{task_id}"),
        ("GET", "/api/training/download/{task_id}"),
        ("POST", "/api/training/predict"),
    }


def test_training_schema_defaults_match_day07():
    assert TrainingTaskCreate(scene_id=1, epochs=5).epochs == 5
    assert ModelValidateRequest().model_dump() == {
        "split": "val",
        "conf": 0.001,
        "iou": 0.6,
    }
    assert ModelExportRequest().upload_minio is True
    assert TrainingService._model_checkpoint("yolov11n") == "yolo11n.pt"


def test_original_training_service_entrypoints_are_preserved():
    service = TrainingService()
    for name in (
        "create_task",
        "get_status",
        "list_tasks",
        "validate_model",
        "export_model",
        "get_model_path",
    ):
        assert hasattr(service, name)


def test_model_download_prefers_best_weight(tmp_path: Path, monkeypatch):
    weights = tmp_path / "weights"
    weights.mkdir()
    (weights / "best.pt").write_bytes(b"best")
    (weights / "last.pt").write_bytes(b"last-weight")
    monkeypatch.setattr(TrainingService, "_task_output_dir", lambda task_uuid: tmp_path)

    result = TrainingService.get_model_download_path(_download_database("a1b2c3d4"), 1)

    assert result == {
        "file_path": str(weights / "best.pt"),
        "filename": "best_a1b2c3d4.pt",
        "file_size": 4,
    }


def test_model_download_falls_back_to_last_weight(tmp_path: Path, monkeypatch):
    weights = tmp_path / "weights"
    weights.mkdir()
    (weights / "last.pt").write_bytes(b"last-weight")
    monkeypatch.setattr(TrainingService, "_task_output_dir", lambda task_uuid: tmp_path)

    result = TrainingService.get_model_download_path(_download_database("a1b2c3d4"), 1)

    assert result == {
        "file_path": str(weights / "last.pt"),
        "filename": "last_a1b2c3d4.pt",
        "file_size": 11,
    }


def test_model_download_reports_missing_weights(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(TrainingService, "_task_output_dir", lambda task_uuid: tmp_path)

    result = TrainingService.get_model_download_path(_download_database("a1b2c3d4"), 1)

    assert result == {"error": "模型权重文件不存在"}


def _download_database(task_uuid: str):
    class Query:
        def filter(self, *args):
            return self

        def first(self):
            return SimpleNamespace(task_uuid=task_uuid)

    class Database:
        def query(self, model):
            return Query()

    return Database()


def test_training_status_matches_documented_shape():
    task = SimpleNamespace(
        id=1,
        task_uuid="a1b2c3d4",
        status="running",
        model_name="yolov11n",
        epochs=5,
        current_epoch=2,
        progress=40,
        device="cpu",
    )
    metric = SimpleNamespace(
        epoch=2,
        box_loss=1.234,
        cls_loss=2.567,
        dfl_loss=1.0,
        precision=0.456,
        recall=0.4,
        map50=0.412,
        map50_95=0.2,
        lr=0.01,
    )

    class Query:
        def __init__(self, item):
            self.item = item

        def filter(self, *args):
            return self

        def order_by(self, *args):
            return self

        def first(self):
            return self.item

    class Database:
        def query(self, model):
            return Query(task if model.__name__ == "TrainingTask" else metric)

    service = TrainingService()
    service._running_tasks[1] = object()
    result = service.get_training_status(Database(), 1)
    assert set(result) == {"task", "latest_metric", "is_running"}
    assert result["task"] == {
        "id": 1,
        "task_uuid": "a1b2c3d4",
        "status": "running",
        "model_name": "yolov11n",
        "epochs": 5,
        "current_epoch": 2,
        "progress": 40,
        "device": "cpu",
    }
    assert result["latest_metric"]["epoch"] == 2
    assert result["is_running"] is True


def test_dataset_splitter_and_yaml_generation(tmp_path: Path):
    images = tmp_path / "raw_images"
    labels = tmp_path / "raw_labels"
    output = tmp_path / "dataset"
    images.mkdir()
    labels.mkdir()
    for index in range(10):
        (images / f"sample_{index}.jpg").write_bytes(b"image")
        if index != 9:
            (labels / f"sample_{index}.txt").write_text(
                "0 0.5 0.5 0.2 0.2\n", encoding="utf-8"
            )

    stats = DatasetSplitter.organize_dataset(
        images,
        labels,
        output,
        train_ratio=0.8,
        val_ratio=0.1,
        test_ratio=0.1,
        class_names=["defect"],
    )
    assert (stats["train"], stats["val"], stats["test"]) == (8, 1, 1)
    assert len(stats["missing_labels"]) == 1
    config = yaml.safe_load((output / "data.yaml").read_text(encoding="utf-8"))
    assert config["names"] == {0: "defect"}


def test_verify_dataset_supports_list_style_names(tmp_path: Path):
    for split in ("train", "val"):
        (tmp_path / "images" / split).mkdir(parents=True)
        (tmp_path / "labels" / split).mkdir(parents=True)
        (tmp_path / "images" / split / f"{split}.jpg").write_bytes(b"image")
        (tmp_path / "labels" / split / f"{split}.txt").write_text(
            "0 0.5 0.5 0.2 0.2\n", encoding="utf-8"
        )
    (tmp_path / "data.yaml").write_text("names:\n  - defect\n", encoding="utf-8")

    result = verify_dataset(tmp_path)
    assert result["class_names"] == {0: "defect"}
    assert result["total_images"] == 2
    assert result["total_annotations"] == 2
    assert result["has_warnings"] is False
