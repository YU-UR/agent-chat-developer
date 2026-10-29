import uuid
from sqlalchemy.ext.asyncio import AsyncSession

from app.memory.extractor import extract_memory_candidates
from app.memory.safety import contains_sensitive_data
from app.memory.writer import write_memory_item
from app.repositories.memory_write_task_repository import (
    MemoryWriteTaskRepository,
)


async def process_memory_task(
    session: AsyncSession,
    *,
    task_id: uuid.UUID,
) -> None:
    """
    处理一个 MemoryWriteTask。

    流程：
    1. 查询并标记 Task 为 processing。
    2. 只从 task.user_message 提取记忆。
    3. 过滤敏感信息。
    4. 幂等创建 MemoryWriteItem。
    5. 逐条写入 Mem0，并保存处理状态。
    6. 全部成功后将 Task 标为 completed。

    异常时记录 failed 并重新抛出，
    让上层 Kafka Worker 决定重试及何时提交 offset。
    """
    repo = MemoryWriteTaskRepository(session)

    task = await repo.get_by_id_for_update(task_id)

    if task is None:
        raise RuntimeError(
            f"MemoryWriteTask not found: {task_id}"
        )

    if task.status == "completed":
        print(
            "MEMORY TASK ALREADY COMPLETED:",
            f"task_id={task.id}",
        )
        return

    try:
        # 先保存处理状态。
        await repo.mark_processing(task)
        await session.commit()

        # ----------------------------------------------------
        # 1. 只处理用户当前消息，不使用 assistant_message。
        # ----------------------------------------------------
        user_message = (task.user_message or "").strip()

        if user_message:
            candidates = await extract_memory_candidates(
                [user_message]
            )
        else:
            candidates = []

        # ----------------------------------------------------
        # 2. 敏感信息过滤。
        # ----------------------------------------------------
        safe_candidates: list[str] = []

        for content in candidates:
            content = content.strip()

            if not content:
                continue

            if contains_sensitive_data(content):
                print(
                    "MEMORY CANDIDATE DROPPED:",
                    "reason=sensitive_data",
                )
                continue

            safe_candidates.append(content)

        # ----------------------------------------------------
        # 3. 幂等创建候选 Item。
        # ----------------------------------------------------
        for content in safe_candidates:
            created_id = await repo.create_item_if_absent(
                task_id=task.id,
                source_run_id=task.source_run_id,
                user_id=task.user_id,
                content=content,
            )

            if created_id is None:
                print(
                    "MEMORY ITEM ALREADY EXISTS:",
                    f"run_id={task.source_run_id}",
                )
            else:
                print(
                    "MEMORY ITEM CREATED:",
                    f"item_id={created_id}",
                )

        await session.commit()

        # ----------------------------------------------------
        # 4. 逐条写入 Mem0。
        # ----------------------------------------------------
        items = await repo.get_items(task.id)

        for item in items:
            if item.status == "completed":
                print(
                    "MEMORY ITEM SKIPPED:",
                    f"item_id={item.id}",
                    "reason=already_completed",
                )
                continue

            # 必须先提交 writing，再执行外部写入。
            await repo.mark_item_writing(item)
            await session.commit()

            try:
                mem0_id, recovered = await write_memory_item(
                    item
                )
            except Exception as exc:
                await repo.mark_item_failed(
                    item,
                    str(exc),
                )
                await session.commit()
                raise

            await repo.mark_item_completed(
                item,
                mem0_memory_id=mem0_id,
            )
            await session.commit()

            print(
                "MEMORY ITEM COMPLETED:",
                f"item_id={item.id}",
                f"recovered={recovered}",
            )

        # ----------------------------------------------------
        # 5. 所有 Item 均完成后，Task 才完成。
        #    零条候选也是成功处理。
        # ----------------------------------------------------
        task = await repo.get_by_id_for_update(task_id)

        if task is None:
            raise RuntimeError(
                f"MemoryWriteTask disappeared: {task_id}"
            )

        await repo.mark_completed(task)
        await session.commit()

        print(
            "MEMORY TASK COMPLETED:",
            f"task_id={task_id}",
            f"item_count={len(items)}",
        )

    except Exception as exc:
        await session.rollback()

        # 重新查询，避免使用 rollback 后失效的 ORM 状态。
        failed_task = await repo.get_by_id_for_update(task_id)

        if failed_task is not None and failed_task.status != "completed":
            await repo.mark_failed(
                failed_task,
                str(exc),
            )
            await session.commit()

        print(
            "MEMORY TASK FAILED:",
            f"task_id={task_id}",
            f"error={exc!r}",
        )
        raise
