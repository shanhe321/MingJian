"""多工具检测 Agent：RAG、统计查询、Redis 记忆与增强 SSE。"""

import json

from typing import AsyncGenerator

from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_openai import ChatOpenAI

from app.agent.agents.analysis_agent import AnalysisSubAgent
from app.agent.agents.detection_agent import DetectionSubAgent
from app.agent.agents.management_agent import ManagementSubAgent
from app.agent.graph import build_agent_graph
from app.agent.memory import conversation_memory
from app.agent.prompts import DETECTION_AGENT_SYSTEM_PROMPT
from app.agent.tools.analysis_tool import ANALYSIS_TOOLS, MANAGEMENT_TOOLS
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


def _safe_event_value(value):
    """移除 SSE 工具事件中的服务器路径和大体积载荷。"""
    if isinstance(value, dict):
        return {
            key: (
                "[已隐藏]"
                if "path" in key.lower() or "base64" in key.lower()
                else _safe_event_value(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_safe_event_value(item) for item in value]
    return value


def _safe_tool_summary(value) -> str:
    if not value:
        return ""
    try:
        parsed = json.loads(str(value))
    except (json.JSONDecodeError, TypeError):
        return "工具执行完成"
    return json.dumps(_safe_event_value(parsed), ensure_ascii=False)[:100]


def create_llm(enable_thinking: bool | None = None):
    """创建聊天模型；仅在显式指定时传递千问思考模式参数。"""
    llm_kwargs = {}
    if settings.QWEN_API_KEY and settings.QWEN_API_KEY != "sk-your-qwen-api-key":
        api_key = settings.QWEN_API_KEY
        base_url = settings.QWEN_BASE_URL
        model_name = settings.QWEN_MODEL
        if enable_thinking is not None:
            # 该参数仅发送给 DashScope 兼容接口。主 Agent 不指定，保持模型
            # 默认推理能力；Supervisor 显式关闭以缩短路由与汇总延迟。
            llm_kwargs["extra_body"] = {"enable_thinking": enable_thinking}
    else:
        api_key = settings.OPENAI_API_KEY
        base_url = settings.OPENAI_BASE_URL
        model_name = settings.OPENAI_MODEL

    return ChatOpenAI(
        model=model_name,
        openai_api_key=api_key,
        openai_api_base=base_url,
        temperature=0.1,
        **llm_kwargs,
    )


class DetectionAgent:
    """绑定检测、分析、管理和知识工具并维护跨轮次上下文。"""

    def __init__(self):
        self.llm = create_llm()
        self.supervisor_llm = create_llm(
            enable_thinking=settings.SUPERVISOR_ENABLE_THINKING
        )
        self.all_tools = DETECTION_TOOLS + ANALYSIS_TOOLS + MANAGEMENT_TOOLS + KNOWLEDGE_TOOLS

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

        # 需求定义的编排：Supervisor → Management/Detection/Analysis → 汇总。
        # 单 Agent executor 保留作为兼容与图构建失败时的降级路径。
        self.graph = None
        try:
            self.graph = build_agent_graph(
                self.llm,
                ManagementSubAgent(self.llm),
                DetectionSubAgent(self.llm),
                AnalysisSubAgent(self.llm),
                supervisor_llm=self.supervisor_llm,
            )
        except Exception as exc:
            logger.error("LangGraph 多 Agent 初始化失败，将使用单 Agent 降级: %s", str(exc))

        logger.info(
            "DetectionAgent 初始化完成，绑定 %d 个工具（检测 %d + 分析 %d + 管理 %d + 知识 %d）",
            len(self.all_tools),
            len(DETECTION_TOOLS),
            len(ANALYSIS_TOOLS),
            len(MANAGEMENT_TOOLS),
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
        user_message = message
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
            conversation_memory.save_message(user_id, session_id, "user", user_message)
        except Exception as exc:
            logger.warning("保存用户消息失败: %s", str(exc))

        yield {"type": "thinking", "content": "正在分析您的请求..."}

        full_text = ""
        agent_used = None
        announced_nodes = set()
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

                    if (
                        event_kind == "on_chain_start"
                        and node_name in {"supervisor", "management", "detection", "analysis", "summarize"}
                        and node_name not in announced_nodes
                    ):
                        announced_nodes.add(node_name)
                        phase_text = {
                            "supervisor": "正在理解问题并选择处理方式...",
                            "management": "正在查询系统管理信息...",
                            "detection": "正在执行检测并分析结果...",
                            "analysis": "正在查询数据与知识库...",
                            "summarize": "正在整理并生成最终回复...",
                        }[node_name]
                        yield {"type": "thinking", "content": phase_text}

                    elif event_kind == "on_tool_start":
                        tool_name = event.get("name", "")
                        tool_input = event.get("data", {}).get("input", {})
                        logger.info("多 Agent 工具调用: %s", tool_name)
                        safe_input = _safe_event_value(
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
                            "summary": _safe_tool_summary(tool_output),
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
                            agent_used = output.get("agent_used")

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
                        safe_input = _safe_event_value(
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
                            "summary": _safe_tool_summary(tool_output),
                        }
        except Exception as exc:
            logger.error("Agent 流式执行异常: %s", str(exc), exc_info=True)
            yield {"type": "error", "content": "处理出错，请稍后重试或检查上传文件"}
        finally:
            current_user_id.reset(user_token)
            current_user_is_superuser.reset(superuser_token)

        if full_text:
            try:
                conversation_memory.save_message(
                    user_id,
                    session_id,
                    "ai",
                    full_text,
                    agent_used=agent_used,
                )
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
                "output": "抱歉，处理过程中出现错误，请稍后重试。",
                "intermediate_steps": [],
            }


detection_agent = DetectionAgent()
