from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "data" / "sources"
OUTPUT_PATH = ROOT / "data" / "processed" / "questions.json"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.concepts import infer_concepts

SECTION_RE = re.compile(r"(?m)^##\s+(.+?)\s*$")
QUESTION_RE = re.compile(r"(?m)^###\s+(.+?)\s*$")
SOLUTION_MARKER = r"(?:解析\s*[:：]|解\s*[:：]|[（(]\s*1\s*[）)]\s*(?:证明|解)\s*[:：])"
ANSWER_RE = re.compile(rf"(?ms)^\s*>?\s*\*\*答案\s*[:：]\*\*\s*(.*?)(?=^\s*>?\s*\*\*{SOLUTION_MARKER}\*\*|\Z)")
SOLUTION_RE = re.compile(rf"(?ms)^\s*>?\s*\*\*{SOLUTION_MARKER}\*\*\s*(.*)\Z")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig").replace("\r\n", "\n")


def first_number(label: str, fallback: int) -> int:
    match = re.search(r"\d+", label)
    return int(match.group(0)) if match else fallback


def section_kind(section: str, block: str) -> str:
    combined = f"{section}\n{block}"
    if "选择" in section or re.search(r"(?m)^\s*(?:[-*]\s*)?(?:\*\*)?[A-D][.、：:]", block):
        return "choice"
    if "填空" in section:
        return "fill"
    if any(token in section for token in ("解答", "计算", "证明", "综合")):
        return "solution"
    if "____" in combined or "______" in combined or "空" in combined:
        return "fill"
    return "solution"


def section_points(kind: str, block: str) -> int:
    full_mark = re.search(r"满分[^0-9]{0,12}(\d+)[^0-9]{0,12}分", block)
    if full_mark:
        return int(full_mark.group(1))
    return 5 if kind in {"choice", "fill"} else 10


def extract_answer(block: str) -> tuple[str, str, bool, bool]:
    answer_match = ANSWER_RE.search(block)
    solution_match = SOLUTION_RE.search(block)
    answer = answer_match.group(1).strip() if answer_match else ""
    solution = solution_match.group(1).strip() if solution_match else ""
    markers = [match.start() for match in (answer_match, solution_match) if match]
    content_end = min(markers) if markers else len(block)
    content = block[:content_end].strip()
    lines = content.splitlines()
    if lines and lines[0].startswith("###"):
        lines = lines[1:]
    content = "\n".join(lines).strip()
    if content.startswith("**题目：**"):
        content = content[len("**题目：**") :].strip()
    return content, answer, solution, bool(answer_match), bool(solution_match)


def extract_section_question(section_body: str) -> tuple[str, str, str, bool, bool]:
    """Read a question stored directly under a ## section.

    Some older source files put a long question under ``##`` and use nested
    ``###`` headings only for solution sub-parts.  The importer keeps the
    source wording instead of dropping that parent question.
    """
    marker = re.search(r"(?m)^\s*\*\*题目\s*[:：]\*\*", section_body)
    if not marker:
        return "", "", "", False, False
    tail = section_body[marker.end() :]
    stop = re.search(rf"(?m)^\s*(?:###\s+|\*\*答案\s*[:：]\*\*|\*\*{SOLUTION_MARKER}\*\*)", tail)
    content = tail[: stop.start() if stop else len(tail)].strip()
    answer_match = re.search(rf"(?ms)^\s*\*\*答案\s*[:：]\*\*\s*(.*?)(?=^\s*\*\*{SOLUTION_MARKER}\*\*|\Z)", section_body)
    solution_match = re.search(rf"(?ms)^\s*\*\*{SOLUTION_MARKER}\*\*\s*(.*)\Z", section_body)
    return (
        content,
        answer_match.group(1).strip() if answer_match else "",
        solution_match.group(1).strip() if solution_match else "",
        bool(answer_match),
        bool(solution_match),
    )


def source_files(repo_dir: Path, exam_type: str) -> list[Path]:
    if not repo_dir.exists():
        return []
    files = []
    for path in repo_dir.rglob("*.md"):
        if path.name.lower() == "readme.md":
            continue
        if re.match(r"^\d{4}-[123]\.md$", path.name) and "刷题版" in str(path.parent):
            files.append(path)
        elif exam_type != "数学二" and re.match(r"^\d{4}-[123]\.md$", path.name):
            files.append(path)
    return sorted(files, key=lambda item: item.name)


