import asyncio
import sys
import json
import os
import socket
import time
from dotenv import load_dotenv

from aiokafka import AIOKafkaConsumer
from aiokafka.structs import TopicPartition

from app.repositories.outbox_repository import OutboxRepository
from app.infrastructure.kafka.topics import (
    CHAT_RUN_REQUESTED,
    MEMORY_EXTRACT_REQUESTED,
)
from app.services.chat_service import (
    chat_service,
    event_bus,
    ChatBusinessError,
)
from app.services.idempotency_service import (
    idempotency_service,
    LeaseLostError,
)
from uuid import UUID

from app.infrastructure.database.session import AsyncSessionLocal

from app.repositories import (
    MessageRepository,
    ChatRunRepository,
    MemoryWriteTaskRepository,
)
from app.infrastructure.langgraph.runtime import (
    start_langgraph_runtime,
    stop_langgraph_runtime,
)
from app.infrastructure.redis.client import redis_client

load_dotenv()
# ==================================================
# Configuration
# ==================================================

MAX_RUN_ATTEMPTS = 3
RUN_ATTEMPT_TTL_SECONDS = 86400

KAFKA_BOOTSTRAP_SERVERS = os.getenv(
    "KAFKA_BOOTSTRAP_SERVERS",
    "localhost:9092",
)

CONSUMER_GROUP = "chat-workers"

WORKER_ID = os.getenv(
    "WORKER_ID",
    socket.gethostname(),
)
# LANGGRAPH_CHECKPOINT_DATABASE_URL = os.getenv(
#     "LANGGRAPH_CHECKPOINT_DATABASE_URL",
#     (
#         "postgresql://"
#         "agent_chat:agent_chat123"
#         "@localhost:5432/"
#         "agent_chat"
#     ),
# )

# 必须小于 lease 时长。
# 例如 lease=60 秒，则每 20 秒续租一次。
HEARTBEAT_INTERVAL = max(
    1,
    idempotency_service.LEASE_SECONDS // 3,
)

# 发现其他 Worker 持有有效 lease 时，
# 重新检查执行权的最大等待间隔。
PROCESSING_RETRY_INTERVAL = 2.0


# ==================================================
# 1. Commit only the successfully processed message
# ==================================================

async def commit_message(
        consumer: AIOKafkaConsumer,
        message,
        *,
        reason: str,
) -> None:
    """
    只提交当前消息所在 partition 的 offset。

    Kafka 提交的是下一条需要消费的 offset，
    因此当前消息 offset=N，应提交 N+1。
    """

    topic_partition = TopicPartition(
        message.topic,
        message.partition,
    )

    next_offset = message.offset + 1

    await consumer.commit({
        topic_partition: next_offset,
    })

    print(
        f"[{WORKER_ID}] KAFKA COMMITTED:",
        f"topic={message.topic}",
        f"partition={message.partition}",
        f"message_offset={message.offset}",
        f"committed_offset={next_offset}",
        f"reason={reason}",
    )


# ==================================================
# 2. Acquire execution right, waiting when necessary
# ==================================================

