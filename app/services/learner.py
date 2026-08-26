from __future__ import annotations

import random
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from statistics import mean
from typing import Any

from app.services.concepts import (
    CONCEPT_META,
    concept_descriptor,
)

QUESTION_TYPE_ORDER = ("choice", "fill", "solution")
QUESTION_TIME_TARGETS = {"choice": 150, "fill": 180, "solution": 600}


def _attempt_datetime(attempt: dict[str, Any]) -> datetime | None:
    raw_value = str(attempt.get("created_at") or "").strip()
    if not raw_value:
        return None
    try:
        value = datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _attempt_score_ratio(attempt: dict[str, Any]) -> float | None:
    maximum = float(attempt.get("max_score") or 0)
    if maximum <= 0:
        return None
    return max(0.0, min(1.0, float(attempt.get("score") or 0) / maximum))


def _question_time_target(question: dict[str, Any]) -> float:
    return float(QUESTION_TIME_TARGETS.get(question.get("question_type"), 300))


def difficulty_descriptor(year: int | str | None) -> tuple[str, str]:
    """Map the real-question year ranges to the study difficulty bands."""
    try:
        normalized_year = int(year or 0)
    except (TypeError, ValueError):
        normalized_year = 0
    if 1987 <= normalized_year <= 2019:
        return "basic", "基础题"
    if 2020 <= normalized_year <= 2026:
        return "advanced", "提高题"
    return "other", "待分层"


def mastery_by_concept(attempts: list[dict[str, Any]]) -> dict[str, float]:
    states: dict[str, float] = defaultdict(lambda: 0.22)
    # Attempts are stored newest-first. Applying them oldest-first produces a
    # stable, interpretable Bayesian-style learning trajectory.
    for attempt in reversed(attempts):
        concepts = attempt.get("concepts") or []
        if not concepts:
            continue
        status = attempt.get("status")
        if status == "correct" or attempt.get("correct") == 1:
            gain = 0.22
            for concept_id in concepts:
                states[concept_id] += (1.0 - states[concept_id]) * gain
        elif status == "partial":
            for concept_id in concepts:
                states[concept_id] += (0.50 - states[concept_id]) * 0.12
        elif status in {"incorrect", "manual"} or attempt.get("correct") == 0:
            for concept_id in concepts:
                states[concept_id] *= 0.78
    return {key: round(max(0.02, min(0.98, value)), 4) for key, value in states.items()}


def progress_summary(attempts: list[dict[str, Any]], questions: list[dict[str, Any]]) -> dict[str, Any]:
    mastery = mastery_by_concept(attempts)
    counts: dict[str, int] = defaultdict(int)
    correct_counts: dict[str, int] = defaultdict(int)
    seconds: dict[str, list[int]] = defaultdict(list)
    for attempt in attempts:
        for concept_id in attempt.get("concepts") or []:
            counts[concept_id] += 1
            if attempt.get("correct") == 1 or attempt.get("status") == "correct":
                correct_counts[concept_id] += 1
            seconds[concept_id].append(int(attempt.get("duration_seconds") or 0))

    question_counts: dict[str, int] = defaultdict(int)
    for question in questions:
        for concept_id in question.get("concept_ids") or []:
            question_counts[concept_id] += 1

    rows = []
    for concept_id, (name, subject) in CONCEPT_META.items():
        value = mastery.get(concept_id, 0.22)
        rows.append(
            {
                "id": concept_id,
                "name": name,
                "subject": subject,
                "mastery": round(value * 100, 1),
                "attempts": counts.get(concept_id, 0),
                "correct": correct_counts.get(concept_id, 0),
                "accuracy": round(correct_counts.get(concept_id, 0) / counts[concept_id] * 100, 1) if counts.get(concept_id) else None,
                "avg_seconds": round(mean(seconds[concept_id]), 1) if seconds.get(concept_id) else None,
                "question_count": question_counts.get(concept_id, 0),
                "status": "薄弱" if value < 0.42 else ("巩固中" if value < 0.7 else "稳定"),
            }
        )
    rows.sort(key=lambda row: (row["mastery"], -row["attempts"]))
    attempted = len({attempt.get("question_id") for attempt in attempts})
    correct = sum(1 for attempt in attempts if attempt.get("correct") == 1 or attempt.get("status") == "correct")
    return {
        "attempts": len(attempts),
        "unique_questions": attempted,
        "correct": correct,
        "accuracy": round(correct / len(attempts) * 100, 1) if attempts else None,
        "overall_mastery": round(mean([row["mastery"] for row in rows]), 1) if rows else 0,
        "concepts": rows,
    }


