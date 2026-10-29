import uuid
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import (
    insert as pg_insert,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.memory.keys import build_memory_key
from app.models.memory_write_item import (
    MemoryWriteItem,
)
from app.models.memory_write_task import (
    MemoryWriteTask,
)


class MemoryWriteTaskRepository:

    def __init__(
        self,
        session: AsyncSession,
    ):
        self.session = session

    # ========================================================
    # MemoryWriteTask
    # ========================================================

    async def create_if_absent(
        self,
        *,
        source_run_id: UUID,
        user_id: UUID,
        conversation_id: UUID,
        user_message: str,
        assistant_message: str,
    ) -> UUID | None:
        """
        创建 Memory Task。

        返回 UUID:
            本次确实创建了新 task。

        返回 None:
            source_run_id 已存在，
            属于重复操作，不再次创建。
        """

        task_id = uuid.uuid4()

        stmt = (
            pg_insert(MemoryWriteTask)
            .values(
                id=task_id,
                source_run_id=source_run_id,
                user_id=user_id,
                conversation_id=conversation_id,
                user_message=user_message,
                assistant_message=assistant_message,
                status="pending",
                retry_count=0,
            )
            .on_conflict_do_nothing(
                index_elements=[
                    MemoryWriteTask.source_run_id,
                ]
            )
            .returning(
                MemoryWriteTask.id
            )
        )

        result = await self.session.execute(
            stmt
        )

        return result.scalar_one_or_none()

    async def get_by_source_run_id(
        self,
        source_run_id: UUID,
    ) -> MemoryWriteTask | None:

        result = await self.session.execute(
            select(MemoryWriteTask)
            .where(
                MemoryWriteTask.source_run_id
                == source_run_id
            )
        )

        return result.scalar_one_or_none()

    async def get_by_id(
        self,
        task_id: UUID,
    ) -> MemoryWriteTask | None:

        return await self.session.get(
            MemoryWriteTask,
            task_id,
        )

    async def get_by_id_for_update(
        self,
        task_id: UUID,
    ) -> MemoryWriteTask | None:
        """
        锁定 task。

        用于 Memory Worker 正式处理任务时，
        防止同一 task 被并发修改。
        """

        result = await self.session.execute(
            select(MemoryWriteTask)
            .where(
                MemoryWriteTask.id
                == task_id
            )
            .with_for_update()
        )

        return result.scalar_one_or_none()

    async def mark_processing(
        self,
        task: MemoryWriteTask,
    ) -> None:

        task.status = "processing"
        task.last_error = None

    async def mark_completed(
        self,
        task: MemoryWriteTask,
    ) -> None:

        task.status = "completed"
        task.last_error = None

        # 如果你的 MemoryWriteTask 模型已经存在
        # completed_at 字段，再打开：
        #
        # task.completed_at = datetime.now(timezone.utc)

    async def mark_failed(
        self,
        task: MemoryWriteTask,
        error: str,
    ) -> None:

        task.status = "failed"
        task.retry_count += 1
        task.last_error = error[:4000]

    # ========================================================
    # MemoryWriteItem
    # ========================================================

    async def get_items(
        self,
        task_id: UUID,
    ) -> list[MemoryWriteItem]:
        """
        获取一个 MemoryWriteTask 下的全部记忆候选。
        """

        result = await self.session.execute(
            select(MemoryWriteItem)
            .where(
                MemoryWriteItem.task_id
                == task_id
            )
            .order_by(
                MemoryWriteItem.created_at
            )
        )

        return list(
            result.scalars().all()
        )

    async def get_item_by_key(
        self,
        *,
        source_run_id: UUID,
        memory_key: str,
    ) -> MemoryWriteItem | None:
        """
        根据：

            source_run_id + memory_key

        查找已经存在的 MemoryWriteItem。
        """

        result = await self.session.execute(
            select(MemoryWriteItem)
            .where(
                MemoryWriteItem.source_run_id
                == source_run_id,
                MemoryWriteItem.memory_key
                == memory_key,
            )
        )

        return result.scalar_one_or_none()

    async def create_item_if_absent(
        self,
        *,
        task_id: UUID,
        source_run_id: UUID,
        user_id: UUID,
        content: str,
    ) -> UUID | None:
        """
        幂等创建 MemoryWriteItem。

        返回 UUID:
            本次真正创建了新 item。

        返回 None:
            source_run_id + memory_key 已存在。

        注意：
        这里直接使用 PostgreSQL
        ON CONFLICT DO NOTHING。

        不采用：
            SELECT -> INSERT

        避免两个 Memory Worker 并发时产生竞态。
        """

        item_id = uuid.uuid4()

        memory_key = build_memory_key(
            user_id=user_id,
            source_run_id=source_run_id,
            content=content,
        )

        stmt = (
            pg_insert(MemoryWriteItem)
            .values(
                id=item_id,
                task_id=task_id,
                source_run_id=source_run_id,
                user_id=user_id,
                memory_key=memory_key,
                content=content,
                status="pending",
                retry_count=0,
            )
            .on_conflict_do_nothing(
                constraint=(
                    "uq_memory_write_items_run_key"
                )
            )
            .returning(
                MemoryWriteItem.id
            )
        )

        result = await self.session.execute(
            stmt
        )

        return result.scalar_one_or_none()

    async def get_item_by_id(
        self,
        item_id: UUID,
    ) -> MemoryWriteItem | None:

        return await self.session.get(
            MemoryWriteItem,
            item_id,
        )

    async def mark_item_writing(
        self,
        item: MemoryWriteItem,
    ) -> None:
        """
        外部 Mem0 写入开始前调用。

        必须先 commit writing 状态，
        然后才能调用 Mem0。
        """

        item.status = "writing"
        item.last_error = None

    async def mark_item_completed(
        self,
        item: MemoryWriteItem,
        *,
        mem0_memory_id: str | None,
    ) -> None:

        item.status = "completed"

        item.mem0_memory_id = (
            mem0_memory_id
        )

        item.last_error = None

        item.completed_at = (
            datetime.now(timezone.utc)
        )

    async def mark_item_failed(
        self,
        item: MemoryWriteItem,
        error: str,
    ) -> None:

        item.status = "failed"
        item.retry_count += 1
        item.last_error = error[:4000]