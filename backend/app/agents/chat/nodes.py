import re
import os
from app.agents.chat.state import (
    ChatGraphState,
)
from app.llm.local_llm import local_llm
from langchain_core.messages import AIMessage
from langgraph.runtime import Runtime

from app.agents.chat.context import (
    ChatGraphContext,
)


# ==================================================
# Router
# ==================================================

async def router_node(
        state: ChatGraphState,
        runtime: Runtime[ChatGraphContext],
) -> dict:
    message = str(
        state.get("user_message") or ""
    ).strip()

    memory_context = str(
        state.get("memory_context") or ""
    ).strip()

    # ==================================================
    # 1. Sandbox
    # ==================================================
    # Sandbox 必须优先判断。
    # 不能让 /python 被 simple / complex 抢走。
    # ==================================================

    if message.lstrip().startswith("/python"):
        route = "sandbox"

        print(
            "LANGGRAPH ROUTER:",
            route,
            "| reason=explicit /python",
        )

        return {
            "route": route,
        }

    # ==================================================
    # 2. 没有问题
    # ==================================================

    if not message:
        route = "simple"

        print(
            "LANGGRAPH ROUTER:",
            route,
            "| reason=empty message",
        )

        return {
            "route": route,
        }

    # ==================================================
    # 3. 当前用户已有相关长期记忆
    # ==================================================

    has_memory = bool(memory_context)

    # ==================================================
    # 4. 简单问题判断
    #
    # 注意：
    # 不再单纯使用 len(message) 判断。
    #
    # 因为：
    #
    # "Which database should I use for my backend project?"
    #
    # 虽然长度 > 20，
    # 但它本质上仍然可以是一个简单的推荐问题。
    # ==================================================

    simple_patterns = (
        "which ",
        "what ",
        "should i use",
        "should i choose",
        "do i need",
        "can i use",
        "is it better",
        "which one",
        "what should i",
        "哪个",
        "什么",
        "应该用",
        "应该选择",
        "推荐",
        "建议",
        "哪个好",
        "哪一个",
        "是否需要",
        "能不能用",
        "可以用",
    )

    lower_message = message.casefold()

    looks_simple = any(
        pattern in lower_message
        for pattern in simple_patterns
    )

    # ==================================================
    # 5. 如果有相关长期记忆，
    #    并且当前问题属于简单推荐/偏好问题，
    #    优先 simple。
    # ==================================================

    if has_memory and looks_simple:
        route = "simple"

        print(
            "LANGGRAPH ROUTER:",
            route,
            "| reason=relevant memory + simple question",
        )

        return {
            "route": route,
        }

    # ==================================================
    # 6. 没有复杂分析要求的短问题
    #
    # 这里保留原来的长度规则作为兜底。
    # ==================================================

    simple_threshold = 20

    if len(message) <= simple_threshold:
        route = "simple"

        print(
            "LANGGRAPH ROUTER:",
            route,
            "| reason=short question",
        )

        return {
            "route": route,
        }

    # ==================================================
    # 7. 其他情况才进入 complex
    # ==================================================

    route = "complex"

    print(
        "LANGGRAPH ROUTER:",
        route,
        "| reason=complex fallback",
    )

    return {
        "route": route,
    }


# ==================================================
# Planner
# ==================================================

async def planner_node(
        state: ChatGraphState,
        runtime: Runtime[ChatGraphContext],
) -> dict:
    message = state["user_message"]
    history_text = format_prior_conversation(state)
    prompt = f"""
Consider the prior conversation and current user question:
Conversation history:
{history_text}

User question:
{message}
"""

    plan = await local_llm.generate(
        system_prompt=(
            "You are a planning assistant. "
            "Create a short structured plan "
            "before answering the user's question. "
            "Do not answer the question yet."
        ),
        user_prompt=prompt,
        max_new_tokens=128,
    )

    print(
        "LANGGRAPH PLAN:",
        plan,
    )

    return {
        "plan": plan,
    }


# ==================================================
# Answer
# ==================================================

