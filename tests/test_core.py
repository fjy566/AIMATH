from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.grading import grade_question
from app.services.learner import difficulty_descriptor, forecast_score, learning_analytics, mastery_by_concept, progress_summary, question_attempt_summaries
from app.services.llm import _api_root


ROOT = Path(__file__).resolve().parents[1]


def load_questions() -> list[dict]:
    return json.loads((ROOT / "data" / "processed" / "questions.json").read_text(encoding="utf-8"))


def test_imported_dataset_is_real_and_complete() -> None:
    questions = load_questions()
    assert len(questions) >= 700
    assert {question["year"] for question in questions} == set(range(1987, 2027))
    assert all(question["question_markdown"].strip() for question in questions)
    assert all(question["raw_markdown"].strip() for question in questions)
    assert all(question["source_path"].endswith(".md") for question in questions)
    assert all(len(question["content_sha256"]) == 64 for question in questions)


def test_math2_catalog_excludes_other_paper_topics_but_keeps_display_metadata() -> None:
    from app.services.concepts import CONCEPT_META, OUT_OF_SYLLABUS_CONCEPT_IDS, concept_descriptor

    assert "series" not in CONCEPT_META
    assert "probability" not in CONCEPT_META
    assert "vector-calculus" not in CONCEPT_META
    assert "vector-space" in CONCEPT_META
    assert {"series", "probability", "vector-calculus"}.issubset(OUT_OF_SYLLABUS_CONCEPT_IDS)
    assert concept_descriptor("series")["scope"] == "out-of-syllabus"
    assert concept_descriptor("series")["name"] == "无穷级数"


def test_concept_inference_does_not_cross_tag_linear_algebra_as_ode() -> None:
    from app.services.concepts import infer_concepts

    linear_system = "四、线性方程组\n求参数使方程组有唯一解、无解或无穷多解，并写出通解。"
    assert "differential-equation" not in infer_concepts(linear_system, "四、线性方程组")

    questions = load_questions()
    assert not any(
        "differential-equation" in question.get("concept_ids", [])
        and any(item in question.get("concept_ids", []) for item in ("matrix", "linear-equation", "vector-space", "eigenvalue"))
        for question in questions
    )


def test_modern_paper_has_real_150_point_total() -> None:
    questions = [question for question in load_questions() if question["year"] == 2025]
    assert len(questions) == 22
    assert sum(question["points"] for question in questions) == 150
    assert questions[-1]["points"] == 12


def test_real_question_years_have_explicit_study_difficulty_bands() -> None:
    assert difficulty_descriptor(1987) == ("basic", "基础题")
    assert difficulty_descriptor(2019) == ("basic", "基础题")
    assert difficulty_descriptor(2020) == ("advanced", "提高题")
    assert difficulty_descriptor(2026) == ("advanced", "提高题")


def test_objective_and_manual_grading_are_honest() -> None:
    choice = next(question for question in load_questions() if question["question_type"] == "choice" and question["has_answer"])
    choice_result = grade_question(choice, choice["answer_markdown"])
    assert choice_result["status"] == "correct"
    assert choice_result["score"] == choice["points"]

    solution = next(question for question in load_questions() if question["question_type"] == "solution")
    manual_result = grade_question(solution, "")
    assert manual_result["status"] == "manual"
    assert manual_result["correct"] is None

    self_grade_result = grade_question(solution, "我的步骤", self_grade=0.7)
    assert self_grade_result["status"] == "partial"
    assert self_grade_result["score"] == solution["points"] * 0.7


def test_learning_state_updates_and_forecast_inputs_are_interpretable() -> None:
    attempts = [
        {"concepts": ["limit-continuity"], "status": "incorrect", "correct": 0, "duration_seconds": 60},
        {"concepts": ["limit-continuity"], "status": "correct", "correct": 1, "duration_seconds": 55},
    ]
    mastery = mastery_by_concept(attempts)
    assert 0.02 <= mastery["limit-continuity"] <= 0.98
    summary = progress_summary(attempts, load_questions())
    row = next(item for item in summary["concepts"] if item["id"] == "limit-continuity")
    assert row["attempts"] == 2
    assert row["correct"] == 1
    assert summary["accuracy"] == 50.0


def test_initial_forecast_is_zero_until_real_attempts_exist() -> None:
    forecast = forecast_score(load_questions(), [], exam_type="数学二")
    assert forecast["available"] is True
    assert forecast["paper_years"] == [2024, 2025, 2026]
    assert forecast["max_score"] == 150
    assert len(forecast["difficulty_calibration"]) == 4
    assert forecast["attempts_used"] == 0
    assert forecast["score_range"]["low"] == 0
    assert forecast["score_range"]["high"] == 0
    assert forecast["outer_range"]["low"] == 0
    assert forecast["outer_range"]["high"] == 0
    assert forecast["population_reference"]["score_tail_observations_percent"]["2019"]["105"] == 5.3
    assert forecast["population_reference"]["funnel_reference"]["national_line_rate"].startswith("约 20%-30%")
    assert forecast["population_reference"]["funnel_reference"]["admission_rate"].startswith("约 20%")
    assert "2025" not in forecast["population_reference"]["score_tail_observations_percent"]
    assert "p50" not in forecast


def test_forecast_shrinks_local_block_evidence_and_returns_an_interval() -> None:
    questions = load_questions()
    same_block = [
        question for question in questions
        if "limit-continuity" in question.get("concept_ids", [])
    ][:4]
    attempts = [
        {
            "question_id": question["id"],
            "status": "correct",
            "correct": 1,
            "score": question["points"],
            "max_score": question["points"],
            "created_at": f"2026-08-26T{index + 8:02d}:00:00+00:00",
        }
        for index, question in enumerate(same_block)
    ]

    forecast = forecast_score(questions, attempts, exam_type="数学二")

    assert forecast["unique_questions_used"] == 4
    assert forecast["concepts_used"] >= 1
    assert forecast["personalization_weight"] < 0.08
    assert forecast["score_range"]["low"] < forecast["score_range"]["high"]
    assert forecast["score_range"]["high"] < 100


def test_forecast_ui_renders_interval_instead_of_a_single_p50() -> None:
    app_source = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")
    html_source = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")

    assert 'forecast.score_range' in app_source
    assert 'forecast-outer-low' in app_source
    assert 'id="forecast-score-range"' in html_source
    assert 'forecast-p50' not in app_source


def test_secondary_views_do_not_repeat_global_page_heading() -> None:
    html_source = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
    app_source = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")

    assert 'class="view-intro' not in html_source
    assert html_source.count('class="view-contextbar"') == 7  # admin access-control view is also a secondary surface
    assert 'id="refresh-analytics"' not in html_source
    assert 'id="reload-blocks"' not in html_source
    assert "function refreshCurrentView" in app_source
    assert 'addEventListener("click", refreshCurrentView)' in app_source
    assert '`${payload.total} 道真题`' in app_source


