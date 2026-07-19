import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.agent.tools.analysis_tool import query_detection_stats
from app.api import chat as chat_api
from app.api.auth import get_current_user
from app.config.settings import settings
from app.core.security import decode_access_token
from app.entity.db_models import User
from app.services.audit_service import sanitized_description
from app.services.user_service import user_service
from app.storage.redis_client import redis_client
from main import app


class UploadRegistry:
    def __init__(self, available=True):
        self.available = available
        self.values = {}

    def ensure_available(self):
        return self.available

    def set_json(self, key, value, expire=None):
        self.values[key] = value
        return True

    def get_json(self, key):
        return self.values.get(key)

    def exists(self, key):
        return key in self.values


def test_disabling_user_revokes_existing_tokens(db_session):
    normal = User(
        username=f"user_{uuid4().hex[:6]}",
        email=f"user-{uuid4().hex[:6]}@example.com",
        hashed_password="x",
        is_active=True,
    )
    db_session.add(normal)
    db_session.flush()
    db_session.commit()

    user_service.set_user_status(db_session, normal.id, False)
    assert normal.is_active is False
    assert redis_client.get(user_service.token_version_key(normal.id))
    redis_client.delete(user_service.token_version_key(normal.id))


def test_chat_upload_reference_is_user_scoped(tmp_path, monkeypatch):
    registry = UploadRegistry()
    monkeypatch.setattr(chat_api, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(chat_api, "redis_client", registry)
    monkeypatch.setattr(settings, "DEBUG", True)

    upload_id = "51c4ec7b-92b0-4a18-9541-737ff06f5e61"
    user_dir = tmp_path / "7"
    user_dir.mkdir()
    image = user_dir / f"{upload_id}.jpg"
    image.write_bytes(b"image")
    registry.set_json(
        chat_api._upload_registry_key(7, upload_id),
        {"path": str(image)},
    )

    assert chat_api._resolve_registered_upload(7, upload_id) == str(image.resolve())
    with pytest.raises(HTTPException, match="不存在或已过期"):
        chat_api._resolve_registered_upload(8, upload_id)
    with pytest.raises(HTTPException, match="无效的图片上传标识"):
        chat_api._resolve_registered_upload(7, str(image))


def test_chat_upload_registry_fails_closed_in_production(monkeypatch):
    monkeypatch.setattr(chat_api, "redis_client", UploadRegistry(available=False))
    monkeypatch.setattr(settings, "DEBUG", False)

    with pytest.raises(HTTPException) as exc_info:
        chat_api._resolve_registered_upload(
            1, "51c4ec7b-92b0-4a18-9541-737ff06f5e61"
        )
    assert exc_info.value.status_code == 503


def test_chat_stream_rejects_arbitrary_server_path(client):
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=91, username="chat-security", is_superuser=False
    )
    try:
        response = client.post(
            "/api/chat/stream",
            json={"message": "检测", "image_path": "C:/Windows/win.ini"},
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 400


def test_personal_analysis_tools_require_user_context():
    result = json.loads(query_detection_stats.invoke({"days": 30}))
    assert result == {"error": "缺少当前用户上下文，无法查询个人数据"}


def test_audit_details_recursively_remove_secrets():
    description = sanitized_description(
        "test",
        {
            "safe": "ok",
            "nested": {
                "access_token": "secret",
                "image_base64": "large-payload",
                "name": "visible",
            },
        },
    )
    assert "secret" not in description
    assert "large-payload" not in description
    assert "visible" in description


def test_password_change_invalidates_previously_issued_token(client):
    suffix = uuid4().hex[:8]
    username = f"token_user_{suffix}"
    client.post(
        "/api/auth/register",
        json={
            "username": username,
            "email": f"token-{suffix}@example.com",
            "password": "123456",
        },
    )
    login = client.post(
        "/api/auth/login",
        json={"username": username, "password": "123456"},
    )
    old_token = login.json()["access_token"]

    changed = client.put(
        "/api/user/password",
        params={"old_password": "123456", "new_password": "abcdef"},
        headers={"Authorization": f"Bearer {old_token}"},
    )
    assert changed.status_code == 200
    assert client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {old_token}"},
    ).status_code == 401

    new_login = client.post(
        "/api/auth/login",
        json={"username": username, "password": "abcdef"},
    )
    assert new_login.status_code == 200
    new_token = new_login.json()["access_token"]
    assert client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {new_token}"},
    ).status_code == 200

    redis_client.delete(
        f"jwt:user_version:{decode_access_token(new_token)['sub']}"
    )
