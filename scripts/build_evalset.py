"""Filter the worked exercises, build wrong attempts and controls, and report counts (no book text)."""

import json
import random
from collections import Counter
from pathlib import Path

from mathhinter.evalset.corrupt import control, corrupt, first_wrong_line
from mathhinter.evalset.quality import is_computation, rejection
from mathhinter.retrieval.labels import module_split

PRIVATE = Path("data/private")
SEED = 20261105


def main() -> None:
    units = {}
    for line in (PRIVATE / "units.jsonl").open(encoding="utf-8"):
        unit = json.loads(line)
        units[unit["id"]] = unit
    pairs = json.loads((PRIVATE / "pairs.json").read_text(encoding="utf-8"))
    rng = random.Random(SEED)
    reasons, kinds, splits, computation = Counter(), Counter(), Counter(), Counter()
    kept, attempts = [], []
    for pair in pairs:
        exercise, solution = units[pair["exercise"]], units[pair["solution"]]
        reason = rejection(exercise["text"], solution["text"])
        reasons[reason or "kept"] += 1
        if reason:
            continue
        split = module_split(exercise)
        splits[split] += 1
        computes = is_computation(exercise["text"])
        computation["computation" if computes else "proof_or_other"] += 1
        kept.append({"exercise": exercise["id"], "solution": solution["id"], "split": split, "computation": computes})
        wrong = corrupt(solution["text"], rng)
        for attempt in ([wrong] if wrong else []) + [control(solution["text"])]:
            kinds[attempt.kind] += 1
            attempts.append({"exercise": exercise["id"], "solution": solution["id"], "split": split,
                             "kind": attempt.kind, "text": attempt.text, "wrong_line": first_wrong_line(attempt),
                             "start": attempt.start, "end": attempt.end, "original": attempt.original,
                             "corrupted": attempt.corrupted})
    (PRIVATE / "kept_exercises.json").write_text(json.dumps(kept), encoding="utf-8")
    with (PRIVATE / "attempts.jsonl").open("w", encoding="utf-8") as out:
        for attempt in attempts:
            out.write(json.dumps(attempt, ensure_ascii=False) + "\n")
    report = {"exercises": len(pairs), "outcome": dict(reasons.most_common()), "kept_by_split": dict(splits),
              "kept_by_type": dict(computation), "attempts_by_kind": dict(kinds.most_common())}
    checks = Path("data/hand_checks/evalset.json")
    if checks.exists():
        judged = json.loads(checks.read_text(encoding="utf-8"))
        report["hand_check"] = {
            "kept_sampled": len(judged["kept"]), "kept_usable": sum(j["usable"] for j in judged["kept"]),
            "corrupted_sampled": len(judged["corrupted"]),
            "corrupted_really_wrong": sum(j["really_wrong"] for j in judged["corrupted"]),
        }
    Path("reports/evalset.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report))
    sample = random.Random(SEED + 1)
    (PRIVATE / "evalset_review.json").write_text(json.dumps({
        "kept": [k["exercise"] for k in sample.sample(kept, 30)],
        "corrupted": sample.sample([i for i, a in enumerate(attempts) if a["kind"] != "none"], 30),
    }), encoding="utf-8")


if __name__ == "__main__":
    main()
