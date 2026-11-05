"""Ranking metrics, with bootstrap intervals over questions."""

from __future__ import annotations

import random
import statistics
from collections.abc import Collection, Sequence


def recall_at(ranked: Sequence[str], gold: Collection[str], k: int) -> float:
    return len(set(ranked[:k]) & set(gold)) / len(gold)


def reciprocal_rank(ranked: Sequence[str], gold: Collection[str]) -> float:
    wanted = set(gold)
    for place, item in enumerate(ranked, start=1):
        if item in wanted:
            return 1 / place
    return 0.0


def interval(values: Sequence[float], seed: int = 11, rounds: int = 3000) -> list[float]:
    rng = random.Random(seed)
    means = sorted(statistics.fmean(rng.choices(values, k=len(values))) for _ in range(rounds))
    return [round(means[int(0.025 * rounds)], 3), round(means[int(0.975 * rounds)], 3)]
