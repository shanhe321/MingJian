"""检测子 Agent：执行 PCB 图片、ZIP 和视频检测。"""

from app.agent.agents.base import ToolAgentNode
from app.agent.prompts import DETECTION_SUB_AGENT_PROMPT
from app.agent.tools.detection_tool import DETECTION_TOOLS


class DetectionSubAgent(ToolAgentNode):
    result_key = "detection_result"
    agent_name = "detection"

    def __init__(self, llm):
        super().__init__(llm, DETECTION_TOOLS, DETECTION_SUB_AGENT_PROMPT)
