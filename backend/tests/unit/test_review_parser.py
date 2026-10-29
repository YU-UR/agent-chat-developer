import re


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

    if normalized.upper() == "PASS":
        return (
            "pass",
            "",
        )

    revise_match = re.match(
        r"(?is)^\s*REVISE\s*:\s*(.+?)\s*$",
        normalized,
    )

    if revise_match is not None:
        return (
            "revise",
            revise_match.group(1).strip(),
        )

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

    return (
        "revise",
        "Reviewer output format is invalid.",
    )


# ==========================================
# Test 1: PASS
# ==========================================

verdict, critique = parse_review_output("PASS")

assert verdict == "pass"
assert critique == ""

print("PASS: direct PASS")


# ==========================================
# Test 2: REVISE
# ==========================================

verdict, critique = parse_review_output(
    "REVISE: Please improve clarity."
)

assert verdict == "revise"
assert critique == "Please improve clarity."

print("PASS: direct REVISE")


# ==========================================
# Test 3: RESULT / CRITIQUE
# ==========================================

verdict, critique = parse_review_output(
    "RESULT: PASS\nCRITIQUE: none"
)

assert verdict == "pass"
assert critique == ""

print("PASS: RESULT PASS")


# ==========================================
# Test 4: invalid output
# ==========================================

verdict, critique = parse_review_output("5")

assert verdict == "revise"

print("PASS: invalid output -> revise")


print()
print("PASS: review parser validation completed.")