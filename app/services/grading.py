from __future__ import annotations

import re
import unicodedata
from typing import Any

from sympy import E, pi, simplify, sympify


CHOICE_RE = re.compile(r"(?<![A-Za-z])([ABCD])(?![A-Za-z])", re.IGNORECASE)


def strip_markdown(value: str) -> str:
    text = unicodedata.normalize("NFKC", value or "")
    text = text.replace("\u200b", "").replace("$", "")
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    text = re.sub(r"[*_`>#]", "", text)
    return text.strip()


def normalize_tex(value: str) -> str:
    text = strip_markdown(value)
    text = text.replace("\\left", "").replace("\\right", "")
    text = text.replace("\\dfrac", "\\frac").replace("\\tfrac", "\\frac")
    text = text.replace("\\,", "").replace("\\!", "").replace("\\;", "")
    text = text.replace("\\cdot", "*").replace("\\times", "*")
    text = text.replace("\\pi", "pi").replace("π", "pi")
    text = text.replace("\\infty", "oo")
    text = re.sub(r"\\(?:mathrm|mathbf|mathit|text|operatorname)\s*\{([^{}]*)\}", r"\1", text)
    text = re.sub(r"\\begin\{[^}]+\}|\\end\{[^}]+\}", "", text)
    text = text.replace("\\\\", ";")
    # This covers ordinary fractions in the answer bank. Complex nested TeX is
    # deliberately left for the LLM/manual review path instead of guessed.
    fraction_pattern = re.compile(r"\\frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}")
    for _ in range(5):
        updated = fraction_pattern.sub(r"(\1)/(\2)", text)
        if updated == text:
            break
        text = updated
    text = re.sub(r"\s+", "", text)
    text = text.strip("。；;，,")
    return text


def extract_choice(value: str) -> str | None:
    matches = CHOICE_RE.findall(strip_markdown(value).upper())
    return matches[0] if matches else None


def _expression(value: str) -> Any:
    text = normalize_tex(value)
    if not text or any(token in text for token in ("=", "<", ">", "∞", "oo", "，", ";")):
        return None
    text = text.replace("^", "**")
    text = text.replace("{", "(").replace("}", ")")
    text = re.sub(r"(?<=\d)(?=[A-Za-z(])", "*", text)
    text = re.sub(r"(?<=[)])(?=\d|[A-Za-z(])", "*", text)
    try:
        return sympify(text, locals={"pi": pi, "E": E, "e": E})
    except (TypeError, ValueError, SyntaxError, NameError):
        return None


def equivalent_expression(left: str, right: str) -> bool:
    left_normalized = normalize_tex(left)
    right_normalized = normalize_tex(right)
    if not left_normalized or not right_normalized:
        return False
    if left_normalized == right_normalized:
        return True
    left_expr = _expression(left)
    right_expr = _expression(right)
    if left_expr is None or right_expr is None:
        return False
    try:
        difference = simplify(left_expr - right_expr)
        return difference == 0 or bool(difference.equals(0))
    except (TypeError, ValueError, AttributeError):
        return False


def answer_text(answer_markdown: str) -> str:
    text = strip_markdown(answer_markdown)
    text = re.sub(r"^答案\s*[:：]?\s*", "", text)
    return text.strip()


def grade_question(question: dict[str, Any], answer: str, self_grade: float | None = None) -> dict[str, Any]:
    kind = question.get("question_type", "solution")
    expected = answer_text(question.get("answer_markdown", ""))
    submitted = (answer or "").strip()
    max_score = float(question.get("points", 0))

    if kind == "choice" and expected:
        expected_choice = extract_choice(expected)
        submitted_choice = extract_choice(submitted)
        is_correct = bool(expected_choice and submitted_choice and expected_choice == submitted_choice)
        return {
            "correct": is_correct,
            "status": "correct" if is_correct else "incorrect",
            "score": max_score if is_correct else 0.0,
            "max_score": max_score,
            "confidence": 1.0,
            "error_type": "" if is_correct else ("未作答" if not submitted else "答案错误"),
            "expected_answer": expected,
        }

    if kind == "fill" and expected:
        is_correct = equivalent_expression(submitted, expected)
        return {
            "correct": is_correct,
            "status": "correct" if is_correct else "incorrect",
            "score": max_score if is_correct else 0.0,
            "max_score": max_score,
            "confidence": 0.9 if is_correct else 0.75,
            "error_type": "" if is_correct else ("未作答" if not submitted else "表达式或数值不等价"),
            "expected_answer": expected,
        }

    if self_grade is not None:
        bounded = max(0.0, min(1.0, float(self_grade)))
        correct = bounded >= 0.999
        status = "correct" if correct else ("partial" if bounded > 0 else "incorrect")
        return {
            "correct": correct,
            "status": status,
            "score": max_score * bounded,
            "max_score": max_score,
            "confidence": 0.55,
            "error_type": "" if correct else ("步骤不完整" if bounded > 0 else "不会或未完成"),
            "expected_answer": expected,
        }

    return {
        "correct": None,
        "status": "manual",
        "score": 0.0,
        "max_score": max_score,
        "confidence": 0.25,
        "error_type": "待自评或AI复核",
        "expected_answer": expected,
    }
