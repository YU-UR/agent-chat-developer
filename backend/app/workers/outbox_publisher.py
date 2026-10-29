import asyncio
from uuid import UUID

from app.infrastructure.database.session import AsyncSessionLocal
from app.infrastructure.kafka.producer import (
    kafka_producer,
)
from app.repositories.outbox_repository import (
    OutboxRepository,
)

POLL_INTERVAL_SECONDS = 1
BATCH_SIZE = 100
"""
双写一致性问题：Postgres有记录、Kafka挂了没消息
解决：不同时写数据库和kafka；
分开两个系统，事务里同时写两张表，一次提交
chat_runs
outbox_events
"""

# Step 1:
# Fetch pending event IDs only.


async def get_pending_event_ids() -> list:
    async with AsyncSessionLocal() as session:
        repository = OutboxRepository(
            session
        )

        return await repository.get_pending_event_ids(
            limit=BATCH_SIZE
        )


# Step 2:
# Publish one Outbox event.

async def publish_event(
        event_id: UUID,
) -> None:
    # ----------------------------------------
    # Step 1: Read event
    # ----------------------------------------

    async with AsyncSessionLocal() as session:

        repository = OutboxRepository(
            session
        )

        event = await repository.get_by_id(
            event_id
        )

        if event is None:
            return

        if event.status != "pending":
            return

        event_type = event.event_type
        aggregate_id = event.aggregate_id
        payload = event.payload

    # ----------------------------------------
    #  2.2 Publish to Kafka
    # ----------------------------------------

    try:

        await kafka_producer.send(
            event_type,
            key=str(aggregate_id),
            value=payload,
        )

    except Exception as exc:
        # Kafka publish failed.
        #
        # Keep status=pending so this event
        # can be retried later.
        async with AsyncSessionLocal() as session:

            repository = OutboxRepository(
                session
            )

            async with session.begin():
                event = await repository.get_by_id(
                    event_id
                )

                if ( # if pending then try send again
                        event is not None
                        and event.status == "pending"
                ):
                    await repository.mark_failed_attempt(
                        event,
                        str(exc),
                    )

        raise

    # ----------------------------------------
    #   # 2.3 Kafka succeeded -> mark published
    # ----------------------------------------

    async with AsyncSessionLocal() as session:

        repository = OutboxRepository(
            session
        )

        async with session.begin():
            event = await repository.get_by_id(
                event_id
            )

            if (
                    event is not None
                    and event.status == "pending"
            ):
                await repository.mark_published(
                    event
                )
    print(
        "OUTBOX PUBLISHED:",
        f"id={event_id}",
        f"type={event_type}",
        f"aggregate_id={aggregate_id}",
    )


# --------------------------------------------------
# Step 3:
# Publisher process
# --------------------------------------------------
async def main() -> None:
    await kafka_producer.start()

    print("OUTBOX PUBLISHER STARTED")

    try:
        while True:  # 死循环-一直轮询数据库
            try:
                event_ids = (
                    await get_pending_event_ids()
                )

                for event_id in event_ids:

                    try:
                        await publish_event(
                            event_id
                        )

                    except Exception as exc:
                        print(
                            "OUTBOX EVENT RETRY LATER:",
                            f"id={event_id}",
                            f"error={exc!r}",
                        )
            except Exception as exc:
                # PostgreSQL temporarily unavailable.
                #
                # Do not kill the publisher process.
                print(
                    "OUTBOX POLL FAILED:",
                    f"error={exc!r}",
                )

            await asyncio.sleep(
                POLL_INTERVAL_SECONDS
            )

    finally:

        await kafka_producer.stop()
        print(
            "OUTBOX PUBLISHER STOPPED"
        )


if __name__ == "__main__":
    asyncio.run(main())
