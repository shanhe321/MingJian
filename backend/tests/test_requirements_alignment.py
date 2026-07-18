"""需求对齐新增能力的回归测试。"""

import io
import zipfile
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import ForeignKeyConstraint

from app.api.datasets import _safe_extract
from app.core.security import create_access_token, decode_access_token
from app.entity.db_models import (
    DashboardSnapshot,
    DetectionItem,
    DetectionReport,
    DetectionResult,
    DetectionScene,
    DetectionTask,
    Role,
    User,
)
from app.services.quality_service import PCB_CLASS_NAMES_CN, _upsert_snapshot, evaluate_quality
from app.services.user_service import user_service
from main import app
from app.storage.redis_client import redis_client


def _result(name: str, confidence: float = 0.9):
    return SimpleNamespace(class_name=name, confidence=confidence)


@pytest.mark.parametrize("name", ["short", "open_circuit", "missing_hole"])
def test_high_risk_quality_rules(name):
    result = evaluate_quality([_result(name)])
    assert result["risk_level"] == "high"
    assert result["quality_conclusion"] == "不合格"


def test_medium_low_and_no_defect_quality_rules():
    assert evaluate_quality([])["quality_conclusion"] == "合格"
    assert evaluate_quality([])["risk_level"] is None
    assert evaluate_quality([_result("mouse_bite")])["risk_level"] == "medium"
    assert evaluate_quality([_result("spur", 0.4)])["risk_level"] == "low"
    assert set(PCB_CLASS_NAMES_CN) == {
        "missing_hole", "mouse_bite", "open_circuit", "short", "spur", "spurious_copper"
    }


def test_detection_item_result_composite_relationship_and_report_uniqueness():
    assert "detection_items" in DetectionItem.metadata.tables
    foreign_keys = [
        constraint for constraint in DetectionResult.__table__.constraints
        if isinstance(constraint, ForeignKeyConstraint)
    ]
    assert any(
        [column.name for column in constraint.columns] == ["item_id", "task_id"]
        and constraint.ondelete == "CASCADE"
        for constraint in foreign_keys
    )
    assert DetectionTask.__table__.c.input_path is not None
    assert DetectionTask.__table__.c.result_path is not None
    assert any(constraint.name == "uq_detection_reports_task" for constraint in DetectionReport.__table__.constraints)
    assert any(index.name == "ix_dashboard_snapshots_date_scene_user" for index in DashboardSnapshot.__table__.indexes)
    task_type_constraint = next(
        constraint for constraint in DetectionTask.__table__.constraints
        if constraint.name == "ck_detection_tasks_task_type"
    )
    assert "'zip'" in str(task_type_constraint.sqltext)


def test_jwt_contains_unique_revocation_id():
    first = decode_access_token(create_access_token({"sub": "1"}))
    second = decode_access_token(create_access_token({"sub": "1"}))
    assert first["jti"] != second["jti"]
    assert "exp" in first and "iat" in first


def test_logout_revokes_current_token(client):
    username = "logout_alignment_user"
    client.post("/api/auth/register", json={
        "username": username, "email": "logout-alignment@example.com", "password": "secret123"
    })
    login = client.post("/api/auth/login", json={"username": username, "password": "secret123"})
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert client.post("/api/auth/logout", headers=headers).status_code == 200
    assert client.get("/api/auth/me", headers=headers).status_code == 401


def test_only_user_and_admin_roles_and_last_admin_guard(db_session):
    user = user_service.register(db_session, "role_guard_user", "role-guard@example.com", "secret123")
    user_service.set_user_roles(db_session, user.id, ["admin"])
    with pytest.raises(HTTPException) as exc:
        user_service.set_user_roles(db_session, user.id, ["user"])
    assert exc.value.status_code == 409
    assert {role.name for role in db_session.query(Role).all()}.issubset({"user", "admin"})


def test_zip_path_traversal_is_rejected(tmp_path):
    archive_bytes = io.BytesIO()
    with zipfile.ZipFile(archive_bytes, "w") as archive:
        archive.writestr("../escape.jpg", b"unsafe")
    with zipfile.ZipFile(io.BytesIO(archive_bytes.getvalue())) as archive:
        with pytest.raises(HTTPException) as exc:
            _safe_extract(archive, tmp_path / "extract")
    assert exc.value.status_code == 400


def test_new_public_routes_are_registered():
    paths = {route.path for route in app.routes}
    assert {
        "/api/auth/logout", "/api/user/{user_id}/roles", "/api/dashboard/overview",
        "/api/datasets/{project_id}/import", "/api/history/tasks/{task_id}/redetect",
        "/api/history/tasks/{task_id}/report.md", "/api/training/models/{model_id}/default",
        "/api/audit/logs", "/api/chat/sessions/{session_id}",
        "/api/scenes", "/api/storage/objects/{object_name:path}",
    }.issubset(paths)


def test_video_progress_checks_task_owner_before_redis(client, db_session, monkeypatch):
    for suffix in ("owner", "other"):
        client.post("/api/auth/register", json={
            "username": f"video_progress_{suffix}",
            "email": f"video-progress-{suffix}@example.com",
            "password": "secret123",
        })
    owner = db_session.query(User).filter(User.username == "video_progress_owner").first()
    scene = DetectionScene(
        name="video_progress_scene",
        display_name="视频进度权限场景",
        category="industry",
        class_names=["short"],
    )
    db_session.add(scene); db_session.flush()
    task = DetectionTask(
        user_id=owner.id,
        scene_id=scene.id,
        task_type="video",
        status="processing",
    )
    db_session.add(task); db_session.commit()
    monkeypatch.setattr("app.api.detection.SessionLocal", lambda: db_session)
    redis_client.set_json(
        f"video_task:{task.id}",
        {"status": "processing", "progress": 50},
        expire=60,
    )
    try:
        login = client.post("/api/auth/login", json={
            "username": "video_progress_other",
            "password": "secret123",
        })
        response = client.get(
            f"/api/detection/video/status/{task.id}",
            headers={"Authorization": f"Bearer {login.json()['access_token']}"},
        )
        assert response.status_code == 403
    finally:
        redis_client.delete(f"video_task:{task.id}")


def test_snapshot_upsert_is_idempotent_with_autoflush_disabled(db_session):
    user = User(
        username="snapshot_upsert_user",
        email="snapshot-upsert@example.com",
        hashed_password="unused",
    )
    scene = DetectionScene(
        name="snapshot_upsert_scene",
        display_name="快照测试场景",
        category="industry",
        class_names=["short"],
    )
    db_session.add_all([user, scene]); db_session.flush()
    tasks = []
    for index in range(2):
        task = DetectionTask(
            user_id=user.id, scene_id=scene.id, task_type="single",
            status="completed", created_at=datetime.now(),
        )
        db_session.add(task); db_session.flush()
        db_session.add(DetectionItem(
            task_id=task.id, item_index=0, file_name=f"{index}.jpg",
            status="completed", defect_count=index,
        ))
        tasks.append(task)
    db_session.flush()

    _upsert_snapshot(db_session, tasks[0], user.id, None)
    _upsert_snapshot(db_session, tasks[1], user.id, None)
    db_session.commit()

    rows = db_session.query(DashboardSnapshot).filter(
        DashboardSnapshot.user_id == user.id,
        DashboardSnapshot.scene_id.is_(None),
    ).all()
    assert len(rows) == 1
    assert rows[0].total_tasks == 2