async def acquire_or_wait(
        run_id: str,
) -> str:
    """
    返回：

        acquired
            当前 Worker 获得执行权。

        completed
            业务已经完成，无需重新执行。

    如果返回 processing：
        不 commit；
        不跳过消息；
        等待 lease 续租、完成或者过期；
        然后再次尝试 acquire。

    这一步在处理当前 Kafka message 的协程中等待，
    不会主动提交该消息的 offset。
    """

    last_log_time = 0.0

    while True:

        result = await idempotency_service.acquire(
            run_id=run_id,
            worker_id=WORKER_ID,
        )

        if result in {"acquired", "completed"}:
            return result

        if result != "processing":
            raise RuntimeError(
                f"Unexpected idempotency result: {result}"
            )

        # 有其他 Worker 持有有效 lease。
        # 不能 commit，也不能直接重新执行。
        status = await idempotency_service.get_status(
            run_id
        )

        now_ms = int(time.time() * 1000)

        lease_until_ms = (
            status.get("lease_until_ms", 0)
            if status is not None
            else 0
        )

        remaining_seconds = (
                                    lease_until_ms - now_ms
                            ) / 1000

        # lease 未到期时短暂等待。
        # lease 过期后，下一轮 acquire() 会尝试原子接管。
        if remaining_seconds > 0:
            sleep_seconds = min(
                PROCESSING_RETRY_INTERVAL,
                remaining_seconds,
            )
        else:
            sleep_seconds = 0.25

        # 控制日志频率，避免每两秒刷屏。
        current_time = time.monotonic()

        if current_time - last_log_time >= 5:
            owner = (
                status.get("worker_id")
                if status is not None
                else "unknown"
            )

            print(
                f"[{WORKER_ID}] IDEMPOTENCY PROCESSING:",
                f"run_id={run_id}",
                f"owner={owner}",
                f"lease_remaining={max(0, remaining_seconds):.1f}s",
                "waiting_without_commit",
            )

            last_log_time = current_time

        await asyncio.sleep(sleep_seconds)


# ==================================================
# 3. Lease heartbeat
# ==================================================

async def renew_lease_loop(
        run_id: str,
        stop_event: asyncio.Event,
        lease_lost_event: asyncio.Event,
) -> None:
    """
    在 ChatService 执行期间定期续租。

    如果续租失败或者无法确认续租结果，
    设置 lease_lost_event，让业务执行协程停止。

    续租失败时不允许继续把当前 Worker 当作 lease owner。
    """

    while not stop_event.is_set():

        try:
            await asyncio.wait_for(
                stop_event.wait(),
                timeout=HEARTBEAT_INTERVAL,
            )

            # stop_event 被设置，任务已经结束。
            return

        except asyncio.TimeoutError:
            pass

        try:
            renewed = await idempotency_service.renew(
                run_id=run_id,
                worker_id=WORKER_ID,
            )

        except asyncio.CancelledError:
            raise

        except Exception as exc:

            print(
                f"[{WORKER_ID}] LEASE RENEW ERROR:",
                f"run_id={run_id}",
                repr(exc),
            )

            lease_lost_event.set()
            return

        if not renewed:
            print(
                f"[{WORKER_ID}] LEASE LOST:",
                f"run_id={run_id}",
                "worker no longer owns the lease",
            )

            lease_lost_event.set()
            return

        print(
            f"[{WORKER_ID}] LEASE RENEWED:",
            f"run_id={run_id}",
        )


# ==================================================
# 4. Run ChatService while renewing the lease
# ==================================================

async def process_chat_with_heartbeat(
        run_id: str,
        user_id: str,
        conversation_id: str,
        user_message: str,
) -> str:
    """
    并行运行：

        Task A: ChatService
        Task B: Lease heartbeat

    如果 ChatService 结束：
        停止 heartbeat。

    如果 lease 丢失：
        取消 ChatService；
        抛出 LeaseLostError；
        不允许 complete 或 commit。
    """

    stop_event = asyncio.Event()
    lease_lost_event = asyncio.Event()

    heartbeat_task = asyncio.create_task(
        renew_lease_loop(
            run_id=run_id,
            stop_event=stop_event,
            lease_lost_event=lease_lost_event,
        )
    )

    business_task = asyncio.create_task(
        chat_service.process_run(
            run_id=run_id,
            user_id=user_id,
            conversation_id=conversation_id,
            message=user_message,
        )
    )

    lease_lost_task = asyncio.create_task(
        lease_lost_event.wait()
    )

    try:

        done, _ = await asyncio.wait(
            {
                business_task,
                lease_lost_task,
            },
            return_when=asyncio.FIRST_COMPLETED,
        )

        # 即使两个任务几乎同时结束，
        # 也先检查是否已经确认失去执行权。
        if lease_lost_event.is_set():

            if not business_task.done():
                business_task.cancel()

            await asyncio.gather(
                business_task,
                return_exceptions=True,
            )

            raise LeaseLostError(
                f"Lease lost during ChatService execution: {run_id}"
            )

        # 这里会重新抛出 ChatService 未处理的异常。
        final_answer = await business_task

        print(
            f"[{WORKER_ID}] CHAT SERVICE FINISHED:",
            f"run_id={run_id}",
        )

        # 业务结束后立即停止续租。
        stop_event.set()

        await heartbeat_task

        # 防止业务结束与最后一次续租失败发生竞争。
        if lease_lost_event.is_set():
            raise LeaseLostError(
                f"Lease lost before completion: {run_id}"
            )
        return final_answer

    finally:

        stop_event.set()

        # 清理尚未结束的协程。
        for task in (
                business_task,
                heartbeat_task,
                lease_lost_task,
        ):
            if not task.done():
                task.cancel()

        await asyncio.gather(
            business_task,
            heartbeat_task,
            lease_lost_task,
            return_exceptions=True,
        )


