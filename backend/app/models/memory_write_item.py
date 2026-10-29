import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base


class MemoryWriteItem(Base):
    __tablename__ = "memory_write_items"

    # 同一个 Run 的同一条记忆,重发不创建第二条item
    # Kafka 重复投递
    # Worker crash
    # Worker restart
    # Outbox
    __table_args__ = (
        UniqueConstraint(
            "source_run_id",
            "memory_key",
            name="uq_memory_write_items_run_key",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "memory_write_tasks.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    source_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "chat_runs.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )

    # SHA256：
    # user_id + source_run_id + normalized content
    memory_key: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    # 最终真正准备进入长期记忆的用户原文
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        index=True,
    )

    retry_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    # Mem0 成功返回 ID 时保存。
    # 不强依赖 Mem0 一定返回 ID。
    mem0_memory_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
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

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
