from collections.abc import (
    Awaitable,
    Callable,
)
from dataclasses import dataclass
from app.sandbox.schemas import (
    SandboxExecuteResponse,
)

# ==================================================
# Progress
# ==================================================

ProgressCallback = Callable[
    [str, str],
    Awaitable[None],
]

SandboxExecuteCallback = Callable[
    [str, int],
    Awaitable[SandboxExecuteResponse],
]


# ==================================================
# Draft streaming
# ==================================================

# generation
#
# 1 = 第一次 answer
# 2 = Review revise 后第二次 answer
DraftStartCallback = Callable[
    [int],
    Awaitable[None],
]


# generation
# chunk_index
# content
TokenCallback = Callable[
    [int, int, str],
    Awaitable[None],
]


# ==================================================
# Runtime context
# ==================================================

@dataclass
class ChatGraphContext:

    emit_progress: (
        ProgressCallback | None
    ) = None

    emit_draft_start: (
        DraftStartCallback | None
    ) = None

    emit_token: (
        TokenCallback | None
    ) = None

    execute_python: (
            SandboxExecuteCallback | None
    ) = None