# ==================================================
# ADD. worker 持久化 到 postgreSQL
# ==================================================
async def mark_run_processing(
        run_id: UUID,
) -> str:
    async with AsyncSessionLocal() as session:
        repository = ChatRunRepository(session)

        async with session.begin():
            current_status = await repository.get_status(run_id)

            if current_status in {"completed", "failed"}:
                # PostgreSQL 已有终态，不再启动业务。
                status = current_status

            elif current_status in {"accepted", "processing"}:
                await repository.mark_processing(run_id)
                status = "processing"

            else:
                raise ValueError(
                    f"Unexpected chat run status: "
                    f"{current_status}, run_id={run_id}"
                )

    if status == "processing":
        print(
            f"[{WORKER_ID}] DB RUN PROCESSING:",
            f"run_id={run_id}",
        )

    return status


async def persist_run_completed(
        *,
        run_id: UUID,
        user_id: UUID,
        conversation_id: UUID,
        user_message: str,
        final_answer: str,
) -> None:
    async with AsyncSessionLocal() as session:
        message_repository = MessageRepository(
            session
        )

        run_repository = ChatRunRepository(
            session
        )

        memory_task_repository = (
            MemoryWriteTaskRepository(session)
        )
        outbox_repository = OutboxRepository(session)
        # 1. assistant message
        async with session.begin():
            await message_repository.create_assistant_message(
                conversation_id=conversation_id,
                run_id=run_id,
                content=final_answer,
            )
            # 2. chat run -> completed
            await run_repository.mark_completed(
                run_id
            )
            # --------------------------------------
            # 3. 创建 Memory Task
            #
            # source_run_id UNIQUE
            # 保证同一个聊天 Run 不会重复创建任务。
            # --------------------------------------

            memory_task_id = (
                await memory_task_repository.create_if_absent(
                    source_run_id=run_id,
                    user_id=user_id,
                    conversation_id=conversation_id,
                    user_message=user_message,
                    assistant_message=final_answer,
                )
            )

            # --------------------------------------
            # 4. 只有真正创建了 task，
            #    才创建 Outbox。
            #
            # 重复调用时：
            # create_if_absent -> None
            #
            # 因此也不会重复产生 Outbox。
            # --------------------------------------

            if memory_task_id is not None:
                await outbox_repository.create_event(
                    aggregate_type="memory_write_task",
                    aggregate_id=memory_task_id,
                    event_type=MEMORY_EXTRACT_REQUESTED,
                    # Kafka payload 不要再复制整个 user_message 和 assistant_message
                    # 已经持久化在memory_write_tasks
                    payload={
                        "task_id": str(memory_task_id),
                        "source_run_id": str(run_id),
                        "user_id": str(user_id),
                        "conversation_id": str(
                            conversation_id
                        ),
                    },
                )

    print(
        f"[{WORKER_ID}] DB RUN COMPLETED:",
        f"run_id={run_id}",
        f"memory_task_created="
        f"{memory_task_id is not None}",
    )


