from langgraph.graph import (
    END,
    START,
    StateGraph,
)

from app.agents.chat.state import (
    ChatGraphState,
)

from app.agents.chat.nodes import (
    router_node,
    planner_node,
    answer_node,
    review_node,
    finalize_node,
    sandbox_execute_node,
    sandbox_finalize_node,
)

from langgraph.runtime import Runtime

from app.agents.chat.context import (
    ChatGraphContext,
)
from app.memory.retriever import retrieve_memory


# ==================================================
# Conditional routes
# ==================================================

def route_after_router(
        state: ChatGraphState,
) -> str:
    return state["route"]


def route_after_review(
        state: ChatGraphState,
) -> str:
    return state["review_result"]


# ==================================================
# Build graph
# ==================================================
PROGRESS_MESSAGES = {
    "router": "正在分析问题",
    "planner": "正在制定回答计划",
    "answer": "正在生成回答",
    "review": "正在检查回答",
    "finalize": "正在整理最终答案",
    "sandbox_execute": "正在隔离环境中执行代码",
    "sandbox_finalize": "正在整理执行结果",
}


def with_progress(node_name, node_func):
    async def wrapped(
            state: ChatGraphState,
            runtime: Runtime[ChatGraphContext],
    ) -> dict:
        callback = runtime.context.emit_progress

        if callback is not None:
            await callback(
                node_name,
                PROGRESS_MESSAGES[node_name],
            )

        return await node_func(state, runtime, )

    return wrapped


builder = StateGraph(
    ChatGraphState,
    context_schema=ChatGraphContext,
)

builder.add_node("retrieve_memory", retrieve_memory)

builder.add_node(
    "router",
    with_progress("router", router_node),
)

builder.add_node(
    "planner",
    with_progress("planner", planner_node),
)

builder.add_node(
    "answer",
    with_progress("answer", answer_node),
)

builder.add_node(
    "review",
    with_progress("review", review_node),
)

builder.add_node(
    "finalize",
    with_progress("finalize", finalize_node),
)

builder.add_node(
    "sandbox_execute",
    with_progress(
        "sandbox_execute",
        sandbox_execute_node,
    ),
)

builder.add_node(
    "sandbox_finalize",
    with_progress(
        "sandbox_finalize",
        sandbox_finalize_node,
    ),
)


# START
builder.add_edge(START, "retrieve_memory")
builder.add_edge("retrieve_memory", "router")

# Router conditional
builder.add_conditional_edges(
    "router",
    route_after_router,
    {
        "simple": "answer",
        "complex": "planner",
        "sandbox": "sandbox_execute",
    },
)

builder.add_edge(
    "sandbox_execute",
    "sandbox_finalize",
)

builder.add_edge(
    "sandbox_finalize",
    END,
)

# Planner
builder.add_edge(
    "planner",
    "answer",
)

# Answer
builder.add_edge(
    "answer",
    "review",
)

# Review conditional
builder.add_conditional_edges(
    "review",
    route_after_review,
    {  # 目标node
        "revise": "answer",
        "pass": "finalize",
        "max_revisions": "finalize",
    },
)

# End
builder.add_edge(
    "finalize",
    END,
)


def build_chat_graph(
        checkpointer=None,
):
    return builder.compile(
        checkpointer=checkpointer,
    )


# 保留：
# python test_langgraph.py
# 仍然可以单独运行。
chat_graph = build_chat_graph()
# chat_graph = builder.compile()
