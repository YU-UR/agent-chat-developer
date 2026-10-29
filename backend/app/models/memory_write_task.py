import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import (
    JSONB,
    UUID,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
)

from app.infrastructure.database.base import Base


class MemoryWriteTask(Base):
    __tablename__ = "memory_write_tasks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # ---------------------------------------------
    # 幂等性的核心字段
    #
    # 一个成功 Chat Run 最多创建一个 Memory Task。
    # ---------------------------------------------
    source_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        unique=True,
        index=True,
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )

    # ---------------------------------------------
    # Memory Worker 所需原始输入
    #
    # 这里保存一次成功聊天的 user/assistant pair，
    # 而不是直接永久写入 Mem0。
    # ---------------------------------------------
    user_message: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    assistant_message: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    # ---------------------------------------------
    # pending
    # processing
    # completed
    # failed
    # ---------------------------------------------
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        index=True,
    )

    # 后面的 Extraction 阶段写入。
    extracted_memories: Mapped[list | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    retry_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    last_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
