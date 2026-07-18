"""Rich detection report generation and portable archive tests."""

from __future__ import annotations

import io
import json
import struct
import zipfile
from types import SimpleNamespace

from app.services.quality_service import evaluate_quality
from app.api.auth import get_current_user
from app.services.history_service import history_service
from app.services.report_service import (
    CHART_FILENAMES,
    CHART_METADATA,
    build_rule_based_ai_analysis,
    build_statistics_explanation,
    build_report_archive,
    persist_online_report,
    render_report_charts,
    render_report_markdown,
    select_representative_items,
)
from app.services.report_narrative_service import (
    generate_report_ai_content,
    generate_statistics_explanation,
)
from main import app


def _detail(item_count: int = 3) -> dict:
    items = [
        {
            "id": index + 1,
            "item_index": index,
            "file_name": f"board-{index}.jpg",
            "input_path": f"detections/1/input/board-{index}.jpg",
            "input_url": f"/input/{index}",
            "result_path": f"detections/1/output/board-{index}.jpg",
            "result_url": f"/result/{index}",
            "status": "completed",
            "defect_count": 0,
            "average_confidence": None,
            "inference_time": 5.0,
            "error_message": None,
        }
        for index in range(item_count)
    ]
    items[-1].update(defect_count=1, average_confidence=0.93)
    return {
        "report_version": "2.0",
        "task": {
            "id": 1,
            "user_id": 7,
            "username": "tester",
            "task_type": "batch",
            "status": "completed",
            "scene_name": "PCB 缺陷检测",
            "total_images": item_count,
            "total_inference_time": item_count * 5.0,
            "conf_threshold": 0.25,
            "iou_threshold": 0.45,
            "created_at": "2026-07-18T02:21:24.687771",
            "completed_at": "2026-07-18T02:21:29.390535",
        },
        "model_version": {
            "model_name": "pcb-yolo",
            "version": "v1",
            "precision": 0.91,
            "recall": 0.88,
            "map50": 0.94,
            "map50_95": 0.72,
        },
        "items": items,
        "results": [
            {
                "item_id": item_count,
                "image_path": items[-1]["input_path"],
                "class_name": "short",
                "class_name_cn": "短路",
                "confidence": 0.93,
                "bbox": [1, 2, 30, 40],
                "image_width": 640,
                "image_height": 480,
                "inference_time": 5.0,
            }
        ],
        "report": {
            "report_uuid": "report-1",
            "quality_conclusion": "不合格",
            "risk_level": "high",
            "defect_count": 1,
            "defect_summary": {"短路": 1},
            "risk_reason": "检测到高风险缺陷：短路",
            "suggestion": "立即隔离并人工复核",
        },
    }


def _single_detail() -> dict:
    detail = _detail(1)
    detail["task"]["task_type"] = "single"
    detail["task"]["image_size"] = 640
    return detail


class _Storage:
    def __init__(self):
        self.uploads = {}

    def upload_bytes(self, object_name, content, content_type):
        self.uploads[object_name] = (content, content_type)
        return f"https://files.example/{object_name}"

    def download_bytes(self, object_name):
        return f"media:{object_name}".encode()


def test_representative_selection_keeps_late_high_risk_item():
    detail = _detail(25)
    selected = select_representative_items(detail, limit=20)
    assert any(item["id"] == 25 for item in selected)
    assert len(selected) == 20


def test_report_charts_are_valid_png_files():
    charts = render_report_charts(_detail())
    assert set(charts) == set(CHART_FILENAMES)
    assert all(content.startswith(b"\x89PNG\r\n\x1a\n") for content in charts.values())
    assert {metadata["type"] for metadata in CHART_METADATA.values()} == {
        "pie", "histogram", "donut", "line", "dashboard"
    }
    assert all(any("\u4e00" <= char <= "\u9fff" for char in metadata["title"])
               for metadata in CHART_METADATA.values())
    regular_width, regular_height = struct.unpack(">II", charts["defect_distribution.png"][16:24])
    dashboard_width, dashboard_height = struct.unpack(">II", charts["overview_dashboard.png"][16:24])
    assert dashboard_width > regular_width
    assert dashboard_height > regular_height