async def persist_run_failed(
        *,
        run_id: UUID,
        error_message: str,
) -> None:
    async with AsyncSessionLocal() as session:
        repository = ChatRunRepository(session)

        async with session.begin():
            await repository.mark_failed(
                run_id=run_id,
                error_message=error_message,
            )

    print(
        f"[{WORKER_ID}] DB RUN FAILED:",
        f"run_id={run_id}",
    )


async def increment_run_attempt(run_id: str) -> int:
    """原子递增持久化重试计数，允许 Worker 重启后继续计数。"""
    key = f"run:{run_id}:worker_attempts"

    pipe = redis_client.pipeline(transaction=True)
    pipe.incr(key)
    pipe.expire(key, RUN_ATTEMPT_TTL_SECONDS)

    result = await pipe.execute()
    return int(result[0])


async def finalize_run_failed(
        *,
        consumer,
        message,
        run_id: UUID,
        run_id_str: str,
        error_message: str,
        reason: str,
) -> None:
    """持久化失败终态，发布事件，最后提交 Kafka offset。"""

    await persist_run_failed(
        run_id=run_id,
        error_message=error_message,
    )

    await event_bus.publish(
        run_id_str,
        {
            "event_key": "failed",
            "type": "failed",
            "data": {
                "message": "本次请求处理失败，请稍后重试。",
            },
        },
    )

    await event_bus.expire(
        run_id_str,
        seconds=86400,
    )

    await idempotency_service.complete(
        run_id=run_id_str,
        worker_id=WORKER_ID,
    )

    await commit_message(
        consumer,
        message,
        reason=reason,
    )

    print(
        f"[{WORKER_ID}] RUN FAILURE FINALIZED:",
        f"run_id={run_id_str}",
        f"reason={reason}",
    )


# ==================================================
# 5. Process one Kafka message
# ==================================================

