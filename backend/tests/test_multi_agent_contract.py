import asyncio
import json
import importlib
from types import SimpleNamespace

import pytest
from langchain_core.messages import HumanMessage

from app.agent.agents.analysis_agent import AnalysisSubAgent
from app.agent.agents.detection_agent import DetectionSubAgent
from app.agent.agents.management_agent import ManagementSubAgent
from app.agent.graph import build_agent_graph
from app.agent.prompts import (
    ANALYSIS_SUB_AGENT_PROMPT,
    DETECTION_AGENT_SYSTEM_PROMPT,
    DETECTION_SUB_AGENT_PROMPT,
    MANAGEMENT_SUB_AGENT_PROMPT,
    SUPERVISOR_ROUTING_PROMPT,
    SUPERVISOR_SUMMARY_PROMPT,
)
from app.agent.supervisor import SupervisorAgent
from app.config.settings import settings
from app.agent.tools.analysis_tool import ANALYSIS_TOOLS, MANAGEMENT_TOOLS
from app.agent.tools.detection_tool import (
    DETECTION_TOOLS,
    detect_batch_images,
    detect_single_image,
    detect_video_file,
    detect_zip_images_file,
)
from app.agent.tools.knowledge_tool import KNOWLEDGE_TOOLS


class QueueLLM:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def ainvoke(self, messages, config=None):
        self.calls.append(messages)
        return SimpleNamespace(content=self.responses.pop(0))


def test_only_explicit_supervisor_llm_disables_qwen_thinking(monkeypatch):
    module = importlib.import_module("app.agent.detection_agent")
    captured = []

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            captured.append(kwargs)

    monkeypatch.setattr(module, "ChatOpenAI", FakeChatOpenAI)
    monkeypatch.setattr(settings, "QWEN_API_KEY", "sk-real-qwen")
    module.create_llm()
    assert "extra_body" not in captured[-1]

    module.create_llm(enable_thinking=False)
    assert captured[-1]["extra_body"] == {"enable_thinking": False}

    monkeypatch.setattr(settings, "QWEN_API_KEY", "sk-your-qwen-api-key")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-openai")
    module.create_llm()
    assert "extra_body" not in captured[-1]


def test_prompts_match_pcb_project_and_permission_boundaries():
    combined = "\n".join(
        [
            DETECTION_AGENT_SYSTEM_PROMPT,
            SUPERVISOR_ROUTING_PROMPT,
            DETECTION_SUB_AGENT_PROMPT,
            ANALYSIS_SUB_AGENT_PROMPT,
            MANAGEMENT_SUB_AGENT_PROMPT,
            SUPERVISOR_SUMMARY_PROMPT,
        ]
    )
    for defect in (
        "missing_hole",
        "mouse_bite",
        "open_circuit",
        "short",
        "spur",
        "spurious_copper",
    ):
        assert defect in combined
    assert "普通用户只能访问自己的" in combined
    assert "仅管理员" in combined or "管理员" in combined
    assert "遥感图像目标" not in combined
    assert "![标注结果图](完整的annotated_image_url)" in DETECTION_SUB_AGENT_PROMPT
    assert "原样保留" in SUPERVISOR_SUMMARY_PROMPT
    assert "禁止输出服务器本地图片路径" in SUPERVISOR_SUMMARY_PROMPT


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("response", "expected"),
    [
        ("detection", "detection"),
        ("analysis", "analysis"),
        ("management", "management"),
        ("qa", "analysis"),
        ("无法判断", "analysis"),
    ],
)
async def test_supervisor_normalizes_routes(response, expected):
    llm = QueueLLM([response])
    supervisor = SupervisorAgent(llm)
    routed = await supervisor.route(
        {
            "messages": [HumanMessage(content="测试请求")],
            "is_superuser": False,
        }
    )
    assert routed == {"next_agent": expected}
    assert "普通用户" in llm.calls[0][1].content


@pytest.mark.asyncio
async def test_supervisor_routes_image_and_question_in_parallel():
    llm = QueueLLM([])
    supervisor = SupervisorAgent(llm)

    routed = await supervisor.route(
        {
            "messages": [
                HumanMessage(
                    content=(
                        "请检测这张 PCB 图片，同时解释 IoU 是什么？\n"
                        "[附件图片路径: upload.jpg]"
                    )
                )
            ],
            "is_superuser": False,
        }
    )

    assert routed == {"next_agent": ["detection", "analysis"]}
    assert llm.calls == []


