"""子 Agent 共用的 LangChain 执行和工具事件提取逻辑。"""

from typing import Any

from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnableConfig


def _content(value: Any) -> str:
    content = getattr(value, "content", value)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            item.get("text", "") if isinstance(item, dict) else str(item)
            for item in content
        )
    return str(content)


def state_messages(state: dict) -> tuple[str, list]:
    messages = state.get("messages", [])
    if not messages:
        return "", []

    latest = _content(messages[-1])
    history = []
    for message in messages[:-1]:
        role = getattr(message, "type", "")
        content = _content(message)
        if role in {"human", "user"}:
            history.append(HumanMessage(content=content))
        elif role in {"ai", "assistant"}:
            history.append(AIMessage(content=content))
    return latest, history


class ToolAgentNode:
    """将一个工具集合封装成 LangGraph 可调用的异步节点。"""

    result_key = "detection_result"
    agent_name = "detection"

    def __init__(self, llm, tools, system_prompt):
        self.tools = tools
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", system_prompt),
                MessagesPlaceholder(variable_name="chat_history", optional=True),
                ("human", "{input}"),
                MessagesPlaceholder(variable_name="agent_scratchpad"),
            ]
        )
        agent = create_openai_tools_agent(llm=llm, tools=tools, prompt=prompt)
        self.executor = AgentExecutor(
            agent=agent,
            tools=tools,
            verbose=True,
            max_iterations=8,
            return_intermediate_steps=True,
        )

    async def __call__(
        self,
        state: dict,
        config: RunnableConfig | None = None,
    ) -> dict:
        message, history = state_messages(state)
        result = await self.executor.ainvoke(
            {"input": message, "chat_history": history},
            config=config,
        )
        tool_events = []
        for step, output in result.get("intermediate_steps", []):
            tool_events.append(
                {
                    "tool": getattr(step, "tool", ""),
                    "input": getattr(step, "tool_input", {}),
                    "output": str(output),
                }
            )
        return {
            self.result_key: {"output": result.get("output", "")},
            "tool_events": tool_events,
            "agent_used": self.agent_name,
        }
