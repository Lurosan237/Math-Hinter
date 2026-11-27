"""Split a write-up into steps, one per line, so that "the first wrong line" means the first wrong step.

Two modes:
- faithful, for students: the model only cuts and joins the student's own words. That is checked: the steps,
  without spaces, must spell exactly the original without spaces, or the original lines are kept.
- repair, for building benchmarks from textbook PDFs: the model may also fix extraction damage (broken fractions,
  glued words), and marks every step it repaired so the repairs can be checked by hand.
"""

from __future__ import annotations

import re

from .transcribe import load_latex_json

SPLIT_MODEL = "qwen/qwen3.8-27b"
SPLIT_EXTRA = {"reasoning_effort": "none"}  # cutting text needs no reasoning, and this keeps it fast and cheap
LONG_LINE = 160

FAITHFUL = """Split this maths write-up into steps, one step per line: one calculation, one deduction or one
statement per step. Keep every character of the original, in order: only choose where to cut and remove line
breaks. Do not add, remove, fix or reword anything, not even an obvious mistake or a typo.
Reply only with JSON: {"steps": ["...", "..."]}"""

REPAIR = """This is a worked solution extracted from a PDF textbook. Extraction damaged it: words glued together,
fractions and exponents flattened ("r + r'" for a fraction), lines broken in the middle of formulas.
Rewrite it as clean steps, one per line: one calculation, one deduction or one statement per step, maths in LaTeX
between $...$. Keep the author's reasoning, notation, numbers and results exactly; do not add steps, explanations or
justifications, and do not correct the mathematics. Only undo extraction damage, using the context.
For each step say whether you repaired damage in it, and what. If you cannot tell what was meant, set "doubtful".
Reply only with JSON: {"steps": [{"text": "...", "repaired": false, "note": ""}, ...], "doubtful": false}"""


def needs_splitting(text: str) -> bool:
    """Worth a model call: a long line, or a single line holding several sentences."""
    lines = [line for line in text.split("\n") if line.strip()]
    if any(len(line) > LONG_LINE for line in lines):
        return True
    return len(lines) == 1 and len(re.findall(r"[.;:](\s|$)", lines[0])) >= 2


def _bare(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _ask(client, prompt: str, statement: str, text: str) -> dict:
    response = client.chat(SPLIT_MODEL, [{"role": "system", "content": prompt},
                                         {"role": "user", "content": f"Exercise:\n{statement}\n\nWrite-up:\n{text}"}],
                           temperature=0.0, max_tokens=4000, extra=SPLIT_EXTRA)
    message = response["choices"][0]["message"]
    content = message.get("content") or message.get("reasoning") or ""
    match = re.search(r"\{.*\}", content, re.S)
    if not match:
        raise ValueError("no JSON")
    return load_latex_json(match[0])


def split_faithfully(client, statement: str, text: str) -> tuple[list[str], bool]:
    """The steps and whether splitting happened. Any change to the student's words keeps the original lines."""
    original = [line.strip() for line in text.split("\n") if line.strip()]
    try:
        steps = [" ".join(str(s).split()) for s in _ask(client, FAITHFUL, statement, text).get("steps") or []]
    except (ValueError, KeyError, TypeError):
        return original, False
    steps = [s for s in steps if s]
    if not steps or _bare("".join(steps)) != _bare(text):
        return original, False
    return steps, steps != original


def split_and_repair(client, statement: str, text: str) -> dict:
    """Clean steps for a benchmark, with the repairs marked. Raises ValueError if the reply is unusable."""
    data = _ask(client, REPAIR, statement, text)
    steps = []
    for step in data.get("steps") or []:
        if isinstance(step, dict) and str(step.get("text", "")).strip():
            steps.append({"text": " ".join(str(step["text"]).split()), "repaired": bool(step.get("repaired")),
                          "note": str(step.get("note") or "")})
    if not steps:
        raise ValueError("no steps")
    return {"steps": steps, "doubtful": bool(data.get("doubtful"))}
