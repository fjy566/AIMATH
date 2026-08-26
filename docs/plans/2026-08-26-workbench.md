# 砺数 Workbench Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a local-first Workbench for Math II answer templates, real examples and variants, rich study notes, and progress-aware navigation.

**Architecture:** Keep the existing FastAPI + SQLite + static JavaScript application. Generate the complete template catalog from the ten active Math II knowledge blocks and three question types, select real questions from the imported question store, and persist notes, note assets, versions, and user template overrides in SQLite. Add one responsive Workbench view that uses the existing KaTeX renderer and CSS token system without a new frontend dependency.

**Tech Stack:** FastAPI, Pydantic, SQLite, vanilla JavaScript, native `contenteditable`, Markdown textarea, Pointer Events canvas, KaTeX.

---

### Task 1: Workbench data and persistence

**Files:**
- Create: `app/services/workbench.py`
- Modify: `app/database.py`
- Modify: `app/main.py`
- Test: `tests/test_core.py`

Implement template copy for every Math II knowledge block and question type, real-question example selection with subject fallback for sparse buckets, note CRUD, note asset upload, version history, template overrides, and JSON import/export endpoints.

Verification: exercise catalog coverage, real question IDs, note version creation, restore, and import/export with the existing pytest suite.

### Task 2: Workbench surface

**Files:**
- Modify: `app/static/index.html`
- Modify: `app/static/app.js`
- Modify: `app/static/styles.css`

Add Workbench navigation and view, template tabs, example/variant previews, searchable/favorite notes, rich editing, Markdown shortcuts, image insertion, handwriting canvas, mind-map branches, theme toggle, and JSON import/export controls. Collapse the sidebar/editor layout for narrow viewports and respect reduced-motion preferences.

Verification: `node --check app/static/app.js`, desktop and 390px browser checks for loading templates, opening a real example, creating/editing a note, and mobile overflow.

### Task 3: Regression and delivery

Run the backend tests with the repository's Windows compatibility shim, compile checks, frontend syntax checks, `git diff --check`, the Impeccable detector once on changed UI files, and browser smoke checks in both themes. Commit the feature and push `main` to `origin`, then compare the remote SHA with the local commit.
