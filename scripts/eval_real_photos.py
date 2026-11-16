"""Real photographed attempts: how well they are read, and whether the review is still right.

Step 1, read:  put the photos in data/private/real_photos/ (git-ignored: classmates' work never enters the repo),
               then run
                   PYTHONPATH=src python scripts/eval_real_photos.py read
               It writes data/private/real_photos/readings.json: for each photo (or group of pages named
               name-1.jpg, name-2.jpg...), the statement and lines as read.
Step 2, check: open readings.json. For each attempt, correct "corrected_lines" to what the student actually wrote
               (one step per line) and set "wrong_line" to the number (from 1) of the first wrong line in
               corrected_lines, or null if the attempt is right.
Step 3, score:     PYTHONPATH=src python scripts/eval_real_photos.py score
               It reviews each attempt from the raw reading and from the corrected text and writes
               reports/real_photos.json and .md: numbers only, no student text.
"""

from __future__ import annotations

import base64
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

FOLDER = ROOT / "data/private/real_photos"
READINGS = FOLDER / "readings.json"
TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}


def groups(folder: Path) -> dict[str, list[Path]]:
    """Photos grouped by attempt: amina-1.jpg and amina-2.jpg are two pages of 'amina'."""
    found = defaultdict(list)
    for path in sorted(folder.iterdir()):
        if path.suffix.lower() in TYPES:
            found[re.sub(r"-\d+$", "", path.stem)].append(path)
    return dict(found)


def data_url(path: Path) -> str:
    """The photo shrunk as the site does (longest side 1600 px) when Pillow is available."""
    try:
        from io import BytesIO

        from PIL import Image, ImageOps
        image = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
        image.thumbnail((1600, 1600))
        buffer = BytesIO()
        image.save(buffer, "JPEG", quality=85)
        return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode()
    except ImportError:
        return f"data:{TYPES[path.suffix.lower()]};base64," + base64.b64encode(path.read_bytes()).decode()


def client():
    from mathhinter.llm.client import Client, read_env
    return Client(read_env(ROOT / ".env")["GROQ_API_KEY"], ROOT / "data/private/llm_cache")


def read() -> None:
    from mathhinter.transcribe import transcribe
    readings = json.loads(READINGS.read_text(encoding="utf-8")) if READINGS.exists() else {"attempts": {}}
    for name, pages in groups(FOLDER).items():
        if name in readings["attempts"]:
            continue
        result = transcribe(client(), [data_url(p) for p in pages])
        readings["attempts"][name] = {"photos": [p.name for p in pages], "statement": result["statement"],
                                      "read_lines": result["lines"], "unclear": result["unclear"],
                                      "corrected_statement": result["statement"],
                                      "corrected_lines": result["lines"], "wrong_line": "TO FILL: number or null"}
        print(name, len(result["lines"]), "lines")
        READINGS.write_text(json.dumps(readings, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Now correct and label {READINGS.relative_to(ROOT)}, then run: score")


def judged(review, wrong_line) -> bool:
    if review.failure:
        return False
    if wrong_line is None:
        return review.verdict == "correct"
    return review.verdict == "wrong" and review.first_wrong_line == wrong_line


def score() -> None:
    from eval_transcription import normal
    from mathhinter.agent.course import CourseSearch
    from mathhinter.agent.tutor import Tutor
    from mathhinter.web import MODEL
    units = json.loads((ROOT / "site/data/corpus.json").read_text(encoding="utf-8"))["units"]
    tutor = Tutor(client(), MODEL, CourseSearch(units))
    attempts = json.loads(READINGS.read_text(encoding="utf-8"))["attempts"]
    rows = []
    for name, a in attempts.items():
        if isinstance(a["wrong_line"], str):
            sys.exit(f"{name}: set wrong_line to a line number (from 1) or null before scoring")
        wrong = None if a["wrong_line"] is None else int(a["wrong_line"]) - 1
        corrected, read_lines = a["corrected_lines"], a["read_lines"]
        same = sum(i < len(read_lines) and normal(read_lines[i]) == normal(line) for i, line in enumerate(corrected))
        statement = a["corrected_statement"] or a["statement"]
        from_reading = tutor.rag(a["statement"] or statement, "\n".join(read_lines), "web", solution="")
        from_corrected = tutor.rag(statement, "\n".join(corrected), "web", solution="")
        # From the raw reading, the wrong line is right if it names the same line, when the line count agrees.
        rows.append({"has_error": wrong is not None, "lines": len(corrected), "read_lines": len(read_lines),
                     "lines_read_right": same, "unclear_marked": len(a["unclear"]),
                     "review_right_from_reading": len(read_lines) == len(corrected) and judged(from_reading, wrong),
                     "review_right_from_corrected": judged(from_corrected, wrong)})
        print(name, rows[-1])
    summary = {"attempts": len(rows), "with_error": sum(r["has_error"] for r in rows),
               "lines": sum(r["lines"] for r in rows), "lines_read_right": sum(r["lines_read_right"] for r in rows),
               "same_line_count": sum(r["lines"] == r["read_lines"] for r in rows),
               "review_right_from_reading": sum(r["review_right_from_reading"] for r in rows),
               "review_right_from_corrected": sum(r["review_right_from_corrected"] for r in rows)}
    (ROOT / "reports/real_photos.json").write_text(json.dumps({"summary": summary, "rows": rows}, indent=1) + "\n",
                                                   encoding="utf-8")
    s = summary
    (ROOT / "reports/real_photos.md").write_text("\n".join([
        "# Real photographed attempts", "",
        "Generated by `scripts/eval_real_photos.py score`. Classmates' handwritten attempts, photographed, read by "
        "the site's vision model, then corrected and labelled by hand. Their text stays private; only these numbers "
        "are published.", "",
        "| | Result |", "|---|---|",
        f"| Attempts (with an error) | {s['attempts']} ({s['with_error']}) |",
        f"| Lines read right, up to notation | {s['lines_read_right']} / {s['lines']} |",
        f"| Same number of lines as written | {s['same_line_count']} / {s['attempts']} |",
        f"| Review right, from the raw reading | {s['review_right_from_reading']} / {s['attempts']} |",
        f"| Review right, from the corrected text | {s['review_right_from_corrected']} / {s['attempts']} |", "",
        "A review is right when it names the first wrong line, or finds nothing in a right attempt. From the raw "
        "reading it also needs the reading to have the right number of lines, so line numbers match.", ""]),
        encoding="utf-8")


if __name__ == "__main__":
    {"read": read, "score": score}.get(sys.argv[1] if len(sys.argv) > 1 else "", lambda: sys.exit(__doc__))()
