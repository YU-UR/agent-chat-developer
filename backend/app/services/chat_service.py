import asyncio
import os
from uuid import uuid4
from app.infrastructure.redis.client import redis_client
from app.infrastructure.redis.run_event_bus import RunEventBus
# from app.agents.chat.graph import chat_graph
from app.agents.chat.context import (
    ChatGraphContext,
)

from app.infrastructure.langgraph.runtime import (
    get_chat_graph,
)
from langchain_core.messages import HumanMessage
from app.sandbox.client import (
    sandbox_client,
)

event_bus = RunEventBus(redis_client)


# CRASH_AFTER_THINKING = os.getenv(
#     "CRASH_AFTER_THINKING",
#     "false",
# ).lower() == "true"


class ChatBusinessError(Exception):
    """明确的、不可通过重试解决的业务异常。"""


class ChatService:

    async def process_run(
            self,
            run_id: str,
            user_id: str,
            conversation_id: str,
            message: str
    ) -> str:
        try:

            print(
                "RUN START:",
                run_id,
                "user_id=",
                user_id,
                "conversation_id=",
                conversation_id,
            )
            # 生命周期：一次 Worker 实际执行（如果 Worker crash，然后 Kafka retry）
            # run_id 不变， attempt_id 改变
            attempt_id = str(
                uuid4()
            )

            print(
                "RUN ATTEMPT:",
                attempt_id,
            )

            # -------------------------------------------------
            # 2. 正式执行 LangGraph
            # -------------------------------------------------
            progress_seq = 0

            async def emit_progress(
                    node_name: str,
                    progress_message: str,
            ) -> None:
                nonlocal progress_seq
                progress_seq += 1

                print(
                    "LANGGRAPH PROGRESS:",
                    node_name,
                    progress_message,
                )

                await event_bus.publish(
                    run_id,
                    {
                        "event_key": (
                            f"langgraph_"
                            f"{node_name}_"
                            f"{progress_seq}"
                        ),
                        "type": "thinking",
                        "data": {
                            "message": progress_message,
                            "stage": node_name,
                        },
                    },
                )
                # -------------------------------------------------
                # Stage 5.10.10
                # Worker crash / Kafka retry 测试开关
                #
                # 只在第一次 progress 事件发布完成后故意失败。
                # -------------------------------------------------
                # if (
                #         CRASH_AFTER_THINKING
                #         and progress_seq == 1
                # ):
                #     print(
                #         "INTENTIONAL CRASH:",
                #         f"run_id={run_id}",
                #         f"after_node={node_name}",
                #     )
                #
                #     raise RuntimeError(
                #         "Intentional crash for Stage 5.10.10 test"
                #     )

            async def emit_draft_start(
                    generation: int,
            ) -> None:

                print(
                    "DRAFT START:",
                    f"attempt={attempt_id}",
                    f"generation={generation}",
                )

                await event_bus.publish_stream(
                    run_id,
                    {
                        "event_key":
                            "draft_start",

                        "type":
                            "draft_start",

                        "data": {
                            "attempt_id":
                                attempt_id,

                            "generation":
                                generation,
                        },
                    },
                )

            async def emit_token(
                    generation: int,
                    chunk_index: int,
                    content: str,
            ) -> None:

                await event_bus.publish_stream(
                    run_id,
                    {
                        "event_key":
                            "draft_token",

                        "type":
                            "token",

                        "data": {
                            "attempt_id":
                                attempt_id,

                            "generation":
                                generation,

                            "chunk_index":
                                chunk_index,

                            "content":
                                content,
                        },
                    },
                )

            # LangGraph initial state
            initial_state = {
                "run_id": run_id,
                "user_id": str(user_id),
                "conversation_id": conversation_id,
                "user_message": message,
                # 每个 run 都必须重置的临时字段
                "route": "simple",
                "plan": "",
                "draft_answer": "",
                "critique": "",
                "final_answer": "",
                "revision_count": 0,
                "max_revisions": 1,
                # 每个run必须重置sandbox
                "sandbox_code": "",
                "sandbox_status": None,
                "sandbox_exit_code": None,
                "sandbox_stdout": "",
                "sandbox_stderr": "",
                # 本轮用户消息
                "messages": [
                    HumanMessage(content=message, id=f"{run_id}:user", )
                ],

            }
            chat_graph = get_chat_graph()

            # snapshot = chat_await graph.aget_state(
            #     {
            #         "configurable": {
            #             "thread_id": conversation_id,
            #         }
            #     }
            # )
            # print(snapshot.values.get("messages", []))

            result = await chat_graph.ainvoke(
                initial_state,
                config={
                    "configurable": {
                        # PostgreSQL Checkpoint 的会话标识
                        "thread_id": conversation_id,
                    }
                },
                # LangGraph 执行期间的进度回调
                context=ChatGraphContext(
                    emit_progress=emit_progress,
                    emit_draft_start=emit_draft_start,
                    emit_token=emit_token,
                    execute_python=sandbox_client.execute_python,
                ),
            )

            # -------------------------------------------------
            # 3. 从 LangGraph State 获取最终答案
            # -------------------------------------------------
            draft_answer = result.get(
                "draft_answer"
            )

            answer = result.get(
                "final_answer"
            )
            review_result = result.get(
                "review_result"
            )

            # -------------------------------------------------
            # 5.10.9 最终输出基本校验
            # -------------------------------------------------

            if not isinstance(
                    answer,
                    str,
            ):
                raise ChatBusinessError(
                    "LangGraph final_answer "
                    "is not a string"
                )

            answer = answer.strip()

            if not answer:
                raise ChatBusinessError(
                    "LangGraph final_answer "
                    "is empty"
                )

            # final_answer 必须来自最新 draft
            if not isinstance(
                    draft_answer,
                    str,
            ):
                raise ChatBusinessError(
                    "LangGraph draft_answer "
                    "is not a string"
                )

            if answer != draft_answer.strip():
                raise ChatBusinessError(
                    "LangGraph final_answer "
                    "does not match draft_answer"
                )
            route = result.get("route")
            if route == "sandbox":
                sandbox_status = result.get("sandbox_status")
                if sandbox_status not in {
                    "success",
                    "failed",
                    "timeout",
                }:
                    raise ChatBusinessError(
                        "Invalid sandbox final state: "
                        f"{sandbox_status!r}"
                    )
            else:
                # Graph 必须处于合法终态
                if review_result not in {
                    "pass",
                    "max_revisions",
                }:
                    raise ChatBusinessError(
                        "Invalid final review state: "
                        f"{review_result!r}"
                    )

            print(
                "LANGGRAPH FINAL ANSWER:",
                answer,
            )

            print(
                "LANGGRAPH FINAL STATE:",
                f"review_result={review_result}",
                f"chars={len(answer)}",
            )

            return answer

        except asyncio.CancelledError:
            # Worker 丢失 Redis Lease 时可能取消业务任务。
            # 必须让取消信号继续向上传播。
            raise

        except Exception as exc:  # 异常终止

            print(
                "RUN FAILED:",
                run_id,
                repr(exc),
            )
            # 不要吞掉异常，让 Worker 处理数据库状态。
            raise


chat_service = ChatService()
