"""多工具检测 Agent：RAG、统计查询、Redis 记忆与增强 SSE。"""

from typing import AsyncGenerator

from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_openai import ChatOpenAI

from app.agent.agents.analysis_agent import AnalysisSubAgent
from app.agent.agents.detection_agent import DetectionSubAgent
from app.agent.agents.qa_agent import QASubAgent
from app.agent.graph import build_agent_graph
from app.agent.memory import conversation_memory
from app.agent.prompts import DETECTION_AGENT_SYSTEM_PROMPT
from app.agent.tools.analysis_tool import ANALYSIS_TOOLS
from app.agent.tools.context import current_user_id, current_user_is_superuser
from app.agent.tools.detection_tool import (
    DETECTION_TOOLS,
    detect_batch_images,
    detect_single_image,
    detect_video_file,
    detect_zip_images_file,
)
from app.agent.tools.knowledge_tool import KNOWLEDGE_TOOLS
from app.config.settings import settings
from app.core.logger import get_logger

logger = get_logger(__name__)


def create_llm():
    """根据配置创建通义千问或 OpenAI 兼容的聊天模型。"""
    if settings.QWEN_API_KEY and settings.QWEN_API_KEY != "sk-your-qwen-api-key":
        api_key = settings.QWEN_API_KEY
        base_url = settings.QWEN_BASE_URL
        model_name = settings.QWEN_MODEL
    else:
        api_key = settings.OPENAI_API_KEY
        base_url = settings.OPENAI_BASE_URL
        model_name = settings.OPENAI_MODEL

    return ChatOpenAI(
        model=model_name,
        openai_api_key=api_key,
        openai_api_base=base_url,
        temperature=0.1,
    )


