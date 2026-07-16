"""
对话相关 API 路由

接口列表：
  - POST /api/chat/upload    上传图片文件，返回服务端路径
  - POST /api/chat/stream    SSE 流式对话
"""

import json
import os
import tempfile
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse

from app.agent.detection_agent import detection_agent
from app.agent.memory import conversation_memory
from app.api.auth import get_current_user
from app.core.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/chat", tags=["智能对话"])

UPLOAD_DIR = os.path.join(tempfile.gettempdir(), "rsod_uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


@router.post("/upload", summary="上传图片文件")
async def upload_image(
    file: UploadFile = File(...),
    current_user=Depends(get_current_user),
):
    """上传图片文件到服务端临时目录。"""
    filename = f"{os.getpid()}_{os.path.basename(file.filename or 'upload.jpg')}"
    file_path = os.path.join(UPLOAD_DIR, filename)

    content = await file.read()
    with open(file_path, "wb") as output_file:
        output_file.write(content)

    logger.info("图片上传成功: %s → %s", file.filename, file_path)
    return {"image_path": file_path}


@router.post("/stream")
async def chat_stream(
    request: Request,
    current_user=Depends(get_current_user),
):
    """SSE 流式对话接口。"""
    body = await request.json()
    message = body.get("message", "")
    image_path = body.get("image_path")
    session_id = body.get("session_id")

    if not message:
        raise HTTPException(status_code=400, detail="消息内容不能为空")

    if not session_id:
        session_id = str(uuid.uuid4())[:8]

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
                {"type": "error", "content": str(exc)},
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
    """获取当前用户的 Redis 会话 ID 列表。"""
    return {"sessions": conversation_memory.get_sessions(current_user.id)}


@router.post("/clear", summary="清空会话历史")
async def clear_session(
    request: Request,
    current_user=Depends(get_current_user),
):
    """清空当前用户的指定 Redis 会话历史。"""
    body = await request.json()
    session_id = body.get("session_id", "default")
    conversation_memory.clear_session(current_user.id, session_id)
    return {"message": f"会话 {session_id} 已清空"}
