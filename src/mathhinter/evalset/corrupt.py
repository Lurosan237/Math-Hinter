"""Make one known error in correct mathematics, so we know exactly where the first wrong step is."""

from __future__ import annotations

import random
import re
from dataclasses import dataclass

_MATH = re.compile(r"\$\$(.+?)\$\$|\$(.+?)\$", re.S)
_SCRIPT_BLOCK = re.compile(r"_\{[^{}]*\}")


@dataclass(frozen=True)
class Edit:
    kind: str
    start: int
    end: int
    replacement: str


def _outside_subscripts(formula: str, position: int) -> bool:
    """A subscript is a label, and changing x_{1} to x_{2} isn't the kind of slip we are testing."""
    return not any(m.start() <= position < m.end() for m in _SCRIPT_BLOCK.finditer(formula))


def _swaps(formula: str, pattern: str, replacement, kind: str) -> list[Edit]:
    edits = []
    for match in re.finditer(pattern, formula):
        if _outside_subscripts(formula, match.start()):
            new = replacement(match)
            if new != match[0]:
                edits.append(Edit(kind, match.start(), match.end(), new))
    return edits


def _bump(match: re.Match) -> str:
    return str(int(match[0]) + 1)


def formula_edits(formula: str) -> list[Edit]:
    """Every single-token slip that could be made in a formula."""
    edits = []
    edits += _swaps(formula, r"(?<=[\w)}])\+(?=[\w(\\])", lambda m: "-", "sign")
    edits += _swaps(formula, r"(?<=[\w)}])-(?=[\w(\\])", lambda m: "+", "sign")
    edits += _swaps(formula, r"\^\{(\d+)\}", lambda m: f"^{{{int(m[1]) + 1}}}", "exponent")
    edits += _swaps(formula, r"(?<![\w.{^_])\d+(?![\w.}])", _bump, "number")
    edits += _swaps(formula, r"\\frac\{([^{}]+)\}\{([^{}]+)\}", lambda m: rf"\frac{{{m[2]}}}{{{m[1]}}}",
                    "inverted_fraction")
    edits += _swaps(formula, r"\bsin(?!h)", lambda m: "cos", "wrong_function")
    edits += _swaps(formula, r"\bcos(?!h)", lambda m: "sin", "wrong_function")
    edits += _swaps(formula, r"\\leqslant", lambda m: r"\geqslant", "inequality")
    edits += _swaps(formula, r"\\geqslant", lambda m: r"\leqslant", "inequality")
    edits += _swaps(formula, r"\\forall", lambda m: r"\exists", "quantifier")
    return edits


def apply(formula: str, edit: Edit) -> str:
    return formula[: edit.start] + edit.replacement + formula[edit.end :]


WORD_SWAPS = [("injective", "surjective"), ("surjective", "injective"), ("croissante", "décroissante"),
              ("décroissante", "croissante"), ("converge", "diverge"), ("diverge", "converge"),
              ("ouvert", "fermé"), ("fermé", "ouvert"), ("majorée", "minorée"), ("minorée", "majorée"),
              ("inversible", "non inversible"), ("continue", "discontinue"), ("positif", "négatif"),
              ("négatif", "positif")]


@dataclass(frozen=True)
class Attempt:
    text: str
    kind: str  # the kind of error, or "none" for a control that keeps the solution unchanged
    start: int | None  # where the error is in text
    end: int | None
    original: str | None
    corrupted: str | None


def _candidates(text: str) -> list[tuple[str, int, int, str]]:
    found = []
    for match in _MATH.finditer(text):
        group = 1 if match[1] is not None else 2
        offset = match.start(group)
        for edit in formula_edits(match[group]):
            found.append((edit.kind, offset + edit.start, offset + edit.end, edit.replacement))
    math_spans = [m.span() for m in _MATH.finditer(text)]
    for old, new in WORD_SWAPS:
        for match in re.finditer(rf"\b{old}\b", text):
            if not any(a <= match.start() < b for a, b in math_spans):
                found.append(("word", match.start(), match.end(), new))
    return found


def corrupt(text: str, rng: random.Random, skip: int = 40) -> Attempt | None:
    """One error, away from the very start so there are earlier correct steps. None if nothing can be changed."""
    options = [c for c in _candidates(text) if c[1] >= skip]
    if not options:
        return None
    # Choose the kind first, or solutions full of plus signs would produce nothing but sign errors.
    kind = rng.choice(sorted({c[0] for c in options}))
    _, start, end, replacement = rng.choice([c for c in options if c[0] == kind])
    return Attempt(text[:start] + replacement + text[end:], kind, start, start + len(replacement), text[start:end],
                   replacement)


def control(text: str) -> Attempt:
    return Attempt(text, "none", None, None, None, None)


def first_wrong_line(attempt: Attempt) -> int | None:
    """The 0-based line holding the error, which is what a detector is scored against."""
    return None if attempt.start is None else attempt.text.count("\n", 0, attempt.start)
