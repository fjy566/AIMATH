from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

from app.services.concepts import CONCEPT_META, MATH2_CONCEPTS, MATH2_CONCEPT_IDS, concept_descriptor


QUESTION_TYPES = ("choice", "fill", "solution")
QUESTION_TYPE_LABELS = {"choice": "选择题", "fill": "填空题", "solution": "解答题"}


CONCEPT_FOCUS = {
    "limit-continuity": "极限存在、极限计算与连续性的判定",
    "derivative": "导数与微分、单调性、极值和凹凸性的综合应用",
    "integral": "原函数、定积分、变限积分和积分应用",
    "multivariable": "偏导数、全微分、复合函数与隐函数求导",
    "multiple-integral": "积分区域识别、直角坐标换序与二重积分计算",
    "differential-equation": "一阶方程、可降阶方程和线性微分方程的通解",
    "matrix": "行列式、矩阵运算、秩与逆矩阵的等价变形",
    "linear-equation": "线性方程组的相容性、通解与基础解系",
    "vector-space": "向量组的线性表示、相关性、秩与极大无关组",
    "eigenvalue": "特征值特征向量、相似对角化与二次型正定性",
}


TYPE_BLUEPRINTS = {
    "choice": {
        "overview": "选择题重点考查概念边界、条件识别和短链条计算。{focus}常把定义、必要条件与结论压缩在一个选项中，先判结构再算数值更稳。",
        "framework": [
            "圈出题干中的定义条件、范围条件和结论词，先判断题目属于概念辨析、性质应用还是直接计算。",
            "把 {focus} 需要的核心定理写成最短可检查形式，逐一核对定理的使用前提。",
            "优先用反例、特殊值、量纲或边界值排除选项，再完成剩余选项的精算。",
            "回看题干是否问‘一定’、‘可能’或‘不存在’，确认结论方向和选项编号没有错位。",
        ],
        "mistakes": [
            "只记结论不看定义域、可导性、可逆性或秩等前提，导致把充分条件当成必要条件。",
            "代入特殊值时没有确认该值属于题目允许范围，或忽略分母、根号和对数的限制。",
            "计算过程正确但最后一行把‘正确选项’看成了‘错误选项’，提交前要复述问题。",
        ],
        "memory_aid": "先条件，后性质；先排除，后精算。",
    },
    "fill": {
        "overview": "填空题要求把 {focus} 的关键结论压缩成一个可核验的结果。得分点通常集中在符号、范围、常数和表达式的完整性。",
        "framework": [
            "先写出对应定义或标准公式，标出待求量与已知量之间的关系。",
            "按‘条件检查 → 公式代入 → 化简整理 → 端点或符号复核’四步推进。",
            "多空题先分空记录中间结果，避免前一空的符号错误传到后一空。",
            "最终答案统一约分、补括号和微分符号，检查是否需要写常数、范围或向量形式。",
        ],
        "mistakes": [
            "漏写负号、绝对值、积分常数、转置符号或求导阶数，导致形式不完整。",
            "换元或分部积分后没有把上下限、变量和剩余因子全部换回。",
            "只看数值不看表达式等价性，尤其容易在根式、分式和矩阵乘法顺序上失分。",
        ],
        "memory_aid": "每一空都做一次定义域、符号、边界三重检查。",
    },
    "solution": {
        "overview": "解答题要把 {focus} 的方法选择、关键依据和结论串成可给分的过程。答案不是只写最后一行，而是让阅卷者看见每个得分点。",
        "framework": [
            "第一行写清已知条件、目标量和适用范围，必要时补充定义域或参数限制。",
            "先选择方法并写出依据，再逐步展开计算；每次变形都说明使用的定理、公式或初等变换。",
            "复杂题按小问或逻辑节点分点，保留关键中间量，避免跳步导致结论无法追溯。",
            "最后单独写结论并回代检查：定义域、边界条件、维数/阶数、符号和题目问法必须一致。",
        ],
        "mistakes": [
            "只写‘显然’或直接跳到结果，没有交代定理前提和关键中间步骤。",
            "解微分方程、方程组或二次型时漏掉通解参数、基础解系、特征向量条件或正定判据。",
            "小问之间相互引用时没有说明前一问结论的适用条件，最终答案也没有回到题目变量。",
        ],
        "memory_aid": "依据写在前，过程分点，结论单列，最后回代。",
    },
}


def _difficulty_label(year: Any) -> tuple[str, str]:
    try:
        value = int(year)
    except (TypeError, ValueError):
        return "other", "待分层"
    if 1987 <= value <= 2019:
        return "basic", "基础题"
    if 2020 <= value <= 2026:
        return "advanced", "提高题"
    return "other", "待分层"


def _question_public(question: dict[str, Any], *, reveal: bool = True) -> dict[str, Any]:
    excluded = {"raw_markdown"}
    if not reveal:
        excluded.update({"answer_markdown", "solution_markdown"})
    result = {key: value for key, value in question.items() if key not in excluded}
    band, label = _difficulty_label(question.get("year"))
    result["difficulty_band"] = band
    result["difficulty_label"] = label
    result["answer_available"] = bool(question.get("has_answer"))
    result["solution_available"] = bool(question.get("has_solution"))
    result["concept_labels"] = [concept_descriptor(item) for item in question.get("concept_ids", [])]
    return result


