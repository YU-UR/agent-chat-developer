import logging
import os
import threading
import time
from typing import Any

from dotenv import load_dotenv
from mem0 import Memory
from mem0.utils.factory import VectorStoreFactory

load_dotenv()

logger = logging.getLogger(__name__)

MEMORY_COLLECTION_NAME = (
    "agent_chat_memories"
)

EMBEDDING_MODEL = (
    "sentence-transformers/"
    "paraphrase-multilingual-MiniLM-L12-v2"
)
MEMORY_LLM_BASE_URL = os.getenv(
    "MEMORY_LLM_BASE_URL",
    "http://127.0.0.1:8020/v1",
)

MILVUS_URI = os.getenv(
    "MILVUS_URI",
    "http://127.0.0.1:19530",
)

memory_config = {
    "llm": {
        "provider": "vllm",

        "config": {
            "model":
                "Qwen/Qwen2.5-0.5B-Instruct",
            "vllm_base_url":
                MEMORY_LLM_BASE_URL,

            "temperature": 0,
            "max_tokens": 256,
        },
    },
    "vector_store": {
        "provider": "milvus",

        "config": {
            "collection_name":
                MEMORY_COLLECTION_NAME,

            "url":
                MILVUS_URI,

            "token": "",

            "embedding_model_dims":
                384,
        },
    },

    "embedder": {
        "provider": "huggingface",

        "config": {
            "model":
                EMBEDDING_MODEL,
        },
    },
}

# memory = Memory.from_config(memory_config)

_memory: Memory | None = None
_memory_lock = threading.RLock()

# 这些操作只读，可以在连接恢复后有限次数重试。
_READ_ONLY_METHODS = {
    "search",
    "get_all",
    "get",
}

_CONNECTION_ERROR_MARKERS = (
    "cannot invoke rpc on closed channel",
    "closed channel",
    "fail connecting to server",
    "server unavailable",
    "connection refused",
    "connection reset",
    "connection timed out",
    "deadline_exceeded",
    "deadline exceeded",
    "connect_failed",
    "failed to connect",
    "statuscode.unavailable",
)


def _looks_like_connection_error(
    exc: Exception,
) -> bool:
    text = (
        f"{type(exc).__name__}: {exc}"
    ).casefold()

    return any(
        marker in text
        for marker in _CONNECTION_ERROR_MARKERS
    )


def _close_store_client(store) -> None:
    if store is None:
        return

    client = getattr(store, "client", None)
    close = getattr(client, "close", None)

    if not callable(close):
        return

    try:
        close()
    except Exception:
        # 旧连接可能已失效，不应阻止新连接替换。
        logger.debug(
            "MEMORY OLD CLIENT CLOSE FAILED",
            exc_info=True,
        )


def _get_memory_locked() -> Memory:
    """
    必须在 _memory_lock 保护下调用。

    Milvus 不可用时，初始化异常会向上抛出；
    _memory 保持 None，下次任务到来时再初始化。
    """
    global _memory

    if _memory is None:
        logger.info("MEMORY INITIALIZATION STARTED")

        candidate = Memory.from_config(
            memory_config
        )

        _memory = candidate

        logger.info(
            "MEMORY INITIALIZATION COMPLETED"
        )

    return _memory


def _rebuild_vector_store_locked(
    instance: Memory,
) -> None:
    """
    仅重新创建向量存储客户端，不删除集合或数据。
    调用时必须持有 _memory_lock。
    """
    old_store = instance.vector_store
    old_entity_store = getattr(
        instance,
        "_entity_store",
        None,
    )

    # 正确的配置层级：
    # instance.config.vector_store.provider
    # instance.config.vector_store.config
    vector_store_config = (
        instance.config.vector_store
    )

    provider = vector_store_config.provider
    provider_config = vector_store_config.config

    logger.warning(
        "MEMORY VECTOR STORE REBUILD STARTED: provider=%s",
        provider,
    )

    # 先建立新客户端。建立失败时不替换旧的 store。
    new_store = VectorStoreFactory.create(
        provider,
        provider_config,
    )

    # 更新主向量存储引用。
    instance.vector_store = new_store

    # Entity store 是延迟初始化的。
    # 清除旧引用，使后续调用重新创建。
    instance._entity_store = None

    _close_store_client(old_entity_store)
    _close_store_client(old_store)

    logger.warning(
        "MEMORY VECTOR STORE REBUILD COMPLETED"
    )


def call_memory(
    method_name: str,
    *args: Any,
    **kwargs: Any,
) -> Any:
    """
    统一调用 Mem0 的入口。

    只读方法：
        最多调用两次，连接异常后尝试重建客户端。

    写入方法：
        只执行一次写入。
        如果发生连接异常，尝试重建客户端后仍然抛出异常，
        交给 MemoryWriteTask 的失败与恢复机制处理。
    """
    with _memory_lock:

        # 初始化失败时，不能把初始化错误误认为写入成功。
        try:
            instance = _get_memory_locked()
        except Exception as exc:
            if _looks_like_connection_error(exc):
                logger.warning(
                    "MEMORY INITIALIZATION FAILED: %s",
                    exc,
                )
            raise

        attempts = (
            2
            if method_name in _READ_ONLY_METHODS
            else 1
        )

        for attempt in range(attempts):
            try:
                method = getattr(
                    instance,
                    method_name,
                )

                return method(
                    *args,
                    **kwargs,
                )

            except Exception as exc:
                if not _looks_like_connection_error(
                    exc
                ):
                    raise

                logger.warning(
                    "MEMORY CONNECTION ERROR: "
                    "method=%s attempt=%s/%s error=%s",
                    method_name,
                    attempt + 1,
                    attempts,
                    exc,
                )

                try:
                    _rebuild_vector_store_locked(
                        instance
                    )
                except Exception:
                    logger.warning(
                        "MEMORY VECTOR STORE REBUILD FAILED",
                        exc_info=True,
                    )

                # 写入失败不能自动重做，以免重复插入。
                if method_name not in _READ_ONLY_METHODS:
                    raise

                if attempt + 1 >= attempts:
                    raise

                time.sleep(0.5)

        raise RuntimeError(
            f"Unexpected Mem0 operation state: {method_name}"
        )


def mem0_get_all(
    *,
    filters: dict[str, Any],
    top_k: int = 1000,
) -> dict[str, Any]:
    result = call_memory(
        "get_all",
        filters=filters,
        top_k=top_k,
    )

    if not isinstance(result, dict):
        raise TypeError(
            f"Mem0 get_all expected dict, got {type(result).__name__}"
        )

    return result


def mem0_add(
    messages: str,
    *,
    user_id: str,
    metadata: dict[str, Any],
    infer: bool = False,
) -> dict[str, Any]:
    result = call_memory(
        "add",
        messages,
        user_id=user_id,
        metadata=metadata,
        infer=infer,
    )

    if not isinstance(result, dict):
        raise TypeError(
            f"Mem0 add expected dict, got {type(result).__name__}"
        )

    return result


def mem0_search(
    query: str,
    *,
    filters: dict[str, Any],
    top_k: int = 20,
    threshold: float = 0.0,
) -> dict[str, Any]:
    result = call_memory(
        "search",
        query,
        filters=filters,
        top_k=top_k,
        threshold=threshold,
    )

    if not isinstance(result, dict):
        raise TypeError(
            f"Mem0 search expected dict, got {type(result).__name__}"
        )

    return result
