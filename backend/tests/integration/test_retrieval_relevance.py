import asyncio

from app.memory.retriever import retrieve_memory


USER_ID = "0f067731-d1ab-4b77-8dc3-ace32dbaf248"


async def main() -> None:
    # 测试 1：问候不应查询长期记忆。
    greeting_result = await retrieve_memory({
        "user_id": USER_ID,
        "user_message": "你好",
    })

    assert greeting_result["memory_context"] == "", (
        "Greeting should not inject long-term memory."
    )

    print("TEST greeting: PASS")

    # 测试 2：数据库偏好查询只返回数据库相关记忆。
    database_result = await retrieve_memory({
        "user_id": USER_ID,
        "user_message": "我之前说过更偏好哪种后端数据库？",
    })

    database_context = (
        database_result["memory_context"]
    )

    print(
        "DATABASE CONTEXT:",
        repr(database_context),
    )

    assert "PostgreSQL".casefold() in database_context.casefold(), (
        "Expected PostgreSQL preference was not retrieved."
    )

    assert "python" not in database_context.casefold(), (
        "Programming-language memory leaked into database context."
    )

    assert "java" not in database_context.casefold(), (
        "Programming-language memory leaked into database context."
    )

    print("TEST database relevance: PASS")

    # 测试 3：编程语言查询不能被数据库偏好主导。
    language_result = await retrieve_memory({
        "user_id": USER_ID,
        "user_message": "我之前说过偏好使用什么编程语言？",
    })

    language_context = (
        language_result["memory_context"]
    )

    print(
        "LANGUAGE CONTEXT:",
        repr(language_context),
    )

    assert "python" in language_context.casefold(), (
        "Expected programming-language preference was not retrieved."
    )

    assert "PostgreSQL".casefold() not in language_context.casefold(), (
        "Database preference leaked into programming-language context."
    )

    print("TEST language relevance: PASS")


if __name__ == "__main__":
    asyncio.run(main())
