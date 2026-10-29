import logging
import re

from app.llm.local_llm import local_llm

logger = logging.getLogger(__name__)

MAX_MEMORIES = 5
MAX_MEMORY_LENGTH = 300


# ============================================================
# 1. 明确没有长期价值的内容
# ============================================================

LOW_VALUE_MESSAGES = {
    "你好",
    "您好",
    "嗨",
    "hi",
    "hello",
    "hey",
    "谢谢",
    "谢谢你",
    "thanks",
    "thank you",
    "好的",
    "好",
    "ok",
    "okay",
    "收到",
    "明白了",
    "知道了",
    "嗯",
    "哦",
    "再见",
    "拜拜",
}


# ============================================================
# 2. 明确表达长期信息的高置信模式
#
# 命中这些规则时，可以直接 KEEP，
# 不需要浪费一次小模型推理。
# ============================================================

STRONG_MEMORY_PATTERNS = (
    # 中文：偏好
    r"我.*偏好",
    r"我.*更喜欢",
    r"我.*喜欢使用",
    r"我.*倾向于",

    # 中文：明确决定
    r"我.*决定使用",
    r"我.*决定采用",
    r"我.*以后.*使用",
    r"我.*今后.*使用",
    r"我.*以后.*采用",
    r"我.*今后.*采用",

    # 中文：长期目标
    r"我的长期目标",
    r"我的目标是",
    r"我计划长期",
    r"我正在长期",

    # 中文：持续项目/环境
    r"我的项目使用",
    r"我的项目是",
    r"我目前使用",
    r"我的开发环境",

    # English
    r"\bi prefer\b",
    r"\bi strongly prefer\b",
    r"\bi decided to use\b",
    r"\bi will use\b",
    r"\bmy long[- ]term goal\b",
    r"\bmy project uses\b",
    r"\bmy development environment\b",
)


# ============================================================
# 3. 明确表示“不确定/暂未决定”
# ============================================================

UNCERTAIN_PATTERNS = (
    r"还没决定",
    r"还没有决定",
    r"尚未决定",
    r"没有决定",
    r"不确定",
    r"还不确定",
    r"正在考虑",
    r"我考虑过",
    r"可能会",
    r"也许会",
    r"或许会",
    r"\bnot decided\b",
    r"\bnot sure\b",
    r"\bconsidering\b",
    r"\bmaybe\b",
    r"\bmight\b",
)


# ============================================================
# 4. 明确的最终决定词
#
# 如果一句话前面说“曾经考虑”，但后面已经明确决定，
# 应允许它进入记忆。
#
# 例如：
# 我之前考虑 MySQL，但现在决定使用 PostgreSQL。
# ============================================================

FINAL_DECISION_PATTERNS = (
    r"但现在.*决定",
    r"现在决定",
    r"最终决定",
    r"最后决定",
    r"已经决定",
    r"目前确定",
    r"最终选择",
    r"现在选择",
    r"\bbut now i decided\b",
    r"\bi have decided\b",
    r"\bfinally decided\b",
)


def normalize_text(text: str) -> str:
    text = " ".join(text.split()).casefold()

    return text.strip(
        " \t\r\n"
        ".,!?;:，。！？；：、"
        "\"'“”‘’"
    )


def split_sentences(text: str) -> list[str]:
    """
    将用户消息切成句子。

    注意：
    最终保存的依旧是这里得到的用户原文，
    不使用 LLM 生成的新文本。
    """
    text = text.strip()

    if not text:
        return []

    parts = re.split(
        r"(?<=[。！？!?；;])\s*|\n+",
        text,
    )

    return [
        part.strip()
        for part in parts
        if part.strip()
    ]


def matches_any(
    text: str,
    patterns: tuple[str, ...],
) -> bool:
    return any(
        re.search(
            pattern,
            text,
            flags=re.IGNORECASE,
        )
        for pattern in patterns
    )


def deterministic_decision(
    sentence: str,
) -> str | None:
    """
    返回：

    "KEEP"
        程序可以高置信度确认应该保存。

    "DROP"
        程序可以高置信度确认不应该保存。

    None
        程序无法可靠判断，交给 LLM。
    """

    normalized = normalize_text(sentence)

    if not normalized:
        return "DROP"

    # --------------------------------------------------------
    # 问候、谢谢、确认等
    # --------------------------------------------------------

    if normalized in LOW_VALUE_MESSAGES:
        return "DROP"

    # --------------------------------------------------------
    # 普通问题默认不作为长期记忆
    # --------------------------------------------------------

    if sentence.rstrip().endswith(
        ("?", "？")
    ):
        return "DROP"

    # --------------------------------------------------------
    # “最终明确决定”优先于前面的考虑/不确定表达
    #
    # 我之前考虑 MySQL，但现在决定使用 PostgreSQL。
    # → KEEP
    # --------------------------------------------------------

    if matches_any(
        sentence,
        FINAL_DECISION_PATTERNS,
    ):
        return "KEEP"

    # --------------------------------------------------------
    # 明确没有做出决定
    # --------------------------------------------------------

    if matches_any(
        sentence,
        UNCERTAIN_PATTERNS,
    ):
        return "DROP"

    # --------------------------------------------------------
    # 明确偏好、决定、长期目标、开发环境
    # --------------------------------------------------------

    if matches_any(
        sentence,
        STRONG_MEMORY_PATTERNS,
    ):
        return "KEEP"

    # 无法确定
    return None


