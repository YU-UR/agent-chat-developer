import asyncio
import time

import docker
from docker.errors import (
    ContainerError,
    DockerException,
    ImageNotFound,
)

from app.sandbox.policies import (
    SANDBOX_IMAGE,
    SANDBOX_MEMORY_LIMIT,
    SANDBOX_NANO_CPUS,
    SANDBOX_PIDS_LIMIT,
    SANDBOX_MAX_STDOUT_BYTES,
    SANDBOX_MAX_STDERR_BYTES,
    SANDBOX_USER,
)


class SandboxExecutionError(Exception):
    pass


def _truncate_output(
    value: bytes | str | None,
    max_bytes: int,
) -> str:

    if value is None:
        return ""

    if isinstance(value, str):
        raw = value.encode(
            "utf-8",
            errors="replace",
        )
    else:
        raw = value

    if len(raw) <= max_bytes:
        return raw.decode(
            "utf-8",
            errors="replace",
        )

    truncated = raw[:max_bytes]

    return (
        truncated.decode(
            "utf-8",
            errors="replace",
        )
        + "\n...[output truncated]"
    )


class DockerSandboxRunner:

    def __init__(self) -> None:
        self.client = docker.from_env()

    def ping(self) -> None:
        self.client.ping()

    async def execute_python(
        self,
        code: str,
        timeout_seconds: int,
    ) -> dict:

        return await asyncio.to_thread(
            self._execute_python_sync,
            code,
            timeout_seconds,
        )

    def _execute_python_sync(
        self,
        code: str,
        timeout_seconds: int,
    ) -> dict:

        container = None

        started_at = time.perf_counter()

        try:
            container = self.client.containers.create(
                image=SANDBOX_IMAGE,

                command=[
                    "python",
                    "-I",
                    "-c",
                    code,
                ],

                network_disabled=True,

                read_only=True,

                user=SANDBOX_USER,

                mem_limit=SANDBOX_MEMORY_LIMIT,

                nano_cpus=SANDBOX_NANO_CPUS,

                pids_limit=SANDBOX_PIDS_LIMIT,

                cap_drop=[
                    "ALL",
                ],

                security_opt=[
                    "no-new-privileges:true",
                ],

                detach=True,

                stdin_open=False,

                tty=False,

                auto_remove=False,
            )

            container.start()

            try:
                wait_result = container.wait(
                    timeout=timeout_seconds,
                )

                exit_code = wait_result[
                    "StatusCode"
                ]

                timed_out = False

            except Exception as exc:

                # docker SDK 的 wait timeout
                # 在不同底层传输下异常类型可能不同；
                # 当前 Stage 6.1 统一视为超时，
                # 下一阶段会进一步细分异常类型。
                print(
                    "SANDBOX WAIT TIMEOUT:",
                    repr(exc),
                )

                timed_out = True

                try:
                    container.kill()
                except Exception:
                    pass

                exit_code = None

            stdout_bytes = container.logs(
                stdout=True,
                stderr=False,
            )

            stderr_bytes = container.logs(
                stdout=False,
                stderr=True,
            )

            duration_ms = int(
                (
                    time.perf_counter()
                    - started_at
                )
                * 1000
            )

            stdout = _truncate_output(
                stdout_bytes,
                SANDBOX_MAX_STDOUT_BYTES,
            )

            stderr = _truncate_output(
                stderr_bytes,
                SANDBOX_MAX_STDERR_BYTES,
            )

            if timed_out:
                status = "timeout"

            elif exit_code == 0:
                status = "success"

            else:
                status = "failed"

            return {
                "status": status,
                "exit_code": exit_code,
                "stdout": stdout,
                "stderr": stderr,
                "timed_out": timed_out,
                "duration_ms": duration_ms,
            }

        except ImageNotFound as exc:
            raise SandboxExecutionError(
                f"Sandbox image not found: "
                f"{SANDBOX_IMAGE}"
            ) from exc

        except DockerException as exc:
            raise SandboxExecutionError(
                f"Docker execution failed: "
                f"{exc}"
            ) from exc

        finally:
            if container is not None:
                try:
                    container.remove(
                        force=True,
                    )
                except Exception as exc:
                    print(
                        "SANDBOX CLEANUP WARNING:",
                        repr(exc),
                    )


sandbox_runner = DockerSandboxRunner()
