"""Management 子 Agent：仅执行管理员只读查询。"""

from app.agent.agents.base import ToolAgentNode
from app.agent.prompts import MANAGEMENT_SUB_AGENT_PROMPT
from app.agent.tools.analysis_tool import MANAGEMENT_TOOLS


class ManagementSubAgent(ToolAgentNode):
    result_key = "management_result"
    agent_name = "management"

    def __init__(self, llm):
        super().__init__(llm, MANAGEMENT_TOOLS, MANAGEMENT_SUB_AGENT_PROMPT)