async def answer_node(
        state: ChatGraphState,
        runtime: Runtime[
            ChatGraphContext
        ],
) -> dict:
    message = state[
        "user_message"
    ]

    history_text = (
        format_prior_conversation(
            state
        )
    )

    plan = state.get(
        "plan",
        "",
    )

    critique = state.get(
        "critique",
        "",
    )
    previous_draft = state.get(
        "draft_answer",
        "",
    )

    # ==================================================
    # Prompt
    # ==================================================
    # add memory
    memory_context = str(
        state.get("memory_context") or ""
    ).strip()
    print(f"[MEMORY] ANSWER RECEIVED: {memory_context!r}")
    if memory_context:
        revision_note = ""

        if critique:
            revision_note = f"""
    Previous draft:
    {previous_draft}

    Reviewer feedback:
    {critique}

    Only apply feedback that identifies a concrete error.
    If the feedback is only a word or topic, do not treat it
    as a complete replacement answer.
    """

        prompt = f"""
    You are a concise technical assistant.

    Current user question:
    {message}

    Relevant long-term memory belonging to this user:
    {memory_context}

    Conversation history:
    {history_text or "No relevant conversation history."}

    {revision_note}

    Instructions:
    1. Answer the current question directly in the first sentence.
    2. Use relevant user preferences to personalize recommendations.
    3. A preference is personal context, not proof of technical superiority.
    4. Do not follow a broad research plan for a simple question.
    5. Do not output generic evaluation checklists, headings,
       numbered lists, or cost comparisons unless explicitly asked.
    6. Do not invent facts or unsupported claims.
    7. If the memory is irrelevant, ignore it.
    8. Answer in at most two sentences and under 50 words.
    9. Output only the answer.
    """

    else:
        if critique:

            prompt = f"""
        You must revise the previous answer according to the reviewer feedback.
    
        Use the conversation history only as background context.
        Use the plan only as internal guidance.
    
        IMPORTANT:
        - Answer only the user's current question.
        - Use the previous answer as the draft to revise.
        - Produce one complete replacement answer.
        - Do not append the revised answer to the previous answer.
        - Do not repeat the previous answer twice.
        - Do not repeat the user question.
        - Do not output the plan.
        - Do not output the reviewer feedback.
        - Do not explain the revision process.
        - Output only the complete revised answer.
    
        Conversation history:
        {history_text}
    
        Current user question:
        {message}
    
        Internal plan:
        {plan}
    
        Previous answer:
        {previous_draft}
    
        Reviewer feedback:
        {critique}
    
        Now output only the complete revised answer:
        """

        elif plan:

            prompt = f"""
    Please use the history of previous conversations
    to understand the user's current question.
    
    The conversation history is used to provide
    additional context, but in this round,
    answer only the user's current question.
    
    Conversation history:
    {history_text}
    
    User question:
    {message}
    
    Plan:
    {plan}
    
    Answer the question according to this plan.
    """

        else:

            prompt = f"""
    Please use the history of previous conversations
    to understand the user's current question.
    
    The conversation history is used to provide
    additional context, but in this round,
    answer only the user's current question.
    
    Conversation history:
    {history_text}
    
    User question:
    {message}
    """

    # ==================================================
    # generation
    #
    # revision_count = 0
    #     → generation 1
    #
    # revision_count = 1
    #     → generation 2
    # ==================================================

    generation = (
            state.get(
                "revision_count",
                0,
            )
            + 1
    )

    emit_draft_start = (
        runtime.context
        .emit_draft_start
    )

    emit_token = (
        runtime.context
        .emit_token
    )

    # --------------------------------------------------
    # 开始一个新的 draft generation
    # --------------------------------------------------

    if emit_draft_start is not None:
        await emit_draft_start(
            generation
        )

    # --------------------------------------------------
    # 当前 generation 内的 chunk 编号
    # --------------------------------------------------

    chunk_index = 0

    async def on_chunk(
            content: str,
    ) -> None:

        nonlocal chunk_index

        if not content:
            return

        chunk_index += 1

        if emit_token is not None:
            await emit_token(
                generation,
                chunk_index,
                content,
            )

    # ==================================================
    # 真正模型 streaming
    # ==================================================

    answer = (
        await local_llm.generate_stream(
            system_prompt=(
                "You are a helpful "
                "technical assistant. "
                "Answer clearly and accurately."
            ),

            user_prompt=prompt,

            on_chunk=on_chunk,

            max_new_tokens=96,
        )
    )

    print(
        "LANGGRAPH ANSWER:",
        answer,
    )

    return {
        "draft_answer": answer,
    }