@pytest.mark.asyncio
async def test_supervisor_routes_detection_dependent_question_sequentially():
    llm = QueueLLM([])
    supervisor = SupervisorAgent(llm)

    routed = await supervisor.route(
        {
            "messages": [
                HumanMessage(
                    content=(
                        "这张图片有什么缺陷，严重吗，应该怎么处理？\n"
                        "[附件图片路径: upload.jpg]"
                    )
                )
            ],
            "is_superuser": False,
        }
    )

    assert routed == {"next_agent": "detection_then_analysis"}
    assert llm.calls == []


@pytest.mark.asyncio
async def test_graph_routes_to_analysis_and_summarizes():
    worker_llm = QueueLLM([])
    supervisor_llm = QueueLLM(["analysis", "已汇总分析结果"])
    called = []

    async def detection_node(state):
        called.append("detection")
        return {"detection_result": {"output": "检测"}}

    async def analysis_node(state):
        called.append("analysis")
        return {
            "analysis_result": {"output": "最近 30 天共检测 5 次"},
            "tool_events": [],
            "agent_used": "analysis",
        }

    async def management_node(state):
        called.append("management")
        return {"management_result": {"output": "管理查询"}}

    graph = build_agent_graph(
        worker_llm,
        management_node,
        detection_node,
        analysis_node,
        supervisor_llm=supervisor_llm,
    )
    result = await graph.ainvoke(
        {
            "messages": [HumanMessage(content="最近检测了多少次？")],
            "user_id": 3,
            "session_id": "abc",
            "is_superuser": False,
            "tool_events": [],
        }
    )

    assert called == ["analysis"]
    assert result["agent_used"] == "analysis"
    assert result["final_response"] == "已汇总分析结果"
    assert len(supervisor_llm.calls) == 2
    assert worker_llm.calls == []


@pytest.mark.asyncio
async def test_graph_runs_detection_and_analysis_branches_in_parallel():
    worker_llm = QueueLLM([])
    supervisor_llm = QueueLLM(["并行结果已汇总"])
    started = set()
    both_started = asyncio.Event()

    async def mark_started(name):
        started.add(name)
        if started == {"detection", "analysis"}:
            both_started.set()
        await asyncio.wait_for(both_started.wait(), timeout=1)

    async def detection_node(state):
        await mark_started("detection")
        return {
            "detection_result": {"output": "检测到 1 个短路缺陷"},
            "tool_events": [{"tool": "detect_single_image"}],
            "agent_used": "detection",
        }

    async def analysis_node(state):
        await mark_started("analysis")
        return {
            "analysis_result": {"output": "IoU 用于衡量预测框与真实框的重叠程度"},
            "tool_events": [{"tool": "search_knowledge"}],
            "agent_used": "analysis",
        }

    async def management_node(state):
        raise AssertionError("不应调用 management")

    graph = build_agent_graph(
        worker_llm,
        management_node,
        detection_node,
        analysis_node,
        supervisor_llm=supervisor_llm,
    )
    result = await graph.ainvoke(
        {
            "messages": [
                HumanMessage(
                    content=(
                        "请检测这张 PCB 图片，同时解释 IoU 是什么？\n"
                        "[附件图片路径: upload.jpg]"
                    )
                )
            ],
            "user_id": 3,
            "session_id": "parallel",
            "is_superuser": False,
            "tool_events": [],
        }
    )

    assert started == {"detection", "analysis"}
    assert result["detection_result"]["output"] == "检测到 1 个短路缺陷"
    assert result["analysis_result"]["output"].startswith("IoU")
    assert result["agent_used"] == "analysis+detection"
    assert {event["tool"] for event in result["tool_events"]} == {
        "detect_single_image",
        "search_knowledge",
    }
    assert result["final_response"] == "并行结果已汇总"


