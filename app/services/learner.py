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
from app.services.workbench import SUBTYPES_BY_ID, question_subtype_ids

QUESTION_TYPE_ORDER = ("choice", "fill", "solution")
QUESTION_TIME_TARGETS = {"choice": 150, "fill": 180, "solution": 600}
ATTEMPT_STATUS_LABELS = {
    "correct": "正确",
    "incorrect": "错误",
    "partial": "部分得分",
    "manual": "待自评",
}

# Public Math II statistics are sparse and do not provide a national,
# all-candidate, year-by-year microdata table.  Keep the observed sources
# separate from admission-candidate score tables: the latter are not valid
# population priors for this forecast.
MATH2_ALL_CANDIDATE_MEAN_SCORES: dict[int, float] = {
    2012: 72.30,
    2013: 85.80,
    2014: 77.60,
    2015: 77.40,
    2016: 60.60,
    2017: 81.70,
    2018: 60.10,
    2019: 71.87,
}
MATH2_ALL_CANDIDATE_TAIL_OBSERVATIONS: dict[int, dict[int, float]] = {
    # 2018 reports the directly observed share at or above 90 points.
    2018: {90: 0.1500},
    # 2019 reports a 137,200-person sample and the high-score tail points.
    2019: {90: 0.1500, 105: 0.0530, 120: 0.0120, 135: 0.0009},
}
MATH2_ALL_CANDIDATE_DEFAULT_YEAR = 2019
MATH2_SCORE_TAIL_THRESHOLDS = (90, 105, 120, 135)
MATH2_SCORE_BANDS = (
    (0.0, 60.0),
    (60.0, 75.0),
    (75.0, 90.0),
    (90.0, 105.0),
    (105.0, 120.0),
    (120.0, 135.0),
    (135.0, 150.0),
)
MATH2_LOWER_TAIL_RATIO = 0.60

# These are national funnel estimates, not Math II score percentages.  They
# are exposed as a scope note so callers do not confuse admission rates with
# the score distribution used by the forecast.
MATH2_PUBLIC_FUNNEL_REFERENCE = {
    "national_line_rate": "约 20%-30%（全国公开汇总估算，年度与分母口径有差异）",
    "admission_rate": "约 20%（公开汇总约 14%-24%，含推免/统考口径差异）",
    "scope_note": "全国考研报名/参考者口径，不是数学二单科分布；仅用于解释群体漏斗，不直接换算数学分数。",
}

# Relative item priors.  The paper-level offset below aligns them to the
# public score-band anchor for that paper year while preserving difficulty
# differences between questions.
MATH2_DIFFICULTY_PRIORS = {1: 0.82, 2: 0.74, 3: 0.60, 4: 0.45, 5: 0.30}
MATH2_FORECAST_PRIOR_STRENGTH = 36.0
MATH2_FORECAST_CONCEPT_SATURATION = 8.0
MATH2_FORECAST_CONCEPT_PRIOR_STRENGTH = 12.0
MATH2_FORECAST_MAX_PERSONAL_SHIFT = 0.24


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


