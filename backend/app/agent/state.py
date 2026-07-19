"""LangGraph 多 Agent 共享状态定义。"""

from typing import Annotated, Any, TypedDict

from langgraph.graph.message import add_messages


class AgentState(TypedDict, total=False):
    """Supervisor、子 Agent 和汇总节点之间传递的状态。"""

    messages: Annotated[list, add_messages]
    next_agent: str
    detection_result: dict[str, Any]
    analysis_result: dict[str, Any]
    management_result: dict[str, Any]
    tool_events: list[dict[str, Any]]
    agent_used: str
    final_response: str
    user_id: int
    session_id: str
    is_superuser: bool