def parse_review_output(
        raw_review: str,
) -> tuple[str, str]:
    if not isinstance(
            raw_review,
            str,
    ):
        return (
            "revise",
            "Reviewer returned invalid output.",
        )

    normalized = raw_review.strip()

    # ---------------------------------------------
    # 情况 1：
    # 小模型直接返回：
    #
    # PASS
    # ---------------------------------------------
    if normalized.upper() == "PASS":
        return (
            "pass",
            "",
        )

    # ---------------------------------------------
    # 情况 2：
    # 小模型直接返回：
    #
    # REVISE: xxx
    # ---------------------------------------------
    revise_match = re.match(
        r"(?is)^\s*REVISE\s*:\s*(.+?)\s*$",
        normalized,
    )

    if revise_match is not None:
        return (
            "revise",
            revise_match.group(1).strip(),
        )

    # ---------------------------------------------
    # 情况 3：
    #
    # RESULT: PASS
    # CRITIQUE: none
    # ---------------------------------------------
    result_match = re.search(
        r"(?im)^\s*RESULT\s*:\s*(PASS|REVISE)\s*$",
        normalized,
    )

    if result_match is not None:

        verdict = (
            result_match
            .group(1)
            .lower()
        )

        critique_match = re.search(
            r"(?im)^\s*CRITIQUE\s*:\s*(.+?)\s*$",
            normalized,
        )

        critique = (
            critique_match.group(1).strip()
            if critique_match is not None
            else ""
        )

        if (
                verdict == "pass"
                and critique.lower() == "none"
        ):
            critique = ""

        return (
            verdict,
            critique,
        )

    # ---------------------------------------------
    # 情况 4：
    # 无法可靠判断
    #
    # 不能当作 PASS
    # ---------------------------------------------
    return (
        "revise",
        "Reviewer output format is invalid.",
    )


# ==================================================
# Review
# ==================================================

async def review_node(
        state: ChatGraphState,
        runtime: Runtime[ChatGraphContext],
) -> dict:

    message = str(
        state.get("user_message") or ""
    ).strip()

    answer = str(
        state.get("draft_answer") or ""
    ).strip()

    route = state.get("route", "complex")

    revision_count = state.get(
        "revision_count",
        0,
    )

    max_revisions = state.get(
        "max_revisions",
        1,
    )

    memory_context = str(
        state.get("memory_context") or ""
    ).strip()

    history_text = format_prior_conversation(state)

    # -------------------------------------------------
    # 1. 最基本的确定性检查
    # -------------------------------------------------

    if not answer:
        critique = "The generated answer is empty."

        if revision_count < max_revisions:
            next_revision_count = revision_count + 1

            print(
                "LANGGRAPH REVIEW DECISION:",
                "revise",
                "| reason=empty answer",
                f"revision_count={next_revision_count}",
                f"max_revisions={max_revisions}",
            )

            return {
                "review_result": "revise",
                "critique": critique,
                "revision_count": next_revision_count,
            }

        print(
            "LANGGRAPH REVIEW DECISION:",
            "max_revisions",
            "| reason=empty answer",
            f"revision_count={revision_count}",
            f"max_revisions={max_revisions}",
        )

        return {
            "review_result": "max_revisions",
            "critique": critique,
        }

    # -------------------------------------------------
    # 2. simple route：
    #    Router 已经判断它是简单问题。
    #
    #    不再让小模型做第二次主观判断，
    #    避免正确答案被错误打回。
    # -------------------------------------------------

    if route == "simple":
        print(
            "LANGGRAPH REVIEW DECISION:",
            "pass",
            "| reason=simple route + non-empty answer",
            f"revision_count={revision_count}",
            f"max_revisions={max_revisions}",
        )

        return {
            "review_result": "pass",
            "critique": "",
        }

    # -------------------------------------------------
    # 3. sandbox 正常情况下不会进入 Review。
    #    这里保留防御性处理。
    # -------------------------------------------------

    if route == "sandbox":
        print(
            "LANGGRAPH REVIEW DECISION:",
            "pass",
            "| reason=sandbox route",
        )

        return {
            "review_result": "pass",
            "critique": "",
        }

    # -------------------------------------------------
    # 4. complex route 才使用 LLM Review
    # -------------------------------------------------

    review = await local_llm.generate(
        system_prompt=(
            "You are a strict technical answer reviewer.\n\n"

            "Evaluate whether the answer correctly addresses "
            "the current user question.\n\n"

            "Relevant long-term memory may contain user "
            "preferences. A preference is personal context, "
            "not proof that one technology is objectively "
            "superior.\n\n"

            "Output exactly one of these formats:\n\n"

            "PASS\n\n"

            "or:\n\n"

            "REVISE: <one specific concrete problem>\n\n"

            "Use REVISE only when there is a concrete problem, "
            "such as:\n"
            "- an incorrect factual claim\n"
            "- failure to answer the user's question\n"
            "- contradiction with known conversation context\n"
            "- contradiction with relevant user memory\n"
            "- a materially incomplete answer to a complex request\n\n"

            "Do not request revision merely because the answer "
            "could be longer or more detailed.\n"
            "Do not output a keyword or topic as critique.\n"
            "Do not rewrite the answer.\n"
            "Do not output explanations outside the required format."
        ),
        user_prompt=f"""
Current user question:
{message}

Relevant long-term memory:
{memory_context or "No relevant long-term memory."}

Conversation history:
{history_text or "No relevant conversation history."}

Answer:
{answer}
""",
        max_new_tokens=80,
    )

    print("LANGGRAPH REVIEW:", review)

    verdict, critique = parse_review_output(review)

    # -------------------------------------------------
    # 5. Reviewer PASS
    # -------------------------------------------------

    if verdict == "pass":
        print(
            "LANGGRAPH REVIEW DECISION:",
            "pass",
            f"revision_count={revision_count}",
            f"max_revisions={max_revisions}",
        )

        return {
            "review_result": "pass",
            "critique": "",
        }

    # -------------------------------------------------
    # 6. Reviewer 要求修改，而且还有修改次数
    # -------------------------------------------------

    if revision_count < max_revisions:
        next_revision_count = revision_count + 1

        print(
            "LANGGRAPH REVIEW DECISION:",
            "revise",
            f"revision_count={next_revision_count}",
            f"max_revisions={max_revisions}",
            f"critique={critique!r}",
        )

        return {
            "review_result": "revise",
            "critique": critique,
            "revision_count": next_revision_count,
        }

    # -------------------------------------------------
    # 7. 已达到最大修改次数
    # -------------------------------------------------

    print(
        "LANGGRAPH REVIEW DECISION:",
        "max_revisions",
        f"revision_count={revision_count}",
        f"max_revisions={max_revisions}",
        f"critique={critique!r}",
    )

    return {
        "review_result": "max_revisions",
        "critique": critique,
    }