def question_attempt_summaries(attempts: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Aggregate every submitted attempt by question for UI and analytics.

    ``attempts`` is deliberately not de-duplicated: a second or third try is
    evidence too. The returned ``correct`` value is the number of correct
    submissions, while callers can use the summary keys for unique coverage.
    """
    summaries: dict[str, dict[str, Any]] = {}
    latest_datetimes: dict[str, datetime | None] = {}
    for attempt in attempts:
        question_id = str(attempt.get("question_id") or "").strip()
        if not question_id:
            continue
        status = str(attempt.get("status") or "").strip() or "manual"
        item = summaries.setdefault(
            question_id,
            {
                "attempted": True,
                "attempts": 0,
                "correct": 0,
                "incorrect": 0,
                "partial": 0,
                "manual": 0,
                "accuracy": None,
                "last_status": "",
                "last_status_label": "",
                "last_score": 0,
                "last_max_score": 0,
                "last_attempt_at": None,
            },
        )
        item["attempts"] += 1
        is_correct = attempt.get("correct") == 1 or status == "correct"
        if is_correct:
            item["correct"] += 1
        elif status in {"incorrect", "partial", "manual"}:
            item[status] += 1
        else:
            item["manual"] += 1
        current_datetime = _attempt_datetime(attempt)
        previous_datetime = latest_datetimes.get(question_id)
        # Database queries are newest-first today, but comparing timestamps
        # keeps this helper correct for imported/test data as well.
        if previous_datetime is None or (current_datetime is not None and current_datetime >= previous_datetime):
            latest_datetimes[question_id] = current_datetime
            item["last_status"] = status
            item["last_status_label"] = ATTEMPT_STATUS_LABELS.get(status, status or "未知")
            item["last_score"] = round(float(attempt.get("score") or 0), 1)
            item["last_max_score"] = round(float(attempt.get("max_score") or 0), 1)
            item["last_attempt_at"] = attempt.get("created_at") or None
        item["accuracy"] = round(item["correct"] / item["attempts"] * 100, 1)
    return summaries


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


def _rebind_attempt_concepts(
    attempts: list[dict[str, Any]], questions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Apply the current question classification to historical attempts.

    Attempts keep a snapshot of the concepts that existed when they were
    submitted.  A user correction is intentionally a per-user overlay, so
    analytics must rebind the snapshot through the effective question before
    calculating mastery; otherwise the correction would affect filtering but
    not the learner profile.
    """
    question_by_id = {str(question.get("id")): question for question in questions}
    rebound: list[dict[str, Any]] = []
    for attempt in attempts:
        item = dict(attempt)
        question = question_by_id.get(str(attempt.get("question_id")))
        if question is not None and question.get("concept_ids") is not None:
            item["concepts"] = list(question.get("concept_ids") or [])
        rebound.append(item)
    return rebound


def progress_summary(attempts: list[dict[str, Any]], questions: list[dict[str, Any]]) -> dict[str, Any]:
    attempts = _rebind_attempt_concepts(attempts, questions)
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
    attempts = _rebind_attempt_concepts(attempts, questions)
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


def subtype_breakdown(
    questions: list[dict[str, Any]], attempts: list[dict[str, Any]], concept_id: str,
) -> list[dict[str, Any]]:
    """Build the selectable, concrete training rows for one Math II block."""
    concept_questions = [
        question for question in questions
        if concept_id in question.get("concept_ids", [])
    ]
    attempt_summaries = question_attempt_summaries(attempts)
    rows: list[dict[str, Any]] = []
    for subtype_id, subtype in SUBTYPES_BY_ID.items():
        if subtype.get("concept_id") != concept_id:
            continue
        matched = [question for question in concept_questions if subtype_id in question_subtype_ids(question)]
        if not matched:
            continue
        question_ids = {question["id"] for question in matched}
        subtype_attempts = [attempt for attempt in attempts if attempt.get("question_id") in question_ids]
        attempted_question_ids = {question_id for question_id in question_ids if question_id in attempt_summaries}
        correct = sum(
            1 for attempt in subtype_attempts
            if attempt.get("correct") == 1 or attempt.get("status") == "correct"
        )
        accuracy = round(correct / len(subtype_attempts) * 100, 1) if subtype_attempts else None
        format_counts = {
            question_type: sum(1 for question in matched if question.get("question_type") == question_type)
            for question_type in QUESTION_TYPE_ORDER
        }
        rows.append({
            "concept_id": concept_id,
            "id": subtype_id,
            "name": subtype.get("name", subtype_id),
            "summary": subtype.get("summary", ""),
            "question_count": len(matched),
            "attempted_question_count": len(attempted_question_ids),
            "unseen_question_count": max(0, len(matched) - len(attempted_question_ids)),
            "attempts": len(subtype_attempts),
            "correct": correct,
            "accuracy": accuracy,
            "question_format_counts": format_counts,
            "status": "待训练" if not subtype_attempts else ("需加强" if (accuracy or 0) < 60 else "继续巩固"),
        })
    rows.sort(key=lambda row: (row["accuracy"] is not None, row["accuracy"] if row["accuracy"] is not None else -1, row["name"]))
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

    attempts = _rebind_attempt_concepts(attempts, questions)
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

    subtype_rows: list[dict[str, Any]] = []
    for concept_id in CONCEPT_META:
        subtype_rows.extend(subtype_breakdown(pool, scoped_attempts, concept_id))

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
        "subtypes": subtype_rows,
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
    exam_type: str = "数学二", concept_id: str, question_type: str | None = None,
    subtype_id: str | None = None,
    limit: int = 15,
    exclude_question_ids: set[str] | list[str] | tuple[str, ...] | None = None,
) -> list[dict[str, Any]]:
    """Select a shuffled set while prioritizing unseen and refreshed questions.

    A refresh excludes the currently displayed set first. If the subtype has
    fewer remaining questions than the requested count, the selector fills
    from the old set so a small real题库 still produces a usable session; it
    never fabricates or duplicates questions.
    """
    pool = [
        question for question in questions
        if question.get("exam_type") == exam_type
        and concept_id in question.get("concept_ids", [])
        and (not question_type or question.get("question_type") == question_type)
        and (not subtype_id or subtype_id in question_subtype_ids(question))
    ]
    if not pool:
        return []
    desired = max(1, min(limit, len(pool)))
    excluded = {str(item) for item in (exclude_question_ids or ()) if str(item)}
    preferred_pool = [question for question in pool if question["id"] not in excluded]
    fallback_pool = [question for question in pool if question["id"] in excluded]
    if not preferred_pool:
        preferred_pool = list(pool)
        fallback_pool = []
    attempted_ids = {attempt.get("question_id") for attempt in attempts}
    rng = random.SystemRandom()

    def prioritized(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        unseen = [question for question in items if question["id"] not in attempted_ids]
        seen = [question for question in items if question["id"] in attempted_ids]
        rng.shuffle(unseen)
        rng.shuffle(seen)
        return unseen + seen

    selected = prioritized(preferred_pool)[:desired]
    if len(selected) < desired:
        selected.extend(prioritized(fallback_pool)[: desired - len(selected)])
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
                "subtypes": subtype_breakdown(questions, attempts, concept["id"]),
            }
        )
    return blocks


