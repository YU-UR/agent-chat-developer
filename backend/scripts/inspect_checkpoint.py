import asyncio
import os
import sys
from typing import Any
from dotenv import load_dotenv
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from langgraph.checkpoint.postgres.aio import (
    AsyncPostgresSaver,
)
# python -m scripts.inspect_checkpoint bc3311e9-f75f-463e-9337-039149566858

# ============================================================
# Configuration
# ============================================================

load_dotenv()
print(os.getcwd())

DATABASE_URL_ENV = (
    "LANGGRAPH_CHECKPOINT_DATABASE_URL"
)


# ============================================================
# Formatting helpers
# ============================================================

def print_separator(
    title: str,
) -> None:

    print()
    print("=" * 70)
    print(title)
    print("=" * 70)


def shorten(
    value: Any,
    max_length: int = 500,
) -> str:

    if value is None:
        return "None"

    text = str(value)

    if len(text) <= max_length:
        return text

    return (
        text[:max_length]
        + "..."
    )


def print_messages(
    messages: list[Any],
) -> None:

    print_separator(
        "MESSAGES"
    )

    if not messages:

        print(
            "(no messages)"
        )

        return

    for index, message in enumerate(
        messages,
        start=1,
    ):

        message_type = getattr(
            message,
            "type",
            type(message).__name__,
        )

        message_id = getattr(
            message,
            "id",
            None,
        )

        content = getattr(
            message,
            "content",
            message,
        )

        print()
        print(
            f"[{index}] "
            f"type={message_type}"
        )

        print(
            f"id={message_id}"
        )

        print(
            "content:"
        )

        print(
            shorten(
                content,
                max_length=2000,
            )
        )


def print_state(
    state: dict[str, Any],
) -> None:

    print_separator(
        "GRAPH STATE"
    )

    if not state:

        print(
            "(empty state)"
        )

        return

    # messages 已经单独打印，
    # 这里不重复输出。
    for key, value in state.items():

        if key == "messages":
            continue

        print(
            f"{key}: "
            f"{shorten(value)}"
        )


# ============================================================
# Checkpoint inspection
# ============================================================

async def inspect_checkpoint(
    thread_id: str,
) -> None:

    database_url = os.getenv(
        DATABASE_URL_ENV
    )

    if not database_url:

        raise RuntimeError(
            f"{DATABASE_URL_ENV} "
            "is not configured"
        )

    print_separator(
        "LANGGRAPH CHECKPOINT INSPECTOR"
    )

    print(
        f"thread_id: {thread_id}"
    )

    # --------------------------------------------------------
    # PostgreSQL connection pool
    # --------------------------------------------------------

    pool = AsyncConnectionPool(
        conninfo=database_url,

        min_size=1,
        max_size=2,

        open=False,

        kwargs={
            "autocommit": True,
            "prepare_threshold": 0,
            "row_factory": dict_row,
        },
    )

    try:

        await pool.open()

        checkpointer = (
            AsyncPostgresSaver(
                pool
            )
        )

        # 注意：
        #
        # 这里不调用：
        #
        # await checkpointer.setup()
        #
        # 因为这是检查工具，
        # 不应该承担数据库初始化职责。

        config = {
            "configurable": {
                "thread_id":
                    thread_id,
            }
        }

        # ----------------------------------------------------
        # Read latest checkpoint
        # ----------------------------------------------------

        checkpoint_tuple = (
            await checkpointer.aget_tuple(
                config
            )
        )

        if checkpoint_tuple is None:

            print_separator(
                "RESULT"
            )

            print(
                "No checkpoint found "
                f"for thread_id={thread_id}"
            )

            return

        # ----------------------------------------------------
        # Basic checkpoint information
        # ----------------------------------------------------

        print_separator(
            "CHECKPOINT"
        )

        checkpoint_config = (
            checkpoint_tuple.config
        )

        configurable = (
            checkpoint_config.get(
                "configurable",
                {}
            )
        )

        checkpoint_id = (
            configurable.get(
                "checkpoint_id"
            )
        )

        checkpoint_ns = (
            configurable.get(
                "checkpoint_ns",
                ""
            )
        )

        print(
            f"thread_id: "
            f"{configurable.get('thread_id')}"
        )

        print(
            f"checkpoint_ns: "
            f"{checkpoint_ns}"
        )

        print(
            f"checkpoint_id: "
            f"{checkpoint_id}"
        )

        # ----------------------------------------------------
        # Checkpoint metadata
        # ----------------------------------------------------

        print_separator(
            "METADATA"
        )

        metadata = (
            checkpoint_tuple.metadata
        )

        if metadata:

            for key, value in (
                metadata.items()
            ):

                print(
                    f"{key}: "
                    f"{shorten(value)}"
                )

        else:

            print(
                "(no metadata)"
            )

        # ----------------------------------------------------
        # Extract state
        # ----------------------------------------------------

        checkpoint = (
            checkpoint_tuple.checkpoint
        )

        channel_values = (
            checkpoint.get(
                "channel_values",
                {}
            )
        )

        if not isinstance(
            channel_values,
            dict,
        ):

            raise RuntimeError(
                "Unexpected checkpoint "
                "channel_values format"
            )

        # ----------------------------------------------------
        # Messages
        # ----------------------------------------------------

        messages = (
            channel_values.get(
                "messages",
                []
            )
        )

        print_messages(
            messages
        )

        # ----------------------------------------------------
        # Other Graph State
        # ----------------------------------------------------

        print_state(
            channel_values
        )

        # ----------------------------------------------------
        # Pending writes
        # ----------------------------------------------------

        print_separator(
            "PENDING WRITES"
        )

        pending_writes = (
            checkpoint_tuple.pending_writes
        )

        if not pending_writes:

            print(
                "(none)"
            )

        else:

            for item in pending_writes:

                print(
                    shorten(
                        item,
                        max_length=1000,
                    )
                )

        # ----------------------------------------------------
        # Summary
        # ----------------------------------------------------

        print_separator(
            "SUMMARY"
        )

        print(
            f"messages_count: "
            f"{len(messages)}"
        )

        print(
            f"latest_run_id: "
            f"{channel_values.get('run_id')}"
        )

        print(
            "conversation_id: "
            f"{channel_values.get('conversation_id')}"
        )

        print(
            f"route: "
            f"{channel_values.get('route')}"
        )

        print(
            "revision_count: "
            f"{channel_values.get('revision_count')}"
        )

        print(
            f"final_answer: "
            f"{shorten(channel_values.get('final_answer'))}"
        )

    finally:

        await pool.close()


# ============================================================
# CLI
# ============================================================

async def main() -> None:

    if len(sys.argv) != 2:

        print(
            "Usage:"
        )

        print(
            "python -m scripts.inspect_checkpoint "
            "<conversation_id>"
        )

        sys.exit(1)

    thread_id = (
        sys.argv[1].strip()
    )

    if not thread_id:

        print(
            "conversation_id/thread_id "
            "cannot be empty"
        )

        sys.exit(1)

    await inspect_checkpoint(
        thread_id
    )


# ============================================================
# Entry point
# ============================================================

if __name__ == "__main__":

    # psycopg async 在 Windows 下不能使用
    # ProactorEventLoop。
    #
    # 与 chat_worker.py 使用相同策略。
    if sys.platform == "win32":

        asyncio.set_event_loop_policy(
            asyncio.WindowsSelectorEventLoopPolicy()
        )

    asyncio.run(
        main()
    )