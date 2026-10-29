import asyncio
import json
import logging
import os
import sys
from uuid import UUID
from dotenv import load_dotenv
from aiokafka import AIOKafkaConsumer
from aiokafka.structs import OffsetAndMetadata, TopicPartition

from app.infrastructure.database.session import AsyncSessionLocal
from app.memory.task_processor import process_memory_task
from app.models.memory_write_task import MemoryWriteTask


load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

KAFKA_BOOTSTRAP_SERVERS = os.getenv(
    "KAFKA_BOOTSTRAP_SERVERS",
    "localhost:9092",
)
MEMORY_TOPIC = "memory.extract.requested"
MEMORY_GROUP_ID = "memory-workers"


def extract_task_id(message) -> UUID:
    """
    优先从 Kafka key 获取 task_id。

    当前 OutboxPublisher 的日志已验证：
    memory.extract.requested 的 Kafka key
    是 MemoryWriteTask 的 UUID。

    同时兼容 payload 中包含 task_id 的情况。
    """
    candidates: list[str] = []

    if message.key:
        candidates.append(
            message.key.decode("utf-8")
        )

    if message.value:
        try:
            payload = json.loads(
                message.value.decode("utf-8")
            )

            if isinstance(payload, dict):
                for field in (
                    "task_id",
                    "memory_write_task_id",
                    "aggregate_id",
                ):
                    value = payload.get(field)

                    if value is not None:
                        candidates.append(str(value))

        except (UnicodeDecodeError, json.JSONDecodeError):
            logger.warning(
                "MEMORY EVENT PAYLOAD IS NOT VALID JSON"
            )

    for candidate in candidates:
        try:
            return UUID(candidate)
        except (ValueError, TypeError):
            continue

    raise ValueError(
        f"Cannot extract MemoryWriteTask ID: "
        f"key={message.key!r}"
    )


async def get_durable_task_status(
    task_id: UUID,
) -> str | None:
    """
    查询数据库，确认失败是否已经持久化。

    只有确认 Task 已经处于 failed 或 completed，
    才能在处理异常后提交 Kafka offset。
    """
    async with AsyncSessionLocal() as session:
        task = await session.get(
            MemoryWriteTask,
            task_id,
        )

        if task is None:
            return None

        return task.status


async def commit_message(
    consumer: AIOKafkaConsumer,
    message,
) -> None:
    """
    只提交当前消息的 offset + 1。
    """
    topic_partition = TopicPartition(
        message.topic,
        message.partition,
    )

    await consumer.commit({
        topic_partition: OffsetAndMetadata(
            message.offset + 1,
            "",
        )
    })


async def main() -> None:
    consumer = AIOKafkaConsumer(
        MEMORY_TOPIC,
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        group_id=MEMORY_GROUP_ID,
        enable_auto_commit=False,
        auto_offset_reset="earliest",
    )

    await consumer.start()

    logger.info(
        "MEMORY WORKER STARTED: "
        "topic=%s group=%s",
        MEMORY_TOPIC,
        MEMORY_GROUP_ID,
    )

    try:
        while True:
            message = await consumer.getone()

            # 无法解析 task_id 时，不提交 offset。
            # 让错误事件保持可调查状态，避免静默丢弃。
            task_id = extract_task_id(message)

            logger.info(
                "MEMORY EVENT RECEIVED: "
                "task_id=%s partition=%s offset=%s",
                task_id,
                message.partition,
                message.offset,
            )

            try:
                async with AsyncSessionLocal() as session:
                    await process_memory_task(
                        session,
                        task_id=task_id,
                    )

            except Exception:
                logger.exception(
                    "MEMORY TASK PROCESSING ERROR: "
                    "task_id=%s",
                    task_id,
                )

                # process_memory_task 会在可处理的业务异常下
                # 尝试将 Task 持久化为 failed。
                #
                # 必须确认状态已落库，才能提交 offset。
                status = await get_durable_task_status(
                    task_id
                )

                if status in {"failed", "completed"}:
                    await commit_message(
                        consumer,
                        message,
                    )

                    logger.warning(
                        "MEMORY EVENT COMMITTED AFTER "
                        "DURABLE RESULT: task_id=%s status=%s "
                        "offset=%s",
                        task_id,
                        status,
                        message.offset,
                    )

                    # 继续处理后续任务。
                    # 失败任务由独立重试流程重新投递。
                    continue

                # 如果数据库状态无法确认，不提交 offset。
                # 退出 Worker，让 Kafka 在重启后重新投递。
                raise RuntimeError(
                    "Memory task result is not durable; "
                    f"refusing to commit offset: {task_id}"
                )

            # 只有 process_memory_task 已成功返回，
            # 才正常提交 offset。
            await commit_message(
                consumer,
                message,
            )

            logger.info(
                "MEMORY KAFKA COMMITTED: "
                "task_id=%s partition=%s offset=%s",
                task_id,
                message.partition,
                message.offset,
            )

    finally:
        await consumer.stop()

        logger.info(
            "MEMORY WORKER STOPPED"
        )


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(
            asyncio.WindowsSelectorEventLoopPolicy()
        )

    asyncio.run(main())
