import asyncio
import uuid
from typing import Any

from app.memory.config import call_memory
from app.models.memory_write_item import MemoryWriteItem
from app.memory.config import mem0_add, mem0_get_all


def _extract_records(result: Any) -> list[dict]:
    """统一处理 Mem0 常见的结果结构。"""
    if isinstance(result, dict):
        records = result.get("results", [])

        if isinstance(records, list):
            return [
                record
                for record in records
                if isinstance(record, dict)
            ]

        # 兼容直接返回单条记录的情况。
        if result.get("id") is not None:
            return [result]

    if isinstance(result, list):
        return [
            record
            for record in result
            if isinstance(record, dict)
        ]

    return []


def _get_memory_key(record: dict) -> str | None:
    metadata = record.get("metadata")

    if isinstance(metadata, dict):
        value = metadata.get("memory_key")
        if value is not None:
            return str(value)

    # 兼容某些版本直接展开 metadata 的返回结构。
    value = record.get("memory_key")
    return str(value) if value is not None else None


def _get_memory_id(record: dict) -> str | None:
    value = record.get("id") or record.get("memory_id")
    return str(value) if value is not None else None


async def find_existing_memory(
    *,
    user_id: uuid.UUID,
    memory_key: str,
) -> str | None:
    """
    检查本用户的 Mem0 记录中是否已有相同 memory_key。

    用于恢复“Mem0 已写成功，但 PostgreSQL 尚未更新”
    这种部分成功场景。
    """
    result = await asyncio.to_thread(
        mem0_get_all,
        filters={"user_id": str(user_id)},
        top_k=1000,
    )

    for record in _extract_records(result):
        if _get_memory_key(record) == memory_key:
            return _get_memory_id(record)

    return None


async def write_memory_item(
    item: MemoryWriteItem,
) -> tuple[str | None, bool]:
    """
    返回：
        mem0_memory_id
        recovered

    recovered=True 表示发现此前已经写入 Mem0，
    本次无需再次调用 memory.add()。
    """
    # 先复制数据库字段，之后执行外部操作。
    user_id = item.user_id
    content = item.content
    memory_key = item.memory_key
    source_run_id = item.source_run_id
    item_id = item.id

    existing_id = await find_existing_memory(
        user_id=user_id,
        memory_key=memory_key,
    )

    if existing_id is not None:
        print(
            "MEMORY WRITE RECOVERED:",
            f"item_id={item_id}",
            f"memory_key={memory_key}",
            f"mem0_id={existing_id}",
        )
        return existing_id, True

    metadata = {
        "memory_key": memory_key,
        "source_run_id": str(source_run_id),
        "memory_write_item_id": str(item_id),
    }

    result = await asyncio.to_thread(
        mem0_add,
        content,
        user_id=str(user_id),
        metadata=metadata,
        infer=False,
    )

    records = _extract_records(result)
    mem0_id = (
        _get_memory_id(records[0])
        if records
        else None
    )

    print(
        "MEMORY WRITE SUCCESS:",
        f"item_id={item_id}",
        f"memory_key={memory_key}",
        f"mem0_id={mem0_id}",
    )

    return mem0_id, False