def parse_llm_decision(raw: str) -> str:
    """
    小模型只允许产生 KEEP / DROP。

    非法、不确定、同时出现 KEEP 和 DROP：
    一律 DROP。

    Memory 系统宁可漏记，也不能错误记忆。
    """
    cleaned = (
        raw
        .strip()
        .upper()
    )

    tokens = re.findall(
        r"\b(?:KEEP|DROP)\b",
        cleaned,
    )

    unique_tokens = set(tokens)

    if unique_tokens == {"KEEP"}:
        return "KEEP"

    if unique_tokens == {"DROP"}:
        return "DROP"

    logger.warning(
        "MEMORY CLASSIFIER INVALID OUTPUT: %r",
        raw,
    )

    return "DROP"


async def classify_with_llm(
    sentence: str,
) -> str:
    """
    只处理规则无法确定的句子。

    LLM 不允许改写记忆，只做二分类。
    """

    system_prompt = """
You are a conservative long-term memory classifier.

Decide whether ONE sentence written by the user should be
stored as long-term memory.

Output exactly one word:

KEEP

or

DROP

KEEP only if the sentence clearly contains durable information
that will probably be useful in future conversations, such as:

- a stable personal preference;
- a clear long-term goal;
- an ongoing project;
- an explicit technical decision;
- a persistent development environment;
- a persistent constraint.

DROP if it is:

- a greeting;
- thanks or conversational filler;
- a temporary request;
- a question;
- a hypothetical idea;
- an uncertain possibility;
- something the user has not decided;
- temporary information;
- ordinary conversation without durable personal context.

Be conservative.

If uncertain, output DROP.

Do not explain.
Do not summarize.
Do not rewrite the sentence.
Do not output punctuation.
Output only KEEP or DROP.
"""

    user_prompt = f"""
User sentence:

{sentence}
"""

    raw = await local_llm.generate(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        max_new_tokens=8,
    )

    decision = parse_llm_decision(raw)

    print(
        "[MEMORY CLASSIFIER]",
        f"sentence={sentence!r}",
        f"raw={raw!r}",
        f"decision={decision}",
    )

    return decision


async def extract_memory_candidates(
    user_messages: list[str],
) -> list[str]:
    """
    从用户消息中提取长期记忆候选。

    设计原则：

    1. 只接受 user 消息。
    2. 优先使用确定性规则。
    3. 边界情况才调用 LLM。
    4. LLM 只能输出 KEEP / DROP。
    5. 最终保存的一定是用户原文。
    6. 默认宁可漏记，也不要错误记忆。
    """

    if not user_messages:
        return []

    sentences: list[str] = []

    for message in user_messages:
        if not isinstance(message, str):
            continue

        sentences.extend(
            split_sentences(message)
        )

    memories: list[str] = []
    seen: set[str] = set()

    for sentence in sentences:

        if len(memories) >= MAX_MEMORIES:
            break

        sentence = sentence.strip()

        if not sentence:
            continue

        if len(sentence) > MAX_MEMORY_LENGTH:
            logger.warning(
                "MEMORY SENTENCE SKIPPED: "
                "too long, chars=%d",
                len(sentence),
            )
            continue

        normalized = normalize_text(sentence)

        if normalized in seen:
            continue

        # ----------------------------------------------------
        # 第一层：确定性规则
        # ----------------------------------------------------

        decision = deterministic_decision(
            sentence
        )

        if decision is not None:
            print(
                "[MEMORY RULE]",
                f"sentence={sentence!r}",
                f"decision={decision}",
            )

        # ----------------------------------------------------
        # 第二层：规则无法判断，再交给 LLM
        # ----------------------------------------------------

        else:
            decision = await classify_with_llm(
                sentence
            )

        # ----------------------------------------------------
        # 只有 KEEP 才进入候选
        # ----------------------------------------------------

        if decision != "KEEP":
            continue

        seen.add(normalized)

        # 注意：
        # 这里加入的是用户原句 sentence，
        # 绝对不是 LLM 输出。
        memories.append(sentence)

    print(
        "[MEMORY EXTRACTOR] FINAL CANDIDATES:",
        repr(memories),
    )

    return memories
