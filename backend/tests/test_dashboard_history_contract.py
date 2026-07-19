"""数据看板、历史记录和用户设置的讲义契约测试。"""

from datetime import datetime
from types import SimpleNamespace

from app.api.auth import get_current_user
from app.core.security import hash_password
from app.entity.db_models import DetectionResult, DetectionScene, DetectionTask, User
from app.services.dashboard_service import dashboard_service
from app.services.history_service import history_service
from app.services.user_service import user_service
from main import app


def test_dashboard_history_and_user_routes_match_guide():
    prefixes = ("/api/dashboard", "/api/history", "/api/user")
    routes = {
        (method, route.path)
        for route in app.routes
        if route.path.startswith(prefixes)
        for method in getattr(route, "methods", set())
    }
    assert {
        ("GET", "/api/dashboard/statistics"),
        ("GET", "/api/dashboard/trend"),
        ("GET", "/api/dashboard/class-dist"),
        ("GET", "/api/dashboard/scene-dist"),
        ("GET", "/api/dashboard/type-dist"),
        ("GET", "/api/history/tasks"),
        ("GET", "/api/history/tasks/{task_id}"),
        ("DELETE", "/api/history/tasks/{task_id}"),
        ("GET", "/api/history/summary"),
        ("GET", "/api/history/scenes"),
        ("GET", "/api/user/list"),
        ("GET", "/api/user/roles"),
        ("PUT", "/api/user/profile"),
        ("PUT", "/api/user/password"),
    }.issubset(routes)


def test_new_routes_require_authentication(client):
    for path in [
        "/api/dashboard/statistics",
        "/api/history/tasks",
        "/api/history/summary",
        "/api/history/scenes",
        "/api/user/list",
        "/api/user/roles",
    ]:
        assert client.get(path).status_code == 401
    assert client.put("/api/user/profile").status_code == 401
    assert client.put("/api/user/password").status_code == 401


def test_dashboard_api_forwards_current_user_and_days(client, monkeypatch):
    calls = []

    def fake_statistics(user_id, days):
        calls.append(("statistics", user_id, days))
        return {"total_tasks": 2}

    def fake_trend(user_id, days):
        calls.append(("trend", user_id, days))
        return {"trend": []}

    def fake_distribution(name):
        def handler(user_id, days):
            calls.append((name, user_id, days))
            return {"distribution": []}

        return handler

    monkeypatch.setattr(dashboard_service, "get_statistics", fake_statistics)
    monkeypatch.setattr(dashboard_service, "get_trend", fake_trend)
    monkeypatch.setattr(
        dashboard_service,
        "get_class_distribution",
        fake_distribution("class"),
    )
    monkeypatch.setattr(
        dashboard_service,
        "get_scene_distribution",
        fake_distribution("scene"),
    )
    monkeypatch.setattr(
        dashboard_service,
        "get_type_distribution",
        fake_distribution("type"),
    )
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=9)
    try:
        assert client.get("/api/dashboard/statistics?days=7").json() == {
            "total_tasks": 2
        }
        client.get("/api/dashboard/trend?days=7")
        client.get("/api/dashboard/class-dist?days=7")
        client.get("/api/dashboard/scene-dist?days=7")
        client.get("/api/dashboard/type-dist?days=7")
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert calls == [
        ("statistics", 9, 7),
        ("trend", 9, 7),
        ("class", 9, 7),
        ("scene", 9, 7),
        ("type", 9, 7),
    ]


