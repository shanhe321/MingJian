"""加载知识文档并切分为可检索文本块。"""

from pathlib import Path

from app.config.settings import settings
from app.core.logger import get_logger

logger = get_logger(__name__)

KNOWLEDGE_BASE_DIR = Path(__file__).resolve().parents[2] / "knowledge_base"


class DocumentLoader:
    """Markdown/TXT 领域文档加载器。"""

    @staticmethod
    def load_documents(base_dir: str | Path | None = None) -> list[dict]:
        """加载目录中的 Markdown/TXT 文档并保留来源元数据。"""
        base_path = Path(base_dir) if base_dir is not None else KNOWLEDGE_BASE_DIR
        if not base_path.exists():
            logger.warning("知识库目录不存在: %s", base_path)
            return []

        documents = []
        file_paths = sorted(base_path.glob("*.md")) + sorted(base_path.glob("*.txt"))
        for file_path in file_paths:
            try:
                content = file_path.read_text(encoding="utf-8")
                documents.append(
                    {
                        "content": content,
                        "metadata": {
                            "source": file_path.name,
                            "title": DocumentLoader._extract_title(content, file_path.stem),
                            "file_path": str(file_path),
                        },
                    }
                )
                logger.info("加载文档: %s (%d 字符)", file_path.name, len(content))
            except Exception as exc:
                logger.error("加载文档失败: %s, 错误: %s", file_path, str(exc))

        logger.info("共加载 %d 个文档", len(documents))
        return documents

    @staticmethod
    def split_documents(
        documents: list[dict],
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
    ) -> list[dict]:
        """按段落优先切分文档，并为相邻块保留指定字符重叠。"""
        chunk_size = chunk_size or settings.RAG_CHUNK_SIZE
        chunk_overlap = (
            settings.RAG_CHUNK_OVERLAP if chunk_overlap is None else chunk_overlap
        )
        chunks = []

        for document in documents:
            current_chunk = ""
            current_headers: list[dict] = []
            metadata = document["metadata"]

            for paragraph in document["content"].split("\n\n"):
                paragraph = paragraph.strip()
                if not paragraph:
                    continue

                if paragraph.startswith("#"):
                    level = len(paragraph) - len(paragraph.lstrip("#"))
                    current_headers = [h for h in current_headers if h["level"] < level]
                    current_headers.append(
                        {"level": level, "text": paragraph.lstrip("#").strip()}
                    )

                if len(current_chunk) + len(paragraph) + 2 > chunk_size and current_chunk:
                    chunks.append(
                        {
                            "content": current_chunk.strip(),
                            "metadata": {
                                **metadata,
                                "header_context": " > ".join(
                                    header["text"] for header in current_headers
                                ),
                                "chunk_index": len(chunks),
                            },
                        }
                    )
                    overlap = current_chunk[-chunk_overlap:] if chunk_overlap > 0 else ""
                    current_chunk = f"{overlap}\n\n{paragraph}" if overlap else paragraph
                else:
                    current_chunk = (
                        f"{current_chunk}\n\n{paragraph}" if current_chunk else paragraph
                    )

            if current_chunk.strip():
                chunks.append(
                    {
                        "content": current_chunk.strip(),
                        "metadata": {
                            **metadata,
                            "header_context": " > ".join(
                                header["text"] for header in current_headers
                            ),
                            "chunk_index": len(chunks),
                        },
                    }
                )

        logger.info("文档分块完成: %d 个文档 → %d 个文本块", len(documents), len(chunks))
        return chunks

    @staticmethod
    def _extract_title(content: str, default: str) -> str:
        """提取 Markdown 一级标题。"""
        for line in content.splitlines():
            line = line.strip()
            if line.startswith("# "):
                return line[2:].strip()
        return default


document_loader = DocumentLoader()