def recommended_questions(
    questions: list[dict[str, Any]], attempts: list[dict[str, Any]], *,
    exam_type: str | None = None, concept_id: str | None = None, limit: int = 8,
) -> list[dict[str, Any]]:
    mastery = mastery_by_concept(attempts)
    question_by_id = {question.get("id"): question for question in questions}
    attempts_by_question: dict[str, list[dict[str, Any]]] = defaultdict(list)
    attempts_by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for attempt in attempts:
        question_id = attempt.get("question_id")
        if question_id:
            attempts_by_question[question_id].append(attempt)
        question_type = str(attempt.get("question_type") or question_by_id.get(question_id, {}).get("question_type") or "")
        if question_type:
            attempts_by_type[question_type].append(attempt)
    dated_attempts = [value for items in attempts_by_question.values() for value in items if _attempt_datetime(value)]
    reference_time = max((_attempt_datetime(item) for item in dated_attempts), default=None)
    type_accuracy: dict[str, float] = {}
    for question_type, items in attempts_by_type.items():
        type_accuracy[question_type] = sum(
            1 for item in items if item.get("correct") == 1 or item.get("status") == "correct"
        ) / len(items)

    candidates = []
    for question in questions:
        if exam_type and question.get("exam_type") != exam_type:
            continue
        if concept_id and concept_id not in question.get("concept_ids", []):
            continue
        concept_values = [mastery.get(item, 0.22) for item in question.get("concept_ids") or []]
        weakest = min(concept_values) if concept_values else 0.22
        question_attempts = attempts_by_question.get(question["id"], [])
        unseen_bonus = 0.32 if not question_attempts else 0
        repetition_penalty = min(0.3, len(question_attempts) * 0.08)
        type_bonus = 0.08 if question.get("question_type") in {"choice", "fill"} else 0
        type_gap_bonus = 0.10 * (1.0 - type_accuracy.get(question.get("question_type", ""), 0.0)) if question_attempts else 0.03
        recent_error_bonus = 0.0
        stale_bonus = 0.0
        slow_bonus = 0.0
        if question_attempts:
            latest_attempt = max(question_attempts, key=lambda item: _attempt_datetime(item) or datetime.min.replace(tzinfo=timezone.utc))
            if latest_attempt.get("status") in {"incorrect", "partial", "manual"}:
                recent_error_bonus = 0.14
            latest_time = _attempt_datetime(latest_attempt)
            if reference_time and latest_time and reference_time - latest_time >= timedelta(days=21):
                stale_bonus = 0.08
            durations = [float(item.get("duration_seconds") or 0) for item in question_attempts if float(item.get("duration_seconds") or 0) > 0]
            if durations and mean(durations) > _question_time_target(question):
                slow_bonus = 0.10
        difficulty_band, _ = difficulty_descriptor(question.get("year"))
        target_band = "basic" if weakest < 0.50 else "advanced"
        difficulty_fit_bonus = 0.08 if difficulty_band == target_band else 0.0
        score = (
            (1.0 - weakest)
            + unseen_bonus
            + type_bonus
            + type_gap_bonus
            + recent_error_bonus
            + stale_bonus
            + slow_bonus
            + difficulty_fit_bonus
            - repetition_penalty
        )
        candidates.append((score, question))
    # Keep the weakness-first score, but randomize equal-priority candidates
    # and the displayed order so refreshes do not become a fixed playlist.
    rng = random.SystemRandom()
    rng.shuffle(candidates)
    candidates.sort(key=lambda item: item[0], reverse=True)
    selected = [item[1] for item in candidates[: max(1, min(limit, 30))]]
    rng.shuffle(selected)
    return selected


def question_type_breakdown(
    questions: list[dict[str, Any]], attempts: list[dict[str, Any]], concept_id: str,
) -> list[dict[str, Any]]:
    """Return usable training sub-blocks for one concept, split by question type."""
    concept_questions = [
        question for question in questions
        if concept_id in question.get("concept_ids", [])
    ]
    question_ids_by_type = {
        question_type: {
            question["id"] for question in concept_questions
            if question.get("question_type") == question_type
        }
        for question_type in QUESTION_TYPE_ORDER
    }
    rows = []
    for question_type in QUESTION_TYPE_ORDER:
        question_ids = question_ids_by_type[question_type]
        if not question_ids:
            continue
        type_attempts = [attempt for attempt in attempts if attempt.get("question_id") in question_ids]
        correct = sum(
            1 for attempt in type_attempts
            if attempt.get("correct") == 1 or attempt.get("status") == "correct"
        )
        accuracy = round(correct / len(type_attempts) * 100, 1) if type_attempts else None
        rows.append(
            {
                "question_type": question_type,
                "question_count": len(question_ids),
                "attempts": len(type_attempts),
                "correct": correct,
                "accuracy": accuracy,
                "status": "待训练" if not type_attempts else ("需加强" if (accuracy or 0) < 60 else "继续巩固"),
            }
        )
    return rows


