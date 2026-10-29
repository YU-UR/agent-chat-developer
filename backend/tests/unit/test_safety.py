from app.memory.safety import contains_sensitive_data


TEST_CASES = [
    (
        "normal preference",
        "我偏好使用 PostgreSQL。",
        False,
    ),
    (
        "normal project background",
        "我的项目使用 FastAPI 和 PostgreSQL。",
        False,
    ),
    (
        "mention API keys without value",
        "如何安全管理 API Key？",
        False,
    ),
    (
        "English password",
        "My password is TEST_ONLY_NOT_A_REAL_SECRET_12345",
        True,
    ),
    (
        "Chinese password",
        "我的测试密码是 TEST_ONLY_NOT_A_REAL_SECRET_12345",
        True,
    ),
    (
        "API key assignment",
        "API key: sk-proj-abcdefghijklmnopqrstuvwxyz0123456789",
        True,
    ),
    (
        "Bearer token",
        "Authorization: Bearer abcdefghijklmnopqrstuvwxyz123456",
        True,
    ),
    (
        "Chinese access token",
        "访问令牌：TEST_TOKEN_123456789",
        True,
    ),
    (
        "GitHub token",
        "ghp_abcdefghijklmnopqrstuvwxyz0123456789",
        True,
    ),
    (
        "PEM private key",
        "-----BEGIN PRIVATE KEY-----",
        True,
    ),
]


def main() -> None:
    passed = 0

    for name, text, expected in TEST_CASES:
        actual = contains_sensitive_data(text)
        success = actual is expected

        print(
            f"{name}: "
            f"{'PASS' if success else 'FAIL'} "
            f"(expected={expected}, actual={actual})"
        )

        if not success:
            print("  INPUT:", repr(text))
        else:
            passed += 1

    print(f"\nSAFETY TESTS: {passed}/{len(TEST_CASES)} PASS")

    if passed != len(TEST_CASES):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
