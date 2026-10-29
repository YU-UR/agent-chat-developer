import os
from dotenv import load_dotenv
from psycopg.rows import dict_row
from psycopg_pool import (
    AsyncConnectionPool,
)

from langgraph.checkpoint.postgres.aio import (
    AsyncPostgresSaver,
)

from app.agents.chat.graph import (
    build_chat_graph,
)
"""
启动并管理 LangGraph Runtime，把 PostgreSQL 配置成 LangGraph 的 Checkpoint（检查点）存储，并生成一个可执行的聊天图（Graph）。
"""

load_dotenv()
print(os.getcwd())
_pool: AsyncConnectionPool | None = None

_checkpointer: (
    AsyncPostgresSaver | None
) = None

_chat_graph = None


async def start_langgraph_runtime():
    global _pool
    global _checkpointer
    global _chat_graph

    if _chat_graph is not None:
        return

    database_url = os.getenv(
        "LANGGRAPH_CHECKPOINT_DATABASE_URL"
    )
    print("database_url =", repr(database_url))

    if not database_url:
        raise RuntimeError(
            "LANGGRAPH_CHECKPOINT_DATABASE_URL "
            "is not configured"
        )

    print(
        "LANGGRAPH CHECKPOINT:",
        "connecting PostgreSQL",
    )

    _pool = AsyncConnectionPool(
        conninfo=database_url,

        min_size=1,
        max_size=5,

        open=False,

        kwargs={
            "autocommit": True,
            "prepare_threshold": 0,
            "row_factory": dict_row,
        },
    )

    await _pool.open()

    _checkpointer = (
        AsyncPostgresSaver(
            _pool
        )
    )

    # 第一次执行会创建 LangGraph
    # 自己需要的 checkpoint 表。
    # 后续重复执行是安全的。
    await _checkpointer.setup()

    _chat_graph = build_chat_graph(
        checkpointer=_checkpointer
    )

    print(
        "LANGGRAPH CHECKPOINT READY"
    )


async def stop_langgraph_runtime():
    global _pool
    global _checkpointer
    global _chat_graph

    _chat_graph = None
    _checkpointer = None

    if _pool is not None:
        await _pool.close()
        _pool = None

    print(
        "LANGGRAPH CHECKPOINT STOPPED"
    )


def get_chat_graph():

    if _chat_graph is None:
        raise RuntimeError(
            "LangGraph runtime "
            "has not been started"
        )

    return _chat_graph


def get_checkpointer():

    if _checkpointer is None:
        raise RuntimeError(
            "LangGraph checkpointer "
            "has not been started"
        )

    return _checkpointer
