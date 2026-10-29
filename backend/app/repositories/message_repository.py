from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.message import Message
from sqlalchemy import select


class MessageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_user_message(
        self,
        conversation_id: UUID,
        run_id: UUID,
        content: str,
    ) -> Message:
        return await self._create_message(
            conversation_id=conversation_id,
            run_id=run_id,
            role="user",
            content=content,
        )

    async def create_assistant_message(
        self,
        conversation_id: UUID,
        run_id: UUID,
        content: str,
    ) -> Message:
        existing_result = await self.session.execute(
            select(Message).where(
                Message.run_id == run_id,
                Message.role == "assistant",
            )
        )

        existing = existing_result.scalar_one_or_none()

        if existing is not None:
            if (
                    existing.conversation_id != conversation_id
                    or existing.content != content
            ):
                raise ValueError(
                    f"Conflicting assistant message for run_id={run_id}"
                )

            return existing

        return await self._create_message(
            conversation_id=conversation_id,
            run_id=run_id,
            role="assistant",
            content=content,
        )

    async def _create_message(
        self,
        conversation_id: UUID,
        run_id: UUID,
        role: str,
        content: str,
    ) -> Message:
        message = Message(
            conversation_id=conversation_id,
            run_id=run_id,
            role=role,
            content=content,
        )

        self.session.add(message)
        await self.session.flush()

        return message

    async def list_by_conversation(
        self,
        conversation_id: UUID,
        limit: int = 100,
    ) -> list[Message]:
        statement = (
            select(Message)
            .where(
                Message.conversation_id == conversation_id
            )
            .order_by(
                Message.created_at.asc(),
                Message.id.asc(),
            )
            .limit(limit)
        )

        result = await self.session.execute(statement)

        return list(result.scalars().all())