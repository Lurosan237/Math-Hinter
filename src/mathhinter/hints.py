"""Further hints after the first: each one more explicit, none giving the corrected line or the result.

The first hint comes with the review. A student who is still stuck can ask for two more:
- the second points at the part of the line that is wrong (which term, sign, rule) without saying what it should be;
- the third quotes the rule or course result to apply, in general form, not worked out on their numbers.
"""

from __future__ import annotations

import json
import re

from .transcribe import load_latex_json

HINT_MODEL = "openai/gpt-oss-120b"
MAX_LEVEL = 3

GUIDE = {
    2: "Point at the exact part of the line that is wrong: the term, the sign, the exponent, the coefficient, the "
       "theorem used. Say WHERE to look, never WHAT it should be. Any sentence of the form 'X should be Y', 'X is "
       "missing', 'Y is required', 'it must be preceded by -' gives the answer away.\n"
       "Good: «Dans la ligne 3, regardez la dérivée de la fonction intérieure : apparaît-elle dans votre calcul ?»\n"
       "Bad: «Il manque le facteur $2x$ dans la dérivée.»\n"
       "Good: «Dans la ligne 1, regardez l'ordre des deux inverses dans le produit.»\n"
       "Bad: «$(AB)^{-1}$ vaut $B^{-1}A^{-1}$.»",
    3: "Quote the rule, formula or course result that applies there, in its general form, with generic letters "
       "(f, g, u, v, a, b, q, n) as the course states it. Do not substitute the student's function, numbers or "
       "expressions into it, do not compute any coefficient or value, and do not name the value of any parameter. "
       "The student does the substitution.\n"
       "Good: «Le cours donne, pour $u$ dérivable et strictement positive : $(\\ln u)'=\\frac{u'}{u}$. Que vaut ici "
       "$u$ ?»\n"
       "Bad: «Ici la dérivée de $\\ln(x^2+1)$ vaut $\\frac{2x}{x^2+1}$.» Bad: «Le coefficient cherché vaut $3$.»",
}

PROMPT = """You help a student find their own mistake in a maths exercise. The first wrong line is known.
Write the next hint, in French, in one or two sentences, more explicit than the previous hints.

{guide}

Never give the answer: no corrected line, no corrected term, no result, no missing coefficient or factor, no final
value, and never say what something should be. If being more explicit would give the answer away, stop just before
it. Write maths in LaTeX between $...$. Reply only with JSON: {{"hint": "..."}}"""


def messages(statement: str, attempt: str, line: int, hints: list[str], explanation: str,
             passages: list[dict]) -> list[dict]:
    level = len(hints) + 1
    # Numbered from 1, as the student sees them on the site (the review itself counts from 0).
    numbered = "\n".join(f"{i}: {text}" for i, text in enumerate(attempt.split("\n"), 1))
    course = "\n\n".join(f"[{p['label']}]\n{p['text']}" for p in passages)
    task = (f"Exercise:\n{statement}\n\nStudent's attempt (lines numbered from 1):\n{numbered}\n\n"
            f"First wrong line: {line + 1}\n"
            f"What is wrong (for you only, never quote it to the student): {explanation}\n\n"
            + (f"Course passages:\n{course}\n\n" if course else "")
            + "Previous hints:\n" + "\n".join(f"- {h}" for h in hints))
    return [{"role": "system", "content": PROMPT.format(guide=GUIDE[level])}, {"role": "user", "content": task}]


def parse(content: str | None) -> str:
    match = re.search(r"\{.*\}", content or "", re.S)
    if not match:
        raise ValueError("no JSON")
    try:
        hint = load_latex_json(match[0]).get("hint")
    except json.JSONDecodeError:
        found = re.search(r'"hint"\s*:\s*"(.*)"', match[0], re.S)
        hint = found[1].replace('\\"', '"') if found else None
    if not hint or not str(hint).strip():
        raise ValueError("empty hint")
    return str(hint).strip()


def next_hint(client, statement: str, attempt: str, line: int, hints: list[str], explanation: str,
              passages: list[dict]) -> str:
    response = client.chat(HINT_MODEL, messages(statement, attempt, line, hints, explanation, passages),
                           temperature=0.0, max_tokens=1500)
    message = response["choices"][0]["message"]
    try:
        return parse(message.get("content"))
    except ValueError:
        return parse(message.get("reasoning"))
