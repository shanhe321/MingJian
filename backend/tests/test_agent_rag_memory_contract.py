import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from app.agent.detection_agent import detection_agent
from app.agent.memory import ConversationMemory, conversation_memory
from app.api.auth import get_current_user
from app.config.settings import settings
from app.rag.document_loader import DocumentLoader
from app.rag.embedding import EmbeddingService
from app.rag.retriever import KnowledgeRetriever
from app.vectorstore.pgvector_client import CREATE_INDEX_SQL, PgvectorClient
from main import app


class MemoryRedis:
    def __init__(self):
        self.values = {}

    def rpush(self, key, *values):
        self.values.setdefault(key, []).extend(values)

    def lrange(self, key, start, end):
        items = self.values.get(key, [])
        stop = None if end == -1 else end + 1
        return items[start:stop]

    def expire(self, key, ttl):
        return True

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value, expire=None):
        self.values[key] = value

    def delete(self, key):
        self.values.pop(key, None)


def test_memory_preserves_chronological_order_and_key_format():
    memory = ConversationMemory(max_messages=20)
    memory.redis = MemoryRedis()

    memory.save_message(7, "abc123", "user", "第一条")
    memory.save_message(7, "abc123", "ai", "第二条")

    assert memory._session_key(7, "abc123") == "chat:session:7:abc123"
    assert memory.load_history(7, "abc123") == [
        {"role": "user", "content": "第一条"},
        {"role": "ai", "content": "第二条"},
    ]
    assert memory.get_sessions(7) == ["abc123"]

    memory.clear_session(7, "abc123")
    assert memory.load_history(7, "abc123") == []


def test_document_loader_loads_three_documents_and_splits_them():
    documents = DocumentLoader.load_documents()
    chunks = DocumentLoader.split_documents(
        documents,
        chunk_size=200,
        chunk_overlap=20,
    )

    assert {document["metadata"]["source"] for document in documents} == {
        "evaluation_metrics.md",
        "pcb_defects.md",
        "yolo_basics.md",
    }
    assert len(chunks) > len(documents)
    assert all(chunk["content"] for chunk in chunks)
    assert all("header_context" in chunk["metadata"] for chunk in chunks)


def test_embedding_service_respects_qwen_batch_limit(monkeypatch):
    service = EmbeddingService()
    calls = []

    class Embeddings:
        def create(self, model, input):
            calls.append((model, list(input)))
            return SimpleNamespace(
                data=[SimpleNamespace(embedding=[float(index)]) for index, _ in enumerate(input)]
            )

    service._client = SimpleNamespace(embeddings=Embeddings())
    service._model = "test-embedding"
    monkeypatch.setattr(service, "_init_client", lambda: None)

    result = service.embed_texts([str(index) for index in range(45)])

    assert [len(batch) for _, batch in calls] == [10, 10, 10, 10, 5]
    assert len(result) == 45


def test_pgvector_client_uses_cast_parameters(monkeypatch):
    executed = []

    class Database:
        def execute(self, statement, params=None):
            executed.append((str(statement), params))
            return SimpleNamespace(fetchall=lambda: [])

        def commit(self):
            pass

        def rollback(self):
            pass

        def close(self):
            pass

    module = __import__("app.vectorstore.pgvector_client", fromlist=["SessionLocal"])
    monkeypatch.setattr(module, "SessionLocal", Database)
    monkeypatch.setattr(settings, "EMBEDDING_DIM", 3)

    inserted = PgvectorClient().insert_embeddings(
        ["content"],
        [[0.1, 0.2, 0.3]],
        [{"source": "test.md"}],
    )

    assert inserted == 1
    assert "CAST(:metadata AS jsonb)" in executed[0][0]
    assert "CAST(:embedding AS vector)" in executed[0][0]


def test_pgvector_uses_hnsw_for_small_dynamic_knowledge_base():
    assert "USING hnsw" in CREATE_INDEX_SQL
    assert "ivfflat" not in CREATE_INDEX_SQL


def test_retriever_build_and_search_pipeline(monkeypatch):
    module = __import__("app.rag.retriever", fromlist=["document_loader"])
    retriever = KnowledgeRetriever()
    stored = {}

    monkeypatch.setattr(module.pgvector_client, "init_table", lambda: True)
    monkeypatch.setattr(module.pgvector_client, "count", lambda: 0)
    monkeypatch.setattr(module.pgvector_client, "clear", lambda: True)
    monkeypatch.setattr(
        module.document_loader,
        "load_documents",
        lambda: [{"content": "doc", "metadata": {"source": "doc.md"}}],
    )
    monkeypatch.setattr(
        module.document_loader,
        "split_documents",
        lambda docs: [{"content": "chunk", "metadata": {"source": "doc.md"}}],
    )
    monkeypatch.setattr(module.embedding_service, "embed_texts", lambda texts: [[0.1]])
    monkeypatch.setattr(module.embedding_service, "embed_query", lambda query: [0.1])

    def insert(contents, embeddings, metadatas):
        stored.update(
            contents=contents,
            embeddings=embeddings,
            metadatas=metadatas,
        )
        return 1

    monkeypatch.setattr(module.pgvector_client, "insert_embeddings", insert)
    monkeypatch.setattr(
        module.pgvector_client,
        "search",
        lambda embedding, top_k: [
            {"content": "answer", "metadata": {"source": "doc.md"}, "similarity": 0.9}
        ],
    )

    stats = retriever.build_index(force_rebuild=True)
    results = retriever.search("query", top_k=1)

    assert stored["contents"] == ["chunk"]
    assert stats["index_built"] is True
    assert results[0]["similarity"] == 0.9