def _question_sort_key(question: dict[str, Any]) -> tuple[int, int, int, str]:
    try:
        difficulty = int(question.get("difficulty", 3))
    except (TypeError, ValueError):
        difficulty = 3
    try:
        year = int(question.get("year", 0))
    except (TypeError, ValueError):
        year = 0
    try:
        number = int(question.get("number", 0))
    except (TypeError, ValueError):
        number = 0
    return (abs(difficulty - 3), -year, number, str(question.get("id", "")))


def _subject_for_concept(concept_id: str) -> str:
    return CONCEPT_META.get(concept_id, ("", ""))[1]


def _unique_questions(items: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        identifier = str(item.get("id", ""))
        if not identifier or identifier in seen:
            continue
        seen.add(identifier)
        result.append(item)
    return result


def _question_pools(questions: list[dict[str, Any]], concept_id: str, question_type: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    exact = [
        question for question in questions
        if question.get("exam_type") == "数学二"
        and question.get("question_type") == question_type
        and concept_id in question.get("concept_ids", [])
    ]
    subject = _subject_for_concept(concept_id)
    same_subject = [
        question for question in questions
        if question.get("exam_type") == "数学二"
        and question.get("question_type") == question_type
        and any(item in MATH2_CONCEPT_IDS and _subject_for_concept(item) == subject for item in question.get("concept_ids", []))
    ]
    return sorted(_unique_questions(exact), key=_question_sort_key), sorted(_unique_questions(same_subject), key=_question_sort_key)


def _copy_template(concept_id: str, question_type: str) -> dict[str, Any]:
    concept_name, subject = CONCEPT_META[concept_id]
    focus = CONCEPT_FOCUS.get(concept_id, concept_name)
    blueprint = TYPE_BLUEPRINTS[question_type]
    return {
        "concept_id": concept_id,
        "concept_name": concept_name,
        "subject": subject,
        "question_type": question_type,
        "question_type_label": QUESTION_TYPE_LABELS[question_type],
        "overview": blueprint["overview"].format(focus=focus),
        "framework": [step.format(focus=focus) for step in blueprint["framework"]],
        "mistakes": list(blueprint["mistakes"]),
        "memory_aid": blueprint["memory_aid"],
        "source": "砺数数学二答题模板库",
    }


def _apply_override(template: dict[str, Any], override: dict[str, Any] | None) -> dict[str, Any]:
    if not override:
        return template
    for key in ("overview", "framework", "mistakes", "memory_aid"):
        if key in override and override[key] not in (None, "", []):
            template[key] = override[key]
    template["customized"] = True
    template["updated_at"] = override.get("updated_at", "")
    return template


def build_workbench_template(
    questions: list[dict[str, Any]],
    concept_id: str,
    question_type: str,
    override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if concept_id not in MATH2_CONCEPT_IDS:
        raise ValueError("Workbench 只支持数学二大纲内知识块。")
    if question_type not in QUESTION_TYPES:
        raise ValueError("不支持的题型。")
    exact, same_subject = _question_pools(questions, concept_id, question_type)
    selected = _unique_questions(exact + same_subject)
    selected = sorted(selected, key=_question_sort_key)
    example = selected[0] if selected else None
    variants = selected[1:4] if selected else []
    template = _apply_override(_copy_template(concept_id, question_type), override)
    template["question_count"] = len(exact)
    template["available_count"] = len(selected)
    template["example_source"] = "当前知识块" if exact else "同科目跨块真实题"
    template["example"] = {
        "question": _question_public(example, reveal=True) if example else None,
        "analysis": example.get("solution_markdown", "") if example else "当前题库没有找到可用的真实例题。",
        "answer": example.get("answer_markdown", "") if example else "",
        "difficulty": example.get("difficulty", 0) if example else 0,
    }
    template["variants"] = [
        {
            "question": _question_public(item, reveal=True),
            "analysis": item.get("solution_markdown", ""),
            "answer": item.get("answer_markdown", ""),
            "difficulty": item.get("difficulty", 0),
            "source_scope": "当前知识块" if concept_id in item.get("concept_ids", []) else "同科目跨块",
        }
        for item in variants
    ]
    template["has_real_example"] = example is not None
    template["variant_count"] = len(variants)
    return template


def workbench_catalog(questions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for question in questions:
        if question.get("exam_type") != "数学二":
            continue
        for concept_id in question.get("concept_ids", []):
            if concept_id in MATH2_CONCEPT_IDS and question.get("question_type") in QUESTION_TYPES:
                counts[concept_id][question["question_type"]] += 1
    result: list[dict[str, Any]] = []
    for concept in MATH2_CONCEPTS:
        concept_id = concept["id"]
        result.append({
            "id": concept_id,
            "name": concept["name"],
            "subject": concept["subject"],
            "scope": "math2",
            "template_count": len(QUESTION_TYPES),
            "question_type_counts": {question_type: counts[concept_id][question_type] for question_type in QUESTION_TYPES},
            "total_questions": sum(counts[concept_id].values()),
        })
    return result


def question_type_catalog() -> list[dict[str, str]]:
    return [{"id": key, "label": QUESTION_TYPE_LABELS[key]} for key in QUESTION_TYPES]
