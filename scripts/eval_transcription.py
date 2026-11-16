"""Does reading a photo keep the student's error? Photo → transcription → review, against the typed attempt.

For each example attempt (8 with a planted error, 8 correct) this reads the rendered photo in data/demo/photos,
compares the transcription with the typed text line by line, and reviews both with the same tutor. Writes
reports/transcription.json and .md.

The photos are typeset, not handwritten (see scripts/render_photos.js), so this measures whether transcription keeps
errors and line breaks, not how well it reads handwriting.

    PYTHONPATH=src python scripts/eval_transcription.py
"""

from __future__ import annotations

import base64
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from mathhinter.agent.course import CourseSearch  # noqa: E402
from mathhinter.agent.tutor import Tutor  # noqa: E402
from mathhinter.llm.client import Client, read_env  # noqa: E402
from mathhinter.transcribe import VISION_MODEL, transcribe  # noqa: E402
from mathhinter.web import MODEL  # noqa: E402


def normal(text: str) -> str:
    """A line without the spacing and notation choices that don't change its meaning."""
    for old, new in [("∈", "\\in"), ("≤", "\\le"), ("≥", "\\ge"), ("≠", "\\neq"), ("−", "-"), ("×", "\\times"),
                     ("→", "\\to"), ("∞", "\\infty"), ("π", "\\pi"), ("·", "\\cdot")]:
        text = text.replace(old, new)
    text = re.sub(r"\\(sin|cos|tan|ln|exp|lim)\b", r"\1", text)  # \sin and sin read the same
    text = re.sub(r"\\[,;:! ]|\\left|\\right|\\displaystyle|\$|\s|\.$", "", text)
    for old, new in [("\\dfrac", "\\frac"), ("\\tfrac", "\\frac"), ("\\leqslant", "\\le"), ("\\leq", "\\le")]:
        text = text.replace(old, new)
    text = text.replace("{", "").replace("}", "").replace("\\mathrm", "").replace("\\operatorname", "")
    return text.replace("’", "'").replace("−", "-").lower()


def judged(review, attempt) -> bool:
    if review.failure:
        return False
    if attempt["kind"] == "control":
        return review.verdict == "correct"
    return review.verdict == "wrong" and review.first_wrong_line == attempt["wrong_line"]


def main() -> None:
    key = read_env(ROOT / ".env")["GROQ_API_KEY"]
    client = Client(key, ROOT / "data/private/llm_cache")
    units = json.loads((ROOT / "site/data/corpus.json").read_text(encoding="utf-8"))["units"]
    tutor = Tutor(client, MODEL, CourseSearch(units))
    exercises = json.loads((ROOT / "data/demo/exercises.json").read_text(encoding="utf-8"))["exercises"]
    rows = []
    for exercise in exercises:
        for attempt in exercise["attempts"]:
            name = f"{exercise['id'].replace(':', '-')}-{attempt['kind']}.jpg"
            photo = (ROOT / "data/demo/photos" / name).read_bytes()
            image = "data:image/jpeg;base64," + base64.b64encode(photo).decode()
            typed = attempt["text"].split("\n")
            read = transcribe(client, [image])
            same = [i < len(read["lines"]) and normal(read["lines"][i]) == normal(line) for i, line in enumerate(typed)]
            row = {"photo": name, "kind": attempt["kind"], "typed_lines": len(typed), "read_lines": len(read["lines"]),
                   "lines_identical": sum(same), "differences": [
                       {"line": i, "typed": typed[i], "read": read["lines"][i] if i < len(read["lines"]) else None}
                       for i, ok in enumerate(same) if not ok]}
            if attempt["kind"] == "wrong":
                i = attempt["wrong_line"]
                row["error_line_identical"] = same[i]
            review_typed = tutor.rag(exercise["statement"], attempt["text"], "web", solution="")
            review_photo = tutor.rag(read["statement"] or exercise["statement"], "\n".join(read["lines"]), "web",
                                     solution="")
            row["typed_review_right"] = judged(review_typed, attempt)
            row["photo_review_right"] = judged(review_photo, attempt)
            row["photo_review"] = {"verdict": review_photo.verdict, "line": review_photo.first_wrong_line}
            rows.append(row)
            print(name, row["read_lines"], "/", row["typed_lines"], "identical", row["lines_identical"],
                  "error kept" if row.get("error_line_identical") else "", row["typed_review_right"],
                  row["photo_review_right"])
    wrong = [r for r in rows if r["kind"] == "wrong"]
    summary = {
        "photos": len(rows), "vision_model": VISION_MODEL, "review_model": MODEL, "review_config": "rag",
        "same_line_count": sum(r["read_lines"] == r["typed_lines"] for r in rows),
        "lines_identical": sum(r["lines_identical"] for r in rows), "lines": sum(r["typed_lines"] for r in rows),
        "error_line_identical": sum(r["error_line_identical"] for r in wrong), "wrong_attempts": len(wrong),
        "typed_reviews_right": sum(r["typed_review_right"] for r in rows),
        "photo_reviews_right": sum(r["photo_review_right"] for r in rows),
    }
    (ROOT / "reports/transcription.json").write_text(
        json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    write_markdown(summary, rows)


def write_markdown(s: dict, rows: list[dict]) -> None:
    lines = [
        "# Reading photos", "",
        "Generated by `scripts/eval_transcription.py`. Each of the 16 example attempts (8 with a planted error, 8 "
        "correct) was rendered as a notebook page by `scripts/render_photos.js`, read by "
        f"`{s['vision_model']}`, and reviewed by `{s['review_model']}` with the course, once from the typed text "
        "and once from the transcription.", "",
        "The pages are typeset maths in a handwriting font, much easier than real handwriting. This checks that "
        "transcription keeps the student's errors and line breaks; it does not measure reading real handwriting, "
        "which needs real photos.", "",
        "Lines count as identical when they match up to spacing and notation (LaTeX or Unicode, `\\sin` or `sin`).", "",
        "| | Result |", "|---|---|",
        f"| Same number of lines as typed | {s['same_line_count']} / {s['photos']} |",
        f"| Lines read identically | {s['lines_identical']} / {s['lines']} |",
        f"| Planted error line read identically | {s['error_line_identical']} / {s['wrong_attempts']} |",
        f"| Review right, typed attempt | {s['typed_reviews_right']} / {s['photos']} |",
        f"| Review right, photo attempt | {s['photo_reviews_right']} / {s['photos']} |", "",
        "A review is right when it names the planted line, or finds nothing in a correct attempt. "
        "With 16 attempts these are checks, not estimates.", "",
        "## Lines read differently", "",
    ]
    for row in rows:
        for d in row["differences"]:
            lines.append(f"- `{row['photo']}`, line {d['line']}: typed `{d['typed']}`, read `{d['read']}`")
    if not any(r["differences"] for r in rows):
        lines.append("None.")
    (ROOT / "reports/transcription.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
