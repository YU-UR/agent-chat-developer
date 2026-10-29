import argparse
import asyncio
from typing import Any

from app.memory.config import call_memory, mem0_get_all


USER_ID_DEFAULT = "0f067731-d1ab-4b77-8dc3-ace32dbaf248"

KNOWN_TEST_FIXTURES = {
    "The user prefers PostgreSQL for backend database projects."
}


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--user-id",
        default=USER_ID_DEFAULT,
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually delete matching test fixture records.",
    )
    args = parser.parse_args()

    result = await asyncio.to_thread(
        mem0_get_all,
        filters={"user_id": args.user_id},
        top_k=1000,
    )

    records = (
        result.get("results", [])
        if isinstance(result, dict)
        else []
    )

    matches: list[dict[str, Any]] = []

    for record in records:
        if not isinstance(record, dict):
            continue

        content = str(
            record.get("memory") or ""
        ).strip()

        if content in KNOWN_TEST_FIXTURES:
            matches.append(record)

    print(
        "MATCHING TEST FIXTURES:",
        len(matches),
    )

    if not matches:
        print("Nothing to clean.")
        return

    for record in matches:
        print(
            "MATCH:",
            f"id={record.get('id')}",
            f"memory={record.get('memory')!r}",
        )

    if not args.apply:
        print(
            "DRY RUN ONLY. Re-run with --apply to delete "
            "these exact fixture records."
        )
        return

    for record in matches:
        memory_id = record.get("id")

        if not memory_id:
            print(
                "SKIPPED: record has no ID",
                repr(record),
            )
            continue

        await asyncio.to_thread(
            call_memory,
            "delete",
            str(memory_id),
        )

        print(
            "TEST FIXTURE DELETED:",
            memory_id,
        )


if __name__ == "__main__":
    asyncio.run(main())
