"""Assemble the static demo in _site: the page, its public data, the evaluation numbers and the checker's Python."""

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "_site"
CHECKER = ["__init__.py", "check/__init__.py", "check/parser.py", "check/equality.py"]


def main() -> None:
    shutil.rmtree(OUT, ignore_errors=True)
    shutil.copytree(ROOT / "site", OUT)
    shutil.copy(ROOT / "data/demo/exercises.json", OUT / "data/exercises.json")
    shutil.copy(ROOT / "reports/agent.json", OUT / "data/agent.json")
    for name in CHECKER:
        target = OUT / "py/mathhinter" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        source = ROOT / "src/mathhinter" / name
        target.write_text(source.read_text(encoding="utf-8") if source.exists() else "", encoding="utf-8")
    (OUT / ".nojekyll").write_text("")
    reviews = json.loads((OUT / "data/runs.json").read_text(encoding="utf-8"))["reviews"]
    print(f"built {OUT} with {len(reviews)} reviews")


if __name__ == "__main__":
    main()