async def process_message(
        consumer: AIOKafkaConsumer,
        message,
) -> None:
    payload = message.value
    run_id_str = payload["run_id"]

    run_id = UUID(run_id_str)

    user_id = UUID(
        payload["user_id"]
    )

    conversation_id = UUID(
        payload["conversation_id"]
    )
    # run_id = payload["run_id"]
    user_message = payload["message"]

    print(
        f"[{WORKER_ID}] KAFKA RECEIVED:",
        f"partition={message.partition}",
        f"offset={message.offset}",
        f"key={message.key}",
        f"run_id={run_id}",
    )

    # --------------------------------------------------
    # Step 1: Obtain execution permission.
    # --------------------------------------------------

    result = await acquire_or_wait(run_id_str)

    print(
        f"[{WORKER_ID}] IDEMPOTENCY RESULT:",
        f"run_id={run_id}",
        f"result={result}",
    )

    # --------------------------------------------------
    # Step 2: Already completed.
    #
    # A previous attempt may have completed the business
    # operation but crashed before committing Kafka offset.
    # --------------------------------------------------

    if result == "completed":
        print(
            f"[{WORKER_ID}] IDEMPOTENCY SKIP COMPLETED:",
            f"run_id={run_id}",
        )

        await commit_message(
            consumer,
            message,
            reason="already_completed",
        )

        return

    # --------------------------------------------------
    # Step 3: Execute business with heartbeat.
    # --------------------------------------------------

    if result != "acquired":
        raise RuntimeError(
            f"Unexpected acquire result: {result}"
        )

    print(
        f"[{WORKER_ID}] IDEMPOTENCY ACQUIRED:",
        f"run_id={run_id_str}",
    )
    # --------------------------------------------------
    # Step : PostgreSQL -> processing
    # --------------------------------------------------

    # await mark_run_processing(
    #     run_id=run_id,
    # )
    db_status = await mark_run_processing(
        run_id=run_id,
    )

    if db_status in {"completed", "failed"}:
        print(
            f"[{WORKER_ID}] DB TERMINAL STATE:",
            f"run_id={run_id_str}",
            f"status={db_status}",
        )

        # 补发终态事件。EventBus 的 event_key 去重机制
        # 应防止同一个终态事件被重复写入。
        if db_status == "completed":
            await event_bus.publish(
                run_id_str,
                {
                    "event_key": "completed",
                    "type": "completed",
                    "data": {},
                },
            )
        else:
            await event_bus.publish(
                run_id_str,
                {
                    "event_key": "failed",
                    "type": "failed",
                    "data": {
                        "message": "本次请求处理失败，请稍后重试。",
                    },
                },
            )

        await event_bus.expire(
            run_id_str,
            seconds=86400,
        )

        await idempotency_service.complete(
            run_id=run_id_str,
            worker_id=WORKER_ID,
        )

        await commit_message(
            consumer,
            message,
            reason=f"database_already_{db_status}",
        )

        return
    # --------------------------------------------------
    # Step 4: Execute ChatService + heartbeat
    # --------------------------------------------------
    # --------------------------------------------------
    # Step 4: ChatService + bounded retry
    # --------------------------------------------------

    while True:
        attempt_number = await increment_run_attempt(
            run_id_str
        )

        # 如果 Worker 在此前的最后一次尝试中崩溃，
        # 重启后也不能突破重试上限。
        if attempt_number > MAX_RUN_ATTEMPTS:
            last_error = await redis_client.get(
                f"run:{run_id_str}:last_error"
            )

            if isinstance(last_error, bytes):
                last_error = last_error.decode(
                    "utf-8",
                    errors="replace",
                )

            await finalize_run_failed(
                consumer=consumer,
                message=message,
                run_id=run_id,
                run_id_str=run_id_str,
                error_message=(
                    str(last_error)
                    if last_error
                    else (
                        "Worker restarted after the "
                        "maximum attempt count was reached."
                    )
                ),
                reason="retry_exhausted_after_restart",
            )
            return

        print(
            f"[{WORKER_ID}] CHAT ATTEMPT:",
            f"run_id={run_id_str}",
            f"attempt={attempt_number}/{MAX_RUN_ATTEMPTS}",
        )

        try:
            final_answer = await process_chat_with_heartbeat(
                run_id=run_id_str,
                user_id=str(user_id),
                conversation_id=str(conversation_id),
                user_message=user_message,
            )
            break

        except asyncio.CancelledError:
            raise

        except LeaseLostError:
            # 已失去执行权，不能继续处理或提交 offset。
            raise

        except ChatBusinessError as exc:
            # 明确的业务异常，不重试。
            await finalize_run_failed(
                consumer=consumer,
                message=message,
                run_id=run_id,
                run_id_str=run_id_str,
                error_message=str(exc),
                reason="business_failed_terminal",
            )
            return

        except Exception as exc:
            # Sandbox API 连接失败、HTTP 超时等通用异常。
            await redis_client.set(
                f"run:{run_id_str}:last_error",
                str(exc)[:2000],
                ex=RUN_ATTEMPT_TTL_SECONDS,
            )

            print(
                f"[{WORKER_ID}] RETRYABLE FAILURE:",
                f"run_id={run_id_str}",
                f"attempt={attempt_number}/{MAX_RUN_ATTEMPTS}",
                f"error={exc!r}",
            )

            if attempt_number >= MAX_RUN_ATTEMPTS:
                await finalize_run_failed(
                    consumer=consumer,
                    message=message,
                    run_id=run_id,
                    run_id_str=run_id_str,
                    error_message=str(exc)[:2000],
                    reason="retry_exhausted",
                )
                return

            delay_seconds = min(
                2 ** (attempt_number - 1),
                4,
            )

            print(
                f"[{WORKER_ID}] RETRYING IN:",
                f"{delay_seconds}s",
            )

            await asyncio.sleep(delay_seconds)
    # --------------------------------------------------
    # Step 5: PostgreSQL durable completion
    # --------------------------------------------------

    if not isinstance(final_answer, str):
        raise TypeError(
            f"ChatService must return str, got "
            f"{type(final_answer).__name__}"
        )

    await persist_run_completed(
        run_id=run_id,
        user_id=user_id,
        conversation_id=conversation_id,
        user_message=user_message,
        final_answer=final_answer,
    )

    # 此处 transaction 已经提交：
    # 1. assistant message 已持久化
    # 2. chat_runs.status = completed

    # --------------------------------------------------
    # Step 6: Publish terminal SSE event
    # --------------------------------------------------

    await event_bus.publish(
        run_id_str,
        {
            "event_key": "completed",
            "type": "completed",
            "data": {},
        },
    )

    print(
        f"[{WORKER_ID}] SSE COMPLETED PUBLISHED:",
        f"run_id={run_id_str}",
    )

    # 终止事件发布后，设置 Redis Stream 的保留期限。
    await event_bus.expire(
        run_id_str,
        seconds=86400,
    )

    # --------------------------------------------------
    # Step 7: Mark Redis idempotency completed
    # --------------------------------------------------

    await idempotency_service.complete(
        run_id=run_id_str,
        worker_id=WORKER_ID,
    )

    print(
        f"[{WORKER_ID}] IDEMPOTENCY COMPLETED:",
        f"run_id={run_id_str}",
    )

    # --------------------------------------------------
    # Step 8: Commit Kafka offset
    # --------------------------------------------------

    await commit_message(
        consumer,
        message,
        reason="business_completed",
    )


