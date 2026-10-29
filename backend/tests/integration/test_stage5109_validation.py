import asyncio

from app.agents.chat.nodes import (
    finalize_node,
)


async def test_empty_draft():
    state = {
        "run_id": "validation-test-1",
        "draft_answer": "",
        "review_result": "pass",
    }

    try:
        await finalize_node(
            state,
            None,
        )
    except ValueError as exc:
        print(
            "PASS empty draft:",
            exc,
        )
        return

    raise AssertionError(
        "empty draft should fail"
    )


async def test_invalid_review_state():
    state = {
        "run_id": "validation-test-2",
        "draft_answer": "正常回答",
        "review_result": "revise",
    }

    try:
        await finalize_node(
            state,
            None,
        )
    except ValueError as exc:
        print(
            "PASS invalid review:",
            exc,
        )
        return

    raise AssertionError(
        "revise state should not finalize"
    )


async def test_valid_answer():
    state = {
        "run_id": "validation-test-3",
        "draft_answer": "  正常回答  ",
        "review_result": "pass",
    }

    result = await finalize_node(
        state,
        None,
    )

    assert (
        result["final_answer"]
        == "正常回答"
    )

    assert (
        result["messages"][0].content
        == "正常回答"
    )

    print(
        "PASS valid answer:",
        result["final_answer"],
    )


async def main():
    await test_empty_draft()

    await test_invalid_review_state()

    await test_valid_answer()

    print(
        "\nPASS: Stage 5.10.9 "
        "basic validation passed."
    )


if __name__ == "__main__":
    asyncio.run(main())