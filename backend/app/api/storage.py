"""同源对象访问代理，浏览器无需连接内部 MinIO。"""

from __future__ import annotations

from collections.abc import Iterator
from urllib.parse import quote

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import StreamingResponse
from minio.error import S3Error

from app.storage.minio_client import MinIOClient


router = APIRouter(prefix="/api/storage", tags=["对象存储"])


def _parse_range(value: str | None, size: int) -> tuple[int, int, int] | None:
    if not value:
        return None
    if not value.startswith("bytes=") or "," in value:
        raise HTTPException(status_code=416, detail="不支持的 Range 请求")
    start_text, end_text = value[6:].split("-", 1)
    try:
        if not start_text:
            suffix = int(end_text)
            if suffix <= 0:
                raise ValueError
            start = max(0, size - suffix)
            end = size - 1
        else:
            start = int(start_text)
            end = int(end_text) if end_text else size - 1
    except ValueError as exc:
        raise HTTPException(status_code=416, detail="Range 参数无效") from exc
    if start < 0 or start >= size or end < start:
        raise HTTPException(status_code=416, detail="Range 超出对象范围")
    end = min(end, size - 1)
    return start, end, end - start + 1


@router.get("/objects/{object_name:path}")
async def read_object(
    object_name: str,
    expires: int = Query(...),
    signature: str = Query(..., min_length=64, max_length=64),
    download: bool = Query(False),
    range_header: str | None = Header(None, alias="Range"),
):
    if not MinIOClient.verify_proxy_signature(object_name, expires, signature):
        raise HTTPException(status_code=403, detail="文件地址已失效或签名无效")
    client = MinIOClient()
    try:
        stat = client.stat_object(object_name)
        byte_range = _parse_range(range_header, stat.size)
        offset, length = (byte_range[0], byte_range[2]) if byte_range else (0, stat.size)
        response = client.client.get_object(
            client.bucket_name, object_name, offset=offset, length=length
        )
    except S3Error as exc:
        if exc.code in {"NoSuchKey", "NoSuchObject", "NoSuchBucket"}:
            raise HTTPException(status_code=404, detail="文件不存在") from exc
        raise HTTPException(status_code=502, detail="对象存储暂时不可用") from exc

    def body() -> Iterator[bytes]:
        try:
            while chunk := response.read(1024 * 1024):
                yield chunk
        finally:
            response.close()
            response.release_conn()

    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(length),
        "Cache-Control": "private, max-age=300",
    }
    if byte_range:
        headers["Content-Range"] = f"bytes {byte_range[0]}-{byte_range[1]}/{stat.size}"
    if download:
        filename = object_name.rsplit("/", 1)[-1].replace('"', "")
        headers["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(filename)}"
    return StreamingResponse(
        body(),
        status_code=206 if byte_range else 200,
        media_type=stat.content_type or "application/octet-stream",
        headers=headers,
    )
