"""LangGraph 状态图：Supervisor → 子 Agent → 汇总。"""

from langgraph.graph import END, StateGraph

from app.agent.state import AgentState
from app.agent.supervisor import SupervisorAgent
from app.core.logger import get_logger

logger = get_logger(__name__)


def build_agent_graph(llm, detection_agent_node, analysis_agent_node, qa_agent_node):
    """构建并编译多 Agent 协作图。"""
    supervisor = SupervisorAgent(llm)
    workflow = StateGraph(AgentState)
    workflow.add_node("supervisor", supervisor.route)
    workflow.add_node("detection", detection_agent_node)
    workflow.add_node("analysis", analysis_agent_node)
    workflow.add_node("qa", qa_agent_node)
    workflow.add_node("summarize", supervisor.summarize)
    workflow.set_entry_point("supervisor")
    workflow.add_conditional_edges(
        "supervisor",
        supervisor.decide_next,
        {"detection": "detection", "analysis": "analysis", "qa": "qa"},
    )
    workflow.add_edge("detection", "summarize")
    workflow.add_edge("analysis", "summarize")
    workflow.add_edge("qa", "summarize")
    workflow.add_edge("summarize", END)
    compiled = workflow.compile()
    logger.info("LangGraph 多 Agent 状态图构建完成")
    return compiled
