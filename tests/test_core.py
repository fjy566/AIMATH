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


def test_frontend_formula_renderer_is_shared_by_rich_text_surfaces() -> None:
    source = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")
    markup = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")

    assert "const TEX_COMMAND_PATTERN" in source
    assert "function normalizeTexSource" in source
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
    assert 'renderLearningText(item.focus, "template-format-focus")' in source
    assert 'renderLearningText(item.steps, "template-format-steps")' in source
    assert 'renderLearningText(item.finish, "template-format-finish")' in source
    assert 'renderLearningText(item.task, "template-practice-task")' in source
    assert "renderLearningText(item.standard)" in source
    assert 'renderLearningText(item, "template-check-item")' in source
    assert ".template-quick-nav" in styles
    assert ".template-format-grid" in styles


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


def test_tex_normalization_preserves_array_row_break_before_command() -> None:
    from app.services.workbench import _normalize_template_formula

    assert _normalize_template_formula(r"$\\left(x\\right)$") == r"$\left(x\right)$"
    array_formula = r"$\begin{array}{l}y^{\prime}+ay=f(x),\\\left.y\right|_{x=0}=0\end{array}$"
    assert _normalize_template_formula(array_formula) == array_formula


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
        assert saved["launch_command"] == "python scripts/run_server.py"
        with pytest.raises(ServerSettingsError):
            save_server_settings("bad host", 8123)
        with pytest.raises(ServerSettingsError):
            save_server_settings("127.0.0.1", 70000)
    finally:
        database.DB_PATH = original_db_path


def test_openai_compatible_url_normalization() -> None:
    assert _api_root("http://127.0.0.1:11434") == "http://127.0.0.1:11434/v1"
    assert _api_root("http://127.0.0.1:11434/v1") == "http://127.0.0.1:11434/v1"
    assert _api_root("http://127.0.0.1:11434/v1/models") == "http://127.0.0.1:11434/v1"


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
