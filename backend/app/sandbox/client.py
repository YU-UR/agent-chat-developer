import os

import httpx
# from dotenv import load_dotenv
from app.sandbox.schemas import (
    SandboxExecuteRequest,
    SandboxExecuteResponse,
)

# load_dotenv()


class SandboxClientError(Exception):
    pass


class SandboxClient:

    def __init__(self) -> None:
        self.base_url = os.getenv(
            "SANDBOX_API_URL",
            "http://127.0.0.1:8010",
        ).rstrip("/")

    async def execute_python(
        self,
        code: str,
        timeout_seconds: int = 5,
    ) -> SandboxExecuteResponse:

        request = SandboxExecuteRequest(
            code=code,
            timeout_seconds=timeout_seconds,
        )
        # print("SANDBOX REQUEST CODE:", repr(code))
        # print("SANDBOX REQUEST TIMEOUT:", timeout_seconds)
        try:
            http_timeout = float(
                os.getenv(
                    "SANDBOX_HTTP_TIMEOUT_SECONDS",
                    str(timeout_seconds + 8),
                )
            )

            async with httpx.AsyncClient(
                # timeout=timeout_seconds + 8,
                timeout=http_timeout,
                trust_env=False,
            ) as client:

                response = await client.post(
                    f"{self.base_url}/execute",
                    json=request.model_dump(),
                )

                response.raise_for_status()

        except httpx.HTTPError as exc:
            raise SandboxClientError(
                f"Sandbox API request failed: {exc}"
            ) from exc

        try:
            return SandboxExecuteResponse.model_validate(
                response.json()
            )

        except Exception as exc:
            raise SandboxClientError(
                "Sandbox API returned invalid response"
            ) from exc


sandbox_client = SandboxClient()
