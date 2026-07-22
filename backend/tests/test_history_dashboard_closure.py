"""历史、报告和看板逻辑闭环测试。"""

from datetime import datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

from app.api.auth import get_current_user
from app.core.security import hash_password
from app.entity.db_models import (
    DetectionItem,
    DetectionReport,
    DetectionScene,
    DetectionTask,
    ModelVersion,
    User,
)
from app.services.dashboard_service import dashboard_service
from app.services.history_service import history_service, render_report_markdown
from app.services.quality_service import _refresh_snapshots, finalize_detection_task
from main import app


class _FakeMinIO:
    def upload_bytes(self, *_args, **_kwargs):
        return "/api/storage/uploaded"

    def get_presigned_url(self, object_name):
        return f"/api/storage/objects/{object_name}?signature=test"

    def object_exists(self, _object_name):
        return True


def _user_scene(db_session):
    token = uuid4().hex[:8]
    user = User(
        username=f"closure_{token}",
        email=f"closure_{token}@example.com",
        hashed_password=hash_password("123456"),
    )
    db_session.add(user)
    db_session.flush()
    scene = DetectionScene(
        name=f"closure_scene_{token}",
        display_name="PCB 闭环测试",
        category="pcb",
        class_names=["short"],
        is_active=True,
        created_by=user.id,
    )
    db_session.add(scene)
    db_session.flush()
    return user, scene


def test_failed_and_partial_tasks_are_never_reported_as_qualified(db_session, monkeypatch):
    import app.services.quality_service as quality_module

    monkeypatch.setattr(quality_module, "MinIOClient", _FakeMinIO)
    monkeypatch.setattr(quality_module, "_upsert_snapshot", lambda *_args, **_kwargs: None)
    user, scene = _user_scene(db_session)

    failed_task = DetectionTask(
        user_id=user.id,
        scene_id=scene.id,
        task_type="batch",
        status="failed",
        total_images=1,
        completed_at=datetime.now(),
    )
    db_session.add(failed_task)
    db_session.flush()
    db_session.add(
        DetectionItem(
            task_id=failed_task.id,
            item_index=0,
            file_name="broken.jpg",
            input_path="detections/broken.jpg",
            status="failed",
            error_message="图片损坏",
        )
    )
    db_session.flush()
    failed_report = finalize_detection_task(db_session, failed_task)
    assert failed_report.quality_conclusion == "检测失败"
    assert "不应据此判定 PCB 合格" in failed_report.suggestion

    partial_task = DetectionTask(
        user_id=user.id,
        scene_id=scene.id,
        task_type="batch",
        status="completed",
        total_images=2,
        completed_at=datetime.now(),
    )
    db_session.add(partial_task)
    db_session.flush()
    db_session.add_all(
        [
            DetectionItem(
                task_id=partial_task.id,
                item_index=0,
                file_name="ok.jpg",
                input_path="detections/ok.jpg",
                status="completed",
            ),
            DetectionItem(
                task_id=partial_task.id,
                item_index=1,
                file_name="broken.jpg",
                input_path="detections/partial-broken.jpg",
                status="failed",
                error_message="无法解码",
            ),
        ]
    )
    db_session.flush()
    partial_report = finalize_detection_task(db_session, partial_task)
    assert partial_report.quality_conclusion == "疑似缺陷"
    assert "结论仅覆盖成功项" in partial_report.risk_reason
    detail = {
        "task": {
            "id": partial_task.id,
            "user_id": user.id,
            "username": user.username,
            "task_type": "batch",
            "total_images": 2,
            "created_at": partial_task.created_at.isoformat(),
            "completed_at": partial_task.completed_at.isoformat(),
        },
        "model_version": None,
        "items": [
            {"file_name": "ok.jpg", "status": "completed", "defect_count": 0, "error_message": None},
            {"file_name": "broken.jpg", "status": "failed", "defect_count": 0, "error_message": "无法解码"},
        ],
        "results": [],
        "report": {
            "report_uuid": partial_report.report_uuid,
            "quality_conclusion": partial_report.quality_conclusion,
            "risk_level": partial_report.risk_level,
            "defect_count": 0,
            "defect_summary": {},
            "risk_reason": partial_report.risk_reason,
            "suggestion": partial_report.suggestion,
        },
    }
    markdown = render_report_markdown(detail).decode()
    assert "开始时间" in markdown
    assert "| 推理总耗时 | - ms | 失败项数 | 1 |" in markdown
    assert "### 4.2 broken.jpg" in markdown
    assert "检测失败原因：无法解码" in markdown


def test_rich_report_embeds_signed_original_and_annotated_images():
    detail = {
        "task": {
            "id": 8,
            "user_id": 1,
            "username": "tester",
            "task_type": "single",
            "status": "completed",
            "scene_name": "PCB 缺陷检测",
            "total_images": 1,
            "total_inference_time": 12.3,
            "conf_threshold": 0.25,
            "iou_threshold": 0.45,
        },
        "model_version": {"model_name": "pcb-yolo", "version": "v1.0.0"},
        "items": [{
            "id": 11,
            "file_name": "[1]_board.jpg",
            "input_path": "detections/8/input/board.jpg",
            "input_url": "/api/storage/objects/input?expires=1&signature=a",
            "result_url": "/api/storage/objects/result?expires=1&signature=b",
            "status": "completed",
            "defect_count": 1,
            "average_confidence": 0.91,
            "inference_time": 12.3,
        }],
        "results": [{
            "item_id": 11,
            "class_name": "short",
            "class_name_cn": "短路",
            "confidence": 0.91,
            "bbox": [1, 2, 30, 40],
            "inference_time": 12.3,
        }],
        "report": {
            "report_uuid": "report-8",
            "quality_conclusion": "不合格",
            "risk_level": "high",
            "defect_count": 1,
            "defect_summary": {"短路": 1},
            "risk_reason": "检测到高风险缺陷：短路",
            "suggestion": "立即隔离并复核",
        },
    }

    markdown = render_report_markdown(detail, "https://pcb.example.com").decode()

    assert "![原始图像 1](https://pcb.example.com/api/storage/objects/input?expires=1&signature=a)" in markdown
    assert "![检测标注图 1](https://pcb.example.com/api/storage/objects/result?expires=1&signature=b)" in markdown
    assert "[在新窗口打开检测标注图](https://pcb.example.com/api/storage/objects/result?expires=1&signature=b)" in markdown
    assert "| # | 类别 | 类别代码 | 置信度 | 置信度等级 | 位置 | 面积占比 | 复核优先级 | 边界框 x1,y1,x2,y2 | 推理耗时 |" in markdown
    assert "| 1 | 短路 | short | 91.00% | 较高 | 未记录 | - | 高 | 1.0, 2.0, 30.0, 40.0 | 12.30 ms |" in markdown


def test_history_detail_returns_model_and_same_origin_urls_for_clean_items(db_session, monkeypatch):
    import app.services.history_service as history_module

    monkeypatch.setattr(history_module, "MinIOClient", _FakeMinIO)
    monkeypatch.setattr(history_module, "SessionLocal", lambda: db_session)
    user, scene = _user_scene(db_session)
    model = ModelVersion(
        scene_id=scene.id,
        version="v1.2.3",
        model_name="pcb-best",
        model_type="yolo11n",
        model_path="models/pcb.pt",
    )
    db_session.add(model)
    db_session.flush()
    task = DetectionTask(
        user_id=user.id,
        scene_id=scene.id,
        model_version_id=model.id,
        task_type="single",
        status="completed",
        input_path="detections/1/input/clean.jpg",
        result_path="detections/1/output/clean.jpg",
        total_images=1,
        completed_at=datetime.now(),
    )
    db_session.add(task)
    db_session.flush()
    db_session.add_all(
        [
            DetectionItem(
                task_id=task.id,
                item_index=0,
                file_name="clean.jpg",
                input_path="detections/1/input/clean.jpg",
                result_path="detections/1/output/clean.jpg",
                status="completed",
                defect_count=0,
            ),
            DetectionReport(
                task_id=task.id,
                report_uuid=str(uuid4()),
                quality_conclusion="合格",
                defect_count=0,
                report_path=f"reports/{user.id}/{task.id}/report.md",
            ),
        ]
    )
    video_task = DetectionTask(
        user_id=user.id,
        scene_id=scene.id,
        model_version_id=model.id,
        task_type="video",
        status="completed",
        total_images=3,
        completed_at=datetime.now(),
    )
    db_session.add(video_task)
    db_session.commit()
    user_id = user.id
    task_id = task.id
    video_task_id = video_task.id

    detail = history_service.get_task_detail(user_id, task_id)
    assert detail["model_version"]["version"] == "v1.2.3"
    assert detail["task"]["input_url"].startswith("/api/storage/")
    assert detail["task"]["result_url"].startswith("/api/storage/")
    assert detail["items"][0]["result_url"].startswith("/api/storage/")
    assert detail["report"]["report_url"].startswith("/api/storage/")
    assert detail["results"] == []
    video_detail = history_service.get_task_detail(user_id, video_task_id)
    assert video_detail["task"]["result_path"] == f"detections/{video_task_id}/annotated_video.mp4"
    assert video_detail["task"]["annotated_video_url"].startswith("/api/storage/")


