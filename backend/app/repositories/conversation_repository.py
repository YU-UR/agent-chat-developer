from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation


class ConversationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_if_not_exists(
        self,
        conversation_id: UUID,
        user_id: UUID,
        title: str | None = None,
    ) -> Conversation:
        """
        创建会话；如果 ID 已存在，则返回现有会话。

        使用 PostgreSQL ON CONFLICT 避免并发请求
        同时创建相同 conversation_id 时发生主键冲突。
        """
        statement = (
            insert(Conversation)
            .values(
                id=conversation_id,
                user_id=user_id,
                title=title,
            )
            .on_conflict_do_nothing(
                index_elements=[Conversation.id]
            )
        )

        await self.session.execute(statement)

        result = await self.session.execute(
            select(Conversation).where(
                Conversation.id == conversation_id
            )
        )

        conversation = (
            result.scalar_one()
        )
        if conversation.user_id != user_id:
            raise ValueError(
                "Conversation does not belong to this user!"
            )
        return conversation

    async def get_by_id(
        self,
        conversation_id: UUID,
    ) -> Conversation | None:
        return await self.session.get(
            Conversation,
            conversation_id,
        )