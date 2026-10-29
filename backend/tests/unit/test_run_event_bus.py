import asyncio
import uuid

from backend.app.infrastructure.redis.client import redis_client
from backend.app.infrastructure.redis.run_event_bus import RunEventBus

event_bus = RunEventBus(redis_client)


async def main():
    # 创建一个独立的测试 run_id
    run_id = str(uuid.uuid4())

    print("TEST RUN ID:", run_id)
    result1 = await event_bus.publish_stream(
        "test-stream-run",
        {
            "event_key": "draft_token",
            "type": "token",
            "data": {
                "content": "A"
            },
        },
    )

    result2 = await event_bus.publish_stream(
        "test-stream-run",
        {
            "event_key": "draft_token",
            "type": "token",
            "data": {
                "content": "B"
            },
        },
    )

    print(result1)
    print(result2)

if __name__ == "__main__":
    asyncio.run(main())