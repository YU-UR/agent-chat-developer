import hashlib
import uuid


def normalize_memory_content(
    content: str,
) -> str:
    return " ".join(
        content.strip().split()
    ).casefold()


def build_memory_key(
    *,
    user_id: uuid.UUID | str,
    source_run_id: uuid.UUID | str,
    content: str,
) -> str:
    normalized = normalize_memory_content(
        content
    )

    raw = (
        f"{user_id}|"
        f"{source_run_id}|"
        f"{normalized}"
    )

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()