@pytest.mark.asyncio
async def test_graph_passes_detection_result_to_dependent_analysis():
    worker_llm = QueueLLM([])
    supervisor_llm = QueueLLM(["依赖问题已汇总"])
    call_order = []

    async def detection_node(state, config=None):
        call_order.append("detection")
        return {
            "detection_result": {"output": "检测到短路，风险等级为 high"},
            "tool_events": [{"tool": "detect_single_image"}],
            "agent_used": "detection",
        }

    async def analysis_node(state, config=None):
        call_order.append("analysis")
        content = state["messages"][-1].content
        assert "本次真实检测结果：检测到短路，风险等级为 high" in content
        return {
            "analysis_result": {"output": "短路应立即隔离并人工复核"},
            "tool_events": [{"tool": "search_knowledge"}],
            "agent_used": "analysis",
        }

    async def management_node(state, config=None):
        raise AssertionError("不应调用 management")

    graph = build_agent_graph(
        worker_llm,
        management_node,
        detection_node,
        analysis_node,
        supervisor_llm=supervisor_llm,
    )
    result = await graph.ainvoke(
        {
            "messages": [
                HumanMessage(
                    content=(
                        "这张图片有什么缺陷，严重吗，应该怎么处理？\n"
                        "[附件图片路径: upload.jpg]"
                    )
                )
            ],
            "user_id": 3,
            "session_id": "dependent",
            "is_superuser": False,
            "tool_events": [],
        }
    )

    assert call_order == ["detection", "analysis"]
    assert result["detection_result"]["output"].startswith("检测到短路")
    assert result["analysis_result"]["output"].startswith("短路应立即隔离")
    assert result["agent_used"] == "analysis+detection"
    assert [event["tool"] for event in result["tool_events"]] == [
        "detect_single_image",
        "search_knowledge",
    ]
    assert result["final_response"] == "依赖问题已汇总"


def test_sub_agents_bind_only_their_documented_tools(monkeypatch):
    class FakeExecutor:
        max_iterations = 8

    def fake_init(self, llm, tools, system_prompt):
        self.tools = tools
        self.executor = FakeExecutor()

    base_module = __import__("app.agent.agents.base", fromlist=["ToolAgentNode"])
    monkeypatch.setattr(base_module.ToolAgentNode, "__init__", fake_init)

    detection = DetectionSubAgent(object())
    analysis = AnalysisSubAgent(object())
    management = ManagementSubAgent(object())

    assert [tool.name for tool in detection.tools] == [tool.name for tool in DETECTION_TOOLS]
    assert [tool.name for tool in analysis.tools] == [tool.name for tool in ANALYSIS_TOOLS + KNOWLEDGE_TOOLS]
    assert [tool.name for tool in management.tools] == [tool.name for tool in MANAGEMENT_TOOLS]


@pytest.mark.parametrize(
    ("tool", "service_method", "tool_input", "service_result"),
    [
        (
            detect_single_image,
            "detect_single",
            {"image_path": "input.jpg"},
            {
                "total_objects": 1,
                "annotated_image_base64": "single-image-payload",
                "annotated_image_url": "http://minio/result.jpg",
            },
        ),
        (
            detect_batch_images,
            "detect_batch",
            {"image_paths": ["one.jpg", "two.jpg"]},
            {
                "total_images": 2,
                "annotated_images": [
                    {
                        "image_path": "one.jpg",
                        "annotated_image_base64": "batch-image-payload",
                    }
                ],
            },
        ),
        (
            detect_zip_images_file,
            "detect_zip",
            {"zip_path": "images.zip"},
            {
                "source": "zip",
                "annotated_images": [
                    {
                        "image_path": "one.jpg",
                        "annotated_image_base64": "zip-image-payload",
                    }
                ],
            },
        ),
        (
            detect_video_file,
            "detect_video",
            {"video_path": "input.mp4"},
            {
                "processed_frames": 1,
                "key_frames": [
                    {
                        "frame_index": 0,
                        "annotated_image_base64": "video-frame-payload",
                    }
                ],
                "annotated_video_url": "http://minio/result.mp4",
            },
        ),
    ],
)
def test_detection_tools_do_not_send_base64_payloads_to_llm(
    monkeypatch,
    tool,
    service_method,
    tool_input,
    service_result,
):
    detection_tool_module = __import__(
        "app.agent.tools.detection_tool",
        fromlist=["detection_service"],
    )
    monkeypatch.setattr(
        getattr(detection_tool_module, "detection_service"),
        service_method,
        lambda *args, **kwargs: service_result,
    )

    serialized = tool.invoke(tool_input)
    result = json.loads(serialized)

    assert "base64" not in serialized.lower()
    assert "payload" not in serialized
    if service_method == "detect_single":
        assert result["annotated_image_url"] == "http://minio/result.jpg"
