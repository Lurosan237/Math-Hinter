"""Rankers over the same list of units. All of them can hide units from a query."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence

import numpy as np
from scipy.sparse import csr_matrix


class BM25:
    def __init__(self, documents: Sequence[list[str]], k1: float = 1.4, b: float = 0.6):
        self.vocabulary: dict[str, int] = {}
        rows, cols, data = [], [], []
        lengths = np.zeros(len(documents))
        for row, tokens in enumerate(documents):
            lengths[row] = len(tokens)
            for token, count in Counter(tokens).items():
                column = self.vocabulary.setdefault(token, len(self.vocabulary))
                rows.append(row)
                cols.append(column)
                data.append(count)
        shape = (len(documents), max(len(self.vocabulary), 1))
        counts = csr_matrix((np.array(data, dtype=float), (rows, cols)), shape=shape).tocsc()
        frequency = np.diff(counts.indptr)
        self.idf = np.log(1 + (len(documents) - frequency + 0.5) / (frequency + 0.5))
        average = lengths.mean() if len(documents) else 1.0
        norm = k1 * (1 - b + b * lengths / max(average, 1e-9))
        rows_of = counts.indices
        counts.data = counts.data * (k1 + 1) / (counts.data + norm[rows_of])
        self.weights = counts
        self.size = len(documents)

    def scores(self, query: Iterable[str]) -> np.ndarray:
        columns = [self.vocabulary[t] for t in set(query) if t in self.vocabulary]
        if not columns:
            return np.zeros(self.size)
        return np.asarray(self.weights[:, columns] @ self.idf[columns])


def rank(scores: np.ndarray, hidden: Iterable[int] = ()) -> np.ndarray:
    """Unit positions, best first, without the hidden ones. Ties break by position, so results are repeatable."""
    order = np.lexsort((np.arange(len(scores)), -scores))
    blocked = set(hidden)
    return np.array([i for i in order if i not in blocked], dtype=int)


def reciprocal_fusion(rankings: Sequence[np.ndarray], size: int, k: int = 60) -> np.ndarray:
    """Scores from combining rankings by position, so differently scaled rankers can be mixed."""
    total = np.zeros(size)
    for ranking in rankings:
        total[ranking] += 1 / (k + np.arange(1, len(ranking) + 1))
    return total
