"""Assemble the static site in _site: the page, the examples, the evaluation numbers and the checker's Python.

Vercel runs this as the build step; the live tutor itself is the function in api/review.py.
"""

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "_site"
CHECKER = ["__init__.py", "check/__init__.py", "check/parser.py", "check/equality.py"]


def main() -> None:
    shutil.rmtree(OUT, ignore_errors=True)
    shutil.copytree(ROOT / "site", OUT)
    shutil.copy(ROOT / "data/demo/exercises.json", OUT / "data/examples.json")
    shutil.copy(ROOT / "reports/agent.json", OUT / "data/agent.json")
    for name in CHECKER:
        target = OUT / "py/mathhinter" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        source = ROOT / "src/mathhinter" / name
        target.write_text(source.read_text(encoding="utf-8") if source.exists() else "", encoding="utf-8")
    (OUT / ".nojekyll").write_text("")
    (OUT / "data/corpus.json").unlink()  # the course is only needed by the function
    examples = json.loads((OUT / "data/examples.json").read_text(encoding="utf-8"))["exercises"]
    print(f"built {OUT} with {len(examples)} examples")


if __name__ == "__main__":
    main()
