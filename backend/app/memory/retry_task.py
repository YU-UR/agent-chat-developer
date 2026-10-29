import asyncio
import sys
from uuid import UUID

from sqlalchemy import select

from app.infrastructure.database.session import AsyncSessionLocal
from app.models.memory_write_task import MemoryWriteTask
from app.models.outbox_event import OutboxEvent


async def retry_failed_task(
    task_id: UUID,
) -> None:

    async with AsyncSessionLocal() as session:
        async with session.begin():

            result = await session.execute(
                select(MemoryWriteTask)
                .where(
                    MemoryWriteTask.id == task_id
                )
                .with_for_update()
            )

            task = result.scalar_one_or_none()

            if task is None:
                raise RuntimeError(
                    f"MemoryWriteTask not found: {task_id}"
                )

            if task.status != "failed":
                raise RuntimeError(
                    "Only failed memory tasks can be retried. "
                    f"task_id={task_id}, "
                    f"status={task.status}"
                )

            # 重新排队，不清除历史 retry_count。
            task.status = "pending"
            task.last_error = None

            # 与 Task 状态变更处于同一事务。
            event = OutboxEvent(
                aggregate_type="memory_write_task",
                aggregate_id=task.id,
                event_type="memory.extract.requested",
                payload={
                    "task_id": str(task.id),
                    "source_run_id": str(
                        task.source_run_id
                    ),
                    "user_id": str(task.user_id),
                    "conversation_id": str(
                        task.conversation_id
                    ),
                },
                status="pending",
                retry_count=0,
            )

            session.add(event)

        # session.begin() 在这里成功退出并提交事务。

    print(
        "MEMORY TASK REQUEUED:",
        f"task_id={task_id}",
    )


async def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(
            "Usage: python -m app.memory.retry_task <task_id>"
        )

    try:
        task_id = UUID(sys.argv[1])
    except ValueError as exc:
        raise SystemExit(
            "task_id must be a valid UUID"
        ) from exc

    await retry_failed_task(task_id)


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(
            asyncio.WindowsSelectorEventLoopPolicy()
        )

    asyncio.run(main())
