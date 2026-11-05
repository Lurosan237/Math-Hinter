"""Retrieval questions labelled by the books themselves.

A proof or solution that says "d'après le théorème 47 de la page 522" tells us a result needed for the statement it
answers. So the statement is the query and the cited result is the right answer, with no labelling by us.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from hashlib import sha256

RESULT_KINDS = {"theorem", "proposition", "lemma", "corollary"}
TARGET_KINDS = RESULT_KINDS | {"definition"}


@dataclass(frozen=True)
class Question:
    query: str  # unit id of the statement
    answer: str  # unit id of its solution or proof, hidden from the search
    source: str  # "exercise" or "result"
    gold: frozenset[str]


def module_split(unit: dict) -> str:
    """Whole modules go to one side, so neighbouring statements can't leak between dev and test."""
    key = f"{unit['volume']}:{unit['module']}".encode()
    return "dev" if sha256(key).digest()[0] % 2 == 0 else "test"


def build_questions(units: Sequence[dict], edges: Sequence[dict]) -> list[Question]:
    position = {u["id"]: i for i, u in enumerate(units)}
    by_id = {u["id"]: u for u in units}
    gathered: dict[tuple[str, str, str], set[str]] = {}
    for edge in edges:
        if edge["kind"] == "exercise" or by_id[edge["target"]]["kind"] not in TARGET_KINDS:
            continue
        source = by_id[edge["source"]]
        index = position[edge["source"]]
        if index == 0:
            continue
        statement = units[index - 1]
        if source["kind"] == "solution" and statement["kind"] == "exercise":
            label = "exercise"
        elif source["kind"] == "proof" and statement["kind"] in RESULT_KINDS:
            label = "result"
        else:
            continue
        if edge["target"] != statement["id"]:
            gathered.setdefault((statement["id"], source["id"], label), set()).add(edge["target"])
    return [Question(q, a, s, frozenset(g)) for (q, a, s), g in sorted(gathered.items())]
