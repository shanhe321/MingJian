from types import SimpleNamespace

import pytest
from langchain_core.messages import HumanMessage

from app.agent.agents.analysis_agent import AnalysisSubAgent
from app.agent.agents.detection_agent import DetectionSubAgent
from app.agent.agents.qa_agent import QASubAgent
from app.agent.graph import build_agent_graph
from app.agent.prompts import (
    ANALYSIS_SUB_AGENT_PROMPT,
    DETECTION_AGENT_SYSTEM_PROMPT,
    DETECTION_SUB_AGENT_PROMPT,
    QA_SUB_AGENT_PROMPT,
    SUPERVISOR_ROUTING_PROMPT,
    SUPERVISOR_SUMMARY_PROMPT,
)
from app.agent.supervisor import SupervisorAgent
from app.agent.tools.analysis_tool import ANALYSIS_TOOLS
from app.agent.tools.detection_tool import DETECTION_TOOLS
from app.agent.tools.knowledge_tool import KNOWLEDGE_TOOLS


class QueueLLM:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def ainvoke(self, messages, config=None):
        self.calls.append(messages)
        return SimpleNamespace(content=self.responses.pop(0))


def test_prompts_match_pcb_project_and_permission_boundaries():
    combined = "\n".join(
        [
            DETECTION_AGENT_SYSTEM_PROMPT,
            SUPERVISOR_ROUTING_PROMPT,
            DETECTION_SUB_AGENT_PROMPT,
            ANALYSIS_SUB_AGENT_PROMPT,
            QA_SUB_AGENT_PROMPT,
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
        ("qa", "qa"),
        ("无法判断", "qa"),
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
async def test_graph_routes_to_analysis_and_summarizes():
    llm = QueueLLM(["analysis", "已汇总分析结果"])
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

    async def qa_node(state):
        called.append("qa")
        return {"qa_result": "问答"}

    graph = build_agent_graph(llm, detection_node, analysis_node, qa_node)
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
    qa = QASubAgent(object())

    assert [tool.name for tool in detection.tools] == [tool.name for tool in DETECTION_TOOLS]
    assert [tool.name for tool in analysis.tools] == [tool.name for tool in ANALYSIS_TOOLS]
    assert [tool.name for tool in qa.tools] == [tool.name for tool in KNOWLEDGE_TOOLS]
