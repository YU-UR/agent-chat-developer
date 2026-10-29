import json
import os

from aiokafka import AIOKafkaProducer
"""
Producer 和 Worker
都通过 KAFKA_BOOTSTRAP_SERVERS
连接到同一个 Kafka 集群

Producer 把消息发送到
CHAT_RUN_REQUESTED Topic

Worker 订阅
CHAT_RUN_REQUESTED Topic

Kafka 负责把 Producer 发出的
key/value 消息转发给 Worker
"""
# Kafka 地址
KAFKA_BOOTSTRAP_SERVERS = os.getenv(
    "KAFKA_BOOTSTRAP_SERVERS",
    "localhost:9092",
)


class KafkaProducer:

    def __init__(self):
        self._producer: AIOKafkaProducer | None = None

    async def start(self) -> None:

        if self._producer is not None:
            return

        self._producer = AIOKafkaProducer(
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,

            key_serializer=lambda key: (
                key.encode("utf-8")
                if key is not None
                else None
            ),

            value_serializer=lambda value: json.dumps(
                value,
                ensure_ascii=False,
            ).encode("utf-8"),

            enable_idempotence=True,
        )

        await self._producer.start()

        print(
            "KAFKA PRODUCER STARTED:",
            KAFKA_BOOTSTRAP_SERVERS,
        )

    async def stop(self) -> None:

        if self._producer is None:
            return

        await self._producer.stop()

        self._producer = None

        print("KAFKA PRODUCER STOPPED")

    async def send(
        self,
        topic: str,
        *,
        key: str,
        value: dict,
    ) -> None:

        if self._producer is None:
            raise RuntimeError(
                "Kafka producer has not been started"
            )

        # CHAT_RUN_REQUESTED      = Topic名称
        # key                     = 分区路由与顺序控制
        # value                   = 业务数据
        # chat_worker 通过Topic 与producer建立连接
        metadata = await self._producer.send_and_wait(
            topic,
            key=key,
            value=value,
        )

        print(
            "KAFKA PUBLISHED:",
            topic,
            "partition=",
            metadata.partition,
            "offset=",
            metadata.offset,
            "key=",
            key,
        )


kafka_producer = KafkaProducer()
