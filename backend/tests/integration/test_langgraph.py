import asyncio

from app.agents.chat.context import ChatGraphContext
from app.agents.chat.graph import (
    chat_graph,
)


async def main():

    initial_state = {
        "run_id": "test-run-001",
        "conversation_id": "test-conversation",
        "user_message": (
            "请解释 Kafka 和 Redis Stream "
            "在企业级 AI 聊天系统中的职责区别，"
            "以及为什么两者可以同时使用。"
        ),
        "revision_count": 0,
        "max_revisions": 1,
    }

    result = await chat_graph.ainvoke(
        initial_state,
        context=ChatGraphContext(),
    )

    print(
        "\n============================"
    )

    print(
        "FINAL STATE:"
    )

    print(result)

    print(
        "\nFINAL ANSWER:"
    )

    print(
        result["final_answer"]
    )


if __name__ == "__main__":
    asyncio.run(main())
