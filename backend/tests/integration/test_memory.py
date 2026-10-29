from app.memory.config import memory


USER_A = (
    "0f067731-d1ab-4b77-8dc3-ace32dbaf248"
)

USER_B = (
    "11111111-1111-1111-1111-111111111111"
)


def main() -> None:

    # ---------------------------------------------
    # 1. 写入 User A 的记忆
    # # ---------------------------------------------
    # print("\n=== ADD USER A ===")
    # memory.add(
    #     "The user prefers PostgreSQL for backend database projects.",
    #     user_id=USER_A,
    #     infer=False,
    # )
    #
    # print("\n=== SEARCH USER A ===")
    # search_a = memory.search(
    #     query="Which database does the user prefer?",
    #     filters={"user_id": USER_A},
    #     limit=5,
    #     threshold=0.0,
    # )
    # print("USER A SEARCH:", search_a)

    # print("\n=== GET ALL USER A ===")
    # all_a = memory.get_all(
    #     filters={"user_id": USER_A},
    #     limit=5,
    # )
    # print("USER A ALL:", all_a)

    # ---------------------------------------------
    # 3. User B 检索
    # ---------------------------------------------

    print(
        "\n=== SEARCH USER B ==="
    )

    search_b = memory.search(
        query=(
            "Which database does "
            "the user prefer?"
        ),
        filters={
            "user_id": USER_B,
        },
        limit=5,
    )

    print(
        "USER B RESULT:",
        search_b,
    )


if __name__ == "__main__":
    main()
