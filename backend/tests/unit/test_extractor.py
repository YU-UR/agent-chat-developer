import asyncio

from app.memory.extractor import (
    extract_memory_candidates,
)


async def run_test(
    name: str,
    user_messages: list[str],
    expected: list[str],
) -> bool:

    print(
        f"\n"
        f"==============================\n"
        f"TEST: {name}\n"
        f"=============================="
    )

    result = await extract_memory_candidates(
        user_messages
    )

    print("EXPECTED:", expected)
    print("ACTUAL:  ", result)

    passed = result == expected

    print(
        "TEST RESULT:",
        "PASS" if passed else "FAIL",
    )

    return passed


async def main() -> None:

    preference_sentence = (
        "我今后的后端项目更偏好使用 PostgreSQL，"
        "而不是 MySQL。"
    )

    decision_sentence = (
        "我以后后端项目决定使用 PostgreSQL。"
    )

    uncertain_sentence = (
        "我考虑过使用 PostgreSQL，"
        "但还没有决定。"
    )

    changed_decision_sentence = (
        "我之前考虑使用 MySQL，"
        "但现在决定使用 PostgreSQL。"
    )

    project_sentence = (
        "我的项目使用 FastAPI 和 PostgreSQL。"
    )

    tests = [
        (
            "greeting",
            ["你好"],
            [],
        ),

        (
            "explicit_preference",
            [preference_sentence],
            [preference_sentence],
        ),

        (
            "question_only",
            [
                "后端项目应该选择 "
                "PostgreSQL 还是 MySQL？"
            ],
            [],
        ),

        (
            "explicit_decision",
            [decision_sentence],
            [decision_sentence],
        ),

        (
            "uncertain_not_decided",
            [uncertain_sentence],
            [],
        ),

        (
            "changed_final_decision",
            [changed_decision_sentence],
            [changed_decision_sentence],
        ),

        (
            "persistent_project",
            [project_sentence],
            [project_sentence],
        ),

        (
            "thanks",
            ["谢谢"],
            [],
        ),

        (
            "duplicate",
            [
                preference_sentence,
                preference_sentence,
            ],
            [preference_sentence],
        ),

        (
            "mixed_messages",
            [
                "你好",
                preference_sentence,
                "谢谢",
            ],
            [preference_sentence],
        ),
    ]

    passed_count = 0

    for name, messages, expected in tests:

        passed = await run_test(
            name=name,
            user_messages=messages,
            expected=expected,
        )

        if passed:
            passed_count += 1

    print(
        "\n"
        "==============================\n"
        "FINAL RESULT\n"
        "=============================="
    )

    print(
        f"PASSED: {passed_count}/{len(tests)}"
    )

    if passed_count == len(tests):
        print("ALL TESTS PASSED")
    else:
        print("SOME TESTS FAILED")


if __name__ == "__main__":
    asyncio.run(main())
