import asyncio
import json
from uuid import uuid4

from app.infrastructure.redis.client import redis_client
from app.infrastructure.redis.run_event_bus import RunEventBus


def to_text(value):
    """兼容 Redis 返回 str 或 bytes 的情况。"""
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return value


async def main() -> None:
    event_bus = RunEventBus(redis_client)

    # 使用独立 run_id，避免污染真实聊天请求。
    run_id = f"stage5101-test-{uuid4()}"

    stream_key = event_bus._stream_key(run_id)
    seq_key = event_bus._seq_key(run_id)

    try:
        # -------------------------------------------
        # 1. 连续发布第一条 Token
        # -------------------------------------------
        first = await event_bus.publish_stream(
            run_id=run_id,
            event={
                "type": "token",
                "event_key": "draft_token",
                "data": {
                    "attempt_id": "attempt-test-001",
                    "generation": 1,
                    "chunk_index": 1,
                    "content": "Kafka ",
                },
            },
        )

        # -------------------------------------------
        # 2. 连续发布第二条 Token
        #    event_key 故意保持相同
        # -------------------------------------------
        second = await event_bus.publish_stream(
            run_id=run_id,
            event={
                "type": "token",
                "event_key": "draft_token",
                "data": {
                    "attempt_id": "attempt-test-001",
                    "generation": 1,
                    "chunk_index": 2,
                    "content": "是分布式流平台。",
                },
            },
        )

        print("FIRST RESULT:", first)
        print("SECOND RESULT:", second)

        # -------------------------------------------
        # 3. 直接检查 Redis Stream
        # -------------------------------------------
        raw_entries = await redis_client.xrange(
            stream_key,
            min="-",
            max="+",
        )

        entries = []

        for redis_stream_id, fields in raw_entries:
            fields = {
                to_text(key): to_text(value)
                for key, value in fields.items()
            }

            entries.append(
                {
                    "redis_stream_id": to_text(redis_stream_id),
                    "event_id": fields["event_id"],
                    "event_key": fields["event_key"],
                    "seq": int(fields["seq"]),
                    "type": fields["type"],
                    "data": json.loads(fields["data"]),
                }
            )

        print("REDIS STREAM ENTRIES:")
        for entry in entries:
            print(entry)

        # -------------------------------------------
        # 4. 验收断言
        # -------------------------------------------
        assert first["published"] is True
        assert second["published"] is True

        assert first["event_key"] == second["event_key"]

        assert first["event_id"] != second["event_id"]
        assert first["seq"] == 1
        assert second["seq"] == 2

        assert len(entries) == 2

        assert [entry["seq"] for entry in entries] == [1, 2]

        assert [
            entry["event_key"] for entry in entries
        ] == ["draft_token", "draft_token"]

        assert [
            entry["data"]["chunk_index"] for entry in entries
        ] == [1, 2]

        assert [
            entry["data"]["content"] for entry in entries
        ] == ["Kafka ", "是分布式流平台。"]

        assert (
            entries[0]["event_id"]
            != entries[1]["event_id"]
        )

        print("\nPASS: 5.10.1 Redis Stream test passed.")
        print("TEST RUN ID:", run_id)
        print("STREAM KEY:", stream_key)

    finally:
        # 保留测试数据 5 分钟，方便手动检查。
        await event_bus.expire(
            run_id,
            seconds=300,
        )


if __name__ == "__main__":
    asyncio.run(main())