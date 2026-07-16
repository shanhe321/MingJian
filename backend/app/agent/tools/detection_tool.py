"""Agent 可调用的单图、批量、ZIP 和视频检测工具。"""

import json
from langchain_core.tools import tool
from app.core.logger import get_logger
from app.services.detection_service import detection_service
from app.agent.tools.context import current_user_id

logger = get_logger(__name__)


def _strip_base64_payloads(value):
    """移除检测结果中的 Base64 图片，避免把二进制内容发送给 LLM。"""
    if isinstance(value, dict):
        return {
            key: _strip_base64_payloads(item)
            for key, item in value.items()
            if "base64" not in key.lower()
        }
    if isinstance(value, list):
        return [_strip_base64_payloads(item) for item in value]
    return value


@tool
def detect_single_image(image_path: str, conf: float = 0.25, iou: float = 0.45) -> str:
    """检测单张遥感图片。当用户上传一张图片并要求检测时使用。参数为服务器绝对路径、置信度和 IoU 阈值；返回目标总数、类别统计、边界框、耗时和标注图 URL。"""
    try:
        result = detection_service.detect_single(
            image_path,
            conf=conf,
            iou=iou,
            user_id=current_user_id.get(),
        )
        return json.dumps(_strip_base64_payloads(result), ensure_ascii=False)
    except Exception as exc:
        logger.error("单图检测失败: %s", str(exc))
        return json.dumps({"error": f"检测失败: {str(exc)}"}, ensure_ascii=False)


@tool
def detect_batch_images(image_paths: list[str], conf: float = 0.25) -> str:
    """批量检测多张遥感图片。当用户上传多张图片时使用；image_paths 是服务器文件路径列表，返回所有图片的目标统计。"""
    try:
        result = detection_service.detect_batch(
            image_paths,
            conf=conf,
            user_id=current_user_id.get(),
        )
        return json.dumps(_strip_base64_payloads(result), ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"error": f"批量检测失败: {str(exc)}"}, ensure_ascii=False)


@tool
def detect_zip_images_file(zip_path: str, conf: float = 0.25) -> str:
    """解压并检测 ZIP 中的全部图片。zip_path 是服务器上的 ZIP 路径，返回图片数量和检测结果汇总。"""
    try:
        result = detection_service.detect_zip(
            zip_path,
            conf=conf,
            user_id=current_user_id.get(),
        )
        return json.dumps(_strip_base64_payloads(result), ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"error": f"ZIP 检测失败: {str(exc)}"}, ensure_ascii=False)


@tool
def detect_video_file(video_path: str, conf: float = 0.25, frame_sample_rate: int = 5) -> str:
    """按帧采样检测视频。当用户上传视频时使用；参数为视频路径、置信度和采样间隔，返回时长、处理帧数和目标统计。"""
    try:
        result = detection_service.detect_video(
            video_path,
            conf=conf,
            frame_sample_rate=frame_sample_rate,
            user_id=current_user_id.get(),
        )
        result.pop("annotated_video_url", None)
        return json.dumps(_strip_base64_payloads(result), ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"error": f"视频检测失败: {str(exc)}"}, ensure_ascii=False)


DETECTION_TOOLS = [detect_single_image, detect_batch_images, detect_zip_images_file, detect_video_file]
