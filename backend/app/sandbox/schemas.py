from typing import Literal

from pydantic import BaseModel, Field


class SandboxExecuteRequest(BaseModel):
    code: str = Field(
        ...,
        min_length=1,
        max_length=20_000,
    )

    timeout_seconds: int = Field(
        default=5,
        ge=1,
        le=10,
    )


class SandboxExecuteResponse(BaseModel):
    status: Literal[
        "success",
        "failed",
        "timeout",
    ] | None

    exit_code: int | None

    stdout: str

    stderr: str

    timed_out: bool

    duration_ms: int
