import asyncio
import uuid

from app.infrastructure.redis.client import redis_client
from app.infrastructure.redis.run_event_bus import RunEventBus


event_bus = RunEventBus(redis_client)


async def main():

    # 创建一个独立的测试 run_id
    run_id = str(uuid.uuid4())

    print("TEST RUN ID:", run_id)

    # 写入 6000 条事件
    for i in range(1):

        await event_bus.publish(
            run_id,
            {
                "type": "token",
                "data": {
                    "content": str(i)
                }
            }
        )

    print("PUBLISHED: 1")
    await event_bus.expire(
        run_id,
        seconds=60
    )

    # 查询 Stream 长度
    stream_key = (
        f"run:{run_id}:events"
    )

    length = await redis_client.xlen(
        stream_key
    )

    print(
        "STREAM LENGTH:",
        length
    )


if __name__ == "__main__":
    asyncio.run(main())