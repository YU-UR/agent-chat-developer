import re


SENSITIVE_PATTERNS = (
    # 英文凭据字段及赋值
    r"(?i)\b(?:api[_ -]?key|access[_ -]?token|"
    r"refresh[_ -]?token|password|passwd|"
    r"client[_ -]?secret|secret[_ -]?key|token)\b"
    r"\s*(?:is|为|是|[:=：])\s*\S+",

    # 中文凭据字段及赋值
    r"(?:密码|口令|访问令牌|刷新令牌|令牌|"
    r"API密钥|密钥|客户端密钥)"
    r"\s*(?:是|为|[:=：])\s*\S+",

    # HTTP Bearer Token
    r"(?i)\bbearer\s+[a-z0-9._~+/=-]{8,}",

    # 常见凭据格式
    r"\bsk-[A-Za-z0-9_-]{20,}\b",
    r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b",
    r"\bAKIA[0-9A-Z]{16}\b",

    # JWT 形态的 Token
    r"\beyJ[A-Za-z0-9_-]{10,}"
    r"\.[A-Za-z0-9_-]{10,}"
    r"\.[A-Za-z0-9_-]{10,}\b",

    # PEM 私钥
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
)


def contains_sensitive_data(text: str) -> bool:
    """
    检测疑似凭据。
    检测到时拒绝保存整条候选记忆。

    注意：这是规则层防护，不保证覆盖所有秘密格式。
    """
    return any(
        re.search(pattern, text)
        for pattern in SENSITIVE_PATTERNS
    )