def test_statistics_explanation_has_stable_fallback_and_markdown_section():
    detail = _detail()
    explanation = build_statistics_explanation(detail)
    assert "检测覆盖率" in explanation
    assert "短路" in explanation
    assert "图像级无检出率" in explanation
    assert "不能据此推断实际 PCB 件数" in explanation
    markdown = render_report_markdown(detail).decode()
    assert "### 3.1 置信度与检测项风险指标" in markdown
    assert "### 3.2 统计解读" in markdown
    assert "### 3.3 AIGC 检测结果解读" in markdown
    assert explanation in markdown
    assert "说明来源：系统根据本报告聚合数据自动生成" in markdown
    assert "依据：缺陷类别统计：短路=1" in markdown


def test_statistics_explanation_agent_receives_aggregate_data_only(monkeypatch):
    calls = []

    class FakeLLM:
        def invoke(self, messages):
            calls.append(messages)
            return SimpleNamespace(content=(
                "- 检测覆盖率完整，合格率为 66.7%。\n"
                "- 有缺陷项占比较低，但短路属于高风险类别。\n"
                "- 平均置信度较高，仍建议人工复核关键结果。\n"
                "- 产品不符合出货质量标准，必须立即报废。"
            ))

    monkeypatch.setattr(
        "app.services.report_narrative_service.settings.REPORT_AGENT_EXPLANATION_ENABLED",
        True,
    )
    narrative = generate_statistics_explanation(_detail(), llm=FakeLLM())
    assert narrative.source == "agent"
    assert "检测覆盖率完整" in narrative.text
    assert "图像级无检出率为 66.7%" in narrative.text
    assert "出货" not in narrative.text
    assert "报废" not in narrative.text
    prompt = calls[0][1].content
    assert "statistics" in prompt
    assert "detections/1/input" not in prompt
    assert "bbox" not in prompt
    assert "base64" not in prompt.lower()


def test_structured_aigc_requires_exact_detection_evidence(monkeypatch):
    calls = []

    class FakeLLM:
        def invoke(self, messages):
            calls.append(messages)
            return SimpleNamespace(content=json.dumps({
                "statistics_explanation": [
                    "本任务检测覆盖率完整。",
                    "主要检测类别为短路。",
                ],
                "result_summary": {
                    "text": "本次共检出 1 个缺陷候选。",
                    "evidence": "缺陷候选数=1",
                },
                "key_findings": [{
                    "text": "检测类别为短路。",
                    "evidence": "类别统计：短路=1",
                }],
                "review_focus": [{
                    "text": "优先复核置信度最低的结果。",
                    "evidence": "最低置信度=93.00%",
                }],
                "recommended_actions": [
                    {
                        "text": "按系统建议进行人工复核。",
                        "evidence": "系统建议=立即隔离并人工复核",
                    },
                    {
                        "text": "产品不符合出货标准，应立即报废。",
                        "evidence": "不存在的检测证据",
                    },
                ],
            }, ensure_ascii=False))

    monkeypatch.setattr(
        "app.services.report_narrative_service.settings.REPORT_AGENT_EXPLANATION_ENABLED",
        True,
    )
    content = generate_report_ai_content(_detail(), llm=FakeLLM())
    assert content.source == "agent"
    assert content.analysis["version"] == "2.5"
    assert content.analysis["result_summary"]["evidence"] == "缺陷候选数=1"
    assert content.analysis["key_findings"][0]["evidence"] == "类别统计：短路=1"
    rendered = json.dumps(content.analysis, ensure_ascii=False)
    assert "出货" not in rendered
    assert "报废" not in rendered
    prompt = calls[0][1].content
    assert "结果#1：类别=短路" in prompt
    assert "位置=左上区域" in prompt
    assert "面积占比未记录" not in prompt
    assert "detections/1/input" not in prompt
    assert "bbox" not in prompt
    assert "base64" not in prompt.lower()


