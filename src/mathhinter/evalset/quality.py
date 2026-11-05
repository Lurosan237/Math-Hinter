"""Decide which exercises are fit to test on. Each is rejected for a stated reason, or kept."""

from __future__ import annotations

import re

_LABEL = re.compile(r"^Exercice\s+\d+\.?\s*")
_NEEDS_CONTEXT = re.compile(
    r"\b(?:précédent(?:e|s|es)?|ci-dessus|ci-dessous|de la page \d+|même méthode|même question|de même|"
    r"cet exemple|cette (?:formule|méthode|proposition|propriété)|ce (?:théorème|résultat|lemme)|on reprend|"
    r"reprenons|en reprenant|notations? de)\b",
    re.I,
)
_STRAY_START = re.compile(r"^\$\$?[^$]{0,16}\$\$?(\s|$)")
_TINY_DISPLAY = re.compile(r"\$\$ [^$]{1,8} \$\$")
_GLUED_WORDS = re.compile(r"\$\$ [^$]*[a-zà-ÿ]{5,}[^$]*[a-zà-ÿ]{5,}[^$]* \$\$")
_BROKEN_MATH = re.compile(r"\^\{[|']?\}|_\{\}|\\frac\{\}|\\sqrt\{\}|\$\\sqrt\$|\\overline\{\}|_\{\\overline|\+_\{")
MIN_STATEMENT = 40
MIN_SOLUTION = 80


def rejection(statement: str, solution: str) -> str | None:
    """Why an exercise can't be used, or None if it can. Most specific problems are checked first."""
    body = _LABEL.sub("", statement).strip()
    if "\ufffd" in statement or "\ufffd" in solution:
        return "unreadable_characters"
    if len(body) < MIN_STATEMENT:
        return "too_short"
    if len(solution) < MIN_SOLUTION:
        return "solution_too_short"
    if _STRAY_START.match(body) or _TINY_DISPLAY.search(statement):
        return "stray_formula_fragment"
    if _BROKEN_MATH.search(statement) or _GLUED_WORDS.search(statement):
        return "broken_formula"
    if body.count("{") != body.count("}") or body.count("$") % 2:
        return "unbalanced_formula"
    if _NEEDS_CONTEXT.search(statement):
        return "needs_earlier_context"
    return None


def is_computation(statement: str) -> bool:
    """Whether the task asks for a result that can be checked, rather than a proof."""
    return bool(re.search(r"\b(Calculer|Déterminer|Résoudre|Trouver|Donner|Expliciter|Quelles?\b)", statement))
