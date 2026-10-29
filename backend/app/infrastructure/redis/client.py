import os

from redis.asyncio import Redis


redis_client = Redis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", "6379")),
    decode_responses=True,

    # TCP connection timeout: 5 seconds
    socket_connect_timeout=5,

    # Must exceed the Redis Stream XREAD block timeout (15000 ms)
    socket_timeout=30,
)

# from redis.asyncio import Redis
#
# redis_client = Redis(
#     host="localhost",
#     port=6379,
#     decode_responses=True,
#     # TCP 建连最多允许 5 秒
#     socket_connect_timeout=5,
#
#     # 必须大于 XREAD 的 block=15000
#     socket_timeout=30,
# )
