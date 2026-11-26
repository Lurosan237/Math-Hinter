"""Turn the lines of an attempt into claims the computer can check (types in claims.py).

The model only transcribes: it must copy what the student wrote, errors included, and never solve or correct. Each
claim carries the line where its conclusion is written, so a refuted claim points at a line.
"""

from __future__ import annotations

import re

from ..transcribe import load_latex_json

FORMALISE_MODEL = "qwen/qwen3.8-27b"

PROMPT = r"""You turn a student's maths write-up into claims a computer algebra system can check.
You are a transcriber, not a corrector: copy the student's expressions exactly as written, with their mistakes.
Never fix, simplify, complete or solve anything. If a line is wrong, the claim must be wrong in the same way.

Lines are numbered from 0. Lines may be broken in the middle of a sentence or formula; a claim belongs to the line
where its conclusion (the right-hand side, the result, the value) is written.

Claim types (expressions in LaTeX, without $):
- {"type": "equality", "line": n, "left": "...", "right": "..."}  for a written equality. For a chain A = B = C, give
  A = B and B = C. Only for expressions, not for definitions such as "f(x) = ..." or "posons u = ...".
- {"type": "derivative", "line": n, "function": "...", "variable": "x", "result": "..."}  "f'(x) = ..." where f
  is defined earlier: put f's expression in "function".
- {"type": "antiderivative", "line": n, "function": "...", "variable": "x", "result": "..."}
- {"type": "integral", "line": n, "function": "...", "variable": "x", "lower": "...", "upper": "...", "result": "..."}
- {"type": "limit", "line": n, "function": "...", "variable": "x", "point": "0, +\infty, 0^+ ...", "result": "..."}
- {"type": "sum", "line": n, "term": "...", "index": "k", "start": "...", "end": "...", "result": "..."}
- {"type": "solution", "line": n, "equations": ["...=...", ...], "values": {"x": "...", ...}}  values claimed to
  solve equations. Use the equations as the student wrote them.
- {"type": "ode", "line": n, "equation": "y'+2y=0", "function": "y", "variable": "x", "solution": "..."}
- {"type": "theorem", "line": n, "name": "théorème de Rolle", "conclusion": "what the student deduces from it"}
- {"type": "other", "line": n, "text": "short description"}  for any other step: a logical deduction, an
  inequality, a definition, a case split, a sentence.

Use "equality" only when the student writes "=" between two expressions meant to be equal. Arrows, "tend vers",
"~", "≈", "≤" and "<" are never equalities: use "limit" when the variable and point are clear, otherwise "other".
An equality that only holds for a value fixed earlier (x = 3, n = 2) is still an equality: keep the letters.

Never put words or \text{...} inside an expression: a claim mixing a formula and words ("= l'aire du triangle")
is "other".

Write clean LaTeX even when the text is garbled by PDF extraction: \cos(2\pi/n) for "cos2π/n", \sin^2(x) for
"sin2x" when that is clearly what is meant, explicit brackets around arguments and fractions. Clean the notation only;
never change a number, sign, exponent or variable.

Give every line at least one claim (use "other" when nothing else applies). Write function names as \sin, \ln,
\exp; products explicitly when a letter is followed by a bracket: x\cdot(x+1). Replace substituted bounds such as
[F(x)]_0^1 by the expression F(1)-F(0) only if the student wrote that difference; otherwise keep it as written.

Reply only with JSON: {"claims": [...]}"""


def messages(statement: str, attempt: str) -> list[dict]:
    numbered = "\n".join(f"{i}: {line}" for i, line in enumerate(attempt.split("\n")))
    return [{"role": "system", "content": PROMPT},
            {"role": "user", "content": f"Exercise:\n{statement}\n\nStudent's write-up:\n{numbered}"}]


def parse(content: str | None, lines: int) -> list[dict]:
    """The claims in the model's reply, keeping only well-formed ones on existing lines."""
    match = re.search(r"\{.*\}", content or "", re.S)
    if not match:
        raise ValueError("no JSON")
    data = load_latex_json(match[0])
    claims = []
    for claim in data.get("claims") or []:
        if not isinstance(claim, dict) or not isinstance(claim.get("type"), str):
            continue
        try:
            line = int(claim.get("line"))
        except (TypeError, ValueError):
            continue
        if 0 <= line < lines:
            claims.append({**claim, "line": line})
    return claims


def formalise(client, statement: str, attempt: str, model: str = FORMALISE_MODEL) -> tuple[list[dict], int]:
    """The claims and the tokens used."""
    response = client.chat(model, messages(statement, attempt), temperature=0.0, max_tokens=6000)
    message = response["choices"][0]["message"]
    lines = attempt.count("\n") + 1
    try:
        claims = parse(message.get("content"), lines)
    except ValueError:
        claims = parse(message.get("reasoning"), lines)
    return claims, response.get("usage", {}).get("total_tokens", 0)