def test_qwen_report_llm_enables_thinking_without_exposing_reasoning(monkeypatch):
    import app.services.report_narrative_service as narrative_module

    captured = {}

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(narrative_module, "ChatOpenAI", FakeChatOpenAI)
    monkeypatch.setattr(narrative_module.settings, "QWEN_API_KEY", "sk-test-qwen")
    monkeypatch.setattr(narrative_module.settings, "REPORT_AGENT_ENABLE_THINKING", True)
    narrative_module._create_report_llm()
    assert captured["extra_body"] == {"enable_thinking": True}
    assert captured["max_tokens"] == 4000
    assert captured["request_timeout"] == 90.0


def test_single_aigc_rejects_batch_metrics_and_batch_prompt_is_bounded(monkeypatch):
    calls = []

    class FakeLLM:
        def invoke(self, messages):
            calls.append(json.loads(messages[1].content))
            return SimpleNamespace(content=json.dumps({
                "statistics_explanation": ["检测结果已完成解读。"],
                "result_summary": {
                    "text": "本次单图检测覆盖率100%，无缺陷率为0%。",
                    "evidence": "E03",
                },
                "key_findings": [{"text": "检测到一处目标。", "evidence": "E03"}],
                "review_focus": [{"text": "复核目标标注区域。", "evidence": "E03"}],
                "recommended_actions": [{"text": "进行人工复核。", "evidence": "E06"}],
            }, ensure_ascii=False))

    monkeypatch.setattr(
        "app.services.report_narrative_service.settings.REPORT_AGENT_EXPLANATION_ENABLED",
        True,
    )
    single_content = generate_report_ai_content(_single_detail(), llm=FakeLLM())
    assert "覆盖率" not in single_content.analysis["result_summary"]["text"]
    assert "无缺陷率" not in single_content.analysis["result_summary"]["text"]

    generate_report_ai_content(_detail(25), llm=FakeLLM())
    batch_payload = calls[-1]
    assert batch_payload["result_evidence_count"] <= 16
    assert batch_payload["item_evidence_count"] <= 8


def test_single_image_report_omits_batch_only_statistics_and_charts():
    detail = _single_detail()
    assert render_report_charts(detail) == {}
    analysis = build_rule_based_ai_analysis(detail)
    assert analysis["result_summary"]["evidence"] == "检测目标数=1"
    markdown = render_report_markdown(detail).decode()
    assert "## 一、单图检测概览" in markdown
    assert "## 二、AIGC 检测结果解读" in markdown
    assert "## 三、检测图像与目标明细" in markdown
    assert "![原始图像 1]" in markdown
    assert "![检测标注图 1]" in markdown
    assert "## 三、结果统计" not in markdown
    assert "检测覆盖率" not in markdown
    assert "无缺陷率" not in markdown
    assert "代表性检测图像" not in markdown
    assert "逐检测项" not in markdown
    assert "统计图表" not in markdown
    assert "2026-07-18 02:21:29" in markdown

    archive_bytes = build_report_archive(detail, _Storage())
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        assert not any(name.startswith("charts/") for name in archive.namelist())
        assert "## 二、AIGC 检测结果解读" in archive.read("report.md").decode()


def test_batch_report_limits_embedded_representative_images():
    markdown = render_report_markdown(_detail(25)).decode()
    assert "选择 8 个代表项" in markdown
    assert "### 4.8 " in markdown
    assert "### 4.9 " not in markdown
    assert "![原始图像 1]" not in markdown
    assert "![检测标注图 1]" in markdown
    assert "[查看原始图像]" in markdown


def test_batch_report_uses_image_level_semantics_and_never_single_board_action():
    detail = _detail(3)
    detail["task"]["task_type"] = "folder"
    detail["task"]["total_inference_time"] = 30.0
    detail["report"]["suggestion"] = "立即隔离该 PCB，停止流转并安排返修或报废复核。"
    markdown = render_report_markdown(detail).decode()

    assert "多图任务筛查未通过" in markdown
    assert "图像级无检出率" in markdown
    assert "疑似缺陷检出项" in markdown
    assert "不能把图像数量直接解释为 PCB 件数" in markdown
    assert "不得据此认定整批 PCB 全部不合格" in markdown
    assert "立即隔离该 PCB" not in markdown
    assert "平均单项推理耗时 | 10.00 ms" in markdown


