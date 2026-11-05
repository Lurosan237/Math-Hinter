"""Run the equality checker on real book equalities and on corrupted copies. Writes reports/checker.json for test."""

import argparse
import json
import random
import re
from collections import Counter
from pathlib import Path

from mathhinter.check.equality import REFUTED, UNVERIFIABLE, VERIFIED, check_equality
from mathhinter.evalset.corrupt import apply, formula_edits
from mathhinter.retrieval.labels import module_split

PRIVATE = Path("data/private")
_MATH = re.compile(r"\$\$(.+?)\$\$|\$(.+?)\$", re.S)
_OTHER_RELATION = re.compile(r"\\in|\\leq|\\geq|<|>|\\to|\\Rightarrow|\\mapsto|:=|\\neq|\\not|\\sim|\\equiv")
# Only slips that change an expression's value. Inequalities and quantifiers don't appear in an equality.
VALUE_KINDS = {"sign", "exponent", "number", "inverted_fraction", "wrong_function"}


def top_level_split(formula: str) -> list[str]:
    """Split on = outside braces, or a = inside a limit would cut the formula in two."""
    sides, depth, start = [], 0, 0
    for at, char in enumerate(formula):
        depth += (char == "{") - (char == "}")
        if char == "=" and depth == 0:
            sides.append(formula[start:at])
            start = at + 1
    return [*sides, formula[start:]]


def equalities(text: str) -> list[tuple[str, str]]:
    """Neighbouring sides of each a = b = c chain, from formulas holding nothing but equalities."""
    pairs = []
    for match in _MATH.finditer(text):
        formula = (match[1] or match[2] or "").strip().rstrip(".,;")
        if "=" not in formula or _OTHER_RELATION.search(formula):
            continue
        sides = [s.strip() for s in top_level_split(formula)]
        pairs += [(a, b) for a, b in zip(sides, sides[1:], strict=False) if a and b]
    return pairs


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=["dev", "test"], default="dev")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    units = [json.loads(line) for line in (PRIVATE / "units.jsonl").open(encoding="utf-8")]
    chosen = [u for u in units if u["kind"] in ("solution", "proof") and u["module"] and module_split(u) == args.split]
    pairs = [p for u in chosen for p in equalities(u["text"])]
    rng = random.Random(404)
    rng.shuffle(pairs)
    if args.limit:
        pairs = pairs[: args.limit]
    verdicts, reasons = Counter(), Counter()
    verified_pairs = []
    for left, right in pairs:
        verdict = check_equality(left, right)
        verdicts[verdict.status] += 1
        reasons[verdict.reason.split(":")[0]] += 1
        if verdict.status == VERIFIED:
            verified_pairs.append((left, right))
    outcomes: dict[str, Counter] = {}
    still_verified = []
    for left, right in verified_pairs:
        edits = [e for e in formula_edits(right) if e.kind in VALUE_KINDS]
        if not edits:
            continue
        edit = rng.choice(edits)
        corrupted = apply(right, edit)
        verdict = check_equality(left, corrupted)
        outcomes.setdefault(edit.kind, Counter())[verdict.status] += 1
        if verdict.status == VERIFIED:
            still_verified.append({"left": left, "right": right, "corrupted": corrupted})
    total = Counter()
    for counter in outcomes.values():
        total.update(counter)
    report = {
        "split": args.split, "equalities": len(pairs),
        "book_equalities": {VERIFIED: verdicts[VERIFIED], REFUTED: verdicts[REFUTED],
                            UNVERIFIABLE: verdicts[UNVERIFIABLE]},
        "why_unverifiable": dict(reasons.most_common()),
        "corrupted_copies_of_verified": {
            "tested": sum(total.values()), "still_verified": total[VERIFIED], "refuted": total[REFUTED],
            "unverifiable": total[UNVERIFIABLE],
            "by_kind": {k: dict(v) for k, v in sorted(outcomes.items())},
        },
    }
    (PRIVATE / f"checker_review_{args.split}.json").write_text(
        json.dumps({"still_verified": still_verified}, ensure_ascii=False, indent=0), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=1))
    if args.split == "test":
        target = Path("reports/checker.json")
        target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
