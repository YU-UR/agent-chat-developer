from contextlib import asynccontextmanager

from fastapi import (
    FastAPI,
    HTTPException,
)

from app.sandbox.docker_runner import (
    SandboxExecutionError,
    sandbox_runner,
)

from app.sandbox.schemas import (
    SandboxExecuteRequest,
    SandboxExecuteResponse,
)


@asynccontextmanager
async def lifespan(
    app: FastAPI,
):

    try:
        sandbox_runner.ping()

        print(
            "SANDBOX DOCKER READY"
        )

    except Exception as exc:
        print(
            "SANDBOX DOCKER ERROR:",
            repr(exc),
        )

        raise

    yield


app = FastAPI(
    title="Agent Chat Sandbox",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health():
    return {
        "status": "ok",
    }


@app.post(
    "/execute",
    response_model=SandboxExecuteResponse,
)
async def execute(
    request: SandboxExecuteRequest,
):
    print(
        "SANDBOX API RECEIVED:",
        repr(request.code),
        request.timeout_seconds,
    )

    try:
        result = (
            await sandbox_runner.execute_python(
                code=request.code,
                timeout_seconds=(
                    request.timeout_seconds
                ),
            )
        )

        print(
            "SANDBOX API RESULT:",
            result,
        )

        return SandboxExecuteResponse(
            **result
        )

    except SandboxExecutionError as exc:

        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc
