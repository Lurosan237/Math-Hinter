"""Score jurors and voting rules from a panel run, as ProcessBench does: accuracy on solutions with an error (the
exact first wrong step), accuracy on correct ones (nothing flagged), and their harmonic mean (F1).

    PYTHONPATH=src python scripts/score_panel.py --name panel-pb [--jurors 120b,20b,qwen-low] [--write]
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from mathhinter.jury import decide  # noqa: E402


def load(name: str) -> dict:
    rows = [json.loads(line) for line in
            (ROOT / "data/private/agent_runs" / name / "jurors.jsonl").read_text(encoding="utf-8").splitlines()]
    items: dict = {}
    for row in rows:
        items.setdefault((row["exercise"], row["kind"]), {"wrong_line": row["wrong_line"]})[row["juror"]] = row
    return items


def score(items: dict, jurors: list[str], needed: int) -> dict | None:
    error_right = error_n = clean_right = clean_n = 0
    for item in items.values():
        if not all(j in item for j in jurors):
            continue
        verdict, line, _ = decide([item[j] for j in jurors], needed)
        if item["wrong_line"] is None:
            clean_n += 1
            clean_right += verdict == "correct"
        else:
            error_n += 1
            error_right += verdict == "wrong" and line == item["wrong_line"]
    if not error_n or not clean_n:
        return None
    a, b = error_right / error_n, clean_right / clean_n
    return {"jurors": jurors, "needed": needed, "items": error_n + clean_n, "error_accuracy": round(a, 3),
            "correct_accuracy": round(b, 3), "f1": round(2 * a * b / (a + b), 3) if a + b else 0.0}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", default="panel-pb")
    parser.add_argument("--jurors", default="")
    parser.add_argument("--min-items", type=int, default=60)
    args = parser.parse_args()
    items = load(args.name)
    names = args.jurors.split(",") if args.jurors else sorted({k for i in items.values() for k in i} - {"wrong_line"})
    results = []
    for size in range(1, min(len(names), 5) + 1):
        for combo in itertools.combinations(names, size):
            for needed in range(1, size + 1):
                result = score(items, list(combo), needed)
                if result and result["items"] >= args.min_items:
                    results.append(result)
    for r in sorted(results, key=lambda r: -r["f1"])[:25]:
        print(f"{'+'.join(r['jurors']):40} {r['needed']}/{len(r['jurors'])}  n={r['items']:3}  "
              f"errors {r['error_accuracy']:.2f}  correct {r['correct_accuracy']:.2f}  F1 {r['f1']:.2f}")


if __name__ == "__main__":
    main()
