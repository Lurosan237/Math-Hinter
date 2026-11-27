"""Rebuild textbook solutions as a clean benchmark: one step per line, extraction damage repaired, then one planted
error per solution, as in the original evaluation set.

    PYTHONPATH=src python scripts/rebuild_bench.py rebuild --stop-after 150   # repeat until FINISHED
    PYTHONPATH=src python scripts/rebuild_bench.py plant

Exercises: the 20 development exercises used so far, and 50 test exercises never used in any evaluation (the 25 of
stages 4 and 6 are left out). Everything stays in data/private/clean_bench: it is derived from licensed books.
Repairs are marked per step, for checking by hand; solutions the model found doubtful are dropped.
"""

from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from mathhinter.evalset.corrupt import control, corrupt, first_wrong_line  # noqa: E402
from mathhinter.llm.client import Client, QuotaExhausted, read_env  # noqa: E402
from mathhinter.steps import split_and_repair  # noqa: E402
from run_agent import MAX_ATTEMPT_CHARS, sample  # noqa: E402

PRIVATE = ROOT / "data/private"
OUT = PRIVATE / "clean_bench"
NEW_TEST = 50
SEED = 1127


def chosen(attempts: list[dict]) -> dict[str, str]:
    """Exercise -> split. Fresh test exercises exclude every exercise already used in a test run."""
    used = set(sample(attempts, "test", 25))
    pool = sorted({a["exercise"] for a in attempts if a["split"] == "test" and len(a["text"]) <= MAX_ATTEMPT_CHARS}
                  - used)
    fresh = random.Random(SEED).sample(pool, NEW_TEST)
    return {**{e: "dev" for e in sample(attempts, "dev", 20)}, **{e: "test" for e in fresh}}


def rebuild(stop_after: float) -> None:
    attempts = [json.loads(line) for line in (PRIVATE / "attempts.jsonl").read_text(encoding="utf-8").splitlines()]
    units = {json.loads(line)["id"]: json.loads(line)
             for line in (PRIVATE / "units.jsonl").read_text(encoding="utf-8").splitlines()}
    originals = {a["exercise"]: a["text"] for a in attempts if a["kind"] == "none"}
    target = OUT / "solutions.jsonl"
    OUT.mkdir(parents=True, exist_ok=True)
    done = {json.loads(line)["exercise"] for line in target.read_text(encoding="utf-8").splitlines()} \
        if target.exists() else set()
    client = Client(read_env(ROOT / ".env")["GROQ_API_KEY"], PRIVATE / "llm_cache")
    started = time.time()
    for exercise, split in chosen(attempts).items():
        if exercise in done or exercise not in originals:
            continue
        if stop_after and time.time() - started > stop_after:
            print("PAUSED: time limit, run again to continue")
            return
        try:
            result = split_and_repair(client, units[exercise]["text"], originals[exercise])
        except QuotaExhausted as error:
            print(f"STOPPED: {error}")
            return
        except ValueError:
            result = {"steps": [], "doubtful": True}
        row = {"exercise": exercise, "split": split, "statement": units[exercise]["text"], **result}
        with target.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(exercise, split, len(result["steps"]), "steps", sum(s["repaired"] for s in result["steps"]), "repaired",
              "DOUBTFUL" if result["doubtful"] else "", flush=True)
    print("FINISHED")


def plant() -> None:
    rows = [json.loads(line) for line in (OUT / "solutions.jsonl").read_text(encoding="utf-8").splitlines()]
    rng = random.Random(SEED)
    out = []
    for row in rows:
        if row["doubtful"] or len(row["steps"]) < 2:
            continue
        text = "\n".join(step["text"] for step in row["steps"])
        # Keep the first step correct, so there is always something right before the error.
        wrong = corrupt(text, rng, skip=len(row["steps"][0]["text"]) + 1)
        if wrong is None:
            continue
        for attempt in (wrong, control(text)):
            out.append({"exercise": row["exercise"], "split": row["split"], "statement": row["statement"],
                        "kind": attempt.kind, "text": attempt.text, "wrong_line": first_wrong_line(attempt),
                        "original": attempt.original, "corrupted": attempt.corrupted})
    (OUT / "attempts.jsonl").write_text("".join(json.dumps(a, ensure_ascii=False) + "\n" for a in out),
                                        encoding="utf-8")
    kept = len(out) // 2
    print(f"{kept} exercises with a planted error and a control, of {len(rows)} rebuilt "
          f"({sum(r['doubtful'] for r in rows)} doubtful)")


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "rebuild":
        stop = float(sys.argv[sys.argv.index("--stop-after") + 1]) if "--stop-after" in sys.argv else 0
        rebuild(stop)
    elif command == "plant":
        plant()
    else:
        sys.exit(__doc__)
