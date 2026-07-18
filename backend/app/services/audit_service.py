"""安全的操作审计写入工具。"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.entity.db_models import OperationLog, User

SENSITIVE_KEYS = {
    "password",
    "old_password",
    "new_password",
    "token",
    "access_token",
    "api_key",
    "content",
    "authorization",
    "image_base64",
}


def _sanitize_details(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _sanitize_details(item)
            for key, item in value.items()
            if key.lower() not in SENSITIVE_KEYS
            and not any(
                marker in key.lower()
                for marker in ("password", "token", "api_key", "base64")
            )
        }
    if isinstance(value, (list, tuple)):
        return [_sanitize_details(item) for item in value]
    return value


def sanitized_description(action: str, details: dict[str, Any] | None = None) -> str:
    safe = _sanitize_details(details or {})
    suffix = ", ".join(f"{key}={value}" for key, value in safe.items())
    return f"{action}{': ' + suffix if suffix else ''}"[:500]


def write_audit(
    db: Session,
    *,
    user: User | None,
    module: str,
    action: str,
    target_type: str | None = None,
    target_id: str | int | None = None,
    details: dict[str, Any] | None = None,
    request=None,
    status: str = "success",
    error_message: str | None = None,
) -> OperationLog:
    log = OperationLog(
        user_id=getattr(user, "id", None),
        username=getattr(user, "username", None),
        module=module,
        action=action,
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        description=sanitized_description(action, details),
        ip_address=request.client.host if request and request.client else None,
        user_agent=request.headers.get("user-agent") if request else None,
        request_method=request.method if request else None,
        request_path=request.url.path if request else None,
        status=status,
        error_message=error_message[:2000] if error_message else None,
    )
    db.add(log)
    return log