def parse_file(path: Path, exam_type: str, source_url: str) -> list[dict[str, Any]]:
    raw = read_text(path)
    question_matches = list(QUESTION_RE.finditer(raw))
    section_matches = list(SECTION_RE.finditer(raw))
    if not question_matches and not section_matches:
        return []
    parsed: list[dict[str, Any]] = []
    year_match = re.match(r"(\d{4})", path.name)
    year = int(year_match.group(1)) if year_match else 0

    section_ranges = []
    for section_index, section_match in enumerate(section_matches):
        section_end = section_matches[section_index + 1].start() if section_index + 1 < len(section_matches) else len(raw)
        section_ranges.append((section_match, section_end))

    def section_for(position: int) -> tuple[str, int, str]:
        for section_match, section_end in section_ranges:
            if section_match.start() < position < section_end:
                return section_match.group(1).strip(), section_match.start(), raw[section_match.end() : section_end]
        return "未分类", -1, ""

    for index, match in enumerate(question_matches):
        start = match.start()
        end = question_matches[index + 1].start() if index + 1 < len(question_matches) else len(raw)
        block = raw[start:end].strip()
        label = match.group(1).strip()
        number = first_number(label, index + 1)
        section, section_start, _ = section_for(start)
        content, answer, solution, has_answer, has_solution = extract_answer(block)
        kind = section_kind(section, block)
        concepts = infer_concepts(f"{section}\n{content}", section)
        relative = path.relative_to(ROOT).as_posix()
        question_id = f"{exam_type}-{year}-{number:02d}-{index + 1:02d}"
        parsed.append(
            {
                "id": question_id,
                "exam_type": exam_type,
                "year": year,
                "number": number,
                "label": label,
                "section": section,
                "question_type": kind,
                "points": section_points(kind, block),
                "question_markdown": content,
                "answer_markdown": answer,
                "solution_markdown": solution,
                "raw_markdown": block,
                "concept_ids": concepts,
                "difficulty": 2 + ((number + year) % 4),
                "source_path": relative,
                "source_url": source_url,
                "source_license_status": "requires-author-confirmation-before-public-or-commercial-redistribution",
                "has_answer": has_answer,
                "has_solution": has_solution,
                "content_complete": bool(content.strip()),
                "content_sha256": hashlib.sha256(block.encode("utf-8")).hexdigest(),
                "_section_start": section_start,
            }
        )

    # Older files use a parent **题目：** before ### solution sub-parts.  Put
    # that exact parent text into each sub-part so no question stem is lost.
    for section_match, section_end in section_ranges:
        section = section_match.group(1).strip()
        section_body = raw[section_match.end() : section_end]
        section_questions = [match for match in question_matches if section_match.start() < match.start() < section_end]
        parent_content, _, _, _, _ = extract_section_question(section_body)
        if not parent_content or not section_questions:
            continue
        for item in parsed:
            if item.get("_section_start") == section_match.start() and not item.get("question_markdown", "").strip():
                item["question_markdown"] = f"{parent_content}\n\n**本小题：** {item['label']}"
                item["content_complete"] = True
                item["concept_ids"] = infer_concepts(f"{section}\n{item['question_markdown']}", section)

    # A few older sections contain one complete question without any ###
    # heading at all.  Add it as a real question rather than silently omitting
    # it from the library and full-paper simulation.
    for section_match, section_end in section_ranges:
        section = section_match.group(1).strip()
        section_body = raw[section_match.end() : section_end]
        has_subsections = any(section_match.start() < match.start() < section_end for match in question_matches)
        if has_subsections:
            continue
        content, answer, solution, has_answer, has_solution = extract_section_question(section_body)
        if not content:
            continue
        block = raw[section_match.start() : section_end].strip()
        number = len(parsed) + 1
        kind = section_kind(section, block)
        parsed.append(
            {
                "id": f"{exam_type}-{year}-{number:02d}-{len(parsed) + 1:02d}",
                "exam_type": exam_type,
                "year": year,
                "number": number,
                "label": section,
                "section": section,
                "question_type": kind,
                "points": section_points(kind, block),
                "question_markdown": content,
                "answer_markdown": answer,
                "solution_markdown": solution,
                "raw_markdown": block,
                "concept_ids": infer_concepts(f"{section}\n{content}", section),
                "difficulty": 2 + ((number + year) % 4),
                "source_path": path.relative_to(ROOT).as_posix(),
                "source_url": source_url,
                "source_license_status": "requires-author-confirmation-before-public-or-commercial-redistribution",
                "has_answer": has_answer,
                "has_solution": has_solution,
                "content_complete": True,
                "content_sha256": hashlib.sha256(block.encode("utf-8")).hexdigest(),
                "_section_start": section_match.start(),
            }
        )

    for item in parsed:
        item.pop("_section_start", None)
    return parsed


def build_questions() -> list[dict[str, Any]]:
    sources = [
        ("数学一", SOURCE_ROOT / "kysx1-zt", "https://github.com/zhaokaifengcom/kysx1-zt"),
        ("数学二", SOURCE_ROOT / "kysx2-zt", "https://github.com/zhaokaifengcom/kysx2-zt"),
        ("数学三", SOURCE_ROOT / "kysx3-zt", "https://github.com/zhaokaifengcom/kysx3-zt"),
    ]
    questions: list[dict[str, Any]] = []
    for exam_type, repo_dir, source_url in sources:
        for path in source_files(repo_dir, exam_type):
            questions.extend(parse_file(path, exam_type, source_url))
    questions.sort(key=lambda item: (item["exam_type"], item["year"], item["number"], item["id"]))
    return questions


def main() -> int:
    questions = build_questions()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(questions, ensure_ascii=False, indent=2), encoding="utf-8")
    summary: dict[str, dict[str, int]] = {}
    for question in questions:
        bucket = summary.setdefault(question["exam_type"], {"questions": 0, "with_answer": 0, "with_solution": 0, "years": 0})
        bucket["questions"] += 1
        bucket["with_answer"] += int(question["has_answer"])
        bucket["with_solution"] += int(question["has_solution"])
    for exam_type, values in summary.items():
        years = sorted({item["year"] for item in questions if item["exam_type"] == exam_type})
        values["years"] = len(years)
        values["year_from"] = years[0] if years else 0
        values["year_to"] = years[-1] if years else 0
    print(json.dumps({"output": str(OUTPUT_PATH), "total": len(questions), "summary": summary}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
