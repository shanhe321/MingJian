"""
对话相关 API 路由

接口列表：
  - POST /api/chat/upload    上传图片文件，返回用户隔离的不透明上传 ID
  - POST /api/chat/stream    SSE 流式对话
"""

import json
import os
import tempfile
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.agent.detection_agent import detection_agent
from app.agent.memory import conversation_memory
from app.api.auth import get_current_user
from app.config.settings import settings
from app.core.logger import get_logger
from app.database.session import get_db
from app.services.audit_service import write_audit
from app.services.upload_service import read_valid_image
from app.storage.redis_client import redis_client

logger = get_logger(__name__)

router = APIRouter(prefix="/api/chat", tags=["智能对话"])

UPLOAD_DIR = Path(tempfile.gettempdir()) / "rsod_uploads" / "chat"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_TTL_SECONDS = 3600


def _upload_registry_key(user_id: int, upload_id: str) -> str:
    return f"chat:upload:{user_id}:{upload_id}"


def _require_upload_registry() -> None:
    if not settings.DEBUG and not redis_client.ensure_available():
        raise HTTPException(status_code=503, detail="上传登记服务暂时不可用，请稍后重试")


def _resolve_registered_upload(user_id: int, upload_id: str) -> str:
    """把不透明上传 ID 解析为当前用户目录中的服务器路径。"""
    _require_upload_registry()
    try:
        normalized_id = str(uuid.UUID(str(upload_id)))
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(status_code=400, detail="无效的图片上传标识")

    try:
        metadata = redis_client.get_json(_upload_registry_key(user_id, normalized_id))
    except (ValueError, TypeError, json.JSONDecodeError):
        metadata = None
    if not metadata or not isinstance(metadata.get("path"), str):
        raise HTTPException(status_code=400, detail="图片上传标识不存在或已过期")

    user_dir = (UPLOAD_DIR / str(user_id)).resolve()
    file_path = Path(metadata["path"]).resolve()
    try:
        file_path.relative_to(user_dir)
    except ValueError:
        logger.warning("拒绝越界 Chat 上传路径: user=%s, upload=%s", user_id, normalized_id)
        raise HTTPException(status_code=400, detail="图片上传标识无效")
    if not file_path.is_file():
        raise HTTPException(status_code=400, detail="上传图片不存在或已清理")
    return str(file_path)


