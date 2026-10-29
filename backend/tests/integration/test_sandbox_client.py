import asyncio
import os
from dotenv import load_dotenv
from app.sandbox.client import SandboxClient
load_dotenv()


async def main():
    client = SandboxClient()

    print("SANDBOX_API_URL env =", os.getenv("SANDBOX_API_URL"))
    print("Effective URL =", client.base_url)

    result = await client.execute_python(
        code="print(6 * 7)",
        timeout_seconds=5,
    )

    print("Result type =", type(result).__name__)
    print("Result =", result.model_dump())

    assert result.status == "success", result
    assert result.stdout.strip() == "42", result

    print("SANDBOX CLIENT TEST: PASS")


if __name__ == "__main__":
    asyncio.run(main())