def test_knowledge_routes_require_jwt(client):
    for method, path in [
        ("get", "/api/knowledge/stats"),
        ("post", "/api/knowledge/build"),
        ("post", "/api/knowledge/search"),
    ]:
        request = getattr(client, method)
        response = request(path) if method == "get" else request(
            path, json={"query": "IoU"}
        )
        assert response.status_code == 401


def test_knowledge_api_contract(client, monkeypatch):
    retriever_module = __import__("app.api.knowledge", fromlist=["knowledge_retriever"])
    monkeypatch.setattr(
        retriever_module.knowledge_retriever,
        "build_index",
        lambda force_rebuild=False: {"total_chunks": 3, "index_built": True},
    )
    monkeypatch.setattr(
        retriever_module.knowledge_retriever,
        "get_stats",
        lambda: {"total_chunks": 3, "index_built": True},
    )
    monkeypatch.setattr(
        retriever_module.knowledge_retriever,
        "search",
        lambda query, top_k: [{"content": query, "similarity": 1.0}],
    )
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=1)
    try:
        assert client.post("/api/knowledge/build?force_rebuild=true").json()["stats"][
            "total_chunks"
        ] == 3
        assert client.get("/api/knowledge/stats").json()["index_built"] is True
        response = client.post(
            "/api/knowledge/search",
            json={"query": "IoU", "top_k": 1},
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.json()["count"] == 1


def test_chat_session_list_and_clear_api(client, monkeypatch):
    calls = []
    monkeypatch.setattr(
        conversation_memory,
        "get_sessions",
        lambda user_id: ["session-a", "session-b"] if user_id == 6 else [],
    )
    monkeypatch.setattr(
        conversation_memory,
        "clear_session",
        lambda user_id, session_id: calls.append((user_id, session_id)),
    )
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=6)
    try:
        sessions = client.get("/api/chat/sessions")
        cleared = client.post(
            "/api/chat/clear",
            json={"session_id": "session-a"},
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert sessions.json() == {"sessions": ["session-a", "session-b"]}
    assert cleared.json() == {"message": "会话 session-a 已清空"}
    assert calls == [(6, "session-a")]


@pytest.mark.asyncio
async def test_agent_stream_emits_six_event_types_and_saves_memory(monkeypatch):
    class Graph:
        async def astream_events(self, state, version):
            assert state["user_id"] == 1
            assert state["session_id"] == "session1"
            assert version == "v2"
            yield {
                "event": "on_tool_start",
                "name": "search_knowledge",
                "data": {"input": {"query": "IoU"}},
                "metadata": {"langgraph_node": "qa"},
            }
            yield {
                "event": "on_tool_end",
                "name": "search_knowledge",
                "data": {"output": "result"},
                "metadata": {"langgraph_node": "qa"},
            }
            yield {
                "event": "on_chat_model_stream",
                "name": "ChatOpenAI",
                "data": {"chunk": SimpleNamespace(content="回答")},
                "metadata": {"langgraph_node": "summarize"},
            }
            yield {
                "event": "on_chain_end",
                "name": "LangGraph",
                "data": {"output": {"final_response": "回答"}},
                "metadata": {},
            }

    saved = []
    monkeypatch.setattr(detection_agent, "graph", Graph())
    monkeypatch.setattr(conversation_memory, "load_history", lambda *args: [])
    monkeypatch.setattr(
        conversation_memory,
        "save_message",
        lambda user_id, session_id, role, content: saved.append((role, content)),
    )

    output = [
        event
        async for event in detection_agent.chat_stream(
            "什么是 IoU？",
            user_id=1,
            session_id="session1",
        )
    ]

    assert {event["type"] for event in output} == {
        "thinking",
        "tool_start",
        "tool_end",
        "text_chunk",
        "done",
    }
    assert ("user", "什么是 IoU？") in saved
    assert ("ai", "回答") in saved

    class FailingGraph:
        async def astream_events(self, state, version):
            raise RuntimeError("failed")
            yield

    monkeypatch.setattr(detection_agent, "graph", FailingGraph())
    error_output = [
        event
        async for event in detection_agent.chat_stream(
            "失败请求",
            user_id=1,
            session_id="session1",
        )
    ]
    assert "error" in {event["type"] for event in error_output}


def test_agent_has_exactly_eight_documented_tools():
    assert [tool.name for tool in detection_agent.all_tools] == [
        "detect_single_image",
        "detect_batch_images",
        "detect_zip_images_file",
        "detect_video_file",
        "query_detection_stats",
        "query_detection_history",
        "query_user_list",
        "search_knowledge",
    ]