def test_library_question_preview_keeps_mobile_formulas_inside_the_page() -> None:
    styles = (ROOT / "app" / "static" / "styles.css").read_text(encoding="utf-8")

    assert ".question-preview { max-height: 108px; overflow: hidden; contain: paint;" in styles
    assert ".question-row-content > p" in styles
    assert ".question-row-content p {" not in styles
    assert ".markdown-body .katex-display { overflow-x: auto" in styles
    assert ".filter-bar { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr));" in styles


def test_learning_analytics_separates_observed_evidence_from_untrained_topics() -> None:
    questions = load_questions()
    first = next(question for question in questions if question["year"] == 2025 and question["question_type"] == "choice")
    second = next(question for question in questions if question["year"] == 2025 and question["question_type"] == "solution")
    attempts = [
        {
            "id": 1,
            "question_id": first["id"],
            "concepts": first["concept_ids"],
            "status": "correct",
            "correct": 1,
            "score": first["points"],
            "max_score": first["points"],
            "duration_seconds": 120,
            "hints_used": 0,
            "error_type": "",
            "created_at": "2026-08-26T09:00:00+00:00",
        },
        {
            "id": 2,
            "question_id": second["id"],
            "concepts": second["concept_ids"],
            "status": "partial",
            "correct": 0,
            "score": second["points"] * 0.4,
            "max_score": second["points"],
            "duration_seconds": 240,
            "hints_used": 1,
            "error_type": "步骤不完整",
            "created_at": "2026-08-26T10:00:00+00:00",
        },
    ]
    result = learning_analytics(questions, attempts)
    assert result["questions_available"] == 792
    assert result["overview"]["attempts"] == 2
    assert result["overview"]["unique_questions"] == 2
    assert result["overview"]["accuracy"] == 50.0
    assert {row["question_type"] for row in result["question_types"]} == {"choice", "fill", "solution"}
    assert result["error_types"][0]["name"] == "步骤不完整"
    assert result["daily_trend"][0]["attempts"] == 2
    assert result["profile"]["recent_attempts"] == 2
    assert result["profile"]["active_days_7d"] == 1
    assert result["recent_years"] == [2024, 2025, 2026]
    assert len(result["difficulty_breakdown"]) == 4
    assert len(result["recent_year_breakdown"]) == 3
    assert any(row["attempts"] == 0 and row["status"] == "待训练" for row in result["concepts"])


def test_workbench_covers_every_math2_block_with_real_examples() -> None:
    from app.services.workbench import (
        SUBTYPE_CATALOG,
        build_workbench_template,
        is_workbench_question_eligible,
        question_subtype_ids,
        subtype_count,
        workbench_catalog,
    )

    questions = load_questions()
    catalog = workbench_catalog(questions)
    assert len(catalog) == 10
    assert subtype_count() == 68
    assert all(item["template_count"] == item["subtype_count"] >= 4 for item in catalog)
    assert all(item["subtypes"] for item in catalog)
    assert all(
        set(subtype["question_format_counts"]).issubset({"choice", "fill", "solution"})
        for item in catalog
        for subtype in item["subtypes"]
    )
    derivative_names = {item["name"] for item in SUBTYPE_CATALOG["derivative"]}
    assert {"罗尔定理的应用", "拉格朗日中值定理的应用"}.issubset(derivative_names)

    for concept_id, subtypes in SUBTYPE_CATALOG.items():
        for subtype in subtypes:
            template = build_workbench_template(questions, concept_id, subtype["id"])
            if template["matched_question_count"]:
                assert template["has_real_example"] is True
                assert template["example"]["question"]["id"] in {item["id"] for item in questions}
                assert template["example"]["question"]["question_markdown"].strip()
                assert template["example"]["analysis"].strip()
                assert template["variant_count"] == min(max(template["matched_question_count"] - 1, 0), 3)
                assert template["example_source"] == "细分题型命中"
                assert template["example"]["source_scope"] == "细分题型命中"
                assert all(is_workbench_question_eligible(item["question"]) for item in template["variants"])
                assert all(item["source_scope"] == "细分题型命中" for item in template["variants"])
            else:
                assert template["has_real_example"] is False
                assert template["example"]["question"] is None
                assert template["example_source"] == "无直接题目"
                assert template["variant_count"] == 0
            assert len(template["framework"]) >= 5
            assert len(template["mistakes"]) >= 4
            assert template["formula_sheet"].strip() and "$" in template["formula_sheet"]
            assert len(template["answer_structure"]) == 6
            assert [item["label"] for item in template["answer_structure"]] == [
                "题型定位", "条件翻译", "定理核验", "核心过程", "边界与分支", "结论复核",
            ]
            assert all(item["prompt"].strip() and item["content"].strip() for item in template["answer_structure"])
            assert [item["label"] for item in template["recognition"]] == ["题干信号", "任务翻译", "方法入口"]
            assert [item["title"] for item in template["exam_directions"]] == [
                "直接型", "参数分类型", "逆向与证明型", "综合串联型", "变式与陷阱型",
            ]
            assert [item["type"] for item in template["question_type_guides"]] == ["choice", "fill", "solution"]
            assert [item["level"] for item in template["practice_levels"]] == ["基础识别", "标准执行", "综合迁移"]
            assert len(template["exam_checklist"]) == 5
            assert all(item["content"].strip() for item in template["recognition"])
            assert all(item["detail"].strip() for item in template["exam_directions"])
            assert all(item["steps"].strip() and item["finish"].strip() for item in template["question_type_guides"])
            assert all(item["task"].strip() and item["standard"].strip() for item in template["practice_levels"])
            assert all(item.strip() for item in template["exam_checklist"])
            assert all(
                value.count("$") % 2 == 0
                for value in [template["overview"], template["memory_aid"], template["formula_sheet"], *template["framework"], *template["mistakes"]]
            )
            assert all(
                "\\\\" not in value
                for value in [template["overview"], template["memory_aid"], *template["framework"], *template["mistakes"]]
            )
            assert r"\\begin" not in template["formula_sheet"]
            assert r"\\end{" not in template["formula_sheet"]
            assert template["overview"]
            assert template["subtype_name"] == subtype["name"]
            assert len(template["construction_patterns"]) >= 4
            assert len(template["solution_steps"]) >= 6
            assert all(
                item["title"].strip()
                and item["when"].strip()
                and item["formula"].strip()
                and item["steps"]
                and item["target"].strip()
                and item["checks"]
                for item in template["construction_patterns"]
            )
            assert all(item["label"].strip() and item["content"].strip() and item["check"].strip() for item in template["solution_steps"])

    assert build_workbench_template(questions, "derivative", "rolle-theorem")["matched_question_count"] > 0
    assert build_workbench_template(questions, "derivative", "lagrange-mvt")["matched_question_count"] > 0
    bernoulli = build_workbench_template(questions, "differential-equation", "bernoulli-ode")
    assert bernoulli["example"]["question"] is None
    reducible = build_workbench_template(questions, "differential-equation", "reducible-higher-ode")
    q2026 = next(item for item in questions if item["id"] == "数学二-2026-21-21")
    assert "reducible-higher-ode" in question_subtype_ids(q2026)
    assert "bernoulli-ode" not in question_subtype_ids(q2026)
    analysis_fragment = next(item for item in questions if item["id"] == "数学二-2023-02-30")
    combined_paper = next(item for item in questions if item["id"] == "数学二-2020-01-01")
    assert is_workbench_question_eligible(analysis_fragment) is False
    assert is_workbench_question_eligible(combined_paper) is False
    eigen_template = build_workbench_template(questions, "eigenvalue", "eigen-computation")
    selected_ids = {eigen_template["example"]["question"]["id"], *(item["question"]["id"] for item in eigen_template["variants"])}
    assert analysis_fragment["id"] not in selected_ids
    assert combined_paper["id"] not in selected_ids


