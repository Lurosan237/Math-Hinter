"""Search over the books for the agent. An exercise's own solution can never come back unless asked for."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

import numpy as np

from ..retrieval.labels import TARGET_KINDS
from ..retrieval.search import BM25, rank, reciprocal_fusion
from ..retrieval.text import tokens

K1, B = 2.2, 0.9  # chosen on the development modules in stage 3
PASSAGE_CHARS = 900


class CourseSearch:
    def __init__(self, units: Sequence[dict]):
        self.units = list(units)
        self.position = {u["id"]: i for i, u in enumerate(self.units)}
        titles = {(u["volume"], u["module"], u["section"]): u["text"].split("\n")[0]
                  for u in self.units if u["kind"] == "heading"}
        documents = [f"{titles.get((u['volume'], u['module'], u['section']), '')}\n{u['text']}" for u in self.units]
        self.index = BM25([tokens(d) for d in documents], K1, B)
        self.results_only = np.array([u["kind"] in TARGET_KINDS for u in self.units])

    def _nearby(self, exercise: str) -> np.ndarray:
        at = self.position[exercise]
        distance = (np.arange(len(self.units)) - at).astype(float)
        return rank(np.where(distance < 0, distance, -len(self.units) - distance))

    def search(self, query: str, exercise: str, hidden: Iterable[str], k: int = 5,
               results_only: bool = True) -> list[dict]:
        """Best units for a query about an exercise. Hidden ids are removed before anything else happens."""
        blocked = {self.position[h] for h in hidden if h in self.position}
        scores = self.index.scores(tokens(query))
        ranking = rank(scores, blocked)
        if results_only:
            ranking = ranking[self.results_only[ranking]]
        nearby = self._nearby(exercise)
        nearby = nearby[self.results_only[nearby]] if results_only else nearby
        nearby = np.array([i for i in nearby if i not in blocked], dtype=int)
        fused = rank(reciprocal_fusion([ranking, nearby], len(self.units)), blocked)
        fused = fused[self.results_only[fused]] if results_only else fused
        return [self.passage(int(i)) for i in fused[:k]]

    def passage(self, at: int) -> dict:
        unit = self.units[at]
        return {"id": unit["id"], "kind": unit["kind"], "volume": unit["volume"], "page": unit["printed_page"],
                "text": unit["text"][:PASSAGE_CHARS]}