def _math2_reference_year(year: int) -> int:
    """Use the latest observed all-candidate tail year without future leakage."""
    known_years = sorted(MATH2_ALL_CANDIDATE_TAIL_OBSERVATIONS)
    try:
        normalized_year = int(year)
    except (TypeError, ValueError):
        normalized_year = MATH2_ALL_CANDIDATE_DEFAULT_YEAR
    previous_years = [item for item in known_years if item <= normalized_year]
    return max(previous_years) if previous_years else known_years[0]


def _math2_reference_mean(year: int) -> float:
    """Return the latest public all-candidate mean available for this year."""
    known_years = sorted(MATH2_ALL_CANDIDATE_MEAN_SCORES)
    try:
        normalized_year = int(year)
    except (TypeError, ValueError):
        normalized_year = MATH2_ALL_CANDIDATE_DEFAULT_YEAR
    previous_years = [item for item in known_years if item <= normalized_year]
    reference_year = max(previous_years) if previous_years else known_years[0]
    return MATH2_ALL_CANDIDATE_MEAN_SCORES[reference_year]


def _math2_score_anchor_distribution(
    tails: dict[int, float], target_mean: float,
) -> dict[int, float]:
    """Build an all-candidate prior from observed tails and the public mean.

    The public source does not publish every lower score cut.  The lower two
    cuts are therefore solved to match the observed mean, while the observed
    high-score tails are retained.  Missing tail points use the complete 2019
    shape only as a conservative shape reference, never as admission data.
    """
    observed_tail_thresholds = MATH2_SCORE_TAIL_THRESHOLDS
    fallback_tails = MATH2_ALL_CANDIDATE_TAIL_OBSERVATIONS[MATH2_ALL_CANDIDATE_DEFAULT_YEAR]
    tail_values = []
    previous_tail = 1.0
    for threshold in observed_tail_thresholds:
        value = tails.get(threshold, fallback_tails.get(threshold, 0.0))
        value = max(0.0, min(previous_tail, min(1.0, float(value))))
        tail_values.append(value)
        previous_tail = value

    p90, p105, p120, p135 = tail_values
    lower_ratio = MATH2_LOWER_TAIL_RATIO
    midpoints = [(start + end) / 2 for start, end in MATH2_SCORE_BANDS]
    high_masses = [p90 - p105, p105 - p120, p120 - p135, p135]
    high_mean = sum(midpoint * mass for midpoint, mass in zip(midpoints[3:], high_masses))
    # Let P(score >= 75) = lower_ratio * P(score >= 60), then solve P(score >= 60)
    # so the resulting piecewise distribution matches the public mean.
    coefficient = (midpoints[1] - midpoints[0]) + lower_ratio * (midpoints[2] - midpoints[1])
    constant = midpoints[0] - midpoints[2] * p90 + high_mean
    p60 = (float(target_mean) - constant) / coefficient if coefficient else 0.0
    p60 = max(p90 / lower_ratio, min(1.0, p60))
    p75 = lower_ratio * p60
    tail_values = [p60, p75, p90, p105, p120, p135]
    masses = [
        1.0 - tail_values[0],
        tail_values[0] - tail_values[1],
        tail_values[1] - tail_values[2],
        tail_values[2] - tail_values[3],
        tail_values[3] - tail_values[4],
        tail_values[4] - tail_values[5],
        tail_values[5],
    ]
    distribution: dict[int, float] = defaultdict(float)
    for (start, end), mass in zip(MATH2_SCORE_BANDS, masses):
        if mass <= 0:
            continue
        # Half-point granularity keeps the interval informative without
        # pretending that the public source contains exact scores.
        steps = int(round((end - start) * 2))
        points = [start + index * 0.5 for index in range(steps)]
        if start == MATH2_SCORE_BANDS[-1][0]:
            points.append(end)
        for point in points:
            distribution[int(round(point * 10))] += mass / len(points)
    total = sum(distribution.values()) or 1.0
    return {score: mass / total for score, mass in distribution.items()}


