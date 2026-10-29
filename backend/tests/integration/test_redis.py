import asyncio

from app.infrastructure.redis.client import redis_client


async def main():

    result = await redis_client.ping()

    print("Redis ping:", result)

    await redis_client.aclose()


if __name__ == "__main__":
    asyncio.run(main())