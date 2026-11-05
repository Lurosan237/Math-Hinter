"""Tokens for French maths text: stemmed words plus the symbols that carry meaning."""

from __future__ import annotations

import re
import unicodedata

import snowballstemmer

_STEM = snowballstemmer.stemmer("french")
STOP = set(
    "a au aux avec ce ces cette dans de des du elle en et est il ils je la le les leur lui ma mais me même mes moi "
    "mon "
    "ne nos notre nous on ou par pas pour qu que qui sa se ses si son sont sur ta te tes toi ton tu un une vos votre "
    "vous y d l c s n m t à soit soient alors donc ainsi tout toute tous toutes être avoir fait".split()
)
# Writing that names a part of the book rather than saying anything about the mathematics.
BOOK_REFERENCE = re.compile(
    r"\b(?:th[ée]or[èe]me|proposition|lemme|corollaire|d[ée]finition|exercice|section|module)s?\s+"
    r"[\w.]*\d[\w.]*(?:\s+(?:de|à|en)\s+la\s+page\s+\d+)?|\b(?:de|à)\s+la\s+page\s+\d+|\[[A-Z][\w, .]*\]",
    re.I,
)
LABEL = re.compile(
    r"^(?:Exercice|Th[ée]or[èe]me|Proposition|Lemme|Corollaire|D[ée]finition)\s+\d+\s*\.?|^Solution\s*\."
)
_MATH = re.compile(r"\$\$?(.+?)\$?\$", re.S)
_COMMAND = re.compile(r"\\(mathbb|mathcal|mathfrak|mathscr)\{(\w)\}|\\([A-Za-z]+)")
# Symbols too common or too structural to tell one result from another.
_NOISE = {"frac", "cdot", "ldots", "cdots", "left", "right", "in", "to", "leqslant", "geqslant", "quad", "overline"}


def fold(word: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", word) if not unicodedata.combining(c))


def clean(text: str) -> str:
    """Drop the unit's own label and any pointer to elsewhere in the book."""
    return BOOK_REFERENCE.sub(" ", LABEL.sub(" ", text.strip()))


def word_tokens(text: str) -> list[str]:
    prose = _MATH.sub(" ", clean(text))
    out = []
    for word in re.findall(r"[^\W\d_]{2,}", prose.lower()):
        if word not in STOP:
            out.append(fold(_STEM.stemWord(word)))
    return out


def math_tokens(text: str) -> list[str]:
    out = []
    for formula in _MATH.findall(clean(text)):
        for match in _COMMAND.finditer(formula):
            if match[1]:
                out.append(f"§{match[1]}_{match[2]}")
            elif match[3] not in _NOISE:
                out.append(f"§{match[3]}")
    return out


def tokens(text: str, use_math: bool = True) -> list[str]:
    return word_tokens(text) + (math_tokens(text) if use_math else [])