def _distribution_quantile(distribution: dict[int, float], quantile: float) -> float:
    if not distribution:
        return 0.0
    target = max(0.0, min(1.0, float(quantile)))
    accumulated = 0.0
    total = sum(distribution.values()) or 1.0
    for score, mass in sorted(distribution.items()):
        accumulated += mass / total
        if accumulated >= target:
            return score / 10.0
    return max(distribution) / 10.0


def _distribution_mean(distribution: dict[int, float]) -> float:
    total = sum(distribution.values()) or 1.0
    return sum(score * mass for score, mass in distribution.items()) / total / 10.0


def _mix_distributions(
    population: dict[int, float], personal: dict[int, float], personal_weight: float,
) -> dict[int, float]:
    weight = max(0.0, min(1.0, float(personal_weight)))
    mixed: dict[int, float] = defaultdict(float)
    for score, mass in population.items():
        mixed[score] += mass * (1.0 - weight)
    for score, mass in personal.items():
        mixed[score] += mass * weight
    total = sum(mixed.values()) or 1.0
    return {score: mass / total for score, mass in mixed.items()}


def _math2_population_reference() -> dict[str, Any]:
    return {
        "mean_score_years": sorted(MATH2_ALL_CANDIDATE_MEAN_SCORES),
        "mean_scores": {
            str(year): round(score, 2)
            for year, score in sorted(MATH2_ALL_CANDIDATE_MEAN_SCORES.items())
        },
        "score_tail_observations_percent": {
            str(year): {
                str(threshold): round(value * 100, 2)
                for threshold, value in sorted(observations.items())
            }
            for year, observations in sorted(MATH2_ALL_CANDIDATE_TAIL_OBSERVATIONS.items())
        },
        "anchor_year": MATH2_ALL_CANDIDATE_DEFAULT_YEAR,
        "funnel_reference": MATH2_PUBLIC_FUNNEL_REFERENCE,
        "source_note": "数学二全体考生/大样本公开均分与尾部观测；不使用录取考生分数段，也不是持续发布的官方逐分微观分布。",
    }


def _difficulty_prior_probability(question: dict[str, Any]) -> float:
    try:
        difficulty = int(question.get("difficulty") or 3)
    except (TypeError, ValueError):
        difficulty = 3
    return MATH2_DIFFICULTY_PRIORS.get(difficulty, MATH2_DIFFICULTY_PRIORS[3])


