"""LangGraph 状态图：Supervisor → 子 Agent → 汇总。"""

from langgraph.graph import END, StateGraph

from app.agent.state import AgentState
from app.agent.supervisor import SupervisorAgent
from app.core.logger import get_logger

logger = get_logger(__name__)


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
    workflow.add_node("summarize", supervisor.summarize)
    workflow.set_entry_point("supervisor")
    workflow.add_conditional_edges(
        "supervisor",
        supervisor.decide_next,
        {"management": "management", "detection": "detection", "analysis": "analysis"},
    )
    workflow.add_edge("management", "summarize")
    workflow.add_edge("detection", "summarize")
    workflow.add_edge("analysis", "summarize")
    workflow.add_edge("summarize", END)
    compiled = workflow.compile()
    logger.info("LangGraph 多 Agent 状态图构建完成")
    return compiled
