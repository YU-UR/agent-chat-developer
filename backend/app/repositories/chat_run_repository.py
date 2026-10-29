from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat_run import ChatRun
from datetime import datetime, timezone


def utc_now() -> datetime:
    return datetime.now(timezone.utc)




class ChatRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
            self,
            run_id: UUID,
            conversation_id: UUID,
    ) -> ChatRun:
        run = ChatRun(
            id=run_id,
            conversation_id=conversation_id,
            status="accepted",
        )

        self.session.add(run)
        await self.session.flush()

        return run

    async def get_by_id(
            self,
            run_id: UUID,
    ) -> ChatRun | None:
        return await self.session.get(
            ChatRun,
            run_id,
        )

    async def _get_required(
            self,
            run_id: UUID,
    ) -> ChatRun:
        run = await self.get_by_id(run_id)

        if run is None:
            raise LookupError(
                f"ChatRun not found: {run_id}"
            )

        return run

    async def get_status(self, run_id: UUID) -> str:
        run = await self._get_required(run_id)
        return run.status

    async def mark_processing(self, run_id: UUID) -> None:
        run = await self._get_required(run_id)

        # 重复调用：保持 processing，不重置 started_at。
        if run.status == "processing":
            return

        # 只有 accepted 可以进入 processing。
        if run.status != "accepted":
            raise ValueError(
                f"Invalid run state transition: "
                f"{run.status} -> processing, run_id={run_id}"
            )

        run.status = "processing"

        if run.started_at is None:
            run.started_at = datetime.now(timezone.utc)

    async def mark_completed(self, run_id: UUID) -> None:
        run = await self._get_required(run_id)

        # 重复完成：幂等返回。
        if run.status == "completed":
            return

        # 不允许把失败请求改成成功。
        if run.status == "failed":
            raise ValueError(
                f"Cannot complete a failed run: {run_id}"
            )

        # 正常成功路径必须先进入 processing。
        if run.status != "processing":
            raise ValueError(
                f"Invalid run state transition: "
                f"{run.status} -> completed, run_id={run_id}"
            )

        run.status = "completed"
        run.completed_at = datetime.now(timezone.utc)
        run.error_message = None

    async def mark_failed(
            self,
            run_id: UUID,
            error_message: str,
    ) -> None:
        run = await self._get_required(run_id)

        # 重复失败：保留第一次保存的失败信息。
        if run.status == "failed":
            return

        # 成功终态不可被失败状态覆盖。
        if run.status == "completed":
            raise ValueError(
                f"Cannot fail a completed run: {run_id}"
            )

        if run.status not in {"accepted", "processing"}:
            raise ValueError(
                f"Invalid run state transition: "
                f"{run.status} -> failed, run_id={run_id}"
            )

        run.status = "failed"
        run.error_message = error_message

    # async def mark_processing(
    #         self,
    #         run_id: UUID,
    # ) -> ChatRun:
    #     run = await self._get_required(run_id)
    #
    #     run.status = "processing"
    #
    #     if run.started_at is None:
    #         run.started_at = utc_now()
    #
    #     await self.session.flush()
    #
    #     return run

    # async def mark_completed(
    #         self,
    #         run_id: UUID,
    # ) -> ChatRun:
    #     run = await self._get_required(run_id)
    #
    #     run.status = "completed"
    #     run.completed_at = utc_now()
    #     run.error_message = None
    #
    #     await self.session.flush()
    #
    #     return run
    #
    # async def mark_failed(
    #         self,
    #         run_id: UUID,
    #         error_message: str,
    # ) -> ChatRun:
    #     run = await self._get_required(run_id)
    #
    #     run.status = "failed"
    #     run.error_message = error_message
    #     run.completed_at = utc_now()
    #
    #     await self.session.flush()
    #
    #     return run
