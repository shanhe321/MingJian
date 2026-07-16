"""当前 Agent 请求上下文，用于工具侧执行用户隔离。"""

from contextvars import ContextVar

current_user_id: ContextVar[int | None] = ContextVar("agent_user_id", default=None)
current_user_is_superuser: ContextVar[bool] = ContextVar(
    "agent_user_is_superuser", default=False
)
