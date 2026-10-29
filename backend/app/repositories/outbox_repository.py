from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.outbox_event import OutboxEvent


class OutboxRepository:

    def __init__(
        self,
        session: AsyncSession,
    ):
        self.session = session

    async def create_event(
        self,
        *,
        aggregate_type: str,
        aggregate_id: UUID,
        event_type: str,
        payload: dict,
    ) -> OutboxEvent:

        event = OutboxEvent(
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            event_type=event_type,
            payload=payload,
            status="pending",
        )

        self.session.add(event)

        await self.session.flush()

        return event

    async def get_pending_event_ids(
            self,
            limit: int = 100,
    ) -> list[UUID]:
        result = await self.session.execute(
            select(OutboxEvent.id)
            .where(
                OutboxEvent.status == "pending"
            )
            .order_by(
                OutboxEvent.created_at
            )
            .limit(limit)
        )

        return list(
            result.scalars().all()
        )

    async def get_by_id(
            self,
            event_id: UUID,
    ) -> OutboxEvent | None:
        return await self.session.get(
            OutboxEvent,
            event_id,
        )

    async def mark_published(
            self,
            event: OutboxEvent,
    ) -> None:
        event.status = "published"
        event.published_at = datetime.now(
            timezone.utc
        )
        event.last_error = None

    async def mark_failed_attempt(
            self,
            event: OutboxEvent,
            error: str,
    ) -> None:
        event.retry_count += 1
        event.last_error = error
