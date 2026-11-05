"""Link units through the book's own cross-references, such as "le théorème 167 de la page 333"."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .structure import Unit, normalise

KINDS = {"théorème": "theorem", "theoreme": "theorem", "proposition": "proposition", "lemme": "lemma",
         "corollaire": "corollary", "définition": "definition", "exercice": "exercise"}
_WORDS = "|".join(KINDS)
BY_NUMBER = re.compile(rf"\b(?P<kind>{_WORDS})\s+(?P<number>\d+)\s+(?:de|à|en)\s+la\s+page\s+(?P<page>\d+)", re.I)
BY_PAGE = re.compile(rf"\b(?P<kind>{_WORDS})\s+de\s+la\s+page\s+(?P<page>\d+)", re.I)
# [L2], [L2, II.1] or [Serre, I.2.1]. A capital alone is left out: K[X] is a polynomial ring, not a book.
OTHER_BOOK = re.compile(r"\[(L[123]|MPA\d?|[A-Z][a-z]{2,})\b[^\]]*\]")
BOOK_VOLUME = {"L1": 1, "L2": 2, "L3": 3}
# A reference to another book is named just before or after it.
NEARBY = 45


@dataclass(frozen=True)
class Reference:
    source: str
    kind: str
    number: str | None
    page: int
    volume: int
    target: str | None
    status: str  # linked, ambiguous, unresolved or external
    start: int


def _book_of(text: str, start: int, end: int, volume: int) -> int | None:
    """The volume a reference points at, or None if it's a book outside this collection."""
    for match in OTHER_BOOK.finditer(text, max(0, start - NEARBY), min(len(text), end + NEARBY)):
        return BOOK_VOLUME.get(match[1])
    return volume


def find_references(units_by_id: dict[str, Unit], index: dict) -> list[Reference]:
    """Find every reference in every unit and try to resolve it to the unit it names."""
    references = []
    for source, unit in units_by_id.items():
        text = normalise(" ".join(unit.lines))
        for pattern in (BY_NUMBER, BY_PAGE):
            for match in pattern.finditer(text):
                kind = KINDS[match["kind"].lower()]
                number = match.groupdict().get("number")
                page = int(match["page"])
                volume = _book_of(text, match.start(), match.end(), unit.volume)
                if volume is None:
                    references.append(
                        Reference(source, kind, number, page, unit.volume, None, "external", match.start()))
                    continue
                candidates = index.get((volume, kind, page), [])
                if number:
                    candidates = [c for c in candidates if c[1] == number]
                    if not candidates:  # the printed page can be off by one around a page break
                        nearby = index.get((volume, kind, page - 1), []) + index.get((volume, kind, page + 1), [])
                        candidates = [c for c in nearby if c[1] == number]
                if len(candidates) == 1:
                    target, status = candidates[0][0], "linked"
                elif candidates:
                    target, status = None, "ambiguous"
                else:
                    target, status = None, "unresolved"
                references.append(Reference(source, kind, number, page, volume, target, status, match.start()))
    return references


def build_index(records: list[tuple[str, Unit]]) -> dict:
    """(volume, kind, printed page) -> [(unit id, number)], counting each page a unit is printed on."""
    index: dict = {}
    for ident, unit in records:
        if unit.printed_page is None or not unit.number:
            continue
        index.setdefault((unit.volume, unit.kind, unit.printed_page), []).append((ident, unit.number))
    return index