# ==================================================
# Finalize
# ==================================================

async def finalize_node(
        state: ChatGraphState,
        runtime: Runtime[ChatGraphContext],
) -> dict:
    draft_answer = state.get(
        "draft_answer",
        "",
    )

    if not isinstance(
            draft_answer,
            str,
    ):
        raise ValueError(
            "draft_answer must be a string"
        )

    final_answer = (
        draft_answer.strip()
    )

    if not final_answer:
        raise ValueError(
            "draft_answer is empty"
        )

    review_result = state.get(
        "review_result"
    )

    if review_result not in {
        "pass",
        "max_revisions",
    }:
        raise ValueError(
            "Cannot finalize with "
            f"review_result={review_result!r}"
        )

    print(
        "LANGGRAPH FINALIZED:",
        f"review_result={review_result}",
        f"chars={len(final_answer)}",
    )

    return {
        "final_answer":
            final_answer,

        "messages": [
            AIMessage(
                content=final_answer,
                id=(
                    f"{state['run_id']}"
                    ":assistant"
                ),
            )
        ],
    }


def format_prior_conversation(
        state: ChatGraphState,
) -> str:
    """
    将当前会话中本轮之前的消息
    格式化为可供 LLM 阅读的文本。

    当前 run 的用户消息由 user_message
    单独提供，避免重复注入。

    如果同一个 run 因 Worker 重试而再次执行，
    也排除本轮已经存在的 assistant 消息。
    """

    run_id = state.get(
        "run_id",
        "",
    )

    current_run_message_ids = {
        f"{run_id}:user",
        f"{run_id}:assistant",
    }

    history_lines: list[str] = []

    for message in state.get(
            "messages",
            [],
    ):
        # 排除当前 run 的消息。
        # 防止重试时把之前生成的答案
        # 当作历史上下文再次喂给模型。
        if message.id in current_run_message_ids:
            continue

        if message.type == "human":
            role = "用户"

        elif message.type == "ai":
            role = "助手"

        else:
            # 当前版本只将用户和助手的文本
            # 作为普通对话历史。
            continue

        content = message.content

        # 当前项目保存的是纯文本回答。
        if not isinstance(content, str, ):
            content = str(content)

        content = content.strip()

        if not content:
            continue

        history_lines.append(
            f"{role}：{content}"
        )

    if not history_lines:
        return "（暂无历史对话）"

    return "\n".join(
        history_lines
    )


