from typing_extensions import TypedDict
from typing import Annotated, Literal
from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class ChatGraphState(
    TypedDict,
    total=False,
):
    # 会话消息历史
    messages: Annotated[list[AnyMessage], add_messages, ]
    # ----------------------------------------
    # Request identity
    # ----------------------------------------
    user_id: str
    run_id: str
    conversation_id: str
    user_message: str
    memory_context: str

    # ----------------------------------------
    # Router
    # ----------------------------------------

    route: Literal[
        "simple",
        "complex",
        "sandbox",
    ]

    # ----------------------------------------
    # Planner
    # ----------------------------------------

    plan: str

    # ----------------------------------------
    # Generation
    # ----------------------------------------

    draft_answer: str

    # ----------------------------------------
    # Review
    # ----------------------------------------

    review_result: Literal[
        "pass",
        "revise",
        "max_revisions",  # 最大修订次数
    ]

    critique: str

    # ----------------------------------------
    # Loop control
    # ----------------------------------------

    revision_count: int
    max_revisions: int

    # ----------------------------------------
    # Final result
    # ----------------------------------------

    final_answer: str

    # ----------------------------------------
    # sandbox
    # ----------------------------------------
    sandbox_code: str

    sandbox_status: Literal[
        "success",
        "failed",
        "timeout",
    ]

    sandbox_exit_code: int | None

    sandbox_stdout: str

    sandbox_stderr: str
