"""知识问答子 Agent：执行 RAG 检索并回答 PCB 检测领域问题。"""

import json

from langchain_core.runnables import RunnableConfig

from app.agent.agents.base import ToolAgentNode
from app.agent.prompts import QA_SUB_AGENT_PROMPT
from app.agent.tools.knowledge_tool import KNOWLEDGE_TOOLS


class QASubAgent(ToolAgentNode):
    result_key = "qa_result"
    agent_name = "qa"

    def __init__(self, llm):
        super().__init__(llm, KNOWLEDGE_TOOLS, QA_SUB_AGENT_PROMPT)

    async def __call__(
        self,
        state: dict,
        config: RunnableConfig | None = None,
    ) -> dict:
        result = await super().__call__(state, config=config)
        output = result.pop("qa_result", {}).get("output", "")
        for event in result.get("tool_events", []):
            if event.get("tool") != "search_knowledge":
                continue
            try:
                tool_output = json.loads(event.get("output", "{}"))
            except (json.JSONDecodeError, TypeError):
                continue
            if tool_output.get("answer") == "知识库中暂无相关内容":
                output = "知识库中暂无相关内容，暂时无法基于项目知识库回答该问题。"
                break
        result["qa_result"] = output
        return result
