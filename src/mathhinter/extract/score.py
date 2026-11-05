"""Compare an extracted formula with a hand transcription, as token sequences."""

from __future__ import annotations

import re

from rapidfuzz.distance import Levenshtein

from .latex import UNICODE

_TOKEN = re.compile(r"\\[A-Za-z]+|\\.|\s+|.", re.S)
_DROP = {r"\left", r"\right", r"\big", r"\Big", r"\bigg", r"\Bigg", r"\,", r"\;", r"\:", r"\!", r"\ ", r"\quad",
         r"\qquad", r"\mathrm", r"\operatorname", r"\mathbf", r"\boldsymbol", r"\mathit", r"\text", r"\displaystyle",
         r"\limits", r"\nolimits", r"\bf", r"\rm", r"\it", r"\overset", r"\stackrel", r"\begin", r"\end",
         r"\\", "&", "~"}
_SAME = {r"\leq": r"\leqslant", r"\le": r"\leqslant", r"\geq": r"\geqslant", r"\ge": r"\geqslant",
         r"\rightarrow": r"\to", r"\longrightarrow": r"\to", r"\epsilon": r"\varepsilon", r"\phi": r"\varphi",
         r"\vert": "|", r"\mid": "|", r"\Vert": r"\|", r"\lVert": r"\|", r"\rVert": r"\|", r"\lbrace": r"\{",
         r"\rbrace": r"\}", r"\dots": "...", r"\ldots": "...", r"\cdots": "...", r"\dotsc": "...",
         r"\prime": "'", r"\tilde": r"\widetilde", r"\bar": r"\overline", r"\mathopen": "", r"\mathclose": "",
         r"\lbrack": "[", r"\rbrack": "]", r"\llbracket": "[[", r"\rrbracket": "]]", r"\colon": ":"}
# Function names are letters in the page's text, however a tool chooses to spell them.
_NAMES = {r"\lim": "lim", r"\sin": "sin", r"\cos": "cos", r"\ln": "ln", r"\log": "log", r"\max": "max", r"\min": "min",
          r"\sup": "sup", r"\inf": "inf", r"\exp": "exp", r"\ker": "Ker", r"\tan": "tan"}


def tokens(latex: str, structure: bool = True) -> list[str]:
    """Canonical tokens. With structure=False, keep only the symbols: no scripts or fraction markers."""
    text = latex.replace("···", r"\cdots").replace("…", r"\ldots")
    out: list[str] = []
    for token in _TOKEN.findall(text):
        if token.isspace() or token in _DROP:
            continue
        token = _NAMES.get(token, token)
        token = UNICODE.get(token, token)
        token = _SAME.get(token, token)
        if not token:
            continue
        out.extend(token if len(token) > 1 and not token.startswith("\\") else [token])
    # Canonicalise script braces, keep the grouping out of the comparison.
    out = [t for t in out if t not in {"{", "}"}]
    if not structure:
        out = [t for t in out if t not in {"_", "^", r"\frac", r"\sqrt"}]
    return out


def similarity(extracted: str, gold: str, structure: bool = True) -> float:
    """1 - normalised edit distance over tokens: 1.0 is identical."""
    a, b = tokens(extracted, structure), tokens(gold, structure)
    if not a and not b:
        return 1.0
    return 1 - Levenshtein.distance(a, b) / max(len(a), len(b))
