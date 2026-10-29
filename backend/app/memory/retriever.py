import asyncio
import logging
import re
from typing import Any
import os
from dotenv import load_dotenv
from app.memory.config import mem0_search
load_dotenv()

logger = logging.getLogger(__name__)

MEMORY_SEARCH_TIMEOUT_SECONDS = float(
    os.getenv("MEMORY_SEARCH_TIMEOUT_SECONDS", "60")
)
MAX_MEMORY_RESULTS = 3

LOW_VALUE_QUERIES = {
    "你好",
    "您好",
    "嗨",
    "hello",
    "hi",
    "hey",
    "你好吗",
    "谢谢",
    "谢谢你",
    "thanks",
    "thank you",
    "好的",
    "好",
    "收到",
    "明白了",
    "知道了",
    "再见",
    "拜拜",
    "ok",
    "okay",
}


# 用于限制主题明显不匹配的检索结果。
# 这是轻量级过滤规则，不替代向量相似度检索。
TOPIC_KEYWORDS = {
    "database": (
        "postgresql",
        "postgres",
        "mysql",
        "sqlite",
        "mariadb",
        "database",
        "databases",
        "sql",
        "数据库",
    ),
    "language": (
        "python",
        "java",
        "javascript",
        "typescript",
        "golang",
        "go语言",
        "编程语言",
        "开发语言",
        "programming language",
    ),
    "framework": (
        "fastapi",
        "django",
        "flask",
        "react",
        "vue",
        "langgraph",
        "框架",
        "framework",
    ),
}


def normalize_text(text: str) -> str:
    text = " ".join(text.split()).casefold()
    return text.strip(
        " \t\r\n"
        ".,!?;:，。！？；：、"
        "\"'“”‘’"
    )


def detect_topics(text: str) -> set[str]:
    normalized = normalize_text(text)

    return {
        topic
        for topic, keywords in TOPIC_KEYWORDS.items()
        if any(keyword in normalized for keyword in keywords)
    }


def extract_memory_text(item: dict[str, Any]) -> str:
    """
    兼容 Mem0 结果中的常见文本字段。
    """
    for field in ("memory", "text", "data"):
        value = item.get(field)

        if isinstance(value, str) and value.strip():
            return value.strip()

    return ""


async def retrieve_memory(
    state: dict[str, Any],
) -> dict[str, str]:
    user_id = str(state.get("user_id") or "").strip()
    query = str(state.get("user_message") or "").strip()

    print(
        f"[MEMORY] NODE ENTER "
        f"user_id={user_id!r}, query={query!r}"
    )

    if not user_id or not query:
        logger.warning(
            "MEMORY SKIPPED: user_id or user_message is empty"
        )
        return {"memory_context": ""}

    normalized_query = normalize_text(query)

    # 问候、礼貌用语不需要查询长期记忆。
    if normalized_query in LOW_VALUE_QUERIES:
        print(
            "[MEMORY] SEARCH SKIPPED:",
            f"reason=low_value_query query={query!r}",
        )
        return {"memory_context": ""}

    query_topics = detect_topics(query)

    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(
                mem0_search,
                query,
                filters={"user_id": user_id},
                top_k=10,
                threshold=0.0,
            ),
            timeout=MEMORY_SEARCH_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.warning(
            "MEMORY SEARCH TIMEOUT: user_id=%s",
            user_id,
        )
        return {"memory_context": ""}
    except Exception:
        logger.exception(
            "MEMORY SEARCH FAILED: user_id=%s",
            user_id,
        )
        return {"memory_context": ""}

    records = (
        result.get("results", [])
        if isinstance(result, dict)
        else []
    )

    seen: set[str] = set()
    unique_memories: list[str] = []

    for item in records:
        if not isinstance(item, dict):
            continue

        content = extract_memory_text(item)

        if not content:
            continue

        normalized_content = normalize_text(content)

        # 先按 memory_key 去重；旧测试记忆没有该字段时，
        # 使用规范化后的文本去重。
        metadata = item.get("metadata")
        memory_key = (
            metadata.get("memory_key")
            if isinstance(metadata, dict)
            else None
        )

        dedupe_key = (
            f"key:{memory_key}"
            if memory_key
            else f"text:{normalized_content}"
        )

        if dedupe_key in seen:
            continue

        memory_topics = detect_topics(content)

        # 如果问题有明确主题，则排除主题完全不匹配的记忆。
        # 例如问数据库偏好时，不把 Python/Java 偏好带入上下文。
        if (
            query_topics
            and not query_topics.intersection(memory_topics)
        ):
            continue

        seen.add(dedupe_key)
        unique_memories.append(content)

        if len(unique_memories) >= MAX_MEMORY_RESULTS:
            break

    memory_context = "\n".join(
        f"- {content}"
        for content in unique_memories
    )

    print(
        "[MEMORY] SEARCH RESULTS:",
        f"raw={len(records)}",
        f"selected={len(unique_memories)}",
        f"topics={sorted(query_topics)}",
    )

    print(
        "[MEMORY] CONTEXT:",
        repr(memory_context),
    )

    return {"memory_context": memory_context}
