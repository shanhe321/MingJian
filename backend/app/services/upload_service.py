"""上传文件校验与临时文件清理。"""

from __future__ import annotations

import io
import os
import tempfile
import time
from pathlib import Path

from fastapi import HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError

from app.config.settings import settings
from app.core.logger import get_logger

logger = get_logger(__name__)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
IMAGE_MIMES = {"image/jpeg", "image/png", "image/bmp", "image/webp"}


async def read_valid_image(file: UploadFile) -> bytes:
    extension = Path(file.filename or "").suffix.lower()
    if extension not in IMAGE_EXTENSIONS or file.content_type not in IMAGE_MIMES:
        raise HTTPException(status_code=415, detail="仅支持 JPEG、PNG、BMP、WebP 图片")
    content = await file.read(settings.MAX_IMAGE_SIZE_MB * 1024 * 1024 + 1)
    if not content:
        raise HTTPException(status_code=400, detail="图片为空")
    if len(content) > settings.MAX_IMAGE_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"图片不能超过 {settings.MAX_IMAGE_SIZE_MB}MB")
    try:
        with Image.open(io.BytesIO(content)) as image:
            image.verify()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="图片无法读取或内容损坏") from exc
    return content


def cleanup_orphan_temp_files() -> dict:
    cutoff = time.time() - settings.TEMP_MAX_AGE_HOURS * 3600
    removed = 0
    failed = 0
    # 只清理由本项目显式命名的临时文件，避免误删系统或其他应用的 tmp* 文件。
    prefixes = ("rsod_",)
    for entry in Path(tempfile.gettempdir()).iterdir():
        try:
            if entry.is_file() and entry.name.startswith(prefixes) and entry.stat().st_mtime < cutoff:
                os.unlink(entry)
                removed += 1
        except Exception as exc:
            failed += 1
            logger.warning("清理孤立临时文件失败 %s: %s", entry, exc)
    upload_dir = Path(tempfile.gettempdir()) / "rsod_uploads"
    if upload_dir.exists():
        for entry in upload_dir.iterdir():
            try:
                if entry.is_file() and entry.stat().st_mtime < cutoff:
                    os.unlink(entry)
                    removed += 1
            except Exception as exc:
                failed += 1
                logger.warning("清理聊天上传临时文件失败 %s: %s", entry, exc)
    return {"removed": removed, "failed": failed}