# ==================================================
# 6. Consumer entry point
# ==================================================

async def main() -> None:
    consumer = AIOKafkaConsumer(
        CHAT_RUN_REQUESTED,

        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,

        group_id=CONSUMER_GROUP,

        enable_auto_commit=False,

        auto_offset_reset="earliest",

        key_deserializer=lambda key: (
            key.decode("utf-8")
            if key is not None
            else None
        ),

        value_deserializer=lambda value: json.loads(
            value.decode("utf-8")
        ),
    )
    langgraph_started = False
    consumer_started = False
    try:
        await start_langgraph_runtime()
        langgraph_started = True
        await consumer.start()
        consumer_started = True
        print(
            f"[{WORKER_ID}] CHAT WORKER STARTED",
            f"group={CONSUMER_GROUP}",
            f"bootstrap={KAFKA_BOOTSTRAP_SERVERS}",
            f"lease_seconds={idempotency_service.LEASE_SECONDS}",
            f"heartbeat_interval={HEARTBEAT_INTERVAL}",
        )
        async for message in consumer:

            try:

                await process_message(
                    consumer=consumer,
                    message=message,
                )

            except asyncio.CancelledError:
                raise

            except Exception as exc:

                print(
                    f"[{WORKER_ID}] MESSAGE PROCESSING FAILED:",
                    f"partition={message.partition}",
                    f"offset={message.offset}",
                    f"key={message.key}",
                    f"error={repr(exc)}",
                )

                # 不能提交当前失败消息的 offset。
                #
                # 退出 Consumer，让 Kafka group 完成 rebalance。
                # 新 Worker 从最后已提交的 offset 重新消费。
                #
                # 如果 Redis 中仍有 processing 记录，
                # 新 Worker 会等待 lease 过期，
                # 然后通过 acquire() 原子接管。

                raise

    finally:
        if consumer_started:
            await consumer.stop()
        if langgraph_started:
            await stop_langgraph_runtime()

        print(
            f"[{WORKER_ID}] CHAT WORKER STOPPED"
        )


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(
            asyncio.WindowsSelectorEventLoopPolicy()
        )
    asyncio.run(main())