def forecast_score(questions: list[dict[str, Any]], attempts: list[dict[str, Any]], exam_type: str = "数学二") -> dict[str, Any]:
    """Return a conservative score interval from hierarchical question evidence.

    The forecast has three deliberate safeguards against local overconfidence:

    * repeated attempts are collapsed to one question-level observation;
    * evidence is shrunk by unique-question count and knowledge-block coverage;
    * the personalized distribution is mixed with public Math II score bands.

    This keeps a few correct answers in one block from being projected onto a
    whole paper.  The API exposes an interval rather than a single score.
    """
    pool = [question for question in questions if question.get("exam_type") == exam_type]
    if not pool:
        return {"available": False, "reason": "当前题库没有该科目数据。"}
    years = sorted({int(question["year"]) for question in pool})
    recent_years = years[-3:]
    papers = {
        year: [question for question in pool if int(question["year"]) == year]
        for year in recent_years
    }
    papers = {year: paper for year, paper in papers.items() if paper}
    recent_years = list(papers)
    target_year = recent_years[-1]
    recent_questions = [question for paper in papers.values() for question in paper]
    question_by_id = {question["id"]: question for question in pool}
    scoped_attempts = sorted(
        (attempt for attempt in attempts if attempt.get("question_id") in question_by_id),
        key=lambda item: _attempt_datetime(item) or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    attempted_count = len(scoped_attempts)
    paper_max_scores = {
        year: sum(float(question.get("points") or 0) for question in paper)
        for year, paper in papers.items()
    }
    max_score = 150.0 if paper_max_scores else 0.0
    difficulty_center = mean(
        [float(question.get("difficulty") or 3) for question in recent_questions]
    ) if recent_questions else 3.0
    recent_question_ids = {question["id"] for question in recent_questions}
    calibration_attempts = [
        attempt for attempt in scoped_attempts if attempt.get("question_id") in recent_question_ids
    ] or scoped_attempts

    def observed_value(attempt: dict[str, Any]) -> float:
        ratio = _attempt_score_ratio(attempt)
        if ratio is not None:
            return ratio
        if attempt.get("correct") == 1 or attempt.get("status") == "correct":
            return 1.0
        return 0.0

    # Build one weighted observation per question.  A repeat is useful as
    # retention evidence, but it cannot count like a new question forever.
    attempts_by_question: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for attempt in calibration_attempts:
        question_id = str(attempt.get("question_id") or "")
        if question_id in question_by_id:
            attempts_by_question[question_id].append(attempt)

    evidence_by_question: dict[str, dict[str, Any]] = {}
    concept_evidence: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for question_id, question_attempts in attempts_by_question.items():
        ordered = sorted(
            question_attempts,
            key=lambda item: _attempt_datetime(item) or datetime.min.replace(tzinfo=timezone.utc),
        )
        weighted_values = []
        for index, attempt in enumerate(reversed(ordered)):
            weight = 1.0 / (1.0 + index * 0.75)
            weighted_values.append((observed_value(attempt), weight))
        total_weight = sum(weight for _, weight in weighted_values) or 1.0
        value = sum(value * weight for value, weight in weighted_values) / total_weight
        question = question_by_id[question_id]
        prior = _difficulty_prior_probability(question)
        item = {
            "question_id": question_id,
            "value": value,
            "prior": prior,
            "residual": value - prior,
            "weight": min(1.5, 1.0 + (len(ordered) - 1) * 0.20),
            "difficulty": int(question.get("difficulty") or 3),
            "concept_ids": list(question.get("concept_ids") or []),
            "attempts": len(ordered),
        }
        evidence_by_question[question_id] = item
        concepts = item["concept_ids"]
        if concepts:
            concept_weight = item["weight"] / len(concepts)
            for concept_id in concepts:
                concept_evidence[concept_id].append((item["residual"], concept_weight))

    unique_attempted_count = len(evidence_by_question)
    effective_unique_count = sum(item["weight"] for item in evidence_by_question.values())
    unique_concepts = set(concept_evidence)
    concept_coverage = min(1.0, len(unique_concepts) / MATH2_FORECAST_CONCEPT_SATURATION)
    coverage_factor = 0.25 + 0.75 * concept_coverage
    sample_weight = effective_unique_count / (effective_unique_count + MATH2_FORECAST_PRIOR_STRENGTH)
    personalization_weight = min(0.82, sample_weight * coverage_factor)

    def weighted_signal(items: list[tuple[float, float]]) -> float:
        total = sum(weight for _, weight in items)
        return sum(value * weight for value, weight in items) / total if total else 0.0

    global_signal = weighted_signal([
        (item["residual"], item["weight"])
        for item in evidence_by_question.values()
    ])
    global_shift = global_signal * personalization_weight

    concept_shifts: dict[str, float] = {}
    for concept_id, items in concept_evidence.items():
        concept_signal = weighted_signal(items)
        concept_weight = sum(weight for _, weight in items)
        concept_reliability = concept_weight / (concept_weight + MATH2_FORECAST_CONCEPT_PRIOR_STRENGTH)
        concept_shifts[concept_id] = concept_signal * concept_reliability * personalization_weight

    difficulty_levels = sorted({int(question.get("difficulty") or 3) for question in recent_questions})
    difficulty_calibration = []
    for difficulty_level in difficulty_levels:
        level_questions = [
            question for question in recent_questions
            if int(question.get("difficulty") or 3) == difficulty_level
        ]
        level_evidence = [
            item for item in evidence_by_question.values()
            if item["difficulty"] == difficulty_level
        ]
        observed = weighted_signal([
            (item["value"], item["weight"])
            for item in level_evidence
        ]) if level_evidence else None
        prior = MATH2_DIFFICULTY_PRIORS.get(difficulty_level, MATH2_DIFFICULTY_PRIORS[3])
        difficulty_calibration.append({
            "difficulty": difficulty_level,
            "label": f"难度 {difficulty_level}",
            "question_count": len(level_questions),
            "attempts": sum(item["attempts"] for item in level_evidence),
            "accuracy": round(observed * 100, 1) if observed is not None else None,
            "adjustment": round((observed - prior) * 100, 1) if observed is not None else 0.0,
            "years": sorted({int(question["year"]) for question in level_questions}),
        })

    anchor_distributions: dict[int, dict[int, float]] = {}
    anchor_means: dict[int, float] = {}
    if exam_type == "数学二":
        for year in recent_years:
            reference_year = _math2_reference_year(year)
            anchor = _math2_score_anchor_distribution(
                MATH2_ALL_CANDIDATE_TAIL_OBSERVATIONS[reference_year],
                _math2_reference_mean(year),
            )
            anchor_distributions[year] = anchor
            anchor_means[year] = _distribution_mean(anchor)
    else:
        for year in recent_years:
            paper_max = paper_max_scores.get(year, 0.0)
            anchor_distributions[year] = {}
            anchor_means[year] = sum(
                float(question.get("points") or 0) * _difficulty_prior_probability(question)
                for question in papers[year]
            ) / paper_max * max_score if paper_max else 0.0

    def paper_baseline_offset(paper: list[dict[str, Any]], paper_max: float, anchor_mean: float) -> float:
        if paper_max <= 0:
            return 0.0
        raw_score = sum(
            float(question.get("points") or 0) * _difficulty_prior_probability(question)
            for question in paper
        ) / paper_max * max_score
        target_score = anchor_mean
        return max(-0.12, min(0.12, (target_score - raw_score) / max_score))

    paper_offsets = {
        year: paper_baseline_offset(papers[year], paper_max_scores[year], anchor_means[year])
        for year in recent_years
        if paper_max_scores.get(year)
    }

    def probability_for(question: dict[str, Any], paper_year: int) -> float:
        base_probability = max(
            0.05,
            min(0.95, _difficulty_prior_probability(question) + paper_offsets.get(paper_year, 0.0)),
        )
        shift = 0.65 * global_shift
        local_shifts = [concept_shifts[concept_id] for concept_id in question.get("concept_ids") or [] if concept_id in concept_shifts]
        if local_shifts:
            shift += 0.35 * sum(local_shifts) / len(local_shifts)
        direct = evidence_by_question.get(question["id"])
        if direct:
            direct_weight = min(0.25, direct["weight"] / (direct["weight"] + 8.0))
            shift += direct["residual"] * direct_weight
        shift = max(-MATH2_FORECAST_MAX_PERSONAL_SHIFT, min(MATH2_FORECAST_MAX_PERSONAL_SHIFT, shift))
        return max(0.02, min(0.95, base_probability + shift))

    def paper_distribution(paper: list[dict[str, Any]], paper_max: float, paper_year: int) -> dict[int, float]:
        # Exact convolution in tenths of a point preserves source point values
        # after normalizing each historical paper to the 150-point scale.
        distribution: dict[int, float] = {0: 1.0}
        for question in paper:
            increment = int(round(float(question.get("points") or 0) / paper_max * max_score * 10)) if paper_max else 0
            probability = probability_for(question, paper_year)
            next_distribution: dict[int, float] = defaultdict(float)
            for score, mass in distribution.items():
                next_distribution[score] += mass * (1.0 - probability)
                next_distribution[score + increment] += mass * probability
            distribution = dict(next_distribution)
        total_mass = sum(distribution.values()) or 1.0
        return {score: mass / total_mass for score, mass in distribution.items()}

    distributions = []
    for year in recent_years:
        if not paper_max_scores.get(year):
            continue
        personal = paper_distribution(papers[year], paper_max_scores[year], year)
        population = anchor_distributions[year]
        distributions.append(
            _mix_distributions(population, personal, personalization_weight)
            if population else personal
        )

    mixture: dict[int, float] = defaultdict(float)
    if distributions:
        paper_weight = 1.0 / len(distributions)
        for distribution in distributions:
            for score, mass in distribution.items():
                mixture[score] += mass * paper_weight
    normalized_mixture = dict(mixture)
    score_range = {
        "low": round(_distribution_quantile(normalized_mixture, 0.20), 1) if normalized_mixture else 0.0,
        "high": round(_distribution_quantile(normalized_mixture, 0.80), 1) if normalized_mixture else 0.0,
        "coverage": "中心 60%",
    }
    outer_range = {
        "low": round(_distribution_quantile(normalized_mixture, 0.10), 1) if normalized_mixture else 0.0,
        "high": round(_distribution_quantile(normalized_mixture, 0.90), 1) if normalized_mixture else 0.0,
        "coverage": "宽参考边界",
    }
    population_reference = _math2_population_reference() if exam_type == "数学二" else None

    if not scoped_attempts:
        return {
            "available": True,
            "exam_type": exam_type,
            "paper_year": target_year,
            "paper_years": recent_years,
            "paper_questions": len(papers.get(target_year, [])),
            "evaluation_questions": sum(len(paper) for paper in papers.values()),
            "max_score": max_score,
            "score_range": {"low": 0.0, "high": 0.0, "coverage": "等待真实作答"},
            "outer_range": {"low": 0.0, "high": 0.0, "coverage": "等待真实作答"},
            "confidence": "暂无",
            "attempts_used": 0,
            "unique_questions_used": 0,
            "concepts_used": 0,
            "personalization_weight": 0.0,
            "recent_difficulty_mean": round(difficulty_center, 2),
            "difficulty_calibration": difficulty_calibration,
            "interval_method": "无作答数据时不推断个人区间，初始值固定为 0 分",
            "population_reference": population_reference,
            "note": f"尚无真实作答记录，暂不推断个人得分区间。完成练习后，将按题目去重、知识块覆盖和难度分层，结合最近三年（{'、'.join(str(year) for year in recent_years)}）真题与全体考生历史均分/高分尾部观测缓慢更新。",
        }

    confidence = "低" if unique_attempted_count < 12 or len(unique_concepts) < 3 else (
        "中" if unique_attempted_count < 35 or len(unique_concepts) < 7 else "较高"
    )
    return {
        "available": True,
        "exam_type": exam_type,
        "paper_year": target_year,
        "paper_years": recent_years,
        "paper_questions": len(papers.get(target_year, [])),
        "evaluation_questions": sum(len(paper) for paper in papers.values()),
        "max_score": max_score,
        "score_range": score_range,
        "outer_range": outer_range,
        "confidence": confidence,
        "attempts_used": attempted_count,
        "unique_questions_used": unique_attempted_count,
        "concepts_used": len(unique_concepts),
        "personalization_weight": round(personalization_weight, 4),
        "recent_difficulty_mean": round(difficulty_center, 2),
        "difficulty_calibration": difficulty_calibration,
        "interval_method": "公共分段先验 + 题目去重 + 知识块覆盖收缩 + 难度分层精确离散分布，展示中心 60% 区间",
        "population_reference": population_reference,
        "note": f"区间基于当前作答证据与最近三年（{'、'.join(str(year) for year in recent_years)}）真实题目；少量同一知识块的作答只产生很小更新，必须扩大题目和知识块覆盖后区间才会逐步移动。全体考生历史均分与高分尾部观测用于校准群体边界，不代表你的个人成绩承诺。",
    }