def test_history_api_matches_frontend_contract(client, monkeypatch):
    calls = []

    def fake_list_tasks(**kwargs):
        calls.append(("list", kwargs))
        return {"total": 0, "page": kwargs["page"], "items": []}

    monkeypatch.setattr(history_service, "list_tasks", fake_list_tasks)
    monkeypatch.setattr(
        history_service,
        "get_task_detail",
        lambda user_id, task_id: {
            "task": {"id": task_id},
            "class_counts": {},
            "results": [],
        },
    )
    monkeypatch.setattr(history_service, "delete_task", lambda user_id, task_id: True)
    monkeypatch.setattr(
        history_service,
        "get_summary",
        lambda user_id: {"total_tasks": 0, "today_tasks": 0},
    )
    monkeypatch.setattr(
        history_service,
        "list_scenes",
        lambda: [{"id": 1, "display_name": "遥感检测"}],
    )
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=7,
        username="tester",
    )
    try:
        response = client.get(
            "/api/history/tasks",
            params={
                "page": 2,
                "page_size": 20,
                "task_type": "video",
                "status": "completed",
                "scene_id": 3,
                "start_date": "2026-07-01",
                "end_date": "2026-07-15",
            },
        )
        assert response.json()["page"] == 2
        assert client.get("/api/history/tasks/12").json()["task"]["id"] == 12
        assert client.delete("/api/history/tasks/12").json()["task_id"] == 12
        assert client.get("/api/history/summary").status_code == 200
        assert client.get("/api/history/scenes").json()["scenes"][0]["id"] == 1
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert calls == [
        (
            "list",
            {
                "user_id": 7,
                "page": 2,
                "page_size": 20,
                "task_type": "video",
                "status": "completed",
                "scene_id": 3,
                "start_date": "2026-07-01",
                "end_date": "2026-07-15",
            },
        )
    ]