def test_rolle_template_exposes_common_constructions_and_stepwise_proof() -> None:
    from app.services.workbench import build_workbench_template

    template = build_workbench_template(load_questions(), "derivative", "rolle-theorem")
    titles = {item["title"] for item in template["construction_patterns"]}
    assert {
        "直接取原函数",
        "减去目标直线（常数斜率）",
        "减去割线（由罗尔推出拉格朗日）",
        "两函数作差",
        "柯西型加权差",
        "参数线性组合",
        "积分平均值构造",
        "加权积分平均",
        "对称端点与镜像差",
        "复合变换保端点",
        "多零点与反复罗尔",
        "原函数型零点与唯一性",
    }.issubset(titles)
    assert [item["label"] for item in template["solution_steps"]] == [
        "目标改写", "选择构造", "写区间条件", "验证端点等值", "引用罗尔定理", "展开并还原", "分支与复核",
    ]
    assert all("$" in item["content"] for item in template["solution_steps"])


def test_frontend_formula_renderer_is_shared_by_rich_text_surfaces() -> None:
    source = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")
    markup = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")

    assert "const TEX_COMMAND_PATTERN" in source
    assert "const TEX_SLASH" in source
    assert "const TEX_ALIGNMENT_ENVS" in source
    assert "function normalizeTexSource" in source
    assert 'rendered.includes("katex-error")' in source
    assert "alignat" in source and "dcases" in source
    assert "function renderTemplateText" in source
    assert "function renderInlineFormulaText" in source
    assert "function renderNoteMarkdownPreview" in source
    assert "function handleStructuredTextKeydown" in source
    assert "const sharedFormulaEditor" in source
    assert "MARKDOWNMEDIATOKEN" in source
    assert "<u>$1</u>" in source
    assert "data-editor-count" in source
    assert "function renderNoteRichPreview" in source
    assert "note-rich-preview-body" in markup
    assert "note-rich-count" in markup
    assert "data-note-command=\"createLink\"" in markup
    assert "renderMarkdown(content)" in source
    assert 'raw.startsWith("\\\\begin")' in source


def test_classification_editor_is_shared_by_block_training_surfaces() -> None:
    source = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")

    assert 'classificationEditorMarkup(question, "block")' in source
    assert 'classificationEditorMarkup(question, "practice")' in source
    assert 'bindClassificationControls($("blocks-container"))' in source
    assert "function practiceQuestionSubtypeLine" in source
    assert "data-practice-subtype-label" in source


def test_workbench_template_navigation_search_and_actions_are_reusable() -> None:
    source = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")
    markup = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
    styles = (ROOT / "app" / "static" / "styles.css").read_text(encoding="utf-8")

    assert 'id="workbench-subtype-search"' in markup
    assert "function workbenchSectionHeadingMarkup" in source
    assert "function templateGuideMarkup" in source
    assert "function bindWorkbenchTemplateActions" in source
    assert "copy-workbench-answer-template" in source
    assert "start-workbench-practice" in source
    assert "state.workbenchCatalog.some((item) => item.id === state.workbenchConceptId)" in source
    assert "activeConcept?.subtypes?.some((item) => item.id === state.workbenchSubtypeId)" in source
    assert "template.exam_directions" in source
    assert "template.question_type_guides" in source
    assert "template.practice_levels" in source
    assert "template.exam_checklist" in source
    assert "function renderLearningText" in source
    assert "function templateConstructionMarkup" in source
    assert "function templateSolutionStepsMarkup" in source
    assert "template.construction_patterns" in source
    assert "template.solution_steps" in source
    assert "template-constructions" in source
    assert "template-solution-steps" in source
    assert 'renderLearningText(item.focus, "template-format-focus")' in source
    assert 'renderLearningText(item.steps, "template-format-steps")' in source
    assert 'renderLearningText(item.finish, "template-format-finish")' in source
    assert 'renderLearningText(item.task, "template-practice-task")' in source
    assert "renderLearningText(item.standard)" in source
    assert 'renderLearningText(item, "template-check-item")' in source
    assert ".template-quick-nav" in styles
    assert ".template-format-grid" in styles
    assert ".template-construction-card" in styles
    assert ".template-solution-step" in styles


def test_block_training_uses_compact_stack_and_single_question_navigation() -> None:
    source = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")
    styles = (ROOT / "app" / "static" / "styles.css").read_text(encoding="utf-8")

    assert "data-block-stack" in source
    assert "function bindBlockStack" in source
    assert "data-practice-question-card" in source
    assert "data-practice-question-index" in source
    assert "function selectPracticeQuestion" in source
    assert ".block-stack-card" in styles
    assert ".practice-question-navigator" in styles
    assert ".practice-session-question[hidden]" in styles


def test_answer_boards_share_touch_handwriting_drafts_and_fullscreen_controls() -> None:
    source = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")
    styles = (ROOT / "app" / "static" / "styles.css").read_text(encoding="utf-8")

    assert "function renderHandwritingPad" in source
    assert "function bindHandwritingPads" in source
    assert "function answerHandwritingKey" in source
    assert "HANDWRITING_STORAGE_PREFIX" in source
    assert "data-handwriting-canvas" in source
    assert "pointerdown" in source and "pointermove" in source
    assert "data-handwriting-fullscreen" in source
    assert 'data-handwriting-tool="eraser"' in source
    assert "globalCompositeOperation" in source
    assert "collectHandwritingAttachments" in source
    assert "handwritingPadToBlob" in source and "toBlob" in source
    assert "handwritingchange" in source
    assert "renderHandwritingPad({ key: handwritingKey, readonly, expanded: mode === \"modal\" })" in source
    assert "data-answer-workspace" in source
    assert "contextId: simulation.id" in source
    assert ".handwriting-canvas {" in styles
    assert "touch-action: none" in styles
    assert ".handwriting-pad:fullscreen" in styles
    assert ".answer-workspace" in styles
    assert "@media (pointer: coarse)" in styles