def learning_analytics(
    questions: list[dict[str, Any]],
    attempts: list[dict[str, Any]],
    *,
    exam_type: str = "数学二",
) -> dict[str, Any]:
    """Build evidence-backed learning analytics from the local attempt log.

    The result intentionally separates observed accuracy/score from the
    modelled mastery value.  An untouched concept therefore remains visible
    as "待训练" instead of being presented as a measured strength.
    """

    pool = [question for question in questions if question.get("exam_type") == exam_type]
    question_by_id = {question["id"]: question for question in pool}
    scoped_attempts = sorted(
        (
            attempt for attempt in attempts
            if attempt.get("question_id") in question_by_id
        ),
        key=lambda item: _attempt_datetime(item) or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    mastery = mastery_by_concept(scoped_attempts)

    def is_correct(attempt: dict[str, Any]) -> bool:
        return attempt.get("correct") == 1 or attempt.get("status") == "correct"

    def is_partial(attempt: dict[str, Any]) -> bool:
        return attempt.get("status") == "partial"

    def is_manual(attempt: dict[str, Any]) -> bool:
        return attempt.get("status") == "manual"

    def is_incorrect(attempt: dict[str, Any]) -> bool:
        return attempt.get("status") == "incorrect" or attempt.get("correct") == 0

    def average(values: list[float]) -> float | None:
        return round(sum(values) / len(values), 1) if values else None

    def percentage(numerator: float, denominator: float) -> float | None:
        return round(numerator / denominator * 100, 1) if denominator else None

    positive_durations = [
        float(attempt.get("duration_seconds") or 0)
        for attempt in scoped_attempts
        if float(attempt.get("duration_seconds") or 0) > 0
    ]
    total_score = sum(float(attempt.get("score") or 0) for attempt in scoped_attempts)
    total_max_score = sum(float(attempt.get("max_score") or 0) for attempt in scoped_attempts)
    correct_count = sum(1 for attempt in scoped_attempts if is_correct(attempt))
    partial_count = sum(1 for attempt in scoped_attempts if is_partial(attempt))
    manual_count = sum(1 for attempt in scoped_attempts if is_manual(attempt))
    incorrect_count = sum(1 for attempt in scoped_attempts if is_incorrect(attempt))
    attempted_question_ids = {attempt.get("question_id") for attempt in scoped_attempts}
    dated_attempts = [(attempt, _attempt_datetime(attempt)) for attempt in scoped_attempts]
    valid_attempt_dates = [value for _, value in dated_attempts if value is not None]
    reference_time = max(valid_attempt_dates, default=datetime.now(timezone.utc))
    recent_ten_attempts = scoped_attempts[:10]
    recent_7d_attempts = [
        attempt for attempt, value in dated_attempts
        if value is not None and reference_time - value <= timedelta(days=7)
    ]
    recent_30d_attempts = [
        attempt for attempt, value in dated_attempts
        if value is not None and reference_time - value <= timedelta(days=30)
    ]
    active_days_7d = len({
        value.date().isoformat()
        for attempt, value in dated_attempts
        if value is not None and reference_time - value <= timedelta(days=7)
    })
    active_days_30d = len({
        value.date().isoformat()
        for attempt, value in dated_attempts
        if value is not None and reference_time - value <= timedelta(days=30)
    })

    attempts_by_question: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for attempt in reversed(scoped_attempts):
        attempts_by_question[attempt.get("question_id")].append(attempt)
    first_attempts = [items[0] for items in attempts_by_question.values() if items]
    repeat_attempts = [attempt for items in attempts_by_question.values() for attempt in items[1:]]

    def accuracy_of(items: list[dict[str, Any]]) -> float | None:
        return percentage(sum(1 for item in items if is_correct(item)), len(items))

    def score_rate_of(items: list[dict[str, Any]]) -> float | None:
        ratios = [ratio for item in items if (ratio := _attempt_score_ratio(item)) is not None]
        return round(mean(ratios) * 100, 1) if ratios else None

    def average_duration_of(items: list[dict[str, Any]]) -> float | None:
        values = [float(item.get("duration_seconds") or 0) for item in items if float(item.get("duration_seconds") or 0) > 0]
        return round(mean(values), 1) if values else None

    def hint_rate_of(items: list[dict[str, Any]]) -> float | None:
        return percentage(sum(1 for item in items if int(item.get("hints_used") or 0) > 0), len(items))

    slow_attempt_count = sum(
        1 for attempt in scoped_attempts
        if float(attempt.get("duration_seconds") or 0) > _question_time_target(question_by_id.get(attempt.get("question_id"), {}))
    )
    positive_time_attempts = [attempt for attempt in scoped_attempts if float(attempt.get("duration_seconds") or 0) > 0]
    first_score_rate = score_rate_of(first_attempts)
    repeat_score_rate = score_rate_of(repeat_attempts)
    repeat_gain = round(repeat_score_rate - first_score_rate, 1) if first_score_rate is not None and repeat_score_rate is not None else None

    def attempt_row_base(
        *,
        question_count: int,
        type_attempts: list[dict[str, Any]],
        question_ids: set[str],
    ) -> dict[str, Any]:
        type_correct = sum(1 for attempt in type_attempts if is_correct(attempt))
        type_partial = sum(1 for attempt in type_attempts if is_partial(attempt))
        type_incorrect = sum(1 for attempt in type_attempts if is_incorrect(attempt))
        type_manual = sum(1 for attempt in type_attempts if is_manual(attempt))
        type_score = sum(float(attempt.get("score") or 0) for attempt in type_attempts)
        type_max_score = sum(float(attempt.get("max_score") or 0) for attempt in type_attempts)
        durations = [
            float(attempt.get("duration_seconds") or 0)
            for attempt in type_attempts
            if float(attempt.get("duration_seconds") or 0) > 0
        ]
        hints = [float(attempt.get("hints_used") or 0) for attempt in type_attempts]
        related_questions = [question_by_id.get(attempt.get("question_id"), {}) for attempt in type_attempts]
        difficulty_values = [float(question.get("difficulty")) for question in related_questions if question.get("difficulty") is not None]
        slow_count = sum(
            1 for attempt, question in zip(type_attempts, related_questions)
            if float(attempt.get("duration_seconds") or 0) > _question_time_target(question)
        )
        return {
            "question_count": question_count,
            "attempts": len(type_attempts),
            "attempted_question_count": len(question_ids),
            "unseen_question_count": max(0, question_count - len(question_ids)),
            "correct": type_correct,
            "partial": type_partial,
            "incorrect": type_incorrect,
            "manual": type_manual,
            "accuracy": percentage(type_correct, len(type_attempts)),
            "score": round(type_score, 1),
            "max_score": round(type_max_score, 1),
            "score_rate": percentage(type_score, type_max_score),
            "avg_seconds": average(durations),
            "avg_hints": average(hints),
            "avg_difficulty": round(mean(difficulty_values), 2) if difficulty_values else None,
            "slow_rate": percentage(slow_count, len(type_attempts)),
        }

    type_rows: list[dict[str, Any]] = []
    for question_type in QUESTION_TYPE_ORDER:
        type_questions = [
            question for question in pool
            if question.get("question_type") == question_type
        ]
        type_ids = {question["id"] for question in type_questions}
        type_attempts = [
            attempt for attempt in scoped_attempts
            if attempt.get("question_id") in type_ids
        ]
        row = {
            "question_type": question_type,
            **attempt_row_base(
                question_count=len(type_questions),
                type_attempts=type_attempts,
                question_ids={attempt.get("question_id") for attempt in type_attempts},
            ),
        }
        row["status"] = (
            "待训练" if not type_attempts
            else "需加强" if (row["accuracy"] or 0) < 60
            else "继续巩固"
        )
        type_rows.append(row)

    years = sorted({int(question["year"]) for question in pool})
    recent_years = years[-3:]
    recent_year_questions = [question for question in pool if int(question["year"]) in recent_years]
    recent_question_ids = {question["id"] for question in recent_year_questions}
    recent_year_attempts = [attempt for attempt in scoped_attempts if attempt.get("question_id") in recent_question_ids]
    difficulty_levels = sorted({int(question.get("difficulty") or 3) for question in recent_year_questions})
    difficulty_rows: list[dict[str, Any]] = []
    for difficulty_level in difficulty_levels:
        level_questions = [
            question for question in recent_year_questions
            if int(question.get("difficulty") or 3) == difficulty_level
        ]
        level_ids = {question["id"] for question in level_questions}
        level_attempts = [attempt for attempt in recent_year_attempts if attempt.get("question_id") in level_ids]
        difficulty_rows.append(
            {
                "difficulty": difficulty_level,
                "label": f"难度 {difficulty_level}",
                "question_count": len(level_questions),
                "attempts": len(level_attempts),
                "attempted_question_count": len({attempt.get("question_id") for attempt in level_attempts}),
                "accuracy": accuracy_of(level_attempts),
                "score_rate": score_rate_of(level_attempts),
                "avg_seconds": average_duration_of(level_attempts),
                "avg_hints": mean([float(attempt.get("hints_used") or 0) for attempt in level_attempts]) if level_attempts else None,
                "years": sorted({int(question["year"]) for question in level_questions}),
            }
        )

    recent_year_rows: list[dict[str, Any]] = []
    for year in recent_years:
        year_questions = [question for question in pool if int(question["year"]) == year]
        year_ids = {question["id"] for question in year_questions}
        year_attempts = [attempt for attempt in scoped_attempts if attempt.get("question_id") in year_ids]
        distribution = {
            str(level): sum(1 for question in year_questions if int(question.get("difficulty") or 3) == level)
            for level in sorted({int(question.get("difficulty") or 3) for question in year_questions})
        }
        recent_year_rows.append(
            {
                "year": year,
                "question_count": len(year_questions),
                "max_score": round(sum(float(question.get("points") or 0) for question in year_questions), 1),
                "average_difficulty": round(mean([float(question.get("difficulty") or 3) for question in year_questions]), 2) if year_questions else None,
                "difficulty_distribution": distribution,
                "attempts": len(year_attempts),
                "attempted_question_count": len({attempt.get("question_id") for attempt in year_attempts}),
                "accuracy": accuracy_of(year_attempts),
                "score_rate": score_rate_of(year_attempts),
                "avg_seconds": average_duration_of(year_attempts),
            }
        )

    concept_ids: set[str] = set()
    concept_question_counts: dict[str, int] = defaultdict(int)
    concept_question_ids: dict[str, set[str]] = defaultdict(set)
    for question in pool:
        for concept_id in question.get("concept_ids") or []:
            concept_ids.add(concept_id)
            concept_question_counts[concept_id] += 1
            concept_question_ids[concept_id].add(question["id"])
    for attempt in scoped_attempts:
        question = question_by_id.get(attempt.get("question_id"))
        for concept_id in (attempt.get("concepts") or question.get("concept_ids", []) if question else []):
            concept_ids.add(concept_id)

    concept_rows: list[dict[str, Any]] = []
    for concept_id in concept_ids:
        question_ids = concept_question_ids.get(concept_id, set())
        concept_attempts = [
            attempt for attempt in scoped_attempts
            if concept_id in (
                attempt.get("concepts")
                or question_by_id.get(attempt.get("question_id"), {}).get("concept_ids", [])
            )
        ]
        concept_recent_attempts = [
            attempt for attempt in recent_ten_attempts
            if concept_id in (
                attempt.get("concepts")
                or question_by_id.get(attempt.get("question_id"), {}).get("concept_ids", [])
            )
        ]
        base = attempt_row_base(
            question_count=concept_question_counts.get(concept_id, 0),
            type_attempts=concept_attempts,
            question_ids={attempt.get("question_id") for attempt in concept_attempts},
        )
        descriptor = concept_descriptor(concept_id)
        mastery_percent = round(mastery.get(concept_id, 0.22) * 100, 1)
        concept_rows.append(
            {
                "id": concept_id,
                "name": descriptor["name"],
                "subject": descriptor["subject"],
                "scope": descriptor["scope"],
                "scope_label": descriptor["scope_label"],
                "scope_note": descriptor["scope_note"],
                "mastery": mastery_percent,
                **base,
                "recent_accuracy": accuracy_of(concept_recent_attempts),
                "last_attempt_at": next(
                    (value.isoformat() for attempt, value in dated_attempts if attempt in concept_attempts and value is not None),
                    None,
                ),
                "status": (
                    "待训练" if not concept_attempts
                    else "需加强" if mastery_percent < 42 or (base["accuracy"] is not None and base["accuracy"] < 60)
                    else "巩固中" if mastery_percent < 70
                    else "稳定"
                ),
            }
        )
    concept_rows.sort(key=lambda row: (row["mastery"], -row["attempts"], row["name"]))

    measured_concepts = [row for row in concept_rows if row["attempts"] > 0]
    math2_measured_concepts = [row for row in measured_concepts if row["scope"] == "math2"]
    overall_mastery = (
        round(sum(row["mastery"] for row in math2_measured_concepts) / len(math2_measured_concepts), 1)
        if math2_measured_concepts
        else 0
    )
    weaknesses = sorted(
        measured_concepts,
        key=lambda row: (row["mastery"], row["accuracy"] if row["accuracy"] is not None else -1, -row["attempts"]),
    )[:5]
    strengths = sorted(
        measured_concepts,
        key=lambda row: (-row["mastery"], -(row["accuracy"] if row["accuracy"] is not None else -1), -row["attempts"]),
    )[:5]

    error_counts: dict[str, int] = defaultdict(int)
    for attempt in scoped_attempts:
        if is_correct(attempt):
            continue
        label = str(attempt.get("error_type") or "").strip()
        if not label:
            label = {
                "partial": "步骤不完整",
                "manual": "待自评",
                "incorrect": "答案错误",
            }.get(str(attempt.get("status") or ""), "未分类")
        error_counts[label] += 1
    error_total = sum(error_counts.values())
    error_types = [
        {"name": name, "count": count, "share": percentage(count, error_total)}
        for name, count in sorted(error_counts.items(), key=lambda item: (-item[1], item[0]))
    ]

    daily: dict[str, dict[str, Any]] = {}
    for attempt in scoped_attempts:
        day = str(attempt.get("created_at") or "")[:10] or "未知日期"
        bucket = daily.setdefault(day, {"date": day, "attempts": 0, "correct": 0, "score": 0.0, "max_score": 0.0, "seconds": 0})
        bucket["attempts"] += 1
        bucket["correct"] += int(is_correct(attempt))
        bucket["score"] += float(attempt.get("score") or 0)
        bucket["max_score"] += float(attempt.get("max_score") or 0)
        bucket["seconds"] += int(attempt.get("duration_seconds") or 0)
    daily_trend = []
    for day, bucket in sorted(daily.items())[-30:]:
        daily_trend.append(
            {
                **bucket,
                "score": round(bucket["score"], 1),
                "max_score": round(bucket["max_score"], 1),
                "accuracy": percentage(bucket["correct"], bucket["attempts"]),
                "score_rate": percentage(bucket["score"], bucket["max_score"]),
                "avg_seconds": round(bucket["seconds"] / bucket["attempts"], 1) if bucket["attempts"] else None,
            }
        )

    recent_attempts = []
    for attempt in scoped_attempts[:10]:
        question = question_by_id.get(attempt.get("question_id"), {})
        status = str(attempt.get("status") or "").strip()
        status_label = {
            "correct": "正确",
            "incorrect": "错误",
            "partial": "部分得分",
            "manual": "待自评",
        }.get(status, status or "未知")
        recent_attempts.append(
            {
                "id": attempt.get("id"),
                "question_id": attempt.get("question_id"),
                "year": question.get("year"),
                "number": question.get("number"),
                "question_type": question.get("question_type", "solution"),
                "status": status,
                "status_label": status_label,
                "score": round(float(attempt.get("score") or 0), 1),
                "max_score": round(float(attempt.get("max_score") or 0), 1),
                "duration_seconds": int(attempt.get("duration_seconds") or 0),
                "error_type": str(attempt.get("error_type") or ""),
                "created_at": attempt.get("created_at", ""),
            }
        )

    overview = {
        "attempts": len(scoped_attempts),
        "unique_questions": len(attempted_question_ids),
        "correct": correct_count,
        "partial": partial_count,
        "incorrect": incorrect_count,
        "manual": manual_count,
        "accuracy": percentage(correct_count, len(scoped_attempts)),
        "score": round(total_score, 1),
        "max_score": round(total_max_score, 1),
        "score_rate": percentage(total_score, total_max_score),
        "mastery": overall_mastery,
        "coverage_rate": percentage(len(attempted_question_ids), len(pool)),
        "unseen_questions": max(0, len(pool) - len(attempted_question_ids)),
        "avg_seconds": average(positive_durations),
        "avg_hints": average([float(attempt.get("hints_used") or 0) for attempt in scoped_attempts]),
        "recent_accuracy": accuracy_of(recent_ten_attempts),
        "recent_score_rate": score_rate_of(recent_ten_attempts),
        "active_days_7d": active_days_7d,
        "slow_rate": percentage(slow_attempt_count, len(positive_time_attempts)),
    }
    profile = {
        "recent_attempts": len(recent_ten_attempts),
        "recent_accuracy": accuracy_of(recent_ten_attempts),
        "recent_score_rate": score_rate_of(recent_ten_attempts),
        "recent_avg_seconds": average_duration_of(recent_ten_attempts),
        "attempts_7d": len(recent_7d_attempts),
        "active_days_7d": active_days_7d,
        "attempts_30d": len(recent_30d_attempts),
        "active_days_30d": active_days_30d,
        "repeat_questions": len([items for items in attempts_by_question.values() if len(items) > 1]),
        "first_pass_score_rate": first_score_rate,
        "repeat_score_rate": repeat_score_rate,
        "repeat_gain": repeat_gain,
        "avg_hints": average([float(attempt.get("hints_used") or 0) for attempt in scoped_attempts]),
        "hint_rate": hint_rate_of(scoped_attempts),
        "manual_rate": percentage(manual_count, len(scoped_attempts)),
        "slow_rate": percentage(slow_attempt_count, len(positive_time_attempts)),
        "timed_attempts": len(positive_time_attempts),
        "last_attempt_at": valid_attempt_dates[0].isoformat() if valid_attempt_dates else None,
        "data_confidence": (
            "暂无" if not scoped_attempts
            else "低" if len(scoped_attempts) < 10 or len(attempted_question_ids) < 8
            else "中" if len(scoped_attempts) < 40 or len(attempted_question_ids) < 25
            else "较高"
        ),
    }
    recommendations: list[str] = []
    type_labels = {"choice": "选择题", "fill": "填空题", "solution": "解答题"}
    if not scoped_attempts:
        recommendations.append("完成第一道真实题后，系统会按知识块、题型和耗时生成个性化分析。")
    else:
        if weaknesses:
            recommendations.append(f"优先复习“{weaknesses[0]['name']}”，当前掌握度 {weaknesses[0]['mastery']}%。")
        weakest_type = next((row for row in sorted(type_rows, key=lambda item: (item["accuracy"] is None, item["accuracy"] or 0)) if row["attempts"]), None)
        if weakest_type:
            label = type_labels.get(weakest_type["question_type"], weakest_type["question_type"])
            accuracy = weakest_type["accuracy"] if weakest_type["accuracy"] is not None else 0
            recommendations.append(f"题型训练先处理{label}，当前正确率 {accuracy}%。")
        if overview["coverage_rate"] is not None and overview["coverage_rate"] < 20:
            recommendations.append(f"当前只覆盖题库 {overview['coverage_rate']}%，先扩大真实作答覆盖面，再看长期掌握度。")
        if overview["avg_seconds"] and overview["avg_seconds"] > 300:
            recommendations.append("平均单题用时偏长，建议加入限时小组训练，先保证基础题的解题节奏。")
        if profile["recent_accuracy"] is not None and overview["accuracy"] is not None and profile["recent_accuracy"] + 12 < overview["accuracy"]:
            recommendations.append(f"近 {profile['recent_attempts']} 题正确率已回落到 {profile['recent_accuracy']}%，建议先复盘最近错题。")
        if profile["slow_rate"] is not None and profile["slow_rate"] >= 40:
            recommendations.append(f"有 {profile['slow_rate']}% 的有效计时作答超过建议用时，优先安排限时训练。")
        if profile["hint_rate"] is not None and profile["hint_rate"] >= 35:
            recommendations.append(f"提示依赖率为 {profile['hint_rate']}%，建议先独立思考再查看提示。")
        if profile["repeat_gain"] is not None and profile["repeat_gain"] < 0:
            recommendations.append("复做得分率暂未提升，建议把同类题间隔 1–3 天后再次练习。")
        if recent_years:
            recommendations.append(f"预测会参考最近三年（{'、'.join(str(year) for year in recent_years)}）的真实难度分布。")

    return {
        "exam_type": exam_type,
        "questions_available": len(pool),
        "attempts": len(scoped_attempts),
        "overview": overview,
        "profile": profile,
        "question_types": type_rows,
        "concepts": concept_rows,
        "weaknesses": weaknesses,
        "strengths": strengths,
        "error_types": error_types,
        "difficulty_breakdown": difficulty_rows,
        "recent_years": recent_years,
        "recent_year_breakdown": recent_year_rows,
        "daily_trend": daily_trend,
        "recent_attempts": recent_attempts,
        "recommendations": recommendations,
    }


def randomized_practice_questions(
    questions: list[dict[str, Any]], attempts: list[dict[str, Any]], *,
    exam_type: str = "数学二", concept_id: str, question_type: str,
    limit: int = 15,
) -> list[dict[str, Any]]:
    """Select a shuffled set while giving unseen questions first priority."""
    pool = [
        question for question in questions
        if question.get("exam_type") == exam_type
        and concept_id in question.get("concept_ids", [])
        and question.get("question_type") == question_type
    ]
    if not pool:
        return []
    attempted_ids = {attempt.get("question_id") for attempt in attempts}
    unseen = [question for question in pool if question["id"] not in attempted_ids]
    seen = [question for question in pool if question["id"] in attempted_ids]
    rng = random.SystemRandom()
    rng.shuffle(unseen)
    rng.shuffle(seen)
    selected = (unseen + seen)[: max(1, min(limit, len(pool)))]
    rng.shuffle(selected)
    return selected


def study_blocks(questions: list[dict[str, Any]], attempts: list[dict[str, Any]], limit: int = 6) -> list[dict[str, Any]]:
    summary = progress_summary(attempts, questions)
    blocks = []
    for concept in summary["concepts"][:limit]:
        selected = recommended_questions(questions, attempts, concept_id=concept["id"], limit=4)
        blocks.append(
            {
                "concept": concept,
                "reason": "掌握度较低，优先用基础题建立正确率，再加入迁移题。" if concept["mastery"] < 50 else "掌握度正在形成，安排间隔复习和变式题。",
                "questions": selected,
                "question_types": question_type_breakdown(questions, attempts, concept["id"]),
            }
        )
    return blocks


def forecast_score(questions: list[dict[str, Any]], attempts: list[dict[str, Any]], exam_type: str = "数学二") -> dict[str, Any]:
    pool = [question for question in questions if question.get("exam_type") == exam_type]
    if not pool:
        return {"available": False, "reason": "当前题库没有该科目数据。"}
    years = sorted({int(question["year"]) for question in pool})
    recent_years = years[-3:]
    target_year = recent_years[-1]
    papers = {
        year: [question for question in pool if int(question["year"]) == year]
        for year in recent_years
    }
    papers = {year: paper for year, paper in papers.items() if paper}
    recent_years = list(papers)
    recent_questions = [question for year in recent_years for question in papers[year]]
    question_by_id = {question["id"]: question for question in pool}
    scoped_attempts = sorted(
        (
            attempt for attempt in attempts
            if attempt.get("question_id") in question_by_id
        ),
        key=lambda item: _attempt_datetime(item) or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    mastery = mastery_by_concept(scoped_attempts)
    attempted_count = len(scoped_attempts)
    unique_attempted_count = len({attempt.get("question_id") for attempt in scoped_attempts})
    rng = random.Random(20260825 + attempted_count + sum(recent_years))
    paper_max_scores = {
        year: sum(float(question.get("points") or 0) for question in paper)
        for year, paper in papers.items()
    }
    # The national postgraduate mathematics paper is scored on a 150-point
    # scale. Some source files distribute points slightly differently, so each
    # recent paper is normalized to that common scale before aggregation.
    max_score = 150.0 if paper_max_scores else 0.0
    difficulty_center = mean([float(question.get("difficulty") or 3) for question in recent_questions]) if recent_questions else 3.0
    recent_question_ids = {question["id"] for question in recent_questions}
    calibration_attempts = [
        attempt for attempt in scoped_attempts
        if attempt.get("question_id") in recent_question_ids
    ] or scoped_attempts

    difficulty_stats: dict[int, dict[str, int]] = defaultdict(lambda: {"attempts": 0, "correct": 0})
    for attempt in calibration_attempts:
        question = question_by_id.get(attempt.get("question_id"), {})
        difficulty_level = int(question.get("difficulty") or 3)
        difficulty_stats[difficulty_level]["attempts"] += 1
        difficulty_stats[difficulty_level]["correct"] += int(
            attempt.get("correct") == 1 or attempt.get("status") == "correct"
        )
    prior_probability = 0.30
    global_attempts = sum(item["attempts"] for item in difficulty_stats.values())
    global_correct = sum(item["correct"] for item in difficulty_stats.values())
    global_smoothed = (global_correct + prior_probability * 4) / (global_attempts + 4) if global_attempts else prior_probability
    difficulty_adjustments: dict[int, float] = {}
    difficulty_calibration = []
    for difficulty_level in sorted({int(question.get("difficulty") or 3) for question in recent_questions}):
        level_questions = [
            question for question in recent_questions
            if int(question.get("difficulty") or 3) == difficulty_level
        ]
        stats = difficulty_stats[difficulty_level]
        smoothed_accuracy = (stats["correct"] + prior_probability * 4) / (stats["attempts"] + 4)
        adjustment = max(-0.06, min(0.06, (smoothed_accuracy - global_smoothed) * 0.25))
        difficulty_adjustments[difficulty_level] = adjustment
        difficulty_calibration.append(
            {
                "difficulty": difficulty_level,
                "label": f"难度 {difficulty_level}",
                "question_count": len(level_questions),
                "attempts": stats["attempts"],
                "accuracy": round(smoothed_accuracy * 100, 1) if stats["attempts"] else None,
                "adjustment": round(adjustment * 100, 1),
                "years": sorted({int(question["year"]) for question in level_questions}),
            }
        )

    def probability_for(question: dict[str, Any]) -> float:
        values = [mastery.get(item, 0.22) for item in question.get("concept_ids") or []]
        state = mean(values) if values else 0.22
        # Keep the conservative no-data anchor, then adjust it with the actual
        # difficulty label from the recent three papers and the learner's
        # observed performance at that difficulty.
        probability = prior_probability + (state - 0.22) * (0.82 - prior_probability) / (1.0 - 0.22)
        difficulty_level = int(question.get("difficulty") or 3)
        probability += (difficulty_center - difficulty_level) * 0.07
        probability += difficulty_adjustments.get(difficulty_level, 0.0)
        return max(0.05, min(0.90, probability))

    if not scoped_attempts:
        return {
            "available": True,
            "exam_type": exam_type,
            "paper_year": target_year,
            "paper_years": recent_years,
            "paper_questions": len(papers.get(target_year, [])),
            "evaluation_questions": sum(len(paper) for paper in papers.values()),
            "max_score": max_score,
            "p10": 0.0,
            "p50": 0.0,
            "p90": 0.0,
            "confidence": "暂无",
            "attempts_used": 0,
            "recent_difficulty_mean": round(difficulty_center, 2),
            "difficulty_calibration": difficulty_calibration,
            "note": f"尚无真实作答记录，初始预估分按 0 分显示。完成练习后，将用最近三年（{'、'.join(str(year) for year in recent_years)}）真题的难度分布校准；人群中约三成考生能超过 50 分，系统不会把这个比例直接当成你的个人成绩。",
        }
    scores: list[float] = []
    for _ in range(800):
        paper_scores = []
        for year, paper in papers.items():
            score = sum(
                float(question.get("points") or 0)
                for question in paper
                if rng.random() < probability_for(question)
            )
            paper_max = paper_max_scores[year]
            paper_scores.append(score / paper_max * max_score if paper_max else 0.0)
        scores.append(mean(paper_scores) if paper_scores else 0.0)
    scores.sort()
    p10 = round(scores[int(len(scores) * 0.10)], 1)
    p50 = round(scores[int(len(scores) * 0.50)], 1)
    p90 = round(scores[int(len(scores) * 0.90)], 1)
    confidence = "低" if attempted_count < 10 or unique_attempted_count < 8 else ("中" if attempted_count < 40 or unique_attempted_count < 25 else "较高")
    return {
        "available": True,
        "exam_type": exam_type,
        "paper_year": target_year,
        "paper_years": recent_years,
        "paper_questions": len(papers.get(target_year, [])),
        "evaluation_questions": sum(len(paper) for paper in papers.values()),
        "max_score": max_score,
        "p10": p10,
        "p50": p50,
        "p90": p90,
        "confidence": confidence,
        "attempts_used": attempted_count,
        "recent_difficulty_mean": round(difficulty_center, 2),
        "difficulty_calibration": difficulty_calibration,
        "note": f"这是基于当前掌握度、最近三年（{'、'.join(str(year) for year in recent_years)}）真实题目难度的模拟区间，不等同于真实考试承诺；低样本阶段仍按约三成考生超过 50 分的保守人群基线校准，完成更多带计时的模拟考后会更可靠。",
    }
