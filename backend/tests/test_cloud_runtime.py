"""云部署同源访问与运行配置回归测试。"""

import pytest
from fastapi import HTTPException

from app.api.storage import _parse_range
from app.config.settings import Settings, settings
from app.storage.minio_client import MinIOClient


def test_default_runtime_config_supports_local_debugging():
    assert Settings.model_fields["DEBUG"].default is True
    assert Settings.model_fields["PUBLIC_BASE_URL"].default == "http://127.0.0.1:8000"
    assert Settings.model_fields["TRUSTED_HOSTS"].default == "*"
    assert Settings.model_fields["TRUST_PROXY_HEADERS"].default is False


def test_storage_url_uses_configured_public_base_and_hides_internal_services(monkeypatch):
    monkeypatch.setattr(settings, "PUBLIC_BASE_URL", "https://pcb.example.com/")
    monkeypatch.setattr(settings, "MINIO_ENDPOINT", "localhost:9000")
    monkeypatch.setattr(settings, "STORAGE_URL_EXPIRE_SECONDS", 60)
    monkeypatch.setattr("app.storage.minio_client.time.time", lambda: 1_000)

    url = MinIOClient.__new__(MinIOClient).get_presigned_url("detections/1/结果图.jpg")

    assert url.startswith("https://pcb.example.com/api/storage/objects/detections/1/")
    assert "expires=1060" in url
    assert "localhost" not in url
    assert "127.0.0.1" not in url
    assert "minio" not in url.lower()
    assert "redis" not in url.lower()


def test_storage_signature_expires(monkeypatch):
    monkeypatch.setattr("app.storage.minio_client.time.time", lambda: 2_000)
    signature = MinIOClient._sign("models/1/best.pt", 2_100)
    assert MinIOClient.verify_proxy_signature("models/1/best.pt", 2_100, signature)
    assert not MinIOClient.verify_proxy_signature("models/2/best.pt", 2_100, signature)

    monkeypatch.setattr("app.storage.minio_client.time.time", lambda: 2_101)
    assert not MinIOClient.verify_proxy_signature("models/1/best.pt", 2_100, signature)


def test_storage_range_parser_supports_video_requests():
    assert _parse_range("bytes=10-19", 100) == (10, 19, 10)
    assert _parse_range("bytes=90-", 100) == (90, 99, 10)
    assert _parse_range("bytes=-8", 100) == (92, 99, 8)
    with pytest.raises(HTTPException) as exc:
        _parse_range("bytes=100-101", 100)
    assert exc.value.status_code == 416