def test_block_stack_has_accessible_motion_and_tablet_layout_guards() -> None:
    source = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")
    styles = (ROOT / "app" / "static" / "styles.css").read_text(encoding="utf-8")

    assert "style=\"--stack-index:${blockIndex}\"" in source
    assert "block-stack-content-inner" in source
    assert ".block-stack-card:not([open]) > .block-stack-content" in styles
    assert "grid-template-rows: 1fr" in styles and "grid-template-rows: 0fr" in styles
    assert "@keyframes stack-card-in" in styles
    assert "@media (min-width: 761px) and (max-width: 860px)" in styles
    assert "@media (min-width: 861px) and (max-width: 1100px)" in styles
    assert "@media (prefers-reduced-motion: reduce)" in styles


def test_view_motion_preserves_navigation_state_and_ignores_stale_results() -> None:
    source = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")
    markup = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
    styles = (ROOT / "app" / "static" / "styles.css").read_text(encoding="utf-8")

    assert 'class="nav-glide"' in markup
    assert 'aria-current="page"' in markup
    assert "async function transitionToView" in source
    assert 'event.animationName === "view-fold-out"' in source
    assert 'button.setAttribute("aria-current", "page")' in source
    assert "requestId !== state.libraryRequestId" in source
    assert ".view.active.view-entering" in styles
    assert ".view.view-leaving" in styles
    assert ".nav-glide { transition: opacity .001ms linear !important; }" in styles


def test_account_settings_and_admin_surface_use_shared_session_identity() -> None:
    source = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")
    markup = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
    styles = (ROOT / "app" / "static" / "styles.css").read_text(encoding="utf-8")

    assert 'id="auth-screen"' in markup
    assert 'id="register-form"' in markup
    assert 'id="view-admin"' in markup
    assert 'id="preferences-settings-form"' in markup
    assert "credentials: \"same-origin\"" in source
    assert 'headers.set("X-CSRF-Token", state.csrfToken)' in source
    assert "function resetUserScopedState" in source
    assert "function simulationPointerKey" in source
    assert "/api/admin/users/" in source
    assert "admin-user-search" in markup
    assert "admin-audit-export" in markup
    assert "password-toggle-icon" in markup
    assert "admin-sessions-revoked" in source
    assert ".auth-screen" in styles
    assert ".admin-user-row" in styles
    assert ".admin-toolbar" in styles


def test_tex_normalization_preserves_array_row_break_before_command() -> None:
    from app.services.workbench import _normalize_template_formula

    assert _normalize_template_formula(r"$\\left(x\\right)$") == r"$\left(x\right)$"
    assert _normalize_template_formula(r"$$\\\\lim_{x\\to0}x$$") == r"$$\lim_{x\to0}x$$"
    array_formula = r"$\begin{array}{l}y^{\prime}+ay=f(x),\\\left.y\right|_{x=0}=0\end{array}$"
    assert _normalize_template_formula(array_formula) == array_formula


def test_formula_normalization_repairs_braces_and_preserves_rows() -> None:
    from app.services.workbench import _normalize_template_formula

    rank_formula = _normalize_template_formula(r"$$r(A)=\\text{阶梯形主元数}=\\max\\{\\text{非零子式阶数}\\}.$$")
    assert rank_formula == r"$$r(A)=\text{阶梯形主元数}=\max\{\text{非零子式阶数}\}.$$"
    cases_formula = _normalize_template_formula(r"$$f(x)=\\begin{cases}f_1(x),&x\\in I_1,\\\\f_2(x),&x\\in I_2.\\end{cases}$$")
    assert cases_formula == r"$$f(x)=\begin{cases}f_1(x),&x\in I_1,\\f_2(x),&x\in I_2.\end{cases}$$"
    substack_formula = _normalize_template_formula(r"$\\substack{u=1\\\\v=1}$")
    assert substack_formula == r"$\substack{u=1\\v=1}$"


def test_matrix_rank_construction_formula_is_ready_for_katex() -> None:
    from app.services.workbench import build_workbench_template

    template = build_workbench_template(load_questions(), "matrix", "matrix-rank")
    rank_formula = next(item["formula"] for item in template["construction_patterns"] if item["title"] == "秩与主子式")
    assert rank_formula == r"$$r(A)=\text{阶梯形主元数}=\max\{\text{非零子式阶数}\}.$$"
    assert r"\\{" not in rank_formula
    assert r"\\}" not in rank_formula


