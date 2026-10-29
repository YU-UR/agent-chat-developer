import json

from redis.asyncio import Redis


class RunEventBus:

    def __init__(self, redis: Redis):
        self.redis = redis

    @staticmethod
    def _stream_key(run_id: str) -> str:
        return f"run:{run_id}:events"

    @staticmethod
    def _event_key_key(
            run_id: str,
            event_key: str,
    ) -> str:
        return f"run:{run_id}:event:{event_key}"

    @staticmethod
    def _seq_key(run_id: str) -> str:
        return f"run:{run_id}:seq"

    # =========================================================
    # 新增：
    # Redis Lua
    #
    # 保证：
    #
    # 1. event_key 已存在 → 不重复写 Stream
    # 2. event_key 不存在 → 分配 seq + XADD + 记录 event_key
    #
    # 三个操作在 Redis 内原子完成
    # =========================================================
    _PUBLISH_LUA = """
        local stream_key = KEYS[1]
        local seq_key = KEYS[2]
        local event_key_key = KEYS[3]

        local existing_event_id = redis.call(
            "GET",
            event_key_key
        )

        if existing_event_id then
            return {
                "duplicate",
                existing_event_id
            }
        end

        local seq = redis.call(
            "INCR",
            seq_key
        )

        local event_id = ARGV[1]
        local event_type = ARGV[2]
        local event_data = ARGV[3]

        redis.call(
            "XADD",
            stream_key,
            "MAXLEN",
            "~",
            "5000",
            "*",
            "event_id",
            event_id,
            "event_key",
            ARGV[4],
            "seq",
            tostring(seq),
            "type",
            event_type,
            "data",
            event_data
        )

        redis.call(
            "SET",
            event_key_key,
            event_id
        )

        return {
            "published",
            event_id,
            tostring(seq)
        }
        """

    # =========================================================
    # 高频流式事件
    #
    # 和 _PUBLISH_LUA 不同：
    #
    # 1. 不建立 event_key dedupe Redis key
    # 2. 每次调用都分配新的 seq
    # 3. 每次调用都 XADD
    #
    # 适用于：
    # - draft_start
    # - token
    # =========================================================

    _PUBLISH_STREAM_LUA = """
        local stream_key = KEYS[1]
        local seq_key = KEYS[2]

        local seq = redis.call(
            "INCR",
            seq_key
        )

        local run_id = ARGV[1]
        local event_type = ARGV[2]
        local event_key = ARGV[3]
        local event_data = ARGV[4]

        local event_id =
            run_id
            .. ":stream:"
            .. tostring(seq)

        local redis_stream_id = redis.call(
            "XADD",
            stream_key,
            "MAXLEN",
            "~",
            "5000",
            "*",
            "event_id",
            event_id,
            "event_key",
            event_key,
            "seq",
            tostring(seq),
            "type",
            event_type,
            "data",
            event_data
        )

        return {
            event_id,
            tostring(seq),
            redis_stream_id
        }
    """

    async def publish(
            self,
            run_id: str,
            event: dict,
    ) -> dict:
        # 如{
        #     "type": "thinking"
        # }；前端addEventListener("thinking")
        event_type = event["type"]
        # {
        #     "message": "正在分析问题"
        # }json.dumps(event_data)变成'{"message":"正在分析问题"}'
        # str 写进Redis; 读出的时候也是str,所以要json.loads(field["data"])
        event_data = event["data"]

        # -----------------------------------------------------
        # ① 逻辑事件 ID
        #
        # 例如：
        # thinking_start
        # thinking_detail
        # token
        # completed
        # failed
        # -----------------------------------------------------

        # 逻辑事件名称
        event_key = event["event_key"]
        # abc123:thinking_start
        # abc123:thinking_model
        # abc123:completed
        # 业务事件唯一ID-event_id;SSE前端去重，断线重连，幂等处理
        event_id = (
            f"{run_id}:{event_key}"
        )

        stream_key = self._stream_key(run_id)

        # 保持事务顺序，如start-model-token-completed
        seq_key = self._seq_key(run_id)

        event_key_key = self._event_key_key(
            run_id,
            event_key,
        )

        # -----------------------------------------------------
        # ② Redis Lua 原子执行
        # XADD自动生成1750000000000 - 0,也就是redis_stream_id（chat.py）
        # -----------------------------------------------------

        result = await self.redis.eval(
            self._PUBLISH_LUA,
            3,
            stream_key,
            seq_key,
            event_key_key,
            event_id,
            event_type,
            json.dumps(
                event_data,  # "data": '{"message":"正在分析问题"}'
                ensure_ascii=False,
            ),
            event_key,
        )

        result_type = result[0]

        # -----------------------------------------------------
        # ③ 已经发布过
        # -----------------------------------------------------

        if result_type == "duplicate":
            return {
                "published": False,
                "event_id": result[1],
                "event_key": event_key,
            }

        # -----------------------------------------------------
        # ④ 第一次发布
        # -----------------------------------------------------

        return {
            "published": True,
            "event_id": result[1],
            "seq": int(result[2]),
            "event_key": event_key,
        }

    async def publish_stream(
            self,
            run_id: str,
            event: dict,
    ) -> dict:
        """
        发布高频流式事件。

        与 publish() 的区别：

        publish()
            用于业务幂等事件。
            相同 event_key 只允许发布一次。

        publish_stream()
            用于实时流事件。
            每一次调用都会写入 Redis Stream。
            不创建 event_key dedupe Redis key。
        """

        event_type = event["type"]
        event_key = event["event_key"]
        event_data = event["data"]

        stream_key = self._stream_key(
            run_id
        )

        seq_key = self._seq_key(
            run_id
        )

        result = await self.redis.eval(
            self._PUBLISH_STREAM_LUA,
            2,
            stream_key,
            seq_key,

            run_id,
            event_type,
            event_key,

            json.dumps(
                event_data,
                ensure_ascii=False,
            ),
        )

        event_id = result[0]
        seq = int(result[1])
        redis_stream_id = result[2]

        return {
            "published": True,
            "event_id": event_id,
            "seq": seq,
            "redis_stream_id": (
                redis_stream_id
            ),
            "event_key": event_key,
        }

    async def read(
            self,
            run_id: str,
            last_event_id: str,  # 读redis stream的游标，从当前之后开始读
            block_ms: int = 15000,
    ):
        stream_key = self._stream_key(run_id)
        result = await self.redis.xread(
            streams={
                stream_key: last_event_id,
            },
            block=block_ms,
        )
        print("XREAD RESULT:", result)
        return result

    async def expire(
            self,
            run_id: str,
            seconds: int = 86400,  # 周期控制
    ) -> None:
        stream_key = (
            self._stream_key(run_id)
        )

        await self.redis.expire(
            stream_key,
            seconds,
        )

        # -----------------------------------------------------
        # seq 也设置 TTL
        # -----------------------------------------------------

        await self.redis.expire(
            self._seq_key(run_id),
            seconds,
        )
