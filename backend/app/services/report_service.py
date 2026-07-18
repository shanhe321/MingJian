"""Detection report serialization, charts, Markdown rendering, and archives."""

from __future__ import annotations

import copy
import io
import json
import mimetypes
import os
import re
import threading
import zipfile
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Callable
from urllib.parse import urljoin

import matplotlib

matplotlib.use("Agg")
from matplotlib import font_manager  # noqa: E402
from matplotlib import pyplot as plt  # noqa: E402


REPORT_VERSION = "2.6"
CHART_METADATA = {
    "overview_dashboard.png": {"title": "检测结果综合统计", "type": "dashboard"},
    "defect_distribution.png": {"title": "缺陷候选类别占比", "type": "pie"},
    "confidence_distribution.png": {"title": "置信度分布", "type": "histogram"},
    "item_status_summary.png": {"title": "图像级检出状态占比", "type": "donut"},
    "item_detection_trend.png": {"title": "逐检测项候选数与置信度趋势", "type": "line"},
}
CHART_FILENAMES = tuple(CHART_METADATA)
REPRESENTATIVE_ITEM_LIMIT = 8
RISK_PRIORITY = {
    "short": 3,
    "open_circuit": 3,
    "missing_hole": 3,
    "mouse_bite": 2,
}
RISK_LEVEL_TEXT = {3: "高", 2: "中", 1: "一般"}
_CHART_RENDER_LOCK = threading.Lock()