def test_workbench_notes_assets_versions_and_template_export(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    import app.database as database
    import app.main as main_module
    from app.main import app

    original_db_path = database.DB_PATH
    original_database_root = database.ROOT_DIR
    original_uploads_dir = database.UPLOADS_DIR
    original_main_root = main_module.ROOT_DIR
    original_main_uploads = main_module.UPLOADS_DIR
    database.DB_PATH = tmp_path / "workbench.sqlite3"
    database.ROOT_DIR = tmp_path
    database.UPLOADS_DIR = tmp_path / "data" / "uploads"
    main_module.ROOT_DIR = tmp_path
    main_module.UPLOADS_DIR = tmp_path / "data" / "uploads"
    try:
        with TestClient(app) as client:
            catalog = client.get("/api/workbench")
            assert catalog.status_code == 200
            assert len(catalog.json()["concepts"]) == 10
            assert catalog.json()["total_templates"] == 68
            assert catalog.json()["taxonomy_version"] == "math2-subtypes-v1"
            template = client.get("/api/workbench", params={"concept_id": "derivative", "subtype_id": "rolle-theorem"})
            assert template.status_code == 200
            template_json = template.json()["template"]
            assert template_json["subtype_name"] == "罗尔定理的应用"
            assert template_json["has_real_example"] is True
            assert template_json["example"]["question"]["solution_markdown"]
            assert len(template_json["variants"]) == min(max(template_json["matched_question_count"] - 1, 0), 3)

            created = client.post(
                "/api/workbench/notes",
                json={
                    "title": "极限错题复盘",
                    "concept_id": "limit-continuity",
                    "tags": ["极限", "错题"],
                    "content_html": "<p>先检查定义域</p><script>alert(1)</script>",
                    "content_markdown": "# 极限错题复盘\n\n先检查定义域",
                    "favorite": True,
                },
            )
            assert created.status_code == 200
            note = created.json()["note"]
            note_id = note["id"]
            assert "script" not in note["content_html"]
            assert "handwriting_data" not in note
            assert "mindmap" not in note
            assert note["favorite"] is True

            asset = client.post(
                "/api/workbench/notes/assets",
                files={"file": ("note.png", b"\x89PNG\r\n\x1a\nreal-note-image", "image/png")},
            )
            assert asset.status_code == 200
            assert client.get(asset.json()["url"]).status_code == 200

            updated = client.put(
                f"/api/workbench/notes/{note_id}",
                json={"title": "极限错题复盘 2", "content_markdown": "第二版", "content_html": "<p>第二版</p>"},
            )
            assert updated.status_code == 200
            versions = client.get(f"/api/workbench/notes/{note_id}/versions")
            assert versions.status_code == 200
            assert len(versions.json()["items"]) >= 2
            first_version_id = versions.json()["items"][-1]["id"]
            restored = client.post(f"/api/workbench/notes/{note_id}/restore/{first_version_id}")
            assert restored.status_code == 200
            assert restored.json()["note"]["title"] == "极限错题复盘"

            saved_template = client.put(
                "/api/workbench/templates/derivative/rolle-theorem",
                json={"overview": "自定义罗尔定理提醒", "framework": ["先判条件"], "mistakes": ["别漏闭区间连续"], "memory_aid": "先验条件再找零点"},
            )
            assert saved_template.status_code == 200
            assert saved_template.json()["template"]["customized"] is True
            revised_template = client.put(
                "/api/workbench/templates/derivative/rolle-theorem",
                json={"overview": "自定义罗尔定理提醒第二版", "framework": ["验连续", "验端点"], "mistakes": ["别漏闭区间连续"], "memory_aid": "条件逐项核对"},
            )
            assert revised_template.status_code == 200
            template_versions = client.get("/api/workbench/templates/derivative/rolle-theorem/versions")
            assert template_versions.status_code == 200
            assert template_versions.json()["items"]
            exported = client.get("/api/workbench/export")
            assert exported.status_code == 200
            assert exported.json()["notes"]
            assert exported.json()["note_versions"][note_id]
            assert exported.json()["template_overrides"]

            imported = client.post(
                "/api/workbench/import",
                json={"notes": [{"title": "导入笔记", "content_markdown": "导入成功"}]},
            )
            assert imported.status_code == 200
            assert imported.json()["imported_notes"] == 1
            assert any(item["title"] == "导入笔记" for item in client.get("/api/workbench/notes").json()["items"])
    finally:
        database.DB_PATH = original_db_path
        database.ROOT_DIR = original_database_root
        database.UPLOADS_DIR = original_uploads_dir
        main_module.ROOT_DIR = original_main_root
        main_module.UPLOADS_DIR = original_main_uploads


def test_question_classification_override_flows_through_library_and_practice(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    import app.database as database
    from app.main import app

    original_db_path = database.DB_PATH
    database.DB_PATH = tmp_path / "classification.sqlite3"
    user_id = "classification-user"
    question_id = "数学二-2026-21-21"
    try:
        with TestClient(app) as client:
            before = client.get(
                "/api/questions",
                params={"user_id": user_id, "exam_type": "数学二", "subtype_id": "reducible-higher-ode", "limit": 200},
            )
            assert before.status_code == 200
            assert question_id in {item["id"] for item in before.json()["items"]}

            corrected = client.put(
                f"/api/questions/{question_id}/classification",
                json={
                    "user_id": user_id,
                    "concept_id": "matrix",
                    "subtype_id": "determinant-properties",
                    "note": "测试用户覆盖分类，不改动原始题库",
                },
            )
            assert corrected.status_code == 200
            corrected_question = corrected.json()["question"]
            assert corrected_question["classification_source"] == "user-correction"
            assert corrected_question["concept_ids"] == ["matrix"]
            assert corrected_question["subtype_ids"] == ["determinant-properties"]

            after_ode = client.get(
                "/api/questions",
                params={"user_id": user_id, "exam_type": "数学二", "subtype_id": "reducible-higher-ode", "limit": 200},
            )
            assert question_id not in {item["id"] for item in after_ode.json()["items"]}
            after_matrix = client.get(
                "/api/questions",
                params={"user_id": user_id, "exam_type": "数学二", "concept_id": "matrix", "subtype_id": "determinant-properties", "limit": 200},
            )
            assert question_id in {item["id"] for item in after_matrix.json()["items"]}

            practice = client.post(
                "/api/practice/sessions",
                json={
                    "user_id": user_id,
                    "exam_type": "数学二",
                    "concept_id": "matrix",
                    "subtype_id": "determinant-properties",
                    "count": 15,
                },
            )
            assert practice.status_code == 200
            assert practice.json()["subtype_id"] == "determinant-properties"
            assert all("determinant-properties" in item["subtype_ids"] for item in practice.json()["questions"])

            progress = client.get("/api/progress", params={"user_id": user_id})
            assert progress.status_code == 200
            assert next(item for item in progress.json()["concepts"] if item["id"] == "matrix")["question_count"] > 0

            source = client.get(f"/api/questions/{question_id}", params={"user_id": user_id, "reveal": "true"})
            assert source.status_code == 200
            assert "solution_markdown" in source.json()

            hint = client.post(
                f"/api/questions/{question_id}/hint",
                json={"user_id": user_id, "answer": "", "request": "请给我第一步思路"},
            )
            assert hint.status_code == 502
            assert "Base URL" in hint.json()["detail"]
    finally:
        database.DB_PATH = original_db_path


def test_question_history_and_practice_refresh_use_all_attempts(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    import app.database as database
    from app.main import app
    from app.services.workbench import SUBTYPES_BY_ID, question_subtype_ids

    original_db_path = database.DB_PATH
    database.DB_PATH = tmp_path / "history.sqlite3"
    questions = load_questions()
    pools: dict[tuple[str, str], list[dict]] = {}
    for question in questions:
        if question["exam_type"] != "数学二":
            continue
        for subtype_id in question_subtype_ids(question):
            subtype = SUBTYPES_BY_ID.get(subtype_id)
            if subtype:
                pools.setdefault((subtype["concept_id"], subtype_id), []).append(question)
    concept_id, subtype_id = max(pools, key=lambda key: len(pools[key]))
    pool = pools[(concept_id, subtype_id)]
    assert len(pool) >= 16
    question = next(item for item in pool if item.get("has_answer") and item.get("answer_markdown"))
    user_id = "history-user"
    try:
        with TestClient(app) as client:
            for _ in range(2):
                response = client.post(
                    f"/api/questions/{question['id']}/attempts",
                    json={"user_id": user_id, "answer": question["answer_markdown"], "mode": "practice"},
                )
                assert response.status_code == 200

            public = client.get(f"/api/questions/{question['id']}", params={"user_id": user_id})
            assert public.status_code == 200
            summary = public.json()["attempt_summary"]
            assert public.json()["attempted"] is True
            assert summary["attempts"] == 2
            assert summary["correct"] == 2

            first = client.post(
                "/api/practice/sessions",
                json={"user_id": user_id, "exam_type": "数学二", "concept_id": concept_id, "subtype_id": subtype_id, "count": 15},
            )
            assert first.status_code == 200
            first_ids = {item["id"] for item in first.json()["questions"]}
            second = client.post(
                "/api/practice/sessions",
                json={
                    "user_id": user_id,
                    "exam_type": "数学二",
                    "concept_id": concept_id,
                    "subtype_id": subtype_id,
                    "count": 15,
                    "exclude_question_ids": sorted(first_ids),
                },
            )
            assert second.status_code == 200
            second_ids = {item["id"] for item in second.json()["questions"]}
            assert second_ids != first_ids
            assert second_ids - first_ids

            workbench_first = client.get(
                "/api/workbench",
                params={"user_id": user_id, "concept_id": concept_id, "subtype_id": subtype_id},
            )
            assert workbench_first.status_code == 200
            first_workbench_ids = {
                workbench_first.json()["template"]["example"]["question"]["id"],
                *(item["question"]["id"] for item in workbench_first.json()["template"]["variants"]),
            }
            workbench_second = client.get(
                "/api/workbench",
                params=[
                    ("user_id", user_id),
                    ("concept_id", concept_id),
                    ("subtype_id", subtype_id),
                    ("refresh", "true"),
                    *(('exclude_question_ids', question_id) for question_id in first_workbench_ids),
                ],
            )
            assert workbench_second.status_code == 200
            second_workbench_ids = {
                workbench_second.json()["template"]["example"]["question"]["id"],
                *(item["question"]["id"] for item in workbench_second.json()["template"]["variants"]),
            }
            assert not first_workbench_ids & second_workbench_ids
            assert workbench_second.json()["template"]["example"]["question"]["attempt_summary"]["attempts"] >= 0

            analytics = client.get("/api/analytics", params={"user_id": user_id, "exam_type": "数学二"})
            assert analytics.status_code == 200
            subtype_row = next(item for item in analytics.json()["subtypes"] if item["id"] == subtype_id)
            assert subtype_row["attempts"] >= 2
            assert subtype_row["correct"] >= 2
    finally:
        database.DB_PATH = original_db_path


def test_question_attempt_summary_counts_repeated_submissions() -> None:
    summaries = question_attempt_summaries(
        [
            {"question_id": "q1", "status": "incorrect", "correct": 0, "created_at": "2026-08-26T09:00:00+00:00"},
            {"question_id": "q1", "status": "correct", "correct": 1, "created_at": "2026-08-26T10:00:00+00:00"},
        ]
    )
    assert summaries["q1"]["attempted"] is True
    assert summaries["q1"]["attempts"] == 2
    assert summaries["q1"]["correct"] == 1
    assert summaries["q1"]["incorrect"] == 1
    assert summaries["q1"]["last_status"] == "correct"


def test_server_settings_validate_and_persist(tmp_path: Path) -> None:
    import app.database as database
    from app.services.server import ServerSettingsError, save_server_settings, server_settings

    original_db_path = database.DB_PATH
    database.DB_PATH = tmp_path / "server.sqlite3"
    try:
        database.init_db()
        defaults = server_settings()
        assert defaults["host"] == "127.0.0.1"
        assert defaults["port"] == 8000
        saved = save_server_settings("0.0.0.0", 8123, "https://math.example.test/study/")
        assert saved["host"] == "0.0.0.0"
        assert saved["port"] == 8123
        assert saved["public_url"] == "https://math.example.test/study"
        assert saved["network_exposure_warning"] is True
        assert saved["browser_url"] == "https://math.example.test/study"
        assert saved["launch_command"] == "python scripts/run_server.py"
        local_only = save_server_settings("0.0.0.0", 8123)
        assert local_only["browser_url"] == "http://127.0.0.1:8123"
        with pytest.raises(ServerSettingsError):
            save_server_settings("bad host", 8123)
        with pytest.raises(ServerSettingsError):
            save_server_settings("127.0.0.1", 70000)
    finally:
        database.DB_PATH = original_db_path


def test_auth_shell_has_a_no_blank_fallback_and_progressive_fields() -> None:
    html_source = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
    app_source = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")
    styles = (ROOT / "app" / "static" / "styles.css").read_text(encoding="utf-8")

    assert '<body class="auth-pending">' not in html_source
    assert 'class="noscript-screen"' in html_source
    assert 'id="auth-retry"' in html_source
    assert 'id="register-optional-fields"' in html_source
    assert 'data-password-toggle' in html_source
    assert "replaceAllLiteral" in app_source
    assert "timeoutMs: 12000" in app_source
    assert 'button, input, select, textarea, summary' in styles


def test_openai_compatible_url_normalization() -> None:
    assert _api_root("http://127.0.0.1:11434") == "http://127.0.0.1:11434/v1"
    assert _api_root("http://127.0.0.1:11434/v1") == "http://127.0.0.1:11434/v1"
    assert _api_root("http://127.0.0.1:11434/v1/models") == "http://127.0.0.1:11434/v1"


def test_llm_target_validation_blocks_metadata_and_credential_urls() -> None:
    from app.services.llm import LLMError, _valid_base_url

    with pytest.raises(LLMError):
        _valid_base_url("http://169.254.169.254/latest/meta-data")
    with pytest.raises(LLMError):
        _valid_base_url("http://user:secret@example.test/v1")


def test_model_settings_preserve_and_mask_local_key(tmp_path: Path) -> None:
    import app.database as database
    from app.services.llm import public_settings, save_settings

    original_db_path = database.DB_PATH
    database.DB_PATH = tmp_path / "settings.sqlite3"
    try:
        database.init_db()
        saved = save_settings("http://127.0.0.1:1234/v1", "local-model", "secret-key-1234")
        assert saved["api_key_set"] is True
        assert saved["api_key_masked"].endswith("1234")
        assert "secret-key" not in str(saved)
        preserved = save_settings("http://127.0.0.1:1234/v1", "local-model-2", None)
        assert preserved["api_key_set"] is True
        assert public_settings()["model"] == "local-model-2"
    finally:
        database.DB_PATH = original_db_path


def test_http_api_health_question_and_full_simulation(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    import app.database as database
    import app.main as main_module
    from app.main import app

    original_db_path = database.DB_PATH
    original_database_root = database.ROOT_DIR
    original_uploads_dir = database.UPLOADS_DIR
    original_main_root = main_module.ROOT_DIR
    original_main_uploads = main_module.UPLOADS_DIR
    database.DB_PATH = tmp_path / "api.sqlite3"
    database.ROOT_DIR = tmp_path
    database.UPLOADS_DIR = tmp_path / "data" / "uploads"
    main_module.ROOT_DIR = tmp_path
    main_module.UPLOADS_DIR = tmp_path / "data" / "uploads"
    try:
        with TestClient(app) as client:
            health = client.get("/api/health")
            stats = client.get("/api/stats")
            paper = client.get("/api/questions", params={"exam_type": "数学二", "year": 2025, "limit": 30})
            choice = next(question for question in load_questions() if question["question_type"] == "choice" and question["has_answer"])
            upload = client.post(
                "/api/uploads/answer-image",
                data={"user_id": "local-user", "question_id": choice["id"]},
                files={"file": ("answer.png", b"\x89PNG\r\n\x1a\nreal-test-image", "image/png")},
            )
            attempt = client.post(
                f"/api/questions/{choice['id']}/attempts",
                json={"answer": choice["answer_markdown"], "mode": "practice", "attachment_ids": [upload.json()["attachment_id"]]},
            )
            progress = client.get("/api/progress")
            analytics = client.get("/api/analytics", params={"user_id": "local-user", "exam_type": "数学二"})
            forecast = client.get("/api/forecast", params={"user_id": "local-user", "exam_type": "数学二"})
            server_settings = client.get("/api/server/settings")
            simulation = client.post("/api/simulations", json={"exam_type": "数学二", "year": 2025, "duration_minutes": 180})
        assert health.status_code == 200
        assert health.json()["question_count"] == 792
        assert stats.json()["total_questions"] == 792
        assert paper.status_code == 200
        assert paper.json()["total"] == 22
        assert sum(item["points"] for item in paper.json()["items"]) == 150
        concepts = client.get("/api/concepts")
        assert concepts.status_code == 200
        assert all(item["scope"] == "math2" for item in concepts.json())
        assert "series" not in {item["id"] for item in concepts.json()}
        assert all(item["concept_labels"] for item in paper.json()["items"])
        assert upload.status_code == 200
        assert attempt.status_code == 200
        assert attempt.json()["result"]["status"] == "correct"
        assert len(attempt.json()["attachments"]) == 1
        assert client.get(attempt.json()["attachments"][0]["url"]).status_code == 200
        assert progress.status_code == 200
        assert progress.json()["attempts"] == 1
        assert analytics.status_code == 200
        assert analytics.json()["questions_available"] == 792
        assert len(analytics.json()["question_types"]) == 3
        assert len(analytics.json()["difficulty_breakdown"]) == 4
        assert analytics.json()["recent_years"] == [2024, 2025, 2026]
        assert forecast.status_code == 200
        assert forecast.json()["max_score"] == 150
        assert server_settings.status_code == 200
        assert server_settings.json()["port"] == 8000
        assert simulation.status_code == 200
        assert len(simulation.json()["questions"]) == 22
        assert simulation.json()["max_score"] == 150
        assert all(item["difficulty_band"] == "advanced" for item in simulation.json()["questions"])
        cancellable = client.post(
            "/api/simulations",
            json={"user_id": "cancel-user", "exam_type": "数学二", "year": 2025, "duration_minutes": 180},
        )
        assert cancellable.status_code == 200
        cancelled_id = cancellable.json()["id"]
        assert client.delete(f"/api/simulations/{cancelled_id}").status_code == 403
        cancelled = client.delete(f"/api/simulations/{cancelled_id}", params={"user_id": "cancel-user"})
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "cancelled"
        assert client.get(f"/api/simulations/{cancelled_id}").status_code == 404
        simulation_question = simulation.json()["questions"][0]
        simulation_upload = client.post(
            "/api/uploads/answer-image",
            data={"user_id": "local-user", "question_id": simulation_question["id"]},
            files={"file": ("simulation-answer.png", b"\x89PNG\r\n\x1a\nsimulation-test-image", "image/png")},
        )
        simulation_submit = client.post(
            f"/api/simulations/{simulation.json()['id']}/submit",
            json={
                "user_id": "local-user",
                "answers": {},
                "attachment_ids": {simulation_question["id"]: [simulation_upload.json()["attachment_id"]]},
            },
        )
        assert simulation_upload.status_code == 200
        assert simulation_submit.status_code == 200
        submitted_question = next(item for item in simulation_submit.json()["questions"] if item["id"] == simulation_question["id"])
        assert len(submitted_question["attempt"]["attachments"]) == 1
    finally:
        database.DB_PATH = original_db_path
        database.ROOT_DIR = original_database_root
        database.UPLOADS_DIR = original_uploads_dir
        main_module.ROOT_DIR = original_main_root
        main_module.UPLOADS_DIR = original_main_uploads


def test_auth_sessions_rbac_and_per_user_data_isolation(tmp_path: Path) -> None:
    """The browser identity, not a submitted user_id, owns every private record."""
    from fastapi.testclient import TestClient

    import app.database as database
    import app.main as main_module
    from app.main import app
    import app.services.auth as auth_service

    original_db_path = database.DB_PATH
    original_database_root = database.ROOT_DIR
    original_uploads_dir = database.UPLOADS_DIR
    original_main_root = main_module.ROOT_DIR
    original_main_uploads = main_module.UPLOADS_DIR
    database.DB_PATH = tmp_path / "auth.sqlite3"
    database.ROOT_DIR = tmp_path
    database.UPLOADS_DIR = tmp_path / "data" / "uploads"
    main_module.ROOT_DIR = tmp_path
    main_module.UPLOADS_DIR = tmp_path / "data" / "uploads"
    auth_service._RATE_LIMIT_BUCKETS.clear()
    question = next(item for item in load_questions() if item["question_type"] == "choice" and item["has_answer"])
    try:
        with TestClient(app) as client:
            # A pre-account local workspace remains usable and is claimed by
            # the first account during registration.
            legacy_attempt = client.post(
                f"/api/questions/{question['id']}/attempts",
                json={"user_id": "local-user", "answer": question["answer_markdown"], "mode": "practice"},
            )
            assert legacy_attempt.status_code == 200
            assert client.get("/api/auth/me").status_code == 401

            registered = client.post(
                "/api/auth/register",
                json={"username": "admin_one", "email": "admin@example.test", "display_name": "管理员", "password": "correct-horse-battery"},
            )
            assert registered.status_code == 200
            admin_payload = registered.json()
            admin = admin_payload["user"]
            admin_csrf = admin_payload["csrf_token"]
            assert admin["role"] == "admin"
            assert isinstance(admin["preferences"], dict)
            assert not {"password_hash", "id_hash", "csrf_hash"} & set(admin)
            assert client.get("/api/auth/me").json()["user"]["id"] == admin["id"]
            assert client.get("/api/progress").json()["attempts"] == 1
            health_headers = client.get("/api/health").headers
            assert health_headers["x-content-type-options"] == "nosniff"
            assert health_headers["cache-control"] == "no-store"

            # Mutating requests require the double-submit CSRF token.
            missing_csrf = client.post(
                f"/api/questions/{question['id']}/attempts",
                json={"answer": question["answer_markdown"], "mode": "practice"},
            )
            assert missing_csrf.status_code == 403

            created_note = client.post(
                "/api/workbench/notes",
                headers={"X-CSRF-Token": admin_csrf},
                json={"title": "管理员私有笔记", "content_markdown": "仅管理员可见"},
            )
            assert created_note.status_code == 200
            upload = client.post(
                "/api/uploads/answer-image",
                headers={"X-CSRF-Token": admin_csrf},
                data={"question_id": question["id"]},
                files={"file": ("private.png", b"\x89PNG\r\n\x1a\nprivate", "image/png")},
            )
            assert upload.status_code == 200

            # A second account receives an isolated workspace and cannot enter
            # admin APIs or spoof the first account through query/body fields.
            client_two = TestClient(app)
            try:
                registered_two = client_two.post(
                    "/api/auth/register",
                    json={"username": "learner_two", "email": "learner@example.test", "display_name": "学习者", "password": "another-secure-pass"},
                )
                assert registered_two.status_code == 200
                learner_csrf = registered_two.json()["csrf_token"]
                learner = registered_two.json()["user"]
                assert learner["role"] == "user"
                assert client_two.get("/api/admin/overview").status_code == 403
                filtered_users = client.get("/api/admin/users", params={"search": "learner_two", "role": "user", "status": "active"})
                assert filtered_users.status_code == 200
                assert len(filtered_users.json()["items"]) == 1
                assert filtered_users.json()["items"][0]["attempt_count"] == 0
                assert client_two.get("/api/progress", params={"user_id": admin["id"]}).json()["attempts"] == 0
                assert client_two.get("/api/workbench/notes", params={"user_id": admin["id"]}).json()["items"] == []
                assert client_two.get(f"/api/attachments/{upload.json()['attachment_id']}", params={"user_id": learner["id"]}).status_code == 404

                learner_attempt = client_two.post(
                    f"/api/questions/{question['id']}/attempts",
                    headers={"X-CSRF-Token": learner_csrf},
                    json={"user_id": admin["id"], "answer": question["answer_markdown"], "mode": "practice"},
                )
                assert learner_attempt.status_code == 200
                assert client.get("/api/progress", params={"user_id": learner["id"]}).json()["attempts"] == 1

                # Only the admin session can change roles and server binding.
                assert client_two.post("/api/server/settings", headers={"X-CSRF-Token": learner_csrf}, json={"host": "127.0.0.1", "port": 8001}).status_code == 403
                promoted = client.patch(
                    f"/api/admin/users/{learner['id']}",
                    headers={"X-CSRF-Token": admin_csrf},
                    json={"role": "admin", "is_active": True, "display_name": "学习管理员"},
                )
                assert promoted.status_code == 200
                assert promoted.json()["user"]["role"] == "admin"
                assert client.get("/api/admin/audit").json()["items"]
                revoked = client.post(
                    f"/api/admin/users/{learner['id']}/sessions/revoke",
                    headers={"X-CSRF-Token": admin_csrf},
                )
                assert revoked.status_code == 200
                assert revoked.json()["revoked"] >= 1
                assert client.get("/api/admin/audit", params={"action": "admin-sessions-revoked"}).json()["items"]
                # Deactivation revokes all sessions, so the old learner cookie
                # cannot be reused after an administrator change.
                deactivated = client.patch(
                    f"/api/admin/users/{learner['id']}",
                    headers={"X-CSRF-Token": admin_csrf},
                    json={"role": "user", "is_active": False, "display_name": "学习者"},
                )
                assert deactivated.status_code == 200
                assert client_two.get("/api/auth/me").status_code == 401
            finally:
                client_two.close()
    finally:
        database.DB_PATH = original_db_path
        database.ROOT_DIR = original_database_root
        database.UPLOADS_DIR = original_uploads_dir
        main_module.ROOT_DIR = original_main_root
        main_module.UPLOADS_DIR = original_main_uploads


def test_fine_grained_practice_session_can_save_and_submit(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    import app.database as database
    from app.main import app

    original_db_path = database.DB_PATH
    database.DB_PATH = tmp_path / "practice.sqlite3"
    try:
        with TestClient(app) as client:
            blocks = client.get("/api/study/blocks", params={"user_id": "local-user", "limit": 12})
            assert blocks.status_code == 200
            target_block = next(
                block for block in blocks.json()["blocks"]
                if any(item["question_count"] >= 15 for item in block["question_types"])
            )
            target_type = next(item for item in target_block["question_types"] if item["question_count"] >= 15)
            session = client.post(
                "/api/practice/sessions",
                json={
                    "user_id": "local-user",
                    "exam_type": "数学二",
                    "concept_id": target_block["concept"]["id"],
                    "question_type": target_type["question_type"],
                    "count": 15,
                },
            )
            assert session.status_code == 200
            session_json = session.json()
            questions = session_json["questions"]
            assert len(questions) == 15
            assert len({question["id"] for question in questions}) == 15
            assert all(question["question_type"] == target_type["question_type"] for question in questions)
            assert all(target_block["concept"]["id"] in question["concept_ids"] for question in questions)

            first_id = questions[0]["id"]
            saved = client.put(
                f"/api/practice/sessions/{session_json['id']}",
                json={"answers": {first_id: "$x^2$"}},
            )
            assert saved.status_code == 200
            saved_first = next(item for item in saved.json()["questions"] if item["id"] == first_id)
            assert saved_first["answer_state"]["answer"] == "$x^2$"
            assert saved.json()["status"] == "active"

            submitted = client.post(
                f"/api/practice/sessions/{session_json['id']}/submit",
                json={"answers": {first_id: "$x^2$"}},
            )
            assert submitted.status_code == 200
            submitted_json = submitted.json()
            assert submitted_json["status"] == "finished"
            assert submitted_json["question_count"] == 15
            submitted_first = next(item for item in submitted_json["questions"] if item["id"] == first_id)
            assert submitted_first["answer_state"]["result"] is not None
            assert submitted_first["answer_state"]["attempt_id"] is not None
    finally:
        database.DB_PATH = original_db_path
