import os

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    create_async_engine,
)


DATABASE_URL = os.getenv(
    "DATABASE_URL",
    (
        "postgresql+asyncpg://"
        "agent_chat:agent_chat123"
        "@localhost:5432/"
        "agent_chat"
    ),
)


engine: AsyncEngine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)