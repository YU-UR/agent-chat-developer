import time
import uuid
from typing import Any

from redis.asyncio import Redis

from app.infrastructure.redis.client import redis_client


class LeaseLostError(RuntimeError):
    """当前 Worker 已经失去任务执行权。"""


class IdempotencyService:
    """
    Kafka Consumer 的业务幂等服务。

    Redis 存储：
        chat:idempotency:v2:{run_id}

    状态：
        processing
        completed

    processing:
        使用 TTL 作为 lease，有效期间由持有者定期续租。

    completed:
        在保留期内，重复投递的 Kafka 消息可以跳过。
    """

    PREFIX = "chat:idempotency:v2"

    LEASE_SECONDS = 60

    COMPLETED_TTL_SECONDS = 86400

    def __init__(self, redis: Redis):
        self.redis = redis

        # 每个 run_id 在当前 Worker 进程中的执行租约。
        # value = (worker_id, owner_token)
        #
        # owner_token 每次成功获取执行权时重新生成，
        # 避免仅凭 worker_id 无法区分新旧执行尝试的问题。
        self._owner_tokens: dict[str, tuple[str, str]] = {}

    def _key(self, run_id: str) -> str:
        return f"{self.PREFIX}:{run_id}"

    # ==================================================
    # 1. acquire()：原子获取执行权
    # ==================================================

    _ACQUIRE_LUA = """
    local key = KEYS[1]

    local worker_id = ARGV[1]
    local owner_token = ARGV[2]
    local now_ms = tonumber(ARGV[3])
    local lease_until_ms = tonumber(ARGV[4])
    local lease_seconds = tonumber(ARGV[5])

    -- 情况 1：第一次处理，Redis 中没有记录。
    if redis.call('EXISTS', key) == 0 then

        redis.call(
            'HSET', key,
            'status', 'processing',
            'worker_id', worker_id,
            'owner_token', owner_token,
            'started_at_ms', now_ms,
            'lease_until_ms', lease_until_ms,
            'attempts', 1
        )

        redis.call('EXPIRE', key, lease_seconds)

        return 'acquired'
    end

    local status = redis.call('HGET', key, 'status')

    -- 存在记录但结构不符合预期时，不擅自覆盖。
    if not status then
        return 'invalid'
    end

    -- 情况 2：任务已经完成。
    if status == 'completed' then
        return 'completed'
    end

    if status ~= 'processing' then
        return 'invalid'
    end

    -- 情况 3：已有 Worker 持有 lease。
    local current_lease_until = tonumber(
        redis.call('HGET', key, 'lease_until_ms') or '0'
    )

    local ttl = redis.call('PTTL', key)

    if current_lease_until > now_ms and ttl > 0 then
        return 'processing'
    end

    -- 情况 4：lease 已过期。
    -- 整个 takeover 过程在一个 Lua 脚本中原子执行。
    -- 并发的其他 Worker 不会同时成功取得这次租约。

    local attempts = tonumber(
        redis.call('HGET', key, 'attempts') or '0'
    ) + 1

    redis.call(
        'HSET', key,
        'status', 'processing',
        'worker_id', worker_id,
        'owner_token', owner_token,
        'started_at_ms', now_ms,
        'lease_until_ms', lease_until_ms,
        'attempts', attempts
    )

    redis.call('EXPIRE', key, lease_seconds)

    return 'acquired'
    """

    async def acquire(
        self,
        run_id: str,
        worker_id: str,
    ) -> str:
        """
        返回值与现有 chat_worker.py 兼容：

            acquired
            processing
            completed

        acquired:
            当前 Worker 获得执行权。

        processing:
            另一个有效 lease 仍在执行。

        completed:
            业务已经完成，不需要再次执行。
        """

        now_ms = int(time.time() * 1000)

        owner_token = uuid.uuid4().hex

        lease_until_ms = (
            now_ms + self.LEASE_SECONDS * 1000
        )

        result = await self.redis.eval(
            self._ACQUIRE_LUA,
            1,
            self._key(run_id),
            worker_id,
            owner_token,
            now_ms,
            lease_until_ms,
            self.LEASE_SECONDS,
        )

        if result == "acquired":
            # 只有 Lua 确认成功后，才记录本次租约。
            self._owner_tokens[run_id] = (
                worker_id,
                owner_token,
            )

        elif result == "invalid":
            raise RuntimeError(
                f"Invalid idempotency record: run_id={run_id}"
            )

        return result

    # ==================================================
    # 2. renew()：原子续租
    # ==================================================

    _RENEW_LUA = """
    local key = KEYS[1]

    local worker_id = ARGV[1]
    local owner_token = ARGV[2]
    local now_ms = tonumber(ARGV[3])
    local lease_until_ms = tonumber(ARGV[4])
    local lease_seconds = tonumber(ARGV[5])

    if redis.call('HGET', key, 'status') ~= 'processing' then
        return 0
    end

    -- 必须同时匹配 Worker 和本次执行的唯一 token。
    if redis.call('HGET', key, 'worker_id') ~= worker_id then
        return 0
    end

    if redis.call('HGET', key, 'owner_token') ~= owner_token then
        return 0
    end

    -- 已过期的 lease 不允许由旧持有者自行恢复。
    local current_lease_until = tonumber(
        redis.call('HGET', key, 'lease_until_ms') or '0'
    )

    local ttl = redis.call('PTTL', key)

    if current_lease_until <= now_ms or ttl <= 0 then
        return 0
    end

    redis.call(
        'HSET', key,
        'lease_until_ms', lease_until_ms
    )

    redis.call('EXPIRE', key, lease_seconds)

    return 1
    """

    async def renew(
        self,
        run_id: str,
        worker_id: str,
    ) -> bool:
        """
        续租成功返回 True。

        如果记录不存在、lease 已过期，或者当前进程
        不再拥有执行权，则返回 False。
        """

        ownership = self._owner_tokens.get(run_id)

        if ownership is None:
            return False

        current_worker_id, owner_token = ownership

        if current_worker_id != worker_id:
            return False

        now_ms = int(time.time() * 1000)

        lease_until_ms = (
            now_ms + self.LEASE_SECONDS * 1000
        )

        result = await self.redis.eval(
            self._RENEW_LUA,
            1,
            self._key(run_id),
            worker_id,
            owner_token,
            now_ms,
            lease_until_ms,
            self.LEASE_SECONDS,
        )

        return bool(result)

    # ==================================================
    # 3. complete()：原子完成
    # ==================================================

    _COMPLETE_LUA = """
    local key = KEYS[1]

    local worker_id = ARGV[1]
    local owner_token = ARGV[2]
    local now_ms = tonumber(ARGV[3])
    local completed_ttl = tonumber(ARGV[4])

    local status = redis.call('HGET', key, 'status')

    -- 允许同一个持有者在结果响应丢失后重试 complete。
    if status == 'completed' then

        if redis.call('HGET', key, 'worker_id') == worker_id
           and redis.call('HGET', key, 'owner_token') == owner_token then
            return 1
        end

        return -1
    end

    if status ~= 'processing' then
        return -1
    end

    if redis.call('HGET', key, 'worker_id') ~= worker_id then
        return -1
    end

    if redis.call('HGET', key, 'owner_token') ~= owner_token then
        return -1
    end

    -- 已过期的旧持有者不能提交完成状态。
    local lease_until = tonumber(
        redis.call('HGET', key, 'lease_until_ms') or '0'
    )

    local ttl = redis.call('PTTL', key)

    if lease_until <= now_ms or ttl <= 0 then
        return -2
    end

    redis.call(
        'HSET', key,
        'status', 'completed',
        'completed_at_ms', now_ms
    )

    redis.call('HDEL', key, 'lease_until_ms')

    -- completed 记录保留一天，之后自动过期。
    redis.call('EXPIRE', key, completed_ttl)

    return 1
    """

    async def complete(
        self,
        run_id: str,
        worker_id: str,
    ) -> None:
        """
        只有当前 lease 持有者可以完成任务。

        如果执行权已丢失，抛出 LeaseLostError；
        调用方不应在这种情况下提交 Kafka offset。
        """

        ownership = self._owner_tokens.get(run_id)

        if ownership is None:
            raise LeaseLostError(
                f"No local lease token: run_id={run_id}"
            )

        current_worker_id, owner_token = ownership

        if current_worker_id != worker_id:
            raise LeaseLostError(
                f"Worker does not own lease: run_id={run_id}"
            )

        now_ms = int(time.time() * 1000)

        result = await self.redis.eval(
            self._COMPLETE_LUA,
            1,
            self._key(run_id),
            worker_id,
            owner_token,
            now_ms,
            self.COMPLETED_TTL_SECONDS,
        )

        if result == 1:
            self._owner_tokens.pop(run_id, None)
            return

        if result == -2:
            raise LeaseLostError(
                f"Lease expired before completion: run_id={run_id}"
            )

        raise LeaseLostError(
            f"Worker no longer owns lease: run_id={run_id}"
        )

    # ==================================================
    # 兼容现有 chat_worker.py 中的旧方法名
    # ==================================================

    async def mark_completed(
        self,
        run_id: str,
        worker_id: str,
    ) -> None:
        """
        兼容旧版 Worker。

        新代码建议直接使用 complete()。
        """
        await self.complete(
            run_id=run_id,
            worker_id=worker_id,
        )

    # ==================================================
    # 4. get_status()：查询状态
    # ==================================================

    async def get_status(
        self,
        run_id: str,
    ) -> dict[str, Any] | None:
        """
        返回任务状态，不存在则返回 None。

        不向调用方暴露 owner_token。
        """

        key = self._key(run_id)

        record = await self.redis.hgetall(key)

        if not record:
            return None

        numeric_fields = (
            "started_at_ms",
            "lease_until_ms",
            "completed_at_ms",
            "attempts",
        )

        result: dict[str, Any] = {
            "run_id": run_id,
            "status": record.get("status"),
            "worker_id": record.get("worker_id"),
        }

        for field in numeric_fields:
            value = record.get(field)

            if value is not None:
                result[field] = int(value)

        result["ttl_seconds"] = await self.redis.ttl(key)

        return result


idempotency_service = IdempotencyService(
    redis=redis_client,
)