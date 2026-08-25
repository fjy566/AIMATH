from __future__ import annotations

import random
from collections import defaultdict
from statistics import mean
from typing import Any

from app.services.concepts import (
    CONCEPT_META,
)

QUESTION_TYPE_ORDER = ("choice", "fill", "solution")


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
    attempts_by_question: dict[str, int] = defaultdict(int)
    latest: dict[str, str] = {}
    for attempt in attempts:
        question_id = attempt.get("question_id")
        attempts_by_question[question_id] += 1
        latest[question_id] = attempt.get("created_at", "")

    candidates = []
    for question in questions:
        if exam_type and question.get("exam_type") != exam_type:
            continue
        if concept_id and concept_id not in question.get("concept_ids", []):
            continue
        concept_values = [mastery.get(item, 0.22) for item in question.get("concept_ids") or []]
        weakest = min(concept_values) if concept_values else 0.22
        unseen_bonus = 0.32 if question["id"] not in attempts_by_question else 0
        repetition_penalty = min(0.3, attempts_by_question[question["id"]] * 0.08)
        type_bonus = 0.08 if question.get("question_type") in {"choice", "fill"} else 0
        score = (1.0 - weakest) + unseen_bonus + type_bonus - repetition_penalty
        candidates.append((score, question))
    candidates.sort(key=lambda item: (-item[0], item[1].get("year", 0), item[1].get("number", 0)))
    return [item[1] for item in candidates[: max(1, min(limit, 30))]]


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
    target_year = years[-1]
    paper = [question for question in pool if int(question["year"]) == target_year]
    if not paper:
        paper = pool[-30:]
    mastery = mastery_by_concept(attempts)
    attempted_count = len(attempts)
    rng = random.Random(20260825 + attempted_count)
    max_score = sum(float(question.get("points", 0)) for question in paper)
    if not attempts:
        return {
            "available": True,
            "exam_type": exam_type,
            "paper_year": target_year,
            "paper_questions": len(paper),
            "max_score": max_score,
            "p10": 0.0,
            "p50": 0.0,
            "p90": 0.0,
            "confidence": "暂无",
            "attempts_used": 0,
            "note": "尚无真实作答记录，初始预估分按 0 分显示。完成练习后再用个人数据更新；人群中约三成考生能超过 50 分，系统不会把这个比例直接当成你的个人成绩。",
        }
    scores: list[float] = []
    for _ in range(800):
        score = 0.0
        for question in paper:
            values = [mastery.get(item, 0.22) for item in question.get("concept_ids") or []]
            state = mean(values) if values else 0.22
            # Anchor the no-data learner to the reported ~30% cohort baseline
            # and let observed mastery, not optimism, move the estimate upward.
            probability = 0.30 + (state - 0.22) * (0.82 - 0.30) / (1.0 - 0.22)
            probability = max(0.05, min(0.90, probability))
            if rng.random() < probability:
                score += float(question.get("points", 0))
        scores.append(score)
    scores.sort()
    p10 = round(scores[int(len(scores) * 0.10)], 1)
    p50 = round(scores[int(len(scores) * 0.50)], 1)
    p90 = round(scores[int(len(scores) * 0.90)], 1)
    confidence = "低" if attempted_count < 10 else ("中" if attempted_count < 40 else "较高")
    return {
        "available": True,
        "exam_type": exam_type,
        "paper_year": target_year,
        "paper_questions": len(paper),
        "max_score": max_score,
        "p10": p10,
        "p50": p50,
        "p90": p90,
        "confidence": confidence,
        "attempts_used": attempted_count,
        "note": "这是基于当前掌握度的模拟区间，不等同于真实考试承诺；低样本阶段按约三成考生超过 50 分的保守人群基线校准，完成更多带计时的模拟考后会更可靠。",
    }