def test_camera_session_contributes_to_dashboard_denominator(db_session, monkeypatch):
    import app.services.dashboard_service as dashboard_module

    monkeypatch.setattr(dashboard_module, "SessionLocal", lambda: db_session)
    user, scene = _user_scene(db_session)
    camera = DetectionTask(
        user_id=user.id,
        scene_id=scene.id,
        task_type="camera",
        status="completed",
        total_images=25,
        total_objects=0,
        created_at=datetime.now(),
        completed_at=datetime.now(),
    )
    defective = DetectionTask(
        user_id=user.id,
        scene_id=scene.id,
        task_type="single",
        status="completed",
        total_images=1,
        total_objects=1,
        created_at=datetime.now(),
        completed_at=datetime.now(),
    )
    db_session.add_all([camera, defective])
    db_session.flush()
    db_session.add(
        DetectionItem(
            task_id=defective.id,
            item_index=0,
            file_name="defect.jpg",
            status="completed",
            defect_count=1,
        )
    )
    db_session.commit()

    overview = dashboard_service.get_overview(user.id, 30)
    assert overview["qualified_pcbs"] == 1
    assert overview["defective_pcbs"] == 1
    assert overview["pass_rate"] == 50.0
    assert overview["total_items"] == 26


def test_all_dashboard_endpoints_enforce_global_admin_scope(client, monkeypatch):
    ordinary = SimpleNamespace(id=31, is_superuser=False, user_roles=[])
    app.dependency_overrides[get_current_user] = lambda: ordinary
    try:
        for path in ["statistics", "trend", "class-dist", "scene-dist", "type-dist"]:
            assert client.get(f"/api/dashboard/{path}?scope=global").status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    calls = []
    for method_name in [
        "get_statistics",
        "get_trend",
        "get_class_distribution",
        "get_scene_distribution",
        "get_type_distribution",
    ]:
        monkeypatch.setattr(
            dashboard_service,
            method_name,
            lambda user_id, days, name=method_name: calls.append((name, user_id, days)) or {},
        )
    admin = SimpleNamespace(id=1, is_superuser=True, user_roles=[])
    app.dependency_overrides[get_current_user] = lambda: admin
    try:
        for path in ["statistics", "trend", "class-dist", "scene-dist", "type-dist"]:
            assert client.get(f"/api/dashboard/{path}?scope=global&days=7").status_code == 200
    finally:
        app.dependency_overrides.pop(get_current_user, None)
    assert len(calls) == 5
    assert all(user_id is None and days == 7 for _, user_id, days in calls)


def test_redetect_rejects_stream_media_instead_of_silently_using_batch(client, monkeypatch):
    monkeypatch.setattr(
        history_service,
        "get_task_detail",
        lambda _user_id, task_id: {"task": {"id": task_id, "task_type": "video"}, "items": []},
    )
    current_user = SimpleNamespace(id=3, username="tester", is_superuser=False, user_roles=[])
    app.dependency_overrides[get_current_user] = lambda: current_user
    try:
        response = client.post("/api/history/tasks/5/redetect")
    finally:
        app.dependency_overrides.pop(get_current_user, None)
    assert response.status_code == 409
    assert "不支持直接重新检测" in response.json()["message"]


def test_snapshot_backfill_builds_four_dimensions_for_every_date(db_session, monkeypatch):
    import app.services.quality_service as quality_module

    task1 = SimpleNamespace(user_id=1, scene_id=10, created_at=datetime.now() - timedelta(days=7))
    task2 = SimpleNamespace(user_id=1, scene_id=10, created_at=datetime.now() - timedelta(days=2))
    calls = []
    monkeypatch.setattr(
        quality_module,
        "_upsert_snapshot",
        lambda _db, _task, user_id, scene_id, day=None: calls.append((day, user_id, scene_id)),
    )
    assert _refresh_snapshots(db_session, [task1, task2]) == 8
    assert len(calls) == 8
    assert {day for day, _, _ in calls} == {task1.created_at.date(), task2.created_at.date()}
    assert {(user_id, scene_id) for _, user_id, scene_id in calls} == {
        (1, 10), (1, None), (None, 10), (None, None)
    }
