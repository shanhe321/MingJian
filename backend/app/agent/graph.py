"""LangGraph 状态图：Supervisor → 单个/并行/顺序复合 Agent → 汇总。"""

import re

from langchain_core.messages import HumanMessage
from langgraph.graph import END, StateGraph

from app.agent.state import AgentState
from app.agent.supervisor import SupervisorAgent
from app.core.logger import get_logger

logger = get_logger(__name__)


def _result_output(update: dict, key: str) -> str:
    value = update.get(key, {})
    if isinstance(value, dict):
        return str(value.get("output", ""))
    return str(value or "")


def build_agent_graph(
    llm,
    management_agent_node,
    detection_agent_node,
    analysis_agent_node,
    supervisor_llm=None,
):
    """构建并编译多 Agent 协作图。"""
    supervisor = SupervisorAgent(supervisor_llm or llm)
    workflow = StateGraph(AgentState)
    workflow.add_node("supervisor", supervisor.route)
    workflow.add_node("management", management_agent_node)
    workflow.add_node("detection", detection_agent_node)
    workflow.add_node("analysis", analysis_agent_node)

    async def detection_then_analysis(state, config=None):
        """先取得真实检测结果，再让 Analysis 回答依赖本次结果的问题。"""
        detection_update = await detection_agent_node(state, config=config)
        messages = state.get("messages", [])
        latest = getattr(messages[-1], "content", "") if messages else ""
        question = re.sub(r"\[附件图片路径:[^\]]+\]", "", str(latest)).strip()
        detection_output = _result_output(detection_update, "detection_result")
        analysis_state = {
            **state,
            **detection_update,
            "messages": [
                HumanMessage(
                    content=(
                        f"用户问题：{question}\n\n"
                        f"本次真实检测结果：{detection_output}\n\n"
                        "请基于以上检测结果回答用户问题；必要时调用知识库，"
                        "不得补造检测结果中不存在的缺陷或数字。"
                    )
                )
            ],
        }
        analysis_update = await analysis_agent_node(analysis_state, config=config)
        return {
            "detection_result": detection_update.get("detection_result", {}),
            "analysis_result": analysis_update.get("analysis_result", {}),
            "tool_events": [
                *detection_update.get("tool_events", []),
                *analysis_update.get("tool_events", []),
            ],
            "agent_used": "analysis+detection",
        }

    workflow.add_node("detection_then_analysis", detection_then_analysis)
    workflow.add_node("summarize", supervisor.summarize)
    workflow.set_entry_point("supervisor")
    workflow.add_conditional_edges(
        "supervisor",
        supervisor.decide_next,
        {
            "management": "management",
            "detection": "detection",
            "analysis": "analysis",
            "detection_then_analysis": "detection_then_analysis",
        },
        then="summarize",
    )
    workflow.add_edge("summarize", END)
    compiled = workflow.compile()
    logger.info("LangGraph 多 Agent 状态图构建完成")
    return compiled