class DetectionAgent:
    """绑定 8 个工具并维护跨轮次上下文的检测智能体。"""

    def __init__(self):
        self.llm = create_llm()
        self.all_tools = DETECTION_TOOLS + ANALYSIS_TOOLS + KNOWLEDGE_TOOLS

        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", DETECTION_AGENT_SYSTEM_PROMPT),
                MessagesPlaceholder(variable_name="chat_history", optional=True),
                ("human", "{input}"),
                MessagesPlaceholder(variable_name="agent_scratchpad"),
            ]
        )
        agent = create_openai_tools_agent(
            llm=self.llm,
            tools=self.all_tools,
            prompt=prompt,
        )
        self.executor = AgentExecutor(
            agent=agent,
            tools=self.all_tools,
            verbose=True,
            max_iterations=8,
            return_intermediate_steps=True,
        )

        # 讲义中的进阶编排：Supervisor → Detection/Analysis/QA → 汇总。
        # 单 Agent executor 保留作为兼容与图构建失败时的降级路径。
        self.graph = None
        try:
            self.graph = build_agent_graph(
                self.llm,
                DetectionSubAgent(self.llm),
                AnalysisSubAgent(self.llm),
                QASubAgent(self.llm),
            )
        except Exception as exc:
            logger.error("LangGraph 多 Agent 初始化失败，将使用单 Agent 降级: %s", str(exc))

        logger.info(
            "DetectionAgent 初始化完成，绑定 %d 个工具（检测 %d + 分析 %d + 知识 %d）",
            len(self.all_tools),
            len(DETECTION_TOOLS),
            len(ANALYSIS_TOOLS),
            len(KNOWLEDGE_TOOLS),
        )

    async def chat_stream(
        self,
        message: str,
        user_id: int = 0,
        session_id: str = "default",
        image_path: str | None = None,
        user_is_superuser: bool = False,
    ) -> AsyncGenerator[dict, None]:
        """加载历史、执行 Agent，并依次产生六类 SSE 事件。"""
        if image_path:
            message = f"{message}\n[附件图片路径: {image_path}]"

        chat_history = []
        try:
            for history_message in conversation_memory.load_history(user_id, session_id):
                if history_message["role"] == "user":
                    chat_history.append(HumanMessage(content=history_message["content"]))
                elif history_message["role"] == "ai":
                    chat_history.append(AIMessage(content=history_message["content"]))
        except Exception as exc:
            logger.warning("加载对话历史失败: %s", str(exc))

        try:
            conversation_memory.save_message(user_id, session_id, "user", message)
        except Exception as exc:
            logger.warning("保存用户消息失败: %s", str(exc))

        yield {"type": "thinking", "content": "正在分析您的请求..."}

        full_text = ""
        user_token = current_user_id.set(user_id)
        superuser_token = current_user_is_superuser.set(user_is_superuser)
        try:
            if self.graph is not None:
                graph_messages = [*chat_history, HumanMessage(content=message)]
                graph_result = {}
                async for event in self.graph.astream_events(
                    {
                        "messages": graph_messages,
                        "user_id": user_id,
                        "session_id": session_id,
                        "is_superuser": user_is_superuser,
                        "tool_events": [],
                    },
                    version="v2",
                ):
                    event_kind = event.get("event")
                    metadata = event.get("metadata", {})
                    node_name = metadata.get("langgraph_node")

                    if event_kind == "on_tool_start":
                        tool_name = event.get("name", "")
                        tool_input = event.get("data", {}).get("input", {})
                        logger.info("多 Agent 工具调用: %s", tool_name)
                        safe_input = (
                            {
                                key: str(value)[:100]
                                for key, value in tool_input.items()
                            }
                            if isinstance(tool_input, dict)
                            else str(tool_input)[:100]
                        )
                        yield {
                            "type": "tool_start",
                            "tool": tool_name,
                            "input": safe_input,
                        }

                    elif event_kind == "on_tool_end":
                        tool_name = event.get("name", "")
                        tool_output = event.get("data", {}).get("output", "")
                        yield {
                            "type": "tool_end",
                            "tool": tool_name,
                            "summary": str(tool_output)[:100] if tool_output else "",
                        }

                    elif event_kind == "on_chat_model_stream" and node_name == "summarize":
                        chunk = event.get("data", {}).get("chunk")
                        content = getattr(chunk, "content", "")
                        if isinstance(content, list):
                            content = "".join(
                                item.get("text", "")
                                if isinstance(item, dict)
                                else str(item)
                                for item in content
                            )
                        if isinstance(content, str) and content:
                            full_text += content
                            yield {"type": "text_chunk", "content": content}

                    elif (
                        event_kind == "on_chain_end"
                        and event.get("name") == "LangGraph"
                    ):
                        output = event.get("data", {}).get("output", {})
                        if isinstance(output, dict):
                            graph_result = output

                final_response = graph_result.get("final_response", "") or ""
                if not full_text and final_response:
                    for start in range(0, len(final_response), 24):
                        chunk = final_response[start : start + 24]
                        full_text += chunk
                        yield {"type": "text_chunk", "content": chunk}
                elif final_response:
                    full_text = final_response
            else:
                async for event in self.executor.astream_events(
                    {"input": message, "chat_history": chat_history},
                    version="v2",
                ):
                    event_kind = event.get("event")

                    if event_kind == "on_chat_model_stream":
                        chunk = event.get("data", {}).get("chunk")
                        content = getattr(chunk, "content", "")
                        if isinstance(content, str) and content:
                            full_text += content
                            yield {"type": "text_chunk", "content": content}

                    elif event_kind == "on_tool_start":
                        tool_name = event.get("name", "")
                        tool_input = event.get("data", {}).get("input", {})
                        logger.info("工具调用: %s, 输入: %s", tool_name, str(tool_input)[:200])
                        safe_input = (
                            {key: str(value)[:100] for key, value in tool_input.items()}
                            if isinstance(tool_input, dict)
                            else str(tool_input)[:100]
                        )
                        yield {
                            "type": "tool_start",
                            "tool": tool_name,
                            "input": safe_input,
                        }

                    elif event_kind == "on_tool_end":
                        tool_name = event.get("name", "")
                        tool_output = event.get("data", {}).get("output", "")
                        logger.info("工具完成: %s", tool_name)
                        yield {
                            "type": "tool_end",
                            "tool": tool_name,
                            "summary": str(tool_output)[:100] if tool_output else "",
                        }
        except Exception as exc:
            logger.error("Agent 流式执行异常: %s", str(exc), exc_info=True)
            yield {"type": "error", "content": f"处理出错：{str(exc)}"}
        finally:
            current_user_id.reset(user_token)
            current_user_is_superuser.reset(superuser_token)

        if full_text:
            try:
                conversation_memory.save_message(user_id, session_id, "ai", full_text)
            except Exception as exc:
                logger.warning("保存 AI 回复失败: %s", str(exc))

        yield {"type": "done", "full_text": full_text}

    async def chat(
        self,
        message: str,
        image_path: str | None = None,
        user_id: int = 0,
        session_id: str = "default",
        user_is_superuser: bool = False,
    ) -> dict:
        """保留非流式调用方式，兼容现有后端调用。"""
        if image_path:
            message = f"{message}\n[附件图片路径: {image_path}]"
        try:
            if self.graph is not None:
                user_token = current_user_id.set(user_id)
                superuser_token = current_user_is_superuser.set(user_is_superuser)
                try:
                    result = await self.graph.ainvoke(
                        {
                            "messages": [HumanMessage(content=message)],
                            "user_id": user_id,
                            "session_id": session_id,
                            "is_superuser": user_is_superuser,
                            "tool_events": [],
                        }
                    )
                finally:
                    current_user_id.reset(user_token)
                    current_user_is_superuser.reset(superuser_token)
                return {
                    "output": result.get("final_response", ""),
                    "intermediate_steps": result.get("tool_events", []),
                }

            result = await self.executor.ainvoke({"input": message, "chat_history": []})
            return {
                "output": result["output"],
                "intermediate_steps": result.get("intermediate_steps", []),
            }
        except Exception as exc:
            logger.error("Agent 执行异常: %s", str(exc), exc_info=True)
            return {
                "output": f"抱歉，处理过程中出现错误：{str(exc)}",
                "intermediate_steps": [],
            }


detection_agent = DetectionAgent()
