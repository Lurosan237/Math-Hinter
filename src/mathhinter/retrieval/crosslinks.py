"""Propose links from a later volume back to an earlier one, using the earlier volume's index of terms."""

from __future__ import annotations

import math
import re
from collections.abc import Sequence

from ..corpus.index_terms import full_term
from .text import STOP, fold

_WORD = re.compile(r"[^\W\d_]{2,}")


def _words(text: str) -> tuple[str, ...]:
    """Light folding only. Stems would make unrelated terms look alike, and an index term must match exactly."""
    prose = re.sub(r"\$.*?\$", " ", text.lower().replace("’", " "), flags=re.S)
    return tuple(fold(w.rstrip("sx")) for w in _WORD.findall(prose) if w not in STOP)


def term_targets(entries: Sequence[dict], units: Sequence[dict]) -> dict[tuple[str, ...], dict]:
    """Each index term that leads to a definition on its page, keyed by its words."""
    definitions: dict[tuple[int, int], list[dict]] = {}
    for unit in units:
        if unit["kind"] == "definition":
            definitions.setdefault((unit["volume"], unit["printed_page"]), []).append(unit)
    targets: dict[tuple[str, ...], dict] = {}
    for entry in entries:
        key = _words(full_term(entry))
        if not key or (len(key) == 1 and len(key[0]) < 5):
            continue
        for page in entry["pages"]:
            for unit in definitions.get((entry["volume"], page), []):
                body = _words(unit["text"])
                if _contains(body, key):
                    targets.setdefault(key, {"unit": unit["id"], "volume": entry["volume"], "term": full_term(entry)})
                    break
    return targets


def _contains(words: tuple[str, ...], key: tuple[str, ...]) -> bool:
    size = len(key)
    return any(words[i : i + size] == key for i in range(len(words) - size + 1))


def document_frequency(keys, documents: Sequence[tuple[str, ...]]) -> dict[tuple[str, ...], int]:
    counts = dict.fromkeys(keys, 0)
    by_first: dict[str, list[tuple[str, ...]]] = {}
    for key in keys:
        by_first.setdefault(key[0], []).append(key)
    for words in documents:
        seen = set()
        for i, word in enumerate(words):
            for key in by_first.get(word, ()):
                if key not in seen and words[i : i + len(key)] == key:
                    seen.add(key)
        for key in seen:
            counts[key] += 1
    return counts


def link_statement(text: str, targets: dict, frequency: dict, total: int, limit: int = 3) -> list[dict]:
    """The rarest, longest terms in a statement. Common words like "fonction" say little about what's needed."""
    words = _words(text)
    found = [key for key in targets if key[0] in words and _contains(words, key)]
    # A term inside a longer matched term adds nothing: "relation" within "relation d'equivalence".
    found = [k for k in found if not any(o != k and _contains(o, k) for o in found)]
    found.sort(key=lambda k: (-len(k) * math.log(total / (1 + frequency.get(k, 0))), k))
    return [targets[key] | {"key": key} for key in found[:limit]]
