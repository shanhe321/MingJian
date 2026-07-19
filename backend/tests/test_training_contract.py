import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from pydantic import ValidationError

from app.entity.schemas import ModelExportRequest, ModelValidateRequest, TrainingTaskCreate
from app.training.dataset_splitter import DatasetSplitter
from app.training.training_service import TrainingService
from app.training import training_service as training_module
from main import app
from tools.verify_dataset import verify_dataset


def test_training_router_exposes_documented_ten_endpoints():
    routes = {
        (method, route.path)
        for route in app.routes
        if route.path.startswith("/api/training")
        for method in route.methods
    }
    assert {
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
    }.issubset(routes)


def test_training_schema_defaults_match_day07():
    training = TrainingTaskCreate(scene_id=1, epochs=5)
    assert training.epochs == 5
    assert training.device == "cpu"
    assert ModelValidateRequest().model_dump() == {
        "split": "val",
        "conf": 0.001,
        "iou": 0.6,
    }
    assert ModelExportRequest().upload_minio is True
    assert TrainingService._model_checkpoint("yolov11n") == "yolo11n.pt"


@pytest.mark.parametrize(
    ("schema", "kwargs"),
    [
        (TrainingTaskCreate, {"scene_id": 1, "img_size": 641}),
        (TrainingTaskCreate, {"scene_id": 1, "device": "cuda:all"}),
        (TrainingTaskCreate, {"scene_id": 1, "lr0": 0}),
        (TrainingTaskCreate, {"scene_id": 1, "model_name": "../best.pt"}),
        (ModelValidateRequest, {"split": "invalid"}),
        (ModelValidateRequest, {"conf": 1.1}),
        (ModelValidateRequest, {"iou": 0}),
    ],
)
def test_training_and_validation_parameters_reject_unsafe_values(schema, kwargs):
    with pytest.raises(ValidationError):
        schema(**kwargs)


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


def test_model_validation_uses_training_device(tmp_path: Path, monkeypatch):
    weights_path = tmp_path / "weights" / "best.pt"
    weights_path.parent.mkdir()
    weights_path.write_bytes(b"weights")
    data_yaml = tmp_path / "data.yaml"
    data_yaml.write_text("names: [defect]\n", encoding="utf-8")

    task = SimpleNamespace(
        id=1,
        task_uuid="a1b2c3d4",
        status="completed",
        data_yaml=str(data_yaml),
        dataset_path=str(tmp_path),
        img_size=640,
        device="0",
        scene_id=1,
        model_name="yolov11n",
    )
    scene = SimpleNamespace(id=1, name="defect")
    model_version = SimpleNamespace(
        id=2,
        version="v1.0.0",
        per_class_ap=None,
        precision=None,
        recall=None,
        map50=None,
        map50_95=None,
    )

    class Query:
        def __init__(self, item):
            self.item = item

        def filter(self, *args):
            return self

        def first(self):
            return self.item

    class Database:
        def query(self, model):
            items = {
                "TrainingTask": task,
                "DetectionScene": scene,
                "ModelVersion": model_version,
            }
            return Query(items[model.__name__])

        def commit(self):
            pass

        def refresh(self, item):
            pass

    captured = {}

    class YOLO:
        names = {0: "defect"}

        def __init__(self, path):
            captured["weights"] = path

        def val(self, **kwargs):
            captured.update(kwargs)
            box = SimpleNamespace(mp=0.9, mr=0.8, map50=0.85, map=0.6, ap=None)
            return SimpleNamespace(box=box)

    monkeypatch.setitem(sys.modules, "ultralytics", SimpleNamespace(YOLO=YOLO))
    monkeypatch.setattr(
        TrainingService,
        "_weights_path",
        classmethod(lambda cls, task_uuid: weights_path),
    )
    monkeypatch.setattr(
        TrainingService,
        "_task_output_dir",
        classmethod(lambda cls, task_uuid: tmp_path),
    )

    result = TrainingService.validate_model(Database(), task_id=1)

    assert "error" not in result
    assert captured["device"] == "0"
    assert captured["workers"] == 0


def test_model_validation_rejects_manual_run_during_postprocess(monkeypatch):
    monkeypatch.setattr(
        training_module.redis_client,
        "exists",
        lambda key: key == TrainingService._postprocess_key(9),
    )

    result = TrainingService.validate_model(object(), task_id=9)

    assert result == {
        "error": "模型正在执行训练后评估和产物整理，请等待当前后处理完成",
        "code": "evaluation_in_progress",
    }


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
        error_message=None,
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
    assert set(result) == {
        "task", "latest_metric", "is_running", "is_evaluating",
        "is_postprocessing", "failure_reason",
    }
    assert result["task"] == {
        "id": 1,
        "task_uuid": "a1b2c3d4",
        "status": "running",
        "model_name": "yolov11n",
        "epochs": 5,
        "current_epoch": 2,
        "progress": 40,
        "device": "cpu",
        "error_message": None,
    }
    assert result["latest_metric"]["epoch"] == 2
    assert result["is_running"] is True
    assert result["is_evaluating"] is False
    assert result["is_postprocessing"] is False
    assert result["failure_reason"] is None


def test_model_path_is_restored_from_minio_to_persistent_cache(tmp_path: Path, monkeypatch):
    model = SimpleNamespace(
        id=7,
        model_path=str(tmp_path / "missing.pt"),
        minio_url="models/scene_1/v1.0.0/best.pt",
    )

    class Client:
        def download_bytes(self, object_name):
            assert object_name == model.minio_url
            return b"real-weight"

    monkeypatch.setattr(training_module, "BACKEND_DIR", tmp_path)
    monkeypatch.setattr("app.storage.minio_client.MinIOClient", Client)

    restored = Path(TrainingService.resolve_model_path(model))
    assert restored.read_bytes() == b"real-weight"
    assert restored == tmp_path / "models" / "cache" / "model_7" / "best.pt"


def test_missing_evaluation_plots_are_reported_without_placeholder_creation(tmp_path: Path):
    (tmp_path / "PR_curve.png").write_bytes(b"real")
    status = TrainingService._artifact_inventory(tmp_path)
    assert status["available"] == ["PR_curve.png"]
    assert "confusion_matrix.png" in status["missing"]
    assert not (tmp_path / "confusion_matrix.png").exists()


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