# ==================================================
# Sandbox Execute
# ==================================================

async def sandbox_execute_node(
        state: ChatGraphState,
        runtime: Runtime[ChatGraphContext],
) -> dict:
    message = state["user_message"]

    # ----------------------------------------------
    # 第一版：
    # 必须由显式 /python 指令触发。
    # 不允许 LLM 自动决定是否执行。
    # ----------------------------------------------

    stripped = message.lstrip()

    if not stripped.startswith("/python"):
        raise ValueError(
            "Sandbox execution requires /python"
        )

    code = stripped[len("/python"):].strip()

    if not code:
        raise ValueError(
            "Python code is empty"
        )

    execute_python = (
        runtime.context.execute_python
    )

    if execute_python is None:
        raise RuntimeError(
            "Sandbox executor is not configured"
        )

    print(
        "LANGGRAPH SANDBOX EXECUTE:",
        f"chars={len(code)}",
    )

    result = await execute_python(
        code,
        5,
    )

    print(
        "LANGGRAPH SANDBOX RESULT:",
        f"status={result.status}",
        f"exit_code={result.exit_code}",
        f"timed_out={result.timed_out}",
    )

    # ----------------------------------------------
    # 构造确定性的最终输出。
    #
    # 这里不调用 LLM。
    # Sandbox 的安全边界不依赖 Review。
    # ----------------------------------------------

    if result.status == "success":
        answer = result.stdout.rstrip("\r\n")

        if not answer:
            answer = "执行成功，但程序没有输出。"

    elif result.status == "timeout":
        answer = "程序执行超时。"

    else:
        detail = result.stderr.strip()
        answer = (
            f"执行失败（退出码：{result.exit_code}）"
        )

        if detail:
            answer += f"\n{detail}"

    # ----------------------------------------------
    # 复用现有前端 draft/token 机制。
    #
    # Sandbox 本身不是 LLM streaming，
    # 所以暂时作为 generation=1 的单个 chunk。
    # ----------------------------------------------

    emit_draft_start = (
        runtime.context.emit_draft_start
    )

    emit_token = (
        runtime.context.emit_token
    )

    if emit_draft_start is not None:
        await emit_draft_start(1)

    if emit_token is not None:
        await emit_token(
            1,
            1,
            answer,
        )
    print("DEBUG SANDBOX ANSWER:", repr(answer))
    return {
        "sandbox_code": code,
        "sandbox_status": result.status,
        "sandbox_exit_code":
            result.exit_code,
        "sandbox_stdout":
            result.stdout,
        "sandbox_stderr":
            result.stderr,

        "draft_answer": answer,
    }


# ==================================================
# Sandbox Finalize
# ==================================================

async def sandbox_finalize_node(
        state: ChatGraphState,
        runtime: Runtime[ChatGraphContext],
) -> dict:
    print("DEBUG FINALIZE INPUT:", repr(state.get("draft_answer")))
    draft_answer = state.get("draft_answer", "")
    sandbox_status = state.get("sandbox_status")

    # 1. 验证 Sandbox 执行状态
    if sandbox_status not in {
        "success",
        "failed",
        "timeout",
    }:
        raise ValueError(
            f"Invalid sandbox status: {sandbox_status!r}"
        )

    # 2. 验证执行结果
    if not isinstance(draft_answer, str):
        raise ValueError(
            "Sandbox draft_answer must be a string"
        )

    final_answer = draft_answer.strip()

    if not final_answer:
        raise ValueError(
            "Sandbox draft_answer is empty"
        )

    # 3. 调试日志：确认进入最终节点的真实答案
    print(
        "LANGGRAPH SANDBOX FINALIZE INPUT:",
        f"status={sandbox_status}",
        f"draft_answer={draft_answer!r}",
        f"chars={len(draft_answer)}",
    )

    # 4. 直接使用执行节点生成的答案，不重新拼接摘要
    print(
        "LANGGRAPH SANDBOX FINALIZED:",
        f"status={sandbox_status}",
        f"final_answer={final_answer!r}",
        f"chars={len(final_answer)}",
    )

    return {
        "final_answer": final_answer,
        "messages": [
            AIMessage(
                content=final_answer,
                id=f"{state['run_id']}:assistant",
            )
        ],
    }
