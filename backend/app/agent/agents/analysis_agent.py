"""分析子 Agent：执行检测历史、统计和管理员查询。"""

from app.agent.agents.base import ToolAgentNode
from app.agent.prompts import ANALYSIS_SUB_AGENT_PROMPT
from app.agent.tools.analysis_tool import ANALYSIS_TOOLS


class AnalysisSubAgent(ToolAgentNode):
    result_key = "analysis_result"
    agent_name = "analysis"

    def __init__(self, llm):
        super().__init__(llm, ANALYSIS_TOOLS, ANALYSIS_SUB_AGENT_PROMPT)
