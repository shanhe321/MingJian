"""
MinIO 对象存储客户端封装
用于存储检测图像、训练模型等文件
"""
import io
import hashlib
import hmac
import time
from urllib.parse import quote

from minio import Minio
from minio.error import S3Error

from app.config.settings import settings


class MinIOClient:
    """MinIO 客户端封装"""

    def __init__(self):
        self.client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE,
        )
        self.bucket_name = settings.MINIO_BUCKET
        self._ensure_bucket()

    def _ensure_bucket(self):
        """确保存储桶存在，不存在则创建"""
        try:
            if not self.client.bucket_exists(self.bucket_name):
                self.client.make_bucket(self.bucket_name)
        except S3Error as e:
            print(f"MinIO bucket 初始化警告: {e}")

    def upload_file(self, object_name: str, file_path: str) -> str:
        """
        上传本地文件到 MinIO

        Args:
            object_name: MinIO 中的对象名称（路径）
            file_path: 本地文件路径

        Returns:
            预签名 URL
        """
        self.client.fput_object(
            bucket_name=self.bucket_name,
            object_name=object_name,
            file_path=file_path,
        )
        return self.get_presigned_url(object_name)

    def upload_bytes(self, object_name: str, data: bytes, content_type: str = "image/jpeg") -> str:
        """
        上传字节数据到 MinIO

        Args:
            object_name: MinIO 中的对象名称
            data: 字节数据
            content_type: MIME 类型

        Returns:
            预签名 URL
        """
        self.client.put_object(
            bucket_name=self.bucket_name,
            object_name=object_name,
            data=io.BytesIO(data),
            length=len(data),
            content_type=content_type,
        )
        return self.get_presigned_url(object_name)

    def get_presigned_url(self, object_name: str) -> str:
        """生成媒体代理 URL；公网基址只读取 PUBLIC_BASE_URL。"""
        expires = int(time.time()) + settings.STORAGE_URL_EXPIRE_SECONDS
        signature = self._sign(object_name, expires)
        base = settings.PUBLIC_BASE_URL.strip().rstrip("/")
        path = f"/api/storage/objects/{quote(object_name, safe='/')}"
        return f"{base}{path}?expires={expires}&signature={signature}"

    @staticmethod
    def _sign(object_name: str, expires: int) -> str:
        payload = f"{object_name}\n{expires}".encode("utf-8")
        return hmac.new(
            settings.JWT_SECRET_KEY.encode("utf-8"), payload, hashlib.sha256
        ).hexdigest()

    @classmethod
    def verify_proxy_signature(cls, object_name: str, expires: int, signature: str) -> bool:
        if expires < int(time.time()):
            return False
        return hmac.compare_digest(cls._sign(object_name, expires), signature)

    def object_exists(self, object_name: str) -> bool:
        try:
            self.client.stat_object(self.bucket_name, object_name)
            return True
        except S3Error:
            return False

    def stat_object(self, object_name: str):
        return self.client.stat_object(self.bucket_name, object_name)

    def list_object_names(self, prefix: str) -> set[str]:
        return {
            item.object_name
            for item in self.client.list_objects(self.bucket_name, prefix=prefix, recursive=True)
        }

    def delete_file(self, object_name: str):
        """删除 MinIO 中的文件"""
        self.client.remove_object(
            bucket_name=self.bucket_name,
            object_name=object_name,
        )

    def download_bytes(self, object_name: str) -> bytes:
        """读取对象内容；调用方负责权限校验。"""
        response = self.client.get_object(self.bucket_name, object_name)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    def download_file(self, object_name: str, file_path: str) -> str:
        """将对象下载到本地文件，供模型缓存和后台任务恢复使用。"""
        self.client.fget_object(self.bucket_name, object_name, file_path)
        return file_path

    def delete_prefix(self, prefix: str) -> int:
        """删除任务所属前缀下的所有对象。"""
        count = 0
        for item in self.client.list_objects(self.bucket_name, prefix=prefix, recursive=True):
            self.client.remove_object(self.bucket_name, item.object_name)
            count += 1
        return count