def test_batch_aigc_rejects_physical_pcb_count_and_unsupported_concentration(monkeypatch):
    class FakeLLM:
        def invoke(self, _messages):
            return SimpleNamespace(content=json.dumps({
                "statistics_explanation": [{
                    "text": "低置信度结果主要集中在短路类别。",
                    "evidence": ["E06"],
                }],
                "result_summary": {
                    "text": "本批次共有 25 块 PCB，其中全部不合格。",
                    "evidence": ["E03", "E06"],
                },
                "recommended_actions": [{
                    "text": "立即隔离该 PCB。",
                    "evidence": ["E08"],
                }],
            }, ensure_ascii=False))

    monkeypatch.setattr(
        "app.services.report_narrative_service.settings.REPORT_AGENT_EXPLANATION_ENABLED",
        True,
    )
    detail = _detail(25)
    content = generate_report_ai_content(detail, llm=FakeLLM())
    rendered = json.dumps(content.analysis, ensure_ascii=False)
    assert "25 块 PCB" not in rendered
    assert "立即隔离该 PCB" not in rendered
    assert "主要集中" not in content.statistics_explanation
    assert "图像/检测项级统计" in rendered


def test_online_report_and_zip_share_charts_and_portable_media():
    detail = _detail()
    storage = _Storage()
    markdown, report_path, chart_urls = persist_online_report(
        detail, storage, "https://app.example"
    )
    assert report_path == "reports/7/1/report-1.md"
    assert set(chart_urls) == set(CHART_FILENAMES)
    assert b"Defect category distribution" not in markdown
    assert "结果统计" in markdown.decode()
    assert "https://files.example/reports/7/1/report-1/charts/defect_distribution.png" in markdown.decode()
    assert "https://files.example/reports/7/1/report-1/charts/item_detection_trend.png" in markdown.decode()
    assert "https://files.example/reports/7/1/report-1/charts/overview_dashboard.png" in markdown.decode()

    archive_bytes = build_report_archive(detail, storage)
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        names = set(archive.namelist())
        assert {"report.md", "manifest.json", "results.json"}.issubset(names)
        assert {f"charts/{name}" for name in CHART_FILENAMES}.issubset(names)
        assert any(name.startswith("images/") for name in names)
        archived_markdown = archive.read("report.md").decode()
        assert "charts/defect_distribution.png" in archived_markdown
        assert "charts/item_detection_trend.png" in archived_markdown
        assert "charts/overview_dashboard.png" in archived_markdown
        assert "images/" in archived_markdown
        manifest = json.loads(archive.read("manifest.json"))
        assert {entry["type"] for entry in manifest["chart_catalog"]} == {
            "pie", "histogram", "donut", "line", "dashboard"
        }


def test_non_pcb_scene_uses_generic_explanation_and_suggestion():
    task = SimpleNamespace(
        scene=SimpleNamespace(
            name="remote_sensing",
            display_name="遥感目标检测",
            category="remote_sensing",
            description="遥感影像目标识别",
        )
    )
    result = SimpleNamespace(class_name="airplane", class_name_cn="飞机", confidence=0.86)
    assessment = evaluate_quality([result], task)
    assert assessment["quality_conclusion"] == "发现目标，需复核"
    assert "PCB" not in assessment["suggestion"]


def test_report_archive_endpoint_returns_portable_zip(client, monkeypatch):
    import app.api.history as history_api

    monkeypatch.setattr(history_service, "get_task_detail", lambda _user_id, _task_id: _detail())
    monkeypatch.setattr(history_api, "MinIOClient", _Storage)
    monkeypatch.setattr(history_api, "write_audit", lambda *_args, **_kwargs: None)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=7, username="tester", is_superuser=False, user_roles=[]
    )
    try:
        response = client.get("/api/history/tasks/1/report.zip")
    finally:
        app.dependency_overrides.pop(get_current_user, None)
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert "report.md" in archive.namelist()
        markdown = archive.read("report.md").decode()
        assert "### 3.2 统计解读" in markdown
        assert "说明来源：系统根据本报告聚合数据自动生成" in markdown