@router.post("/upload", summary="上传图片文件")
async def upload_image(
    request: Request,
    file: UploadFile = File(...),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """上传图片文件到服务端临时目录。"""
    _require_upload_registry()
    upload_id = str(uuid.uuid4())
    suffix = Path(os.path.basename(file.filename or "upload.jpg")).suffix.lower() or ".jpg"
    user_dir = UPLOAD_DIR / str(current_user.id)
    user_dir.mkdir(parents=True, exist_ok=True)
    file_path = user_dir / f"{upload_id}{suffix}"
    try:
        content = await read_valid_image(file)
        file_path.write_bytes(content)
        key = _upload_registry_key(current_user.id, upload_id)
        redis_client.set_json(
            key,
            {
                "path": str(file_path),
                "original_name": os.path.basename(file.filename or "upload.jpg"),
            },
            expire=UPLOAD_TTL_SECONDS,
        )
        if not settings.DEBUG and (
            not redis_client.ensure_available() or not redis_client.exists(key)
        ):
            file_path.unlink(missing_ok=True)
            raise HTTPException(status_code=503, detail="上传登记服务暂时不可用，请稍后重试")
        write_audit(
            db,
            user=current_user,
            module="agent",
            action="upload_attachment",
            target_type="chat_upload",
            target_id=upload_id,
            details={"file_name": os.path.basename(file.filename or "upload.jpg")},
            request=request,
        )
        db.commit()
    except Exception as exc:
        file_path.unlink(missing_ok=True)
        if not isinstance(exc, HTTPException) or exc.status_code != 503:
            write_audit(
                db,
                user=current_user,
                module="agent",
                action="upload_attachment",
                target_type="chat_upload",
                target_id=upload_id,
                request=request,
                status="failed",
                error_message=str(getattr(exc, "detail", exc)),
            )
            db.commit()
        raise

    logger.info("Chat 图片上传成功: user=%s, upload=%s", current_user.id, upload_id)
    # image_path 保留为兼容字段，但值已变为不透明 ID，不再泄露服务器路径。
    return {"upload_id": upload_id, "image_path": upload_id, "expires_in": UPLOAD_TTL_SECONDS}


@router.post("/stream")
async def chat_stream(
    request: Request,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """SSE 流式对话接口。"""
    try:
        body = await request.json()
    except (json.JSONDecodeError, ValueError):
        raise HTTPException(status_code=400, detail="请求体必须是 JSON 对象")
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="请求体必须是 JSON 对象")
    message = body.get("message", "")
    image_reference = body.get("upload_id") or body.get("image_path")
    session_id = body.get("session_id")

    if not isinstance(message, str) or not message.strip():
        raise HTTPException(status_code=400, detail="消息内容不能为空")
    if len(message) > 10000:
        raise HTTPException(status_code=400, detail="消息内容格式无效或过长")

    image_path = (
        _resolve_registered_upload(current_user.id, image_reference)
        if image_reference
        else None
    )

    if not session_id:
        session_id = str(uuid.uuid4())[:8]
    if (
        not isinstance(session_id, str)
        or len(session_id) > 100
        or not all(char.isalnum() or char in "-_" for char in session_id)
    ):
        raise HTTPException(status_code=400, detail="会话标识格式无效")

    write_audit(
        db,
        user=current_user,
        module="agent",
        action="chat",
        target_type="chat_session",
        target_id=session_id,
        details={"has_attachment": bool(image_path)},
        request=request,
    )
    db.commit()

    logger.info(
        "用户 %s 发起对话: message=%s, image=%s, session=%s",
        current_user.username,
        message[:50],
        "有" if image_path else "无",
        session_id,
    )

    async def event_generator():
        try:
            async for event in detection_agent.chat_stream(
                message=message,
                user_id=current_user.id,
                session_id=session_id,
                image_path=image_path,
                user_is_superuser=getattr(current_user, "is_superuser", False),
            ):
                event_data = json.dumps(event, ensure_ascii=False)
                yield f"data: {event_data}\n\n"

            yield "data: [DONE]\n\n"

        except Exception as exc:
            logger.error("SSE 流异常: %s", str(exc), exc_info=True)
            error_data = json.dumps(
                {"type": "error", "content": "智能体处理失败，请稍后重试"},
                ensure_ascii=False,
            )
            yield f"data: {error_data}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/sessions", summary="获取会话列表")
async def get_sessions(current_user=Depends(get_current_user)):
    """从 PostgreSQL 获取会话列表，数据库不可用时回退 Redis 索引。"""
    items = conversation_memory.get_session_summaries(current_user.id)
    return {
        "sessions": [item["session_id"] for item in items],
        "items": items,
    }


@router.get("/sessions/{session_id}", summary="从数据库读取会话历史")
async def get_session_history(session_id: str, current_user=Depends(get_current_user)):
    return {
        "session_id": session_id,
        "messages": conversation_memory.get_session_history(current_user.id, session_id),
    }


@router.post("/clear", summary="清空会话历史")
async def clear_session(
    request: Request,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """清空当前用户的指定 Redis 会话历史。"""
    try:
        body = await request.json()
    except (json.JSONDecodeError, ValueError):
        raise HTTPException(status_code=400, detail="请求体必须是 JSON 对象")
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="请求体必须是 JSON 对象")
    session_id = body.get("session_id", "default")
    if (
        not isinstance(session_id, str)
        or not session_id
        or len(session_id) > 100
        or not all(char.isalnum() or char in "-_" for char in session_id)
    ):
        raise HTTPException(status_code=400, detail="会话标识格式无效")
    conversation_memory.clear_session(current_user.id, session_id)
    write_audit(
        db,
        user=current_user,
        module="agent",
        action="clear_session",
        target_type="chat_session",
        target_id=session_id,
        request=request,
    )
    db.commit()
    return {"message": f"会话 {session_id} 已清空"}
