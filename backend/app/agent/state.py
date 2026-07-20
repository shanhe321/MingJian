"""LangGraph 多 Agent 共享状态定义。"""

from operator import add
from typing import Annotated, Any, TypedDict

from langgraph.graph.message import add_messages


def merge_agent_names(left: str, right: str) -> str:
    """并行分支写入 Agent 名称时，生成稳定且去重的组合标识。"""
    names = {
        name
        for value in (left, right)
        for name in str(value or "").split("+")
        if name
    }
    return "+".join(sorted(names))


class AgentState(TypedDict, total=False):
    """Supervisor、子 Agent 和汇总节点之间传递的状态。"""

    messages: Annotated[list, add_messages]
    next_agent: str | list[str]
    detection_result: dict[str, Any]
    analysis_result: dict[str, Any]
    management_result: dict[str, Any]
    tool_events: Annotated[list[dict[str, Any]], add]
    agent_used: Annotated[str, merge_agent_names]
    final_response: str
    user_id: int
    session_id: str
    is_superuser: bool