def test_history_api_rejects_other_users_task(client, monkeypatch):
    monkeypatch.setattr(
        history_service,
        "get_task_detail",
        lambda user_id, task_id: None,
    )
    monkeypatch.setattr(
        history_service,
        "delete_task",
        lambda user_id, task_id: False,
    )
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=7,
        username="tester",
    )
    try:
        assert client.get("/api/history/tasks/99").status_code == 404
        assert client.delete("/api/history/tasks/99").status_code == 404
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_user_api_matches_settings_contract(client, monkeypatch):
    calls = []
    monkeypatch.setattr(
        user_service,
        "list_users",
        lambda page, page_size, keyword: {
            "total": 0,
            "page": page,
            "page_size": page_size,
            "items": [],
        },
    )
    monkeypatch.setattr(user_service, "list_roles", lambda: [])

    def fake_profile(user_id, phone, email, db=None):
        calls.append(("profile", user_id, phone, email))
        return {"message": "个人信息已更新"}

    def fake_password(user_id, old_password, new_password, db=None):
        calls.append(("password", user_id, old_password, new_password))
        return {"message": "密码修改成功"}

    monkeypatch.setattr(user_service, "update_profile", fake_profile)
    monkeypatch.setattr(user_service, "change_password", fake_password)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=5, is_superuser=True, user_roles=[]
    )
    try:
        assert client.get("/api/user/list?page=1&page_size=20").status_code == 200
        assert client.get("/api/user/roles").json() == {"roles": []}
        assert (
            client.put(
                "/api/user/profile",
                params={"email": "new@example.com", "phone": "13800000000"},
            ).status_code
            == 200
        )
        assert (
            client.put(
                "/api/user/password",
                params={"old_password": "123456", "new_password": "abcdef"},
            ).status_code
            == 200
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert calls == [
        ("profile", 5, "13800000000", "new@example.com"),
        ("password", 5, "123456", "abcdef"),
    ]


def test_dashboard_days_validation(client):
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=1)
    try:
        assert client.get("/api/dashboard/statistics?days=0").status_code == 422
        assert client.get("/api/dashboard/statistics?days=366").status_code == 422
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_services_isolate_users_and_match_frontend_payloads(db_session, monkeypatch):
    import app.services.dashboard_service as dashboard_module
    import app.services.history_service as history_module
    import app.services.user_service as user_module

    owner = User(
        username="dashboard_owner",
        email="dashboard_owner@example.com",
        hashed_password=hash_password("123456"),
    )
    other = User(
        username="dashboard_other",
        email="dashboard_other@example.com",
        hashed_password=hash_password("123456"),
    )
    db_session.add_all([owner, other])
    db_session.flush()

    scene = DetectionScene(
        name="dashboard_scene",
        display_name="看板测试场景",
        category="industry",
        class_names=["defect"],
        is_active=True,
        created_by=owner.id,
    )
    db_session.add(scene)
    db_session.flush()

    owner_task = DetectionTask(
        user_id=owner.id,
        scene_id=scene.id,
        task_type="single",
        status="completed",
        total_images=1,
        total_objects=2,
        total_inference_time=12.5,
        created_at=datetime.now(),
        completed_at=datetime.now(),
    )
    other_task = DetectionTask(
        user_id=other.id,
        scene_id=scene.id,
        task_type="video",
        status="completed",
        total_images=20,
        total_objects=50,
        total_inference_time=999.0,
        created_at=datetime.now(),
        completed_at=datetime.now(),
    )
    db_session.add_all([owner_task, other_task])
    db_session.flush()
    db_session.add_all(
        [
            DetectionResult(
                task_id=owner_task.id,
                image_path="owner.jpg",
                class_name="defect",
                class_id=0,
                confidence=0.9,
                bbox=[1, 2, 3, 4],
                inference_time=12.5,
            ),
            DetectionResult(
                task_id=owner_task.id,
                image_path="owner.jpg",
                class_name="defect",
                class_id=0,
                confidence=0.8,
                bbox=[2, 3, 4, 5],
                inference_time=12.5,
            ),
            DetectionResult(
                task_id=other_task.id,
                image_path="other.jpg",
                class_name="private-class",
                class_id=1,
                confidence=0.95,
                bbox=[1, 1, 2, 2],
                inference_time=999.0,
            ),
        ]
    )
    db_session.commit()
    owner_id = owner.id
    other_task_id = other_task.id
    owner_task_id = owner_task.id

    monkeypatch.setattr(dashboard_module, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(history_module, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(user_module, "SessionLocal", lambda: db_session)

    statistics = dashboard_service.get_statistics(owner_id, days=30)
    assert statistics["total_tasks"] == 1
    assert statistics["total_images"] == 1
    assert statistics["total_objects"] == 2
    assert statistics["avg_inference_time"] == 12.5

    trend = dashboard_service.get_trend(owner_id, days=7)
    assert len(trend["trend"]) == 7
    assert trend["trend"][-1]["task_count"] == 1
    assert trend["trend"][-1]["object_count"] == 2

    assert dashboard_service.get_class_distribution(owner_id)["distribution"] == [
        {"name": "defect", "value": 2}
    ]
    assert dashboard_service.get_scene_distribution(owner_id)["distribution"] == [
        {"name": "看板测试场景", "value": 1}
    ]
    assert dashboard_service.get_type_distribution(owner_id)["distribution"] == [
        {"name": "单图检测", "value": 1}
    ]

    history = history_service.list_tasks(owner_id)
    assert history["total"] == 1
    assert history["items"][0]["id"] == owner_task_id
    detail = history_service.get_task_detail(owner_id, owner_task_id)
    assert detail["class_counts"] == {"defect": 2}
    assert len(detail["results"]) == 2
    assert history_service.get_task_detail(owner_id, other_task_id) is None
    assert history_service.delete_task(owner_id, other_task_id) is False

    user_list = user_service.list_users(keyword="dashboard_owner")
    assert user_list["total"] == 1
    assert user_list["items"][0]["username"] == "dashboard_owner"
    profile = user_service.update_profile(
        owner_id,
        phone="13800000000",
        email="dashboard_owner_new@example.com",
    )
    assert profile["user"]["phone"] == "13800000000"
    assert user_service.change_password(owner_id, "123456", "abcdef") == {
        "message": "密码修改成功"
    }
