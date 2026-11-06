"""Score reviews against the known error. Everything is by exercise, because each has a wrong attempt and a control."""

from __future__ import annotations

import random
import statistics
from collections.abc import Sequence


def summarise(rows: Sequence[dict]) -> dict:
    """Rows have: exercise, kind ("none" for a control), wrong_line, verdict, first_wrong_line, failure, lines."""
    wrong = [r for r in rows if r["kind"] != "none"]
    controls = [r for r in rows if r["kind"] == "none"]
    flagged = [r for r in wrong if r["verdict"] == "wrong"]
    exact = [r for r in wrong if r["verdict"] == "wrong" and r["first_wrong_line"] == r["wrong_line"]]
    near = [r for r in flagged
            if r["first_wrong_line"] is not None and abs(r["first_wrong_line"] - r["wrong_line"]) <= 1]

    def share(part, whole) -> float | None:
        return round(len(part) / len(whole), 3) if whole else None

    return {
        "wrong_attempts": len(wrong), "controls": len(controls),
        "error_flagged": share(flagged, wrong),
        "false_alarm": share([r for r in controls if r["verdict"] == "wrong"], controls),
        "exact_line": share(exact, wrong), "within_one_line": share(near, wrong),
        "exact_line_when_flagged": share(exact, flagged),
        "invalid": share([r for r in rows if r["verdict"] is None], rows),
        "both_right": _both_right(rows),
    }


def _pairs(rows: Sequence[dict]) -> dict[str, dict[str, dict]]:
    grouped: dict[str, dict[str, dict]] = {}
    for row in rows:
        grouped.setdefault(row["exercise"], {})["control" if row["kind"] == "none" else "wrong"] = row
    return grouped


def pair_score(pair: dict[str, dict]) -> bool:
    """Found the exact line in the wrong attempt and left the control alone. Crying wrong always can't pass this."""
    wrong, control = pair.get("wrong"), pair.get("control")
    if not wrong or not control:
        return False
    return (wrong["verdict"] == "wrong" and wrong["first_wrong_line"] == wrong["wrong_line"]
            and control["verdict"] == "correct")


def _both_right(rows: Sequence[dict]) -> float | None:
    pairs = _pairs(rows)
    if not pairs:
        return None
    return round(statistics.fmean(pair_score(p) for p in pairs.values()), 3)


def difference_interval(a: Sequence[dict], b: Sequence[dict], seed: int = 3, rounds: int = 4000) -> dict:
    """Bootstrap the difference in both_right (a minus b), resampling exercises so the pairing is kept."""
    first, second = _pairs(a), _pairs(b)
    shared = sorted(set(first) & set(second))
    deltas = [pair_score(first[e]) - pair_score(second[e]) for e in shared]
    if not deltas:
        return {"exercises": 0}
    rng = random.Random(seed)
    means = sorted(statistics.fmean(rng.choices(deltas, k=len(deltas))) for _ in range(rounds))
    return {"exercises": len(shared), "difference": round(statistics.fmean(deltas), 3),
            "ci95": [round(means[int(0.025 * rounds)], 3), round(means[int(0.975 * rounds)], 3)]}


def proportion_interval(rows: Sequence[dict], seed: int = 3, rounds: int = 4000) -> list[float]:
    values = [float(pair_score(p)) for p in _pairs(rows).values()]
    rng = random.Random(seed)
    means = sorted(statistics.fmean(rng.choices(values, k=len(values))) for _ in range(rounds))
    return [round(means[int(0.025 * rounds)], 3), round(means[int(0.975 * rounds)], 3)]


def chance_exact_line(rows: Sequence[dict]) -> float:
    """What guessing a line at random would score on the wrong attempts."""
    wrong = [r for r in rows if r["kind"] != "none"]
    return round(statistics.fmean(1 / r["lines"] for r in wrong), 3)
