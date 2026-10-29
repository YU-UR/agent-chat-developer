import asyncio
import sys
import uuid

from app.infrastructure.database.session import AsyncSessionLocal
from app.memory.task_processor import process_memory_task


async def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(
            "Usage: python -m app.memory.test_task_processor <task_id>"
        )

    try:
        task_id = uuid.UUID(sys.argv[1])
    except ValueError as exc:
        raise SystemExit("task_id must be a valid UUID") from exc

    async with AsyncSessionLocal() as session:
        await process_memory_task(
            session,
            task_id=task_id,
        )


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(
            asyncio.WindowsSelectorEventLoopPolicy()
        )

    asyncio.run(main())
