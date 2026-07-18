"""Supervisor：在 Management、Detection、Analysis 三个 Agent 之间路由。"""

from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from app.agent.prompts import SUPERVISOR_ROUTING_PROMPT, SUPERVISOR_SUMMARY_PROMPT
from app.core.logger import get_logger

logger = get_logger(__name__)


def _message_content(message: Any) -> str:
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in content
        )
    return str(content)


class SupervisorAgent:
    """负责路由和最终回复汇总，不直接执行检测工具。"""

    def __init__(self, llm):
        self.llm = llm

    async def _invoke(self, messages, config: RunnableConfig | None = None):
        if hasattr(self.llm, "ainvoke"):
            if config is None:
                return await self.llm.ainvoke(messages)
            return await self.llm.ainvoke(messages, config=config)
        if config is None:
            return self.llm.invoke(messages)
        return self.llm.invoke(messages, config=config)

    async def route(
        self,
        state: dict,
        config: RunnableConfig | None = None,
    ) -> dict:
        """识别当前用户意图，只返回三个合法路由之一。"""
        messages = state.get("messages", [])
        latest = messages[-1] if messages else HumanMessage(content="")
        role = "管理员" if state.get("is_superuser", False) else "普通用户"
        role_context = SystemMessage(content=f"当前用户身份：{role}。必须遵守权限边界。")
        response = await self._invoke(
            [
                SystemMessage(content=SUPERVISOR_ROUTING_PROMPT),
                role_context,
                latest,
            ],
            config=config,
        )
        raw = _message_content(response).strip().lower()
        next_agent = self._normalize_route(raw)
        logger.info("Supervisor 路由决策: raw=%s, route=%s", raw[:80], next_agent)
        return {"next_agent": next_agent}

    @staticmethod
    def _normalize_route(value: str) -> str:
        if "management" in value or "管理" in value or "用户列表" in value or "权限" in value:
            return "management"
        if "detection" in value or "检测" in value:
            return "detection"
        if "analysis" in value or "分析" in value or "统计" in value:
            return "analysis"
        return "analysis"

    def decide_next(self, state: dict) -> str:
        """LangGraph 条件边使用的路由函数。"""
        return self._normalize_route(str(state.get("next_agent", "analysis")))

    async def summarize(
        self,
        state: dict,
        config: RunnableConfig | None = None,
    ) -> dict:
        """将子 Agent 结果汇总为面向用户的中文回复。"""
        context_parts = []
        for label, key in (
            ("管理查询结果", "management_result"),
            ("检测结果", "detection_result"),
            ("分析结果", "analysis_result"),
        ):
            value = state.get(key)
            if value:
                if isinstance(value, dict):
                    value = value.get("output", value)
                context_parts.append(f"{label}：{value}")

        if not context_parts:
            return {"final_response": "抱歉，我没有理解您的请求，请重新描述。"}

        summary_prompt = SUPERVISOR_SUMMARY_PROMPT.format(
            context="\n".join(context_parts)
        )
        try:
            chunks = []
            if hasattr(self.llm, "astream"):
                async for chunk in self.llm.astream(
                    [HumanMessage(content=summary_prompt)],
                    config=config,
                ):
                    content = _message_content(chunk)
                    if content:
                        chunks.append(content)
                final_response = "".join(chunks).strip()
            else:
                response = await self._invoke(
                    [HumanMessage(content=summary_prompt)],
                    config=config,
                )
                final_response = _message_content(response).strip()
        except Exception as exc:
            logger.warning("Supervisor 汇总失败，使用子 Agent 原始结果: %s", str(exc))
            final_response = str(context_parts[0].split("：", 1)[-1])

        return {"final_response": final_response}
