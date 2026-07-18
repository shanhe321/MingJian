"""Generate concise report statistics explanations with an LLM and a safe fallback."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.config.settings import settings
from app.core.logger import get_logger
from app.services.report_service import (
    build_rule_based_ai_analysis,
    build_statistics_explanation,
    category_statistics,
    report_semantics,
    report_statistics,
)

logger = get_logger(__name__)
AIGC_ANALYSIS_VERSION = "2.5"


@dataclass(frozen=True)
class StatisticsNarrative:
    text: str
    source: str
    generated_at: datetime


@dataclass(frozen=True)
class ReportAIContent:
    statistics_explanation: str
    analysis: dict
    source: str
    generated_at: datetime


UNSUPPORTED_CLAIMS = (
    "出货",
    "安全隐患",
    "电气连接隐患",
    "质量标准",
    "报废",
    "保证",
    "必然",
)


def _valid_key(value: str | None) -> bool:
    return bool(value and not value.startswith("sk-your-") and value.strip())


def _create_report_llm():
    llm_kwargs = {}
    if _valid_key(settings.QWEN_API_KEY):
        api_key = settings.QWEN_API_KEY
        base_url = settings.QWEN_BASE_URL
        model_name = settings.QWEN_MODEL
        llm_kwargs["extra_body"] = {
            "enable_thinking": settings.REPORT_AGENT_ENABLE_THINKING
        }
    elif _valid_key(settings.OPENAI_API_KEY):
        api_key = settings.OPENAI_API_KEY
        base_url = settings.OPENAI_BASE_URL
        model_name = settings.OPENAI_MODEL
    else:
        return None
    return ChatOpenAI(
        model=model_name,
        openai_api_key=api_key,
        openai_api_base=base_url,
        temperature=0.1,
        request_timeout=settings.REPORT_AGENT_EXPLANATION_TIMEOUT_SECONDS,
        max_retries=0,
        max_tokens=4000,
        **llm_kwargs,
    )


def _response_text(response) -> str:
    content = getattr(response, "content", response)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            str(item.get("text") or item.get("content") or "")
            if isinstance(item, dict) else str(item)
            for item in content
        )
    return str(content or "")


def _normalize_explanation(value: str) -> str:
    value = re.sub(r"```(?:markdown)?|```", "", value, flags=re.IGNORECASE).strip()
    lines = [re.sub(r"^#{1,6}\s*", "", line).strip() for line in value.splitlines() if line.strip()]
    normalized = []
    for line in lines[:6]:
        line = re.sub(r"^(?:[-*•]|\d+[.)、])\s*", "", line).strip()
        line = line.replace("合格率", "图像级无检出率").replace("无缺陷率", "图像级无检出率")
        if line and not any(claim in line for claim in UNSUPPORTED_CLAIMS):
            normalized.append(f"- {line[:300]}")
    return "\n".join(normalized)[:1200]


def _prompt_payload(detail: dict) -> dict:
    task = detail.get("task") or {}
    report = report_semantics(detail)
    statistics = dict(report_statistics(detail))
    statistics.pop("high_risk_item_names", None)
    return {
        "scene": task.get("scene_name"),
        "task_type": task.get("task_type"),
        "quality_conclusion": report.get("quality_conclusion"),
        "risk_level": report.get("risk_level"),
        "risk_reason": report.get("risk_reason"),
        "statistics": statistics,
        "defect_distribution": report.get("defect_summary") or {},
    }


def generate_statistics_explanation(
    detail: dict,
    *,
    allow_agent: bool = True,
    llm=None,
) -> StatisticsNarrative:
    """Generate from aggregate-only data; never send images, paths, boxes, or Base64."""
    generated_at = datetime.now()
    fallback = build_statistics_explanation(detail)
    if not settings.REPORT_AGENT_EXPLANATION_ENABLED or not allow_agent:
        return StatisticsNarrative(fallback, "rules", generated_at)
    try:
        llm = llm or _create_report_llm()
        if llm is None:
            return StatisticsNarrative(fallback, "rules", generated_at)
        payload = json.dumps(_prompt_payload(detail), ensure_ascii=False, separators=(",", ":"))
        response = llm.invoke([
            SystemMessage(content=(
                "你是工业视觉检测报告的统计解读 Agent。仅依据用户提供的聚合统计生成 3 至 4 条中文要点，"
                "说明覆盖率、图像级无检出率、主要缺陷候选、置信度或失败项。不得推测原因、不得编造数据、不得给出"
                "超出检测证据的质量承诺，不得推断出货、安全、电气隐患或报废结论。pass_rate 只能称为"
                "图像级无检出率，所有置信度使用百分比表达。多图任务中的文件数只能称为图像检测项数，"
                "不得推断 PCB 件数或生产良率；只有统计中提供了分类计数时才能使用“集中于”等关系描述。"
                "每条不超过 80 字，只输出 Markdown 无序列表，不要标题。"
            )),
            HumanMessage(content=f"请解读以下检测统计：{payload}"),
        ])
        text = _normalize_explanation(_response_text(response))
        if len(text) < 20:
            raise ValueError("Agent 返回的统计说明过短")
        return StatisticsNarrative(text, "agent", generated_at)
    except Exception as exc:
        logger.warning("统计解读 Agent 调用失败，使用规则化说明: %s", exc)
        return StatisticsNarrative(fallback, "rules", generated_at)


def _position_evidence(result: dict, default_image_size=None) -> tuple[str, str]:
    bbox = result.get("bbox")
    width = result.get("image_width")
    height = result.get("image_height")
    if (not width or not height) and default_image_size:
        if isinstance(default_image_size, (list, tuple)) and len(default_image_size) >= 2:
            width, height = default_image_size[:2]
        else:
            try:
                width = height = float(default_image_size)
            except (TypeError, ValueError):
                pass
    if not isinstance(bbox, (list, tuple)) or len(bbox) != 4 or not width or not height:
        return "位置未记录", "面积占比未记录"
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
    area = max(0.0, x2 - x1) * max(0.0, y2 - y1) / (float(width) * float(height))
    return position, f"目标框面积约占图像 {area:.2%}"


def _selected_result_evidence(results: list[dict], limit: int = 40) -> list[dict]:
    if len(results) <= limit:
        return results
    ordered = sorted(
        enumerate(results),
        key=lambda pair: float(pair[1].get("confidence") or 0),
    )
    low_count = min(6, max(2, limit // 4))
    high_count = max(1, limit - low_count)
    selected_indexes = {index for index, _ in ordered[:low_count]}
    selected_indexes.update(index for index, _ in ordered[-high_count:])
    return [result for index, result in enumerate(results) if index in selected_indexes]


def _aigc_prompt_payload(detail: dict) -> tuple[dict, dict[str, str]]:
    task = detail.get("task") or {}
    report = report_semantics(detail)
    results = detail.get("results") or []
    items = detail.get("items") or []
    stats = report_statistics(detail)
    facts = [
        f"检测模式={task.get('task_type') or '未记录'}",
        f"检测场景={task.get('scene_name') or '未记录'}",
        f"缺陷候选数={len(results)}",
        f"成功处理项={stats['completed_items']}/{stats['total_items']}",
        f"失败项={stats['failed_items']}",
        f"自动筛查结论={report.get('quality_conclusion') or '未记录'}",
        f"风险等级={report.get('risk_level') or '无'}",
        f"风险原因={report.get('risk_reason') or '无'}",
        f"系统建议={report.get('suggestion') or '无'}",
    ]
    if stats["coverage_rate"] is not None:
        facts.append(f"检测覆盖率={stats['coverage_rate']:.2f}%")
    if stats["pass_rate"] is not None:
        facts.append(f"图像级无检出率={stats['pass_rate']:.2f}%")
    if stats["average_confidence"] is not None:
        facts.extend([
            f"平均置信度={stats['average_confidence']:.2%}",
            f"最低置信度={stats['minimum_confidence']:.2%}",
            f"最高置信度={stats['maximum_confidence']:.2%}",
            f"低于50%置信度结果={sum(float(result.get('confidence') or 0) < 0.5 for result in results)}",
            (
                f"置信度分层：较高={stats['high_confidence_results']}，"
                f"中等={stats['medium_confidence_results']}，"
                f"较低={stats['low_confidence_results']}"
            ),
            f"近阈值结果={stats['near_threshold_results']}",
        ])
        if stats["low_confidence_by_class"]:
            facts.append(
                "低置信度类别分布：" + "，".join(
                    f"{name}={count}"
                    for name, count in sorted(
                        stats["low_confidence_by_class"].items(),
                        key=lambda item: (-item[1], item[0]),
                    )
                )
            )
    if stats["defective_item_rate"] is not None:
        facts.extend([
            f"疑似缺陷检出项比例={stats['defective_item_rate']:.2f}%",
            f"多缺陷检测项={stats['multiple_defect_items']}",
            (
                f"单项最大缺陷数={stats['max_defects_per_item']}，"
                f"文件={stats['max_defect_item_name'] or '未记录'}"
            ),
        ])
        if stats["average_defects_per_defective_item"] is not None:
            facts.append(
                f"平均每个缺陷项目标数={stats['average_defects_per_defective_item']:.2f}"
            )
    if stats["average_inference_time_per_item"] is not None:
        facts.append(
            f"平均单项推理耗时={stats['average_inference_time_per_item']:.2f} ms"
        )
    if task.get("task_type") != "single":
        facts.extend([
            (
                f"检测项风险分层：高风险候选检出项={stats['high_risk_items']}，"
                f"中风险候选检出项={stats['medium_risk_items']}，"
                f"一般风险候选检出项={stats['general_risk_items']}"
            ),
            "数据范围=仅记录图像检测项，未记录 PCB 实物编号或多视图归组标识",
        ])
        if stats["high_risk_item_names"]:
            facts.append(
                "高风险候选对应文件=" + "、".join(stats["high_risk_item_names"][:10])
            )
    for name, count in (report.get("defect_summary") or {}).items():
        facts.append(f"类别统计：{name}={int(count)}")
    for row in category_statistics(detail):
        facts.append(
            f"类别质量：{row['name']}，数量={row['count']}，占比={row['share']:.2%}，"
            f"平均置信度={row['average_confidence']:.2%}，"
            f"范围={row['minimum_confidence']:.2%}～{row['maximum_confidence']:.2%}，"
            f"风险级别={row['risk_level']}"
        )

    result_evidence = []
    result_limit = 40 if task.get("task_type") == "single" else 16
    for index, result in enumerate(
        _selected_result_evidence(results, result_limit),
        start=1,
    ):
        position, area = _position_evidence(result, task.get("image_size"))
        fact = (
            f"结果#{index}：类别={result.get('class_name_cn') or result.get('class_name') or '未知类别'}，"
            f"置信度={float(result.get('confidence') or 0):.2%}，位置={position}，{area}"
        )
        facts.append(fact)
        result_evidence.append(fact)

    item_evidence = []
    sorted_items = sorted(
        items,
        key=lambda item: (
            item.get("status") == "failed",
            int(item.get("defect_count") or 0),
        ),
        reverse=True,
    )[:8]
    for item in sorted_items:
        average_confidence = (
            f"{float(item['average_confidence']):.2%}"
            if item.get("average_confidence") is not None
            else "未记录"
        )
        fact = (
            f"检测项：文件={Path(item.get('file_name') or '未命名').name}，"
            f"状态={item.get('status') or '未记录'}，缺陷数={int(item.get('defect_count') or 0)}，"
            f"平均置信度={average_confidence}"
        )
        facts.append(fact)
        item_evidence.append(fact)

    evidence_map = {
        f"E{index:02d}": fact
        for index, fact in enumerate(facts, start=1)
    }
    payload = {
        "evidence_facts": [
            {"id": evidence_id, "fact": fact}
            for evidence_id, fact in evidence_map.items()
        ],
        "analysis_focus": (
            "单图：结合类别、置信度、目标位置和面积占比，指出最值得人工复核的检测框；不要复述整张表。"
            if task.get("task_type") == "single"
            else (
                "多图任务：解释图像检测项的类别分布、低置信度结果和高风险候选检出项；"
                "文件可能来自多个 PCB，也可能是同一 PCB 的多视图，不得把检测项数写成 PCB 件数。"
                "处置建议必须指向命中风险候选的检测项，不得使用‘该 PCB’或暗示整批全部不合格。"
            )
        ),
        "result_evidence_count": len(result_evidence),
        "omitted_result_count": max(0, len(results) - len(result_evidence)),
        "item_evidence_count": len(item_evidence),
    }
    return payload, evidence_map


def _extract_json(value: str) -> dict:
    fence = chr(96) * 3
    value = value.replace(f"{fence}json", "").replace(fence, "").strip()
    start = value.find("{")
    end = value.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("Agent 未返回 JSON 对象")
    parsed = json.loads(value[start:end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("Agent AIGC 内容不是对象")
    return parsed


def _safe_text(value, limit: int = 500) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    text = text.replace("合格率", "图像级无检出率").replace("无缺陷率", "图像级无检出率")
    if any(claim in text for claim in UNSUPPORTED_CLAIMS):
        return ""
    return text[:limit]


def _number_values(value: str) -> set[float]:
    return {
        round(float(number), 4)
        for number in re.findall(r"\d+(?:\.\d+)?", value)
    }


def _validated_entry(value, allowed_evidence: dict[str, str]):
    if not isinstance(value, dict):
        return None
    text = _safe_text(value.get("text"), 300)
    references = value.get("evidence") or []
    if not isinstance(references, list):
        references = [references]
    evidence_items = []
    for reference in references[:6]:
        evidence_reference = str(reference or "").strip()
        evidence = allowed_evidence.get(evidence_reference)
        if evidence is None and evidence_reference in allowed_evidence.values():
            evidence = evidence_reference
        if evidence and evidence not in evidence_items:
            evidence_items.append(evidence)
    combined_evidence = "；".join(evidence_items)
    if (
        not text
        or not combined_evidence
        or not _number_values(text).issubset(_number_values(combined_evidence))
        or (
            any(term in text for term in ("集中于", "主要集中", "集中在"))
            and "低置信度类别分布" not in combined_evidence
            and "类别统计" not in combined_evidence
        )
        or ("数据完整" in text and "数据完整" not in combined_evidence)
        or (
            "缺陷" in text
            and "候选" not in text
            and any(term in text for term in ("唯一缺陷", "检出", "检测到", "发现", "存在"))
        )
    ):
        return None
    normalized = {"text": text, "evidence": combined_evidence}
    priority = str(value.get("priority") or "").strip()
    if priority in {"立即处置", "优先复核", "一般复核", "补充检测"}:
        normalized["priority"] = priority
    return normalized


def _validated_analysis(value: dict, allowed_evidence: dict[str, str], fallback: dict) -> dict:
    summary = _validated_entry(value.get("result_summary"), allowed_evidence)
    normalized = {"result_summary": summary or fallback["result_summary"]}
    for field in (
        "key_findings",
        "confidence_assessment",
        "review_focus",
        "recommended_actions",
        "data_quality_notes",
    ):
        entries = [
            entry
            for entry in (
                _validated_entry(item, allowed_evidence)
                for item in (value.get(field) or [])[:6]
            )
            if entry is not None
        ]
        normalized[field] = entries[:4] or fallback[field]
    return normalized


def _enforce_task_mode(analysis: dict, fallback: dict, task_type: str | None) -> dict:
    if task_type == "single":
        batch_terms = ("覆盖率", "无检出率", "成功处理项", "批次")
        summary = analysis.get("result_summary") or {}
        if any(term in str(summary.get("text") or "") for term in batch_terms):
            analysis["result_summary"] = fallback["result_summary"]
        for field in (
            "key_findings",
            "confidence_assessment",
            "review_focus",
            "recommended_actions",
            "data_quality_notes",
        ):
            filtered = [
                entry for entry in (analysis.get(field) or [])
                if not any(term in str(entry.get("text") or "") for term in batch_terms)
            ]
            analysis[field] = filtered or fallback[field]
        return analysis

    physical_unit_patterns = (
        re.compile(r"\d+\s*(?:块|件)\s*PCB", re.IGNORECASE),
        re.compile(r"该\s*PCB", re.IGNORECASE),
        re.compile(r"整批.*(?:全部|均).*(?:不合格|缺陷)", re.IGNORECASE),
    )
    for field in (
        "result_summary",
        "key_findings",
        "confidence_assessment",
        "review_focus",
        "recommended_actions",
        "data_quality_notes",
    ):
        entries = [analysis.get(field)] if field == "result_summary" else (analysis.get(field) or [])
        filtered = [
            entry for entry in entries
            if isinstance(entry, dict)
            and not any(pattern.search(str(entry.get("text") or "")) for pattern in physical_unit_patterns)
        ]
        if field == "result_summary":
            analysis[field] = filtered[0] if filtered else fallback[field]
        else:
            analysis[field] = filtered or fallback[field]
    return analysis


def generate_report_ai_content(
    detail: dict,
    *,
    allow_agent: bool = True,
    llm=None,
) -> ReportAIContent:
    """Generate evidence-linked AIGC; every displayed claim carries a supplied fact."""
    generated_at = datetime.now()
    fallback_statistics = build_statistics_explanation(detail)
    fallback_analysis = build_rule_based_ai_analysis(detail)
    fallback_analysis["version"] = AIGC_ANALYSIS_VERSION
    fallback = ReportAIContent(
        fallback_statistics,
        fallback_analysis,
        "rules",
        generated_at,
    )
    if not settings.REPORT_AGENT_EXPLANATION_ENABLED or not allow_agent:
        return fallback
    try:
        llm = llm or _create_report_llm()
        if llm is None:
            return fallback
        payload, allowed_evidence = _aigc_prompt_payload(detail)
        response = llm.invoke([
            SystemMessage(content=(
                "你是工业视觉检测报告 AIGC Agent。你只能根据 evidence_facts 解读检测结果，不能补充外部知识、"
                "原因推测或质量承诺。先在内部分析证据之间的关系，再只输出最终 JSON，不输出思考过程。"
                "解读必须比统计表更有信息量，避免逐行复述；应指出主要模式、类别风险、置信度可靠性、"
                "数据质量和人工复核优先级，并区分立即处置、优先复核和一般复核。"
                "输出严格 JSON，结构为："
                "{\"statistics_explanation\":[{\"text\":\"...\",\"evidence\":[\"E01\"]}],"
                "\"result_summary\":{\"text\":\"...\",\"evidence\":[\"E01\",\"E02\"]},"
                "\"key_findings\":[{\"text\":\"...\",\"evidence\":[\"E03\"]}],"
                "\"confidence_assessment\":[{\"text\":\"...\",\"evidence\":[\"E04\"]}],"
                "\"review_focus\":[{\"text\":\"...\",\"evidence\":[\"E05\"]}],"
                "\"recommended_actions\":[{\"priority\":\"立即处置|优先复核|一般复核|补充检测\","
                "\"text\":\"...\",\"evidence\":[\"E06\"]}],"
                "\"data_quality_notes\":[{\"text\":\"...\",\"evidence\":[\"E07\"]}]}。"
                "evidence 必须是 evidence_facts 中真实存在的 id 数组，不要复制 fact 文本。正文中的每个数字"
                "都必须出现在该条引用的证据中；需要多个事实支撑时必须引用多个 id。"
                "每项 1 至 4 条，每条不超过 80 字。不得推断出货、安全、电气隐患、报废或保证性结论；"
                "pass_rate 只能称图像级无检出率，置信度使用百分比。所有模型结果都称为缺陷候选或目标候选，"
                "不能直接写成已经人工确认的缺陷。单图任务禁止使用覆盖率、无检出率、成功处理项等批量指标。"
                "多图任务不得把图像检测项数解释为 PCB 件数，不得使用‘该 PCB’，不得暗示整批 PCB 全部不合格；"
                "隔离、复核等措施必须指向命中风险候选的检测项。只有证据中提供分类计数时才能使用‘集中’类描述，"
                "不得仅凭 completed 状态声称‘数据完整’。不要输出 JSON 以外内容。"
            )),
            HumanMessage(content=json.dumps(payload, ensure_ascii=False, separators=(",", ":"))),
        ])
        parsed = _extract_json(_response_text(response))
        statistics_entries = [
            entry
            for entry in (
                _validated_entry(item, allowed_evidence)
                for item in (parsed.get("statistics_explanation") or [])[:6]
            )
            if entry is not None
        ]
        statistics = "\n".join(
            f"- {entry['text']}（依据：{entry['evidence']}）"
            for entry in statistics_entries[:4]
        )
        if len(statistics) < 20:
            statistics = fallback_statistics
        analysis = _validated_analysis(parsed, allowed_evidence, fallback_analysis)
        analysis = _enforce_task_mode(
            analysis,
            fallback_analysis,
            detail.get("task", {}).get("task_type"),
        )
        analysis["version"] = AIGC_ANALYSIS_VERSION
        return ReportAIContent(statistics, analysis, "agent", generated_at)
    except Exception as exc:
        logger.warning("报告 AIGC Agent 调用失败，使用规则化内容: %s", exc)
        return fallback
