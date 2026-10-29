import asyncio
import json
import logging

from uuid import uuid4

from fastapi import APIRouter, Request, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.schemas.chat import (
    ChatRequest,
    ChatAcceptedResponse
)

from app.services.chat_service import chat_service
# from app.services.run_manager import run_manager
from collections.abc import AsyncIterable
from fastapi.sse import (
    EventSourceResponse,
    ServerSentEvent
)
from app.infrastructure.database.session import get_db_session
from app.infrastructure.redis.client import redis_client
from app.infrastructure.redis.run_event_bus import RunEventBus
from app.infrastructure.kafka.producer import kafka_producer
from app.infrastructure.kafka.topics import CHAT_RUN_REQUESTED
from app.repositories import (
    ConversationRepository,
    MessageRepository,
    ChatRunRepository,
    OutboxRepository,
)
# from app.repositories.outbox_repository import OutboxRepository

logger = logging.getLogger(__name__)

router = APIRouter()

event_bus = RunEventBus(redis_client)


@router.post(
    "/chat",
    response_model=ChatAcceptedResponse
)
async def create_chat(
        request: ChatRequest,
        session: AsyncSession = Depends(get_db_session),
):
    # ① 创建一个任务ID
    run_id = uuid4()

    # # ③ 启动后台任务
    # asyncio.create_task(
    #     chat_service.process_run(
    #         run_id=run_id,
    #         message=request.message
    #     )
    # )
    # Step 1: Generate run_id
    conversation_repository = ConversationRepository(session)
    message_repository = MessageRepository(session)
    chat_run_repository = ChatRunRepository(session)
    outbox_repository = OutboxRepository(session)
    # --------------------------------------------------
    # Step 2:
    # PostgreSQL transaction
    #
    # conversation
    # + chat_run
    # + user message
    # + outbox event
    #
    # must commit together
    # --------------------------------------------------

    #
    try:
        async with session.begin():

            await conversation_repository.create_if_not_exists(
                conversation_id=request.conversation_id,
                user_id=request.user_id,
            )

            await chat_run_repository.create(
                run_id=run_id,
                conversation_id=request.conversation_id,
            )

            await message_repository.create_user_message(
                conversation_id=request.conversation_id,
                run_id=run_id,
                content=request.message,
            )

            await outbox_repository.create_event(
                aggregate_type="chat_run",
                aggregate_id=run_id,
                event_type=CHAT_RUN_REQUESTED,
                payload={
                    "run_id": str(run_id),
                    "user_id": str(request.user_id),
                    "conversation_id": str(
                        request.conversation_id
                    ),
                    "message": request.message,
                },
            )

    except Exception:
        logger.exception(
            "Failed to persist chat request: run_id=%s",
            run_id,
        )

        raise HTTPException(
            status_code=500,
            detail="Failed to create chat run",
        )

        # --------------------------------------------------
        # Step 3:
        # Database transaction committed.
        #
        # Kafka is NOT called here anymore.
        # Outbox Publisher is responsible for Kafka delivery.
        # --------------------------------------------------

    return ChatAcceptedResponse(
        run_id=str(run_id),
        status="accepted",
    )


@router.get(
    "/chat/{run_id}/events",
    response_class=EventSourceResponse,
)
async def stream_events(
    run_id: str,
    request: Request,
) -> AsyncIterable[ServerSentEvent]:

    last_event_id = (
        request.headers.get("last-event-id")
        or "0-0"
    )

    while True:

        if await request.is_disconnected():
            break

        result = await event_bus.read(
            run_id=run_id,
            last_event_id=last_event_id,
            block_ms=15000,
        )

        if not result:
            continue

        for _, messages in result:

            for redis_stream_id, fields in messages:
                # -------------------------------------------------
                # Redis Stream 游标
                #
                # 注意：
                # 这里仍然使用 Redis Stream ID 作为读取游标
                # Redis Stream ID
                # 1750000000000-0
                #         ↓
                # 用于 XREAD cursor\ SSE ID\ Last-Event-ID
                #
                # business event_id
                # 93c...:thinking_start
                #         ↓
                # 用于 payload.event_id/zustand processedEventIds / 业务事件去重
                # -------------------------------------------------
                # 这里redis_stream_id如：1750000000000-0；是XADD自动生成的
                # Redis游标
                # XREAD从哪里继续读
                last_event_id = redis_stream_id

                event_type = fields["type"]
                # event_data = fields["data"]
                # '{"message":"正在分析问题"}'loads 加载str
                # 变回dict
                # {
                #     "message": "正在分析问题"
                # }
                event_data = json.loads(fields["data"])
                # print(type(event_data))  # <class 'str'>
                # print(event_data)
                business_event_id = fields["event_id"]

                event_key = fields["event_key"]

                seq = int(fields["seq"])
                payload = {
                    "event_id": business_event_id,
                    "event_key": event_key,
                    "seq": seq,
                    "data": event_data,  # dict
                }
                # print(type(payload))  # dict
                # print(payload)
                raw = json.dumps(payload, ensure_ascii=False)

                # print(type(raw))  # str
                # print(raw)

                print(
                    "SSE SEND:",
                    business_event_id,
                    "redis_id=",
                    redis_stream_id,
                    "seq=",
                    seq,
                    event_type,
                    event_data,
                )
                yield ServerSentEvent(
                    id=redis_stream_id,

                    event=event_type,
                    # data=payload
                    raw_data=raw,
                    # raw_data 接收str | None = None
                    # data 接收Any = None；python对象：Pydantic model
                    # dict
                    # list
                    # string
                    # number
                    # raw_data=json.dumps(
                    #     payload,  # 又序列化成 str
                    #     ensure_ascii=False,
                    # ),
                )

                if event_type in {
                    "completed",
                    "failed",
                }:
                    return