def _configure_chinese_font() -> str:
    candidates = (
        "Microsoft YaHei",
        "SimHei",
        "DengXian",
        "Noto Sans CJK SC",
        "Noto Sans CJK JP",
        "WenQuanYi Micro Hei",
        "Arial Unicode MS",
    )
    installed = {font.name for font in font_manager.fontManager.ttflist}
    selected = next((font for font in candidates if font in installed), "DejaVu Sans")
    plt.rcParams["font.sans-serif"] = [selected, "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    return selected


CHART_FONT_FAMILY = _configure_chinese_font()


def _object_url(client, object_path: str | None) -> str | None:
    if not client or not object_path:
        return None
    if object_path.startswith("/api/storage/"):
        return object_path
    if object_path.startswith(("http://", "https://")) or os.path.isabs(object_path):
        return None
    return client.get_presigned_url(object_path)


def _markdown_cell(value) -> str:
    return str(value if value not in (None, "") else "-").replace("|", "\\|").replace("\n", " ")


def _absolute_media_url(url: str | None, public_base_url: str | None) -> str | None:
    if not url or not public_base_url or not url.startswith("/"):
        return url
    return urljoin(f"{public_base_url.rstrip('/')}/", url.lstrip("/"))


def _format_bbox(bbox) -> str:
    if not isinstance(bbox, (list, tuple)):
        return "-"
    return ", ".join(f"{float(value):.1f}" for value in bbox)


def _format_percent(value) -> str:
    return f"{float(value):.2%}" if value is not None else "-"


def _format_ms(value) -> str:
    return f"{float(value):.2f} ms" if value is not None else "- ms"


def _format_datetime(value) -> str:
    if value in (None, ""):
        return "未记录"
    try:
        parsed = datetime.fromisoformat(str(value))
        return parsed.strftime("%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return str(value)


def _task_type_label(value) -> str:
    return {
        "single": "单图检测",
        "batch": "批量检测",
        "folder": "文件夹检测",
        "zip": "压缩包检测",
        "video": "视频检测",
        "camera": "摄像头检测",
    }.get(value, str(value or "未记录"))


def _status_label(value) -> str:
    return {
        "pending": "等待处理",
        "processing": "处理中",
        "completed": "已完成",
        "failed": "处理失败",
    }.get(value, str(value or "未记录"))


def _humanize_evidence(value) -> str:
    text = str(value or "当前结构化检测结果")
    replacements = {
        "检测模式=single": "检测模式=单图检测",
        "检测模式=batch": "检测模式=批量检测",
        "检测模式=folder": "检测模式=文件夹检测",
        "检测模式=zip": "检测模式=压缩包检测",
        "风险等级=high": "风险等级=高风险",
        "风险等级=medium": "风险等级=中风险",
        "风险等级=low": "风险等级=低风险",
        "状态=completed": "状态=已完成",
        "状态=failed": "状态=处理失败",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    return text


def _safe_filename(value: str, fallback: str) -> str:
    value = Path(value or fallback).name
    value = re.sub(r"[^0-9A-Za-z._-]+", "_", value).strip("._")
    return value[:120] or fallback


def _item_identity(item: dict):
    if item.get("id") is not None:
        return ("id", item["id"])
    if item.get("input_path"):
        return ("path", item["input_path"])
    if item.get("item_index") is not None:
        return ("index", item["item_index"])
    return ("file", item.get("file_name"), item.get("status"))


def _report_title(detail: dict) -> str:
    task = detail.get("task", {})
    scene_name = task.get("scene_name")
    if not scene_name:
        return "目标检测报告"
    if task.get("task_type") in {"batch", "folder", "zip"}:
        return f"{scene_name}多图任务报告"
    return f"{scene_name}报告" if str(scene_name).endswith("检测") else f"{scene_name}检测报告"


def serialize_detection_task(task, storage_client=None, report=None, task_result_path=None) -> dict:
    """Serialize an ORM task into the single detail contract used by every report output."""
    report = report or task.report
    result_path = task_result_path if task_result_path is not None else task.result_path
    class_counts: dict[str, int] = {}
    results = []
    for result in task.results:
        class_counts[result.class_name] = class_counts.get(result.class_name, 0) + 1
        results.append(
            {
                "id": result.id,
                "item_id": result.item_id,
                "class_name": result.class_name,
                "class_name_cn": result.class_name_cn,
                "class_id": result.class_id,
                "confidence": round(result.confidence, 4),
                "bbox": result.bbox,
                "image_path": result.image_path,
                "image_url": _object_url(storage_client, result.image_path),
                "annotated_image_path": result.annotated_image_path,
                "annotated_image_url": _object_url(storage_client, result.annotated_image_path),
                "inference_time": round(result.inference_time, 2) if result.inference_time is not None else None,
                "image_width": result.image_width,
                "image_height": result.image_height,
            }
        )

    model = task.model_version
    detail = {
        "report_version": REPORT_VERSION,
        "task": {
            "id": task.id,
            "user_id": task.user_id,
            "username": task.user.username if task.user else None,
            "task_type": task.task_type,
            "status": task.status,
            "scene_id": task.scene_id,
            "scene_name": task.scene.display_name if task.scene else None,
            "scene_category": task.scene.category if task.scene else None,
            "model_version_id": task.model_version_id,
            "input_path": task.input_path,
            "input_url": _object_url(storage_client, task.input_path),
            "result_path": result_path,
            "result_url": _object_url(storage_client, result_path),
            "annotated_video_url": _object_url(storage_client, result_path) if task.task_type == "video" else None,
            "total_images": task.total_images or 0,
            "total_objects": task.total_objects or 0,
            "total_inference_time": round(task.total_inference_time or 0, 2),
            "conf_threshold": task.conf_threshold,
            "iou_threshold": task.iou_threshold,
            "image_size": task.image_size,
            "error_message": task.error_message,
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        },
        "model_version": (
            {
                "id": model.id,
                "version": model.version,
                "model_name": model.model_name,
                "model_type": model.model_type,
                "precision": model.precision,
                "recall": model.recall,
                "map50": model.map50,
                "map50_95": model.map50_95,
                "per_class_ap": model.per_class_ap,
            }
            if model
            else None
        ),
        "class_counts": class_counts,
        "results": results,
        "items": [
            {
                "id": item.id,
                "item_index": item.item_index,
                "file_name": item.file_name,
                "input_path": item.input_path,
                "input_url": _object_url(storage_client, item.input_path),
                "result_path": item.result_path,
                "result_url": _object_url(storage_client, item.result_path),
                "status": item.status,
                "defect_count": item.defect_count,
                "average_confidence": item.average_confidence,
                "inference_time": item.inference_time,
                "error_message": item.error_message,
            }
            for item in task.items
        ],
        "report": (
            {
                "report_uuid": report.report_uuid,
                "quality_conclusion": report.quality_conclusion,
                "risk_level": report.risk_level,
                "defect_count": report.defect_count,
                "defect_summary": report.defect_summary,
                "risk_reason": report.risk_reason,
                "suggestion": report.suggestion,
                "statistics_explanation": report.statistics_explanation,
                "statistics_explanation_source": report.statistics_explanation_source,
                "statistics_explanation_generated_at": (
                    report.statistics_explanation_generated_at.isoformat()
                    if report.statistics_explanation_generated_at else None
                ),
                "aigc_analysis": report.aigc_analysis,
                "aigc_analysis_source": report.aigc_analysis_source,
                "aigc_analysis_generated_at": (
                    report.aigc_analysis_generated_at.isoformat()
                    if report.aigc_analysis_generated_at else None
                ),
                "report_path": report.report_path,
                "report_url": _object_url(storage_client, report.report_path),
                "created_at": report.created_at.isoformat() if report.created_at else None,
            }
            if report
            else None
        ),
    }
    if detail.get("report"):
        detail["report"] = report_semantics(detail)
    return detail


def _item_result_groups(detail: dict) -> dict[object, list[dict]]:
    """Associate results with image items without inferring physical PCB identity."""
    groups: dict[object, list[dict]] = defaultdict(list)
    for result in detail.get("results") or []:
        if result.get("item_id") is not None:
            groups[("id", result["item_id"])].append(result)
        if result.get("image_path"):
            groups[("path", result["image_path"])].append(result)
    return groups


def report_statistics(detail: dict) -> dict:
    items = detail.get("items") or []
    results = detail.get("results") or []
    completed = [item for item in items if item.get("status") == "completed"]
    failed = [item for item in items if item.get("status") == "failed"]
    defective = [item for item in completed if int(item.get("defect_count") or 0) > 0]
    clean = [item for item in completed if int(item.get("defect_count") or 0) == 0]
    confidences = [float(result["confidence"]) for result in results if result.get("confidence") is not None]
    successful = len(completed)
    threshold = float(detail.get("task", {}).get("conf_threshold") or 0)
    high_confidence = sum(confidence >= 0.7 for confidence in confidences)
    medium_confidence = sum(0.5 <= confidence < 0.7 for confidence in confidences)
    low_confidence = sum(confidence < 0.5 for confidence in confidences)
    near_threshold = sum(
        threshold <= confidence < min(1.0, threshold + 0.1)
        for confidence in confidences
    )
    multiple_defect_items = sum(
        int(item.get("defect_count") or 0) >= 2
        for item in defective
    )
    max_defect_item = max(
        defective,
        key=lambda item: int(item.get("defect_count") or 0),
        default=None,
    )
    result_groups = _item_result_groups(detail)
    item_risk_rows = []
    for item in completed:
        related = result_groups.get(("id", item.get("id")), [])
        if not related and item.get("input_path"):
            related = result_groups.get(("path", item.get("input_path")), [])
        priority = max(
            (RISK_PRIORITY.get(result.get("class_name"), 1) for result in related),
            default=0,
        )
        item_risk_rows.append((item, priority))
    high_risk_items = [item for item, priority in item_risk_rows if priority >= 3]
    medium_risk_items = [item for item, priority in item_risk_rows if priority == 2]
    general_risk_items = [item for item, priority in item_risk_rows if priority == 1]
    low_confidence_by_class = Counter(
        result.get("class_name_cn") or result.get("class_name") or "未知类别"
        for result in results
        if float(result.get("confidence") or 0) < 0.5
    )
    task_inference_time = float(detail.get("task", {}).get("total_inference_time") or 0)
    item_inference_total = sum(float(item.get("inference_time") or 0) for item in completed)
    inference_total = task_inference_time or item_inference_total
    return {
        "total_items": len(items) or int(detail.get("task", {}).get("total_images") or 0),
        "completed_items": successful,
        "failed_items": len(failed),
        "clean_items": len(clean),
        "defective_items": len(defective),
        "pass_rate": round(100 * len(clean) / successful, 2) if successful else None,
        "coverage_rate": round(100 * successful / len(items), 2) if items else None,
        "total_defects": len(results),
        "average_confidence": round(sum(confidences) / len(confidences), 4) if confidences else None,
        "minimum_confidence": round(min(confidences), 4) if confidences else None,
        "maximum_confidence": round(max(confidences), 4) if confidences else None,
        "high_confidence_results": high_confidence,
        "medium_confidence_results": medium_confidence,
        "low_confidence_results": low_confidence,
        "low_confidence_by_class": dict(low_confidence_by_class),
        "near_threshold_results": near_threshold,
        "defective_item_rate": round(100 * len(defective) / successful, 2) if successful else None,
        "multiple_defect_items": multiple_defect_items,
        "average_defects_per_defective_item": (
            round(len(results) / len(defective), 2) if defective else None
        ),
        "max_defects_per_item": (
            int(max_defect_item.get("defect_count") or 0)
            if max_defect_item else 0
        ),
        "max_defect_item_name": (
            max_defect_item.get("file_name")
            if max_defect_item else None
        ),
        "high_risk_items": len(high_risk_items),
        "medium_risk_items": len(medium_risk_items),
        "general_risk_items": len(general_risk_items),
        "high_risk_item_names": [
            str(item.get("file_name") or f"检测项 {item.get('item_index') or '-'}")
            for item in high_risk_items
        ],
        "average_inference_time_per_item": (
            round(inference_total / successful, 2)
            if successful else None
        ),
    }


def report_semantics(detail: dict) -> dict:
    """Return task-aware report wording while keeping persisted legacy data intact."""
    report = copy.deepcopy(detail.get("report") or {})
    task = detail.get("task") or {}
    if task.get("task_type") not in {"batch", "folder", "zip"}:
        return report
    if task.get("status") == "failed" or report.get("quality_conclusion") == "检测失败":
        return report

    results = detail.get("results") or []
    priorities = [RISK_PRIORITY.get(result.get("class_name"), 1) for result in results]
    highest_priority = max(priorities, default=0)
    if highest_priority >= 3:
        high_names = sorted({
            result.get("class_name_cn") or result.get("class_name") or "未知类别"
            for result in results
            if RISK_PRIORITY.get(result.get("class_name"), 1) >= 3
        })
        report.update({
            "quality_conclusion": "多图任务筛查未通过",
            "risk_level": "high",
            "risk_reason": f"一个或多个检测项检出高风险缺陷候选：{', '.join(high_names)}",
            "suggestion": (
                "隔离命中高风险缺陷候选的对应检测项并逐项人工复核；"
                "其他检测项是否流转应按批次质检规则决定，不得据此认定整批 PCB 全部不合格。"
            ),
        })
    elif highest_priority == 2:
        report.update({
            "quality_conclusion": "多图任务需重点复核",
            "risk_level": "medium",
            "risk_reason": "一个或多个检测项检出中风险缺陷候选",
            "suggestion": "按检测项逐一人工复核，并分别记录每张图像对应检测对象的处置结论。",
        })
    elif highest_priority == 1:
        report.update({
            "quality_conclusion": "多图任务需人工复核",
            "risk_level": "low",
            "risk_reason": "一个或多个检测项检出一般风险缺陷候选",
            "suggestion": "按检测项人工抽检并分别记录复核结论，不应把文件级检出换算为 PCB 件数良率。",
        })
    else:
        report.update({
            "quality_conclusion": "多图任务未检出疑似缺陷",
            "risk_level": None,
            "risk_reason": "成功处理的图像中未检出达到当前置信度阈值的缺陷候选",
            "suggestion": (
                "当前结论仅适用于图像级自动筛查；建议按批次抽检规则复核后再决定流转，"
                "不得将图像无检出率直接解释为 PCB 件数良率。"
            ),
        })
    failed_items = report_statistics(detail)["failed_items"]
    if failed_items:
        report["risk_reason"] = (
            f"{report.get('risk_reason') or '当前结论仅覆盖成功项'}；"
            f"另有 {failed_items} 个检测项处理失败"
        )
        report["suggestion"] = (
            f"{report.get('suggestion') or ''} 请重新检测失败项；"
            "结果补齐前不得作为整批放行依据。"
        ).strip()
    return report


def category_statistics(detail: dict) -> list[dict]:
    results = detail.get("results") or []
    grouped: dict[str, list[dict]] = defaultdict(list)
    for result in results:
        name = result.get("class_name_cn") or result.get("class_name") or "未知类别"
        grouped[name].append(result)
    total = max(1, len(results))
    rows = []
    for name, entries in grouped.items():
        confidences = [
            float(entry.get("confidence") or 0)
            for entry in entries
        ]
        priority = max(
            (RISK_PRIORITY.get(entry.get("class_name"), 1) for entry in entries),
            default=1,
        )
        rows.append({
            "name": name,
            "count": len(entries),
            "share": len(entries) / total,
            "average_confidence": sum(confidences) / len(confidences),
            "minimum_confidence": min(confidences),
            "maximum_confidence": max(confidences),
            "risk_level": RISK_LEVEL_TEXT.get(priority, "一般"),
        })
    return sorted(
        rows,
        key=lambda row: (
            {"高": 3, "中": 2, "一般": 1}.get(row["risk_level"], 0),
            row["count"],
        ),
        reverse=True,
    )


def describe_result_geometry(result: dict, task: dict) -> dict:
    bbox = result.get("bbox")
    width = result.get("image_width")
    height = result.get("image_height")
    image_size = task.get("image_size")
    if (not width or not height) and image_size:
        if isinstance(image_size, (list, tuple)) and len(image_size) >= 2:
            width, height = image_size[:2]
        else:
            try:
                width = height = float(image_size)
            except (TypeError, ValueError):
                pass
    position = "未记录"
    area_ratio = None
    if isinstance(bbox, (list, tuple)) and len(bbox) == 4 and width and height:
        x1, y1, x2, y2 = (float(value) for value in bbox)
        center_x = ((x1 + x2) / 2) / float(width)
        center_y = ((y1 + y2) / 2) / float(height)
        horizontal = "左" if center_x < 1 / 3 else "右" if center_x > 2 / 3 else "中"
        vertical = "上" if center_y < 1 / 3 else "下" if center_y > 2 / 3 else "中"
        if horizontal == vertical == "中":
            position = "中央区域"
        elif horizontal == "中":
            position = f"{vertical}部区域"
        elif vertical == "中":
            position = f"{horizontal}侧区域"
        else:
            position = f"{horizontal}{vertical}区域"
        area_ratio = (
            max(0.0, x2 - x1) * max(0.0, y2 - y1)
            / (float(width) * float(height))
        )
    confidence = float(result.get("confidence") or 0)
    confidence_level = "较高" if confidence >= 0.7 else "中等" if confidence >= 0.5 else "较低"
    priority = RISK_PRIORITY.get(result.get("class_name"), 1)
    review_priority = (
        "高"
        if priority >= 3 or confidence < 0.5
        else "中"
        if priority == 2 or confidence < 0.7
        else "一般"
    )
    return {
        "position": position,
        "area_ratio": area_ratio,
        "confidence_level": confidence_level,
        "review_priority": review_priority,
    }


def build_statistics_explanation(detail: dict) -> str:
    """根据结构化结果生成可复现的中文统计说明，作为 Agent 降级内容。"""
    stats = report_statistics(detail)
    report = report_semantics(detail)
    distribution = report.get("defect_summary") or {}
    total_items = stats["total_items"]
    coverage_text = f"{stats['coverage_rate']:.2f}%" if stats["coverage_rate"] is not None else "暂无"
    pass_text = f"{stats['pass_rate']:.2f}%" if stats["pass_rate"] is not None else "暂无"
    lines = [
        (
            f"- 本次共纳入 {total_items} 个图像检测项，成功处理 {stats['completed_items']} 个，"
            f"失败 {stats['failed_items']} 个，检测覆盖率为 {coverage_text}。"
        ),
        (
            f"- 成功处理项中，无目标检出项 {stats['clean_items']} 个、疑似缺陷检出项 "
            f"{stats['defective_items']} 个，图像级无检出率为 {pass_text}。"
        ),
    ]
    if distribution:
        total_defects = max(1, sum(int(count) for count in distribution.values()))
        top_name, top_count = max(distribution.items(), key=lambda item: int(item[1]))
        lines.append(
            f"- 共检出 {stats['total_defects']} 个缺陷候选，数量最多的类别为“{top_name}”"
            f"（{int(top_count)} 个，占 {int(top_count) / total_defects:.1%}）。"
        )
    else:
        lines.append("- 当前结果中未检测到达到置信度阈值的目标，仍需结合场景和图像质量判断。")
    if stats["average_confidence"] is not None:
        lines.append(
            f"- 检测结果平均置信度为 {stats['average_confidence']:.2%}，"
            f"范围为 {stats['minimum_confidence']:.2%}～{stats['maximum_confidence']:.2%}；"
            "低置信度或业务关键结果建议人工复核。"
        )
    elif stats["failed_items"]:
        lines.append("- 存在处理失败项，当前统计结论仅覆盖成功项，建议修复失败原因后重新检测。")
    if detail.get("task", {}).get("task_type") != "single":
        lines.append(
            "- 以上均为图像/检测项级统计；当前任务未记录 PCB 序列号或多视图归组信息，"
            "不能据此推断实际 PCB 件数或生产良率。"
        )
    return "\n".join(lines)


def build_rule_based_ai_analysis(detail: dict) -> dict:
    """Create evidence-linked fallback content without introducing facts outside results."""
    task = detail.get("task") or {}
    report = report_semantics(detail)
    results = detail.get("results") or []
    stats = report_statistics(detail)
    distribution = report.get("defect_summary") or {}
    task_type = task.get("task_type")
    if task_type == "single":
        summary = (
            f"本图共检出 {len(results)} 个达到当前置信度阈值的目标候选，自动筛查结论为“"
            f"{report.get('quality_conclusion') or '未记录'}”。"
            if results else
            f"本图未检出达到当前置信度阈值的目标候选，自动筛查结论为“{report.get('quality_conclusion') or '未记录'}”。"
        )
    else:
        summary = (
            f"本次多图任务成功处理 {stats['completed_items']}/{stats['total_items']} 个图像检测项，"
            f"共检出 {stats['total_defects']} 个缺陷候选，自动筛查结论为“"
            f"{report.get('quality_conclusion') or '未记录'}”。"
        )

    findings = []
    if distribution:
        top_name, top_count = max(distribution.items(), key=lambda item: int(item[1]))
        findings.append({
            "text": f"数量最多的检测类别为“{top_name}”，共 {int(top_count)} 个。",
            "evidence": f"缺陷类别统计：{top_name}={int(top_count)}",
        })
    if results:
        highest = max(results, key=lambda result: float(result.get("confidence") or 0))
        lowest = min(results, key=lambda result: float(result.get("confidence") or 0))
        findings.append({
            "text": (
                f"最高置信度结果为“{highest.get('class_name_cn') or highest.get('class_name') or '未知类别'}”"
                f"（{float(highest.get('confidence') or 0):.2%}），最低置信度为 {float(lowest.get('confidence') or 0):.2%}。"
            ),
            "evidence": "检测结果中的最高与最低置信度",
        })
    elif not findings:
        findings.append({
            "text": "当前结构化检测结果中没有达到阈值的目标候选记录。",
            "evidence": "检测目标数=0",
        })

    confidence_assessment = []
    if stats["average_confidence"] is not None:
        confidence_assessment.append({
            "text": (
                f"置信度结果中，较高置信度 {stats['high_confidence_results']} 个、"
                f"中等置信度 {stats['medium_confidence_results']} 个、"
                f"较低置信度 {stats['low_confidence_results']} 个。"
            ),
            "evidence": (
                f"置信度分层：较高={stats['high_confidence_results']}，"
                f"中等={stats['medium_confidence_results']}，"
                f"较低={stats['low_confidence_results']}"
            ),
        })
        if stats["near_threshold_results"]:
            confidence_assessment.append({
                "text": "部分结果接近当前置信度阈值，应结合原图重点确认。",
                "evidence": f"近阈值结果={stats['near_threshold_results']}",
            })
    else:
        confidence_assessment.append({
            "text": "当前没有可用于置信度质量分析的目标记录。",
            "evidence": "检测目标数=0",
        })

    review_focus = []
    low_confidence = [result for result in results if float(result.get("confidence") or 0) < 0.5]
    if low_confidence:
        review_focus.append({
            "text": "优先复核低于 50% 置信度的检测结果，确认是否存在误检或边界不清。",
            "evidence": f"低于 50% 置信度的结果共 {len(low_confidence)} 个",
        })
    if stats["failed_items"]:
        review_focus.append({
            "text": "失败项未进入有效统计，应在形成完整结论前重新检测。",
            "evidence": f"处理失败项={stats['failed_items']}",
        })
    if report.get("risk_reason"):
        review_focus.append({
            "text": "人工复核时应优先核对风险原因涉及的检测类别和对应标注区域。",
            "evidence": str(report["risk_reason"]),
        })
    if not review_focus:
        review_focus.append({
            "text": "建议抽查置信度最低的结果，并结合原图确认类别和标注区域。",
            "evidence": "当前检测结果与置信度记录",
        })

    actions = [{
        "text": report.get("suggestion") or "建议结合业务规则进行人工复核后再采取后续措施。",
        "evidence": report.get("risk_reason") or report.get("quality_conclusion") or "当前检测结论",
        "priority": "立即处置" if report.get("risk_level") == "high" else "优先复核",
    }]
    if task_type != "single" and stats["high_risk_items"]:
        preview = "、".join(stats["high_risk_item_names"][:5])
        actions.append({
            "text": (
                f"优先隔离并复核 {stats['high_risk_items']} 个高风险候选检出项；"
                f"示例文件：{preview}。"
            ),
            "evidence": (
                f"高风险候选检出项={stats['high_risk_items']}；"
                f"对应文件={preview}"
            ),
            "priority": "立即处置",
        })
    if low_confidence:
        actions.append({
            "text": "低置信度结果应在人工确认类别和边界后再纳入最终处置结论。",
            "evidence": f"较低置信度结果={stats['low_confidence_results']}",
            "priority": "优先复核",
        })
    if stats["failed_items"]:
        actions.append({
            "text": "重新检测失败项并补齐结果后，再更新整批质量结论。",
            "evidence": f"处理失败项={stats['failed_items']}",
            "priority": "补充检测",
        })
    if task_type != "single":
        actions.append({
            "text": "按检测项保留人工复核结论；在缺少 PCB 编号或多视图归组信息时，不生成 PCB 件数良率结论。",
            "evidence": "当前数据结构仅记录图像检测项，未记录 PCB 实物归组标识",
            "priority": "一般复核",
        })

    if task_type == "single":
        bbox_count = sum(
            isinstance(result.get("bbox"), (list, tuple))
            and len(result.get("bbox")) == 4
            for result in results
        )
        data_quality_notes = [{
            "text": (
                f"本图共保留 {len(results)} 条目标记录，其中 {bbox_count} 条包含完整边界框，"
                "可用于位置与面积占比复核。"
            ),
            "evidence": f"目标记录={len(results)}；完整边界框={bbox_count}",
        }]
    else:
        data_quality_notes = [{
            "text": (
                f"本次检测覆盖率为 {stats['coverage_rate']:.2f}%，"
                f"平均单项推理耗时为 {stats['average_inference_time_per_item']:.2f} ms。"
                if stats["coverage_rate"] is not None and stats["average_inference_time_per_item"] is not None
                else "当前任务缺少完整的覆盖率或单项耗时数据。"
            ),
            "evidence": (
                f"检测覆盖率={stats['coverage_rate']:.2f}%；"
                f"平均单项推理耗时={stats['average_inference_time_per_item']:.2f} ms"
                if stats["coverage_rate"] is not None and stats["average_inference_time_per_item"] is not None
                else "覆盖率或推理耗时未记录"
            ),
        }, {
            "text": "当前结果为图像/检测项级统计，不能直接换算为实际 PCB 件数或生产良率。",
            "evidence": "当前数据结构仅记录图像检测项，未记录 PCB 实物归组标识",
        }]
    return {
        "result_summary": {
            "text": summary,
            "evidence": (
                f"检测目标数={len(results)}"
                if task_type == "single"
                else f"成功处理项={stats['completed_items']}/{stats['total_items']}"
            ),
        },
        "key_findings": findings[:4],
        "confidence_assessment": confidence_assessment[:4],
        "review_focus": review_focus[:4],
        "recommended_actions": actions,
        "data_quality_notes": data_quality_notes,
    }


def select_representative_items(
    detail: dict,
    limit: int = REPRESENTATIVE_ITEM_LIMIT,
) -> list[dict]:
    """Select informative items instead of blindly taking the first N records."""
    items = detail.get("items") or []
    original_order = {_item_identity(item): index for index, item in enumerate(items)}
    results = detail.get("results") or []
    by_item: dict[object, list[dict]] = defaultdict(list)
    by_path: dict[str, list[dict]] = defaultdict(list)
    for result in results:
        if result.get("item_id") is not None:
            by_item[result["item_id"]].append(result)
        if result.get("image_path"):
            by_path[result["image_path"]].append(result)

    def item_results(item: dict) -> list[dict]:
        return by_item.get(item.get("id"), []) or by_path.get(item.get("input_path"), [])

    def key(item: dict):
        related = item_results(item)
        priority = max((RISK_PRIORITY.get(result.get("class_name"), 1) for result in related), default=0)
        confidence = max((float(result.get("confidence") or 0) for result in related), default=0)
        return (priority, int(item.get("defect_count") or len(related)), confidence, -int(item.get("item_index") or 0))

    selected: list[dict] = []
    selected_keys: set[object] = set()

    def add(item: dict) -> None:
        identity = _item_identity(item)
        if identity not in selected_keys and len(selected) < limit:
            selected_keys.add(identity)
            selected.append(item)

    # Guarantee one representative for each detected class first.
    class_candidates: dict[str, list[dict]] = defaultdict(list)
    for item in items:
        for result in item_results(item):
            class_candidates[result.get("class_name") or "unknown"].append(item)
    for class_name in sorted(class_candidates, key=lambda name: -RISK_PRIORITY.get(name, 1)):
        add(max(class_candidates[class_name], key=key))

    failed = [item for item in items if item.get("status") == "failed"]
    defective = [item for item in items if int(item.get("defect_count") or 0) > 0]
    clean = [item for item in items if item.get("status") == "completed" and int(item.get("defect_count") or 0) == 0]
    for item in sorted(failed, key=lambda entry: int(entry.get("item_index") or 0))[:2]:
        add(item)
    for item in sorted(defective, key=key, reverse=True):
        add(item)
    for item in sorted(clean, key=lambda entry: int(entry.get("item_index") or 0))[:2]:
        add(item)
    for item in sorted(items, key=key, reverse=True):
        add(item)
    return sorted(
        selected,
        key=lambda entry: original_order.get(
            _item_identity(entry),
            0,
        ),
    )


def _figure_bytes(draw: Callable) -> bytes:
    with _CHART_RENDER_LOCK:
        figure, axis = plt.subplots(figsize=(8, 4.5), dpi=140)
        try:
            draw(figure, axis)
            figure.tight_layout()
            buffer = io.BytesIO()
            figure.savefig(buffer, format="png", bbox_inches="tight", facecolor="white")
            return buffer.getvalue()
        finally:
            plt.close(figure)


def _dashboard_figure_bytes(draw: Callable) -> bytes:
    with _CHART_RENDER_LOCK:
        figure, axes = plt.subplots(2, 2, figsize=(12, 8), dpi=140)
        try:
            draw(figure, axes)
            figure.tight_layout(rect=(0, 0, 1, 0.96))
            buffer = io.BytesIO()
            figure.savefig(buffer, format="png", bbox_inches="tight", facecolor="white")
            return buffer.getvalue()
        finally:
            plt.close(figure)


def _empty_axis(axis, message: str) -> None:
    axis.text(0.5, 0.5, message, ha="center", va="center", transform=axis.transAxes)
    axis.set_xticks([])
    axis.set_yticks([])


def render_report_charts(detail: dict) -> dict[str, bytes]:
    if detail.get("task", {}).get("task_type") == "single":
        # 单图报告以原图、标注图和目标明细为核心；批次状态与趋势图没有解释价值。
        return {}
    results = detail.get("results") or []
    items = detail.get("items") or []
    class_counts = Counter(
        (result.get("class_name_cn") or result.get("class_name") or "未知类别")
        for result in results
    )
    confidences = [float(result["confidence"]) for result in results if result.get("confidence") is not None]
    status_counts = report_statistics(detail)
    ordered_items = sorted(
        items,
        key=lambda item: (
            item.get("item_index") is None,
            int(item.get("item_index") or 0),
            int(item.get("id") or 0),
        ),
    )
    item_positions = list(range(1, len(ordered_items) + 1))
    item_defects = [int(item.get("defect_count") or 0) for item in ordered_items]
    item_confidences = [
        float(item["average_confidence"]) if item.get("average_confidence") is not None else None
        for item in ordered_items
    ]

    def draw_defect_pie(axis, title="缺陷候选类别占比"):
        if class_counts:
            names, values = zip(*class_counts.most_common())
            axis.pie(
                values,
                labels=names,
                autopct=lambda percent: f"{percent:.1f}%" if percent >= 3 else "",
                startangle=90,
                counterclock=False,
                wedgeprops={"linewidth": 1, "edgecolor": "white"},
            )
            axis.axis("equal")
        else:
            _empty_axis(axis, "未检出缺陷候选")
        axis.set_title(title)

    def draw_status_donut(axis, title="图像级检出状态占比"):
        labels = ["无目标检出", "疑似缺陷检出", "处理失败"]
        values = [status_counts["clean_items"], status_counts["defective_items"], status_counts["failed_items"]]
        colors = ["#16a34a", "#f59e0b", "#dc2626"]
        visible = [(label, value, color) for label, value, color in zip(labels, values, colors) if value > 0]
        if visible:
            visible_labels, visible_values, visible_colors = zip(*visible)
            axis.pie(
                visible_values,
                labels=visible_labels,
                autopct=lambda percent: f"{percent:.1f}%",
                startangle=90,
                counterclock=False,
                colors=visible_colors,
                wedgeprops={"width": 0.42, "linewidth": 1, "edgecolor": "white"},
            )
            axis.text(0, 0, str(sum(visible_values)), ha="center", va="center", fontsize=16, fontweight="bold")
            axis.axis("equal")
        else:
            _empty_axis(axis, "暂无检测项统计")
        axis.set_title(title)

    def draw_item_trend(axis, title="逐检测项趋势", include_confidence=True):
        if not ordered_items:
            _empty_axis(axis, "暂无检测项序列")
            axis.set_title(title)
            return
        axis.plot(item_positions, item_defects, marker="o", linewidth=2, color="#7c3aed", label="缺陷候选数")
        axis.fill_between(item_positions, item_defects, alpha=0.12, color="#7c3aed")
        axis.set_xlabel("检测项序号")
        axis.set_ylabel("缺陷候选数")
        axis.set_ylim(bottom=0)
        axis.grid(alpha=0.2)
        axis.set_title(title)
        if len(item_positions) <= 12:
            axis.set_xticks(item_positions)
        if include_confidence and any(value is not None for value in item_confidences):
            confidence_axis = axis.twinx()
            confidence_axis.plot(
                item_positions,
                [value * 100 if value is not None else float("nan") for value in item_confidences],
                marker="s",
                linewidth=1.8,
                color="#0f766e",
                label="平均置信度",
            )
            confidence_axis.set_ylabel("平均置信度（%）")
            confidence_axis.set_ylim(0, 100)
            lines = axis.get_lines() + confidence_axis.get_lines()
            axis.legend(lines, [line.get_label() for line in lines], loc="upper left")
        else:
            axis.legend(loc="upper left")

    def defect_chart(_figure, axis):
        draw_defect_pie(axis)

    def confidence_chart(_figure, axis):
        if confidences:
            axis.hist(confidences, bins=min(10, max(3, len(confidences))), range=(0, 1), color="#0f766e", edgecolor="white")
            threshold = detail.get("task", {}).get("conf_threshold")
            if threshold is not None:
                axis.axvline(float(threshold), color="#dc2626", linestyle="--", label=f"置信度阈值={threshold}")
                axis.legend()
        else:
            _empty_axis(axis, "暂无置信度样本")
        axis.set_xlim(0, 1)
        axis.set_xlabel("置信度")
        axis.set_ylabel("候选结果数量")
        axis.set_title("置信度分布")
        axis.grid(axis="y", alpha=0.2)

    def status_chart(_figure, axis):
        draw_status_donut(axis)

    def item_trend_chart(_figure, axis):
        draw_item_trend(axis)

    def overview_chart(figure, axes):
        figure.suptitle("检测结果综合统计", fontsize=16, fontweight="bold")
        draw_status_donut(axes[0, 0], "图像级检出状态占比")
        draw_defect_pie(axes[0, 1], "缺陷候选类别占比")
        draw_item_trend(axes[1, 0], "逐检测项候选数量趋势", include_confidence=False)
        confidence_axis = axes[1, 1]
        if confidences:
            result_positions = list(range(1, len(confidences) + 1))
            confidence_axis.plot(result_positions, [value * 100 for value in confidences], marker="o", color="#0f766e")
            threshold = detail.get("task", {}).get("conf_threshold")
            if threshold is not None:
                confidence_axis.axhline(float(threshold) * 100, color="#dc2626", linestyle="--", label="置信度阈值")
                confidence_axis.legend(loc="lower right")
            confidence_axis.set_ylim(0, 100)
            confidence_axis.set_xlabel("检测结果序号")
            confidence_axis.set_ylabel("置信度（%）")
            confidence_axis.grid(alpha=0.2)
        else:
            _empty_axis(confidence_axis, "暂无置信度样本")
        confidence_axis.set_title("置信度趋势")

    return {
        "overview_dashboard.png": _dashboard_figure_bytes(overview_chart),
        "defect_distribution.png": _figure_bytes(defect_chart),
        "confidence_distribution.png": _figure_bytes(confidence_chart),
        "item_status_summary.png": _figure_bytes(status_chart),
        "item_detection_trend.png": _figure_bytes(item_trend_chart),
    }


def _append_related_charts(
    lines: list[str],
    chart_urls: dict[str, str] | None,
    public_base_url: str | None,
    chart_names: tuple[str, ...],
) -> None:
    if not chart_urls:
        return
    for name in chart_names:
        url = _absolute_media_url(chart_urls.get(name), public_base_url)
        if not url:
            continue
        title = CHART_METADATA[name]["title"]
        lines.extend([
            f"**相关图表：{title}**",
            "",
            f"![{title}]({url})",
            "",
        ])


def _append_ai_analysis(
    lines: list[str],
    analysis: dict,
    source: str | None,
    heading: str,
    chart_urls: dict[str, str] | None = None,
    public_base_url: str | None = None,
) -> None:
    lines.extend([heading, "", "**检测结果摘要**", ""])
    summary = analysis.get("result_summary") or {}
    if isinstance(summary, str):
        summary = {"text": summary, "evidence": "当前结构化检测结果"}
    lines.extend([
        str(summary.get("text") or "暂无可解读的检测结果。"),
        "",
        f"> 依据：{_markdown_cell(_humanize_evidence(summary.get('evidence')))}",
        "",
    ])
    _append_related_charts(
        lines,
        chart_urls,
        public_base_url,
        ("overview_dashboard.png", "item_status_summary.png"),
    )
    chart_groups = {
        "key_findings": ("defect_distribution.png",),
        "confidence_assessment": (
            "confidence_distribution.png",
            "item_detection_trend.png",
        ),
    }
    for title, field in (
        ("**关键发现**", "key_findings"),
        ("**置信度与可靠性评估**", "confidence_assessment"),
        ("**人工复核重点**", "review_focus"),
        ("**建议措施**", "recommended_actions"),
        ("**数据质量与适用范围**", "data_quality_notes"),
    ):
        lines.extend([title, ""])
        entries = analysis.get(field) or []
        if not entries:
            lines.extend(["- 暂无。", ""])
            continue
        for entry in entries:
            if isinstance(entry, str):
                lines.append(f"- {entry}")
            else:
                priority = (
                    f"【{entry.get('priority')}】"
                    if entry.get("priority") else ""
                )
                lines.append(
                    f"- {priority}{_markdown_cell(entry.get('text'))}"
                    f"（依据：{_markdown_cell(_humanize_evidence(entry.get('evidence')))}）"
                )
        lines.append("")
        _append_related_charts(
            lines,
            chart_urls,
            public_base_url,
            chart_groups.get(field, ()),
        )
    lines.extend([
        (
            "> 内容来源：AIGC Agent；每条内容均绑定本报告中的结构化检测证据。"
            if source == "agent"
            else "> 内容来源：规则化降级解读；所有内容均由本报告检测结果直接计算。"
        ),
        "",
    ])


def _render_single_image_markdown(
    detail: dict,
    public_base_url: str | None = None,
) -> bytes:
    task = detail["task"]
    report = report_semantics(detail)
    model = detail.get("model_version") or {}
    items = detail.get("items") or []
    results = detail.get("results") or []
    item = items[0] if items else {}
    analysis = report.get("aigc_analysis") or build_rule_based_ai_analysis(detail)
    source = report.get("aigc_analysis_source")
    risk_text = {"low": "低风险", "medium": "中风险", "high": "高风险"}.get(
        report.get("risk_level"), "无"
    )
    model_text = f"{model.get('model_name')} / {model.get('version')}" if model else "未记录"
    average_confidence = (
        sum(float(result.get("confidence") or 0) for result in results) / len(results)
        if results else None
    )
    lines = [
        f"# {_report_title(detail)} {report['report_uuid']}",
        "",
        f"> 报告格式版本：{detail.get('report_version') or REPORT_VERSION}",
        "",
        "## 一、单图检测概览",
        "",
        "| 项目 | 内容 | 项目 | 内容 |",
        "|---|---|---|---|",
        f"| 检测场景 | {_markdown_cell(task.get('scene_name'))} | 自动筛查结论 | **{_markdown_cell(report.get('quality_conclusion'))}** |",
        f"| 缺陷候选数 | {len(results)} | 风险等级 | **{risk_text}** |",
        f"| 平均置信度 | {_format_percent(average_confidence)} | 推理耗时 | {_format_ms(item.get('inference_time') or task.get('total_inference_time'))} |",
        f"| 模型版本 | {_markdown_cell(model_text)} | 完成时间 | {_format_datetime(task.get('completed_at'))} |",
        "",
    ]
    _append_ai_analysis(lines, analysis, source, "## 二、AIGC 检测结果解读")
    lines.extend(["## 三、检测图像与目标明细", ""])
    input_url = _absolute_media_url(
        item.get("input_url") or task.get("input_url"),
        public_base_url,
    )
    result_url = _absolute_media_url(
        item.get("result_url") or task.get("result_url"),
        public_base_url,
    )
    if input_url:
        lines.extend([
            "**原始图像**",
            "",
            f"![原始图像 1]({input_url})",
            "",
            f"[在新窗口打开原始图像]({input_url})",
            "",
        ])
    if result_url:
        lines.extend([
            "**检测标注图**",
            "",
            f"![检测标注图 1]({result_url})",
            "",
            f"[在新窗口打开检测标注图]({result_url})",
            "",
        ])
    if not input_url and not result_url:
        lines.extend(["当前报告未包含可访问的原图或标注图。", ""])
    if results:
        lines.extend([
            "| # | 类别 | 类别代码 | 置信度 | 置信度等级 | 位置 | 面积占比 | 复核优先级 | 边界框 x1,y1,x2,y2 | 推理耗时 |",
            "|---:|---|---|---:|---|---|---:|---|---|---:|",
        ])
        for index, result in enumerate(results, start=1):
            geometry = describe_result_geometry(result, task)
            lines.append(
                f"| {index} | {_markdown_cell(result.get('class_name_cn') or result.get('class_name'))} | "
                f"{_markdown_cell(result.get('class_name'))} | {float(result.get('confidence') or 0):.2%} | "
                f"{geometry['confidence_level']} | {geometry['position']} | "
                f"{_format_percent(geometry['area_ratio'])} | {geometry['review_priority']} | "
                f"{_format_bbox(result.get('bbox'))} | {_format_ms(result.get('inference_time'))} |"
            )
        lines.append("")
    else:
        lines.extend([
            "未检出达到当前置信度阈值的目标候选；这不代表图像中绝对不存在异常。",
            "",
        ])
    lines.extend([
        "## 四、检测参数",
        "",
        "| 参数 | 数值 | 参数 | 数值 |",
        "|---|---:|---|---:|",
        f"| 置信度阈值 | {_markdown_cell(task.get('conf_threshold'))} | IoU 阈值 | {_markdown_cell(task.get('iou_threshold'))} |",
        f"| 输入尺寸 | {_markdown_cell(task.get('image_size'))} | 模型版本 | {_markdown_cell(model_text)} |",
        "",
        "## 五、指标定义与适用边界",
        "",
        "- 置信度等级定义：较高为 ≥70%，中等为 50%～70%，较低为 <50%；该分层用于复核排序，不代表检测准确率。",
        "- 目标位置和面积占比根据检测框与输入尺寸计算；边界框越界、裁剪或尺寸缺失会影响几何指标。",
        "- 复核优先级综合缺陷类别风险规则和置信度生成，仅用于安排人工检查顺序。",
        "- 报告中的“缺陷”均表示模型检出的缺陷候选，最终缺陷性质应由人工复核确认。",
        "- AIGC 内容仅基于本次结构化检测结果生成，不读取原始图片，也不补充检测证据之外的结论。",
        "- 自动检测结果用于辅助分析；低置信度、边界模糊或业务关键结果应由人工复核。",
        "- “未检测到目标”仅表示当前模型和阈值未返回目标，不代表绝对不存在异常。",
    ])
    return ("\n".join(lines) + "\n").encode("utf-8")


def render_report_markdown(
    detail: dict,
    public_base_url: str | None = None,
    chart_urls: dict[str, str] | None = None,
    representative_limit: int = REPRESENTATIVE_ITEM_LIMIT,
) -> bytes:
    task = detail["task"]
    report = report_semantics(detail)
    if task.get("task_type") == "single":
        return _render_single_image_markdown(detail, public_base_url=public_base_url)
    model = detail.get("model_version") or {}
    items = detail.get("items") or []
    results = detail.get("results") or []
    stats = report_statistics(detail)
    failed = [item for item in items if item.get("status") == "failed"]
    highest = max(
        results,
        key=lambda result: (RISK_PRIORITY.get(result.get("class_name"), 1), float(result.get("confidence") or 0)),
        default=None,
    )
    highest_text = (
        f"{highest.get('class_name_cn') or highest.get('class_name')}（置信度 {float(highest.get('confidence') or 0):.2%}）"
        if highest else "无"
    )
    model_text = f"{model.get('model_name')} / {model.get('version')}" if model else "未记录"
    risk_text = {"low": "低风险", "medium": "中风险", "high": "高风险"}.get(report.get("risk_level"), "无")
    high_risk_preview = stats["high_risk_item_names"][:10]
    high_risk_preview_text = "、".join(high_risk_preview) if high_risk_preview else "无"
    if len(stats["high_risk_item_names"]) > len(high_risk_preview):
        high_risk_preview_text += f" 等 {len(stats['high_risk_item_names'])} 项"
    lines = [
        f"# {_report_title(detail)} {report['report_uuid']}",
        "",
        f"> 报告格式版本：{detail.get('report_version') or REPORT_VERSION}",
        "",
        "## 一、任务概览",
        "",
        "| 项目 | 内容 | 项目 | 内容 |",
        "|---|---|---|---|",
        f"| 检测任务 | {_markdown_cell(task['id'])} | 检测用户 | {_markdown_cell(task.get('username') or task.get('user_id'))} |",
        f"| 检测场景 | {_markdown_cell(task.get('scene_name'))} | 检测模式 | {_task_type_label(task.get('task_type'))} |",
        f"| 开始时间 | {_format_datetime(task.get('created_at'))} | 完成时间 | {_format_datetime(task.get('completed_at'))} |",
        f"| 模型版本 | {_markdown_cell(model_text)} | 图像检测项数 | {_markdown_cell(task.get('total_images', 0))} |",
        f"| 置信度阈值 | {_markdown_cell(task.get('conf_threshold'))} | IoU 阈值 | {_markdown_cell(task.get('iou_threshold'))} |",
        f"| 推理总耗时 | {_format_ms(task.get('total_inference_time'))} | 失败项数 | {len(failed)} |",
        "",
        "## 二、多图任务自动筛查结论与处置建议",
        "",
        "| 结论项 | 内容 |",
        "|---|---|",
        f"| 自动筛查结论 | **{_markdown_cell(report['quality_conclusion'])}** |",
        f"| 风险等级 | **{risk_text}** |",
        f"| 缺陷候选总数 | {report['defect_count']} |",
        f"| 高风险类别中最高置信度结果 | {_markdown_cell(highest_text)} |",
        f"| 风险原因 | {_markdown_cell(report.get('risk_reason') or '无')} |",
        f"| 处理建议 | {_markdown_cell(report.get('suggestion') or '无')} |",
        "",
        "### 2.1 结论适用范围与高风险检测项",
        "",
        "> 本结论是图像/检测项级自动筛查结果。当前任务未记录 PCB 序列号、批次实物编号或多视图归组信息，",
        "> 因此不能把图像数量直接解释为 PCB 件数，也不能据此计算生产良率或认定整批 PCB 全部不合格。",
        "",
        "| 高风险候选检出项 | 中风险候选检出项 | 一般风险候选检出项 |",
        "|---:|---:|---:|",
        f"| {stats['high_risk_items']} | {stats['medium_risk_items']} | {stats['general_risk_items']} |",
        "",
        f"- 高风险候选对应检测项（最多展示 10 项）：{_markdown_cell(high_risk_preview_text)}",
        "- 完整的逐项结果和文件映射请查看本报告代表项及 ZIP 归档中的 `results.json`。",
        "",
        "## 三、结果统计",
        "",
        "| 指标 | 数值 | 指标 | 数值 |",
        "|---|---:|---|---:|",
        f"| 成功处理项 | {stats['completed_items']} | 失败项 | {stats['failed_items']} |",
        f"| 无目标检出项 | {stats['clean_items']} | 疑似缺陷检出项 | {stats['defective_items']} |",
        f"| 图像级无检出率 | {_format_percent(stats['pass_rate'] / 100 if stats['pass_rate'] is not None else None)} | 检测覆盖率 | {_format_percent(stats['coverage_rate'] / 100 if stats['coverage_rate'] is not None else None)} |",
        f"| 平均置信度 | {_format_percent(stats['average_confidence'])} | 置信度范围 | {_format_percent(stats['minimum_confidence'])} ～ {_format_percent(stats['maximum_confidence'])} |",
        "",
        "### 3.1 置信度与检测项风险指标",
        "",
        "| 指标 | 数值 | 指标 | 数值 |",
        "|---|---:|---|---:|",
        f"| 较高置信度（≥70%） | {stats['high_confidence_results']} | 中等置信度（50%～70%） | {stats['medium_confidence_results']} |",
        f"| 较低置信度（<50%） | {stats['low_confidence_results']} | 近阈值结果 | {stats['near_threshold_results']} |",
        f"| 疑似缺陷检出项比例 | {_format_percent(stats['defective_item_rate'] / 100 if stats['defective_item_rate'] is not None else None)} | 多候选检测项 | {stats['multiple_defect_items']} |",
        f"| 每个检出项平均候选数 | {_markdown_cell(stats['average_defects_per_defective_item'])} | 单项最大候选数 | {stats['max_defects_per_item']} |",
        f"| 最大候选数检测项 | {_markdown_cell(stats['max_defect_item_name'])} | 平均单项推理耗时 | {_format_ms(stats['average_inference_time_per_item'])} |",
        "",
        "### 3.2 统计解读",
        "",
    ]
    explanation = report.get("statistics_explanation") or build_statistics_explanation(detail)
    explanation_source = report.get("statistics_explanation_source")
    lines.extend([
        explanation,
        "",
        (
            "> 说明来源：统计解读 Agent 根据本报告聚合数据自动生成；内容仅用于辅助分析。"
            if explanation_source == "agent"
            else "> 说明来源：系统根据本报告聚合数据自动生成；模型不可用时仍可稳定输出。"
        ),
        "",
    ])
    analysis = report.get("aigc_analysis") or build_rule_based_ai_analysis(detail)
    _append_ai_analysis(
        lines,
        analysis,
        report.get("aigc_analysis_source"),
        "### 3.3 AIGC 检测结果解读",
        chart_urls=chart_urls,
        public_base_url=public_base_url,
    )
    lines.extend([
        "### 3.4 缺陷候选类别统计明细",
        "",
        "| 缺陷候选类别 | 规则风险级别 | 数量 | 占比 | 平均置信度 | 置信度范围 |",
        "|---|---|---:|---:|---:|---:|",
    ])
    category_rows = category_statistics(detail)
    if category_rows:
        lines.extend(
            f"| {_markdown_cell(row['name'])} | {row['risk_level']} | {row['count']} | "
            f"{row['share']:.1%} | {row['average_confidence']:.2%} | "
            f"{row['minimum_confidence']:.2%}～{row['maximum_confidence']:.2%} |"
            for row in category_rows
        )
    else:
        lines.append("| 无 | - | 0 | 0% | - | - |")

    display_items = select_representative_items(detail, representative_limit)
    lines.extend(["", "## 四、代表性检测图像与逐文件明细", ""])
    if len(items) > len(display_items):
        lines.append("> 为控制报告长度，代表项优先嵌入检测标注图，原始图像保留为可点击链接。")
        lines.extend([
            f"> 本任务共 {len(items)} 个文件，报告按风险、缺陷类别、置信度和处理状态选择 {len(display_items)} 个代表项；完整结果见归档中的 `results.json`。",
            "",
        ])
    if not display_items and task.get("task_type") == "camera":
        lines.append(f"浏览器摄像头会话共处理 {task.get('total_images', 0)} 帧。")
    elif not display_items:
        display_items = [{
            "id": None,
            "file_name": os.path.basename(task.get("input_path") or "检测输入"),
            "input_path": task.get("input_path"),
            "input_url": task.get("input_url"),
            "result_url": task.get("result_url"),
            "status": task.get("status"),
            "defect_count": report.get("defect_count", 0),
            "average_confidence": None,
            "inference_time": task.get("total_inference_time"),
            "error_message": task.get("error_message"),
        }]

    results_by_item: dict[object, list[dict]] = defaultdict(list)
    results_by_path: dict[str, list[dict]] = defaultdict(list)
    for result in results:
        results_by_item[result.get("item_id")].append(result)
        if result.get("image_path"):
            results_by_path[result["image_path"]].append(result)
    for index, item in enumerate(display_items, start=1):
        item_results = results_by_item.get(item.get("id"), []) or results_by_path.get(item.get("input_path"), [])
        lines.extend([
            f"### 4.{index} {_markdown_cell(item.get('file_name') or f'文件 {index}')}",
            "",
            "| 状态 | 缺陷候选数 | 平均置信度 | 推理耗时 |",
            "|---|---:|---:|---:|",
            f"| {_status_label(item.get('status'))} | {item.get('defect_count') or 0} | {_format_percent(item.get('average_confidence'))} | {_format_ms(item.get('inference_time'))} |",
            "",
        ])
        if item.get("error_message"):
            lines.extend([f"> 检测失败原因：{_markdown_cell(item['error_message'])}", ""])
        input_url = _absolute_media_url(item.get("input_url"), public_base_url)
        result_url = _absolute_media_url(item.get("result_url"), public_base_url)
        if input_url:
            if result_url:
                lines.extend([f"[查看原始图像]({input_url})", ""])
            else:
                lines.extend([
                    "**原始图像**", "", f"![原始图像 {index}]({input_url})", "",
                    f"[在新窗口打开原始图像]({input_url})", "",
                ])
        if result_url:
            lines.extend([
                "**检测标注图**", "", f"![检测标注图 {index}]({result_url})", "",
                f"[在新窗口打开检测标注图]({result_url})", "",
            ])
        if item_results:
            lines.extend([
                "**检测框明细**", "",
                "| # | 类别 | 英文类别 | 置信度 | 边界框 x1,y1,x2,y2 | 推理耗时 |",
                "|---:|---|---|---:|---|---:|",
            ])
            for result_index, result in enumerate(item_results, start=1):
                lines.append(
                    f"| {result_index} | {_markdown_cell(result.get('class_name_cn') or result.get('class_name'))} | "
                    f"{_markdown_cell(result.get('class_name'))} | {float(result.get('confidence') or 0):.2%} | "
                    f"{_format_bbox(result.get('bbox'))} | {_format_ms(result.get('inference_time'))} |"
                )
            lines.append("")
        elif item.get("status") == "completed":
            lines.extend(["未检出达到当前置信度阈值的目标候选。", ""])

    lines.extend(["## 五、模型与可复现信息", ""])
    if model:
        lines.extend([
            "| 模型 | Precision | Recall | mAP@0.50 | mAP@0.50:0.95 |",
            "|---|---:|---:|---:|---:|",
            f"| {_markdown_cell(model_text)} | {_format_percent(model.get('precision'))} | {_format_percent(model.get('recall'))} | {_format_percent(model.get('map50'))} | {_format_percent(model.get('map50_95'))} |",
            "",
            "> 上述指标来自模型评估集，用于说明模型能力，不等同于本次检测任务的准确率。",
            "",
        ])
    else:
        lines.extend(["本任务未记录可追溯的模型版本和评估指标。", ""])
    lines.extend([
        "## 六、指标定义、适用边界与复核要求",
        "",
        "- 缺陷候选类别数量按模型返回目标计数；疑似缺陷检出项比例按成功处理文件计数，两者不能直接互换。",
        "- 图像级无检出率表示成功处理项中未返回目标候选的文件占比，不等同于生产良率或模型准确率。",
        "- 当前数据没有 PCB 序列号或多视图归组标识，图像检测项数不能直接换算为实际 PCB 件数。",
        "- 置信度等级定义：较高为 ≥70%，中等为 50%～70%，较低为 <50%；近阈值结果应优先人工确认。",
        "- 类别风险级别来自当前业务规则，用于复核排序，不替代企业质量标准或最终放行判定。",
        "- 统计结论仅覆盖成功处理的输入；失败项不会被当作无目标检出项。",
        "- “未检出目标候选”表示在当前模型、图像尺寸及置信度/IoU 阈值下未返回目标，不代表绝对不存在异常。",
        "- 自动检测结果用于辅助分析；高风险、低置信度、边界模糊或业务关键结果应由人工复核。",
        "- Markdown 在线图片使用临时签名地址；需要长期保存时请下载 ZIP 归档。",
    ])
    return ("\n".join(lines) + "\n").encode("utf-8")


def persist_online_report(detail: dict, storage_client, public_base_url: str | None = None) -> tuple[bytes, str, dict[str, str]]:
    """Generate and persist the same report and chart set used by the download API."""
    task = detail["task"]
    report = detail["report"]
    prefix = f"reports/{task['user_id']}/{task['id']}/{report['report_uuid']}"
    chart_urls: dict[str, str] = {}
    for name, content in render_report_charts(detail).items():
        chart_urls[name] = storage_client.upload_bytes(f"{prefix}/charts/{name}", content, "image/png")
    markdown = render_report_markdown(detail, public_base_url=public_base_url, chart_urls=chart_urls)
    report_path = f"{prefix}.md"
    storage_client.upload_bytes(report_path, markdown, "text/markdown; charset=utf-8")
    return markdown, report_path, chart_urls


def build_report_archive(detail: dict, storage_client=None, max_media_bytes: int = 100 * 1024 * 1024) -> bytes:
    """Build a portable ZIP containing report text, charts, JSON, and representative media."""
    archive_detail = copy.deepcopy(detail)
    representative = select_representative_items(archive_detail)
    representative_ids = {_item_identity(item) for item in representative}
    chart_bytes = render_report_charts(archive_detail)
    chart_urls = {name: f"charts/{name}" for name in chart_bytes}
    media_files: list[tuple[str, bytes]] = []
    media_bytes = 0
    skipped_media: list[str] = []

    for ordinal, item in enumerate(archive_detail.get("items") or [], start=1):
        identity = _item_identity(item)
        if identity not in representative_ids:
            item["input_url"] = None
            item["result_url"] = None
            continue
        for field, url_field, label in (("input_path", "input_url", "original"), ("result_path", "result_url", "annotated")):
            object_path = item.get(field)
            if not object_path or object_path.startswith(("http://", "https://", "/api/")) or os.path.isabs(object_path):
                item[url_field] = None
                continue
            if storage_client is None:
                skipped_media.append(object_path)
                item[url_field] = None
                continue
            try:
                content = storage_client.download_bytes(object_path)
            except Exception:
                skipped_media.append(object_path)
                item[url_field] = None
                continue
            if media_bytes + len(content) > max_media_bytes:
                skipped_media.append(object_path)
                item[url_field] = None
                continue
            extension = Path(object_path).suffix.lower() or mimetypes.guess_extension("image/jpeg") or ".jpg"
            filename = _safe_filename(item.get("file_name") or f"item-{ordinal}", f"item-{ordinal}")
            archive_path = f"images/{ordinal:02d}_{label}_{Path(filename).stem}{extension}"
            media_files.append((archive_path, content))
            media_bytes += len(content)
            item[url_field] = archive_path

    markdown = render_report_markdown(archive_detail, chart_urls=chart_urls)
    manifest = {
        "report_version": REPORT_VERSION,
        "report_uuid": detail.get("report", {}).get("report_uuid"),
        "task_id": detail.get("task", {}).get("id"),
        "statistics": report_statistics(detail),
        "statistics_explanation": detail.get("report", {}).get("statistics_explanation"),
        "statistics_explanation_source": detail.get("report", {}).get("statistics_explanation_source"),
        "aigc_analysis": detail.get("report", {}).get("aigc_analysis"),
        "aigc_analysis_source": detail.get("report", {}).get("aigc_analysis_source"),
        "charts": list(chart_bytes),
        "chart_catalog": [
            {"filename": name, **CHART_METADATA[name]}
            for name in chart_bytes
        ],
        "media_files": [name for name, _ in media_files],
        "skipped_media": skipped_media,
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        archive.writestr("report.md", markdown)
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        archive.writestr("results.json", json.dumps(detail, ensure_ascii=False, indent=2, default=str))
        for name, content in chart_bytes.items():
            archive.writestr(f"charts/{name}", content)
        for name, content in media_files:
            archive.writestr(name, content)
    return buffer.getvalue()
