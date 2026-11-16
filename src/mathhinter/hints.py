"""Further hints after the first: each one more explicit, none giving the corrected line or the result.

The first hint comes with the review. A student who is still stuck can ask for two more:
- the second names precisely what is wrong in the line (which term, sign, rule) without fixing it;
- the third states the rule or course result to apply, in general form, not worked out on their numbers.
"""

from __future__ import annotations

import json
import re

from .transcribe import load_latex_json

HINT_MODEL = "openai/gpt-oss-120b"
MAX_LEVEL = 3

GUIDE = {
    2: "Name precisely what is wrong in that line: which term, sign, exponent, coefficient, condition or rule. "
       "Do not write the corrected line or any value it should have. End with a short question that sends the "
       "student back to that line.",
    3: "State the rule, formula or course result the student must apply there, in its general form with letters, "
       "as the course states it. Do not apply it to the student's expressions, do not write the corrected line, "
       "the missing value or the final result.",
}

PROMPT = """You help a student find their own mistake in a maths exercise. The first wrong line is known.
Write the next hint, in French, in one or two sentences, more explicit than the previous hints.

{guide}

Never give the answer: no corrected line, no result, no missing coefficient, no final value. If the only way to be
more explicit would give the answer away, write a hint that stops just before it.
Write maths in LaTeX between $...$. Reply only with JSON: {{"hint": "..."}}"""


def messages(statement: str, attempt: str, line: int, hints: list[str], explanation: str,
             passages: list[dict]) -> list[dict]:
    level = len(hints) + 1
    numbered = "\n".join(f"{i}: {text}" for i, text in enumerate(attempt.split("\n")))
    course = "\n\n".join(f"[{p['label']}]\n{p['text']}" for p in passages)
    task = (f"Exercise:\n{statement}\n\nStudent's attempt (lines numbered from 0):\n{numbered}\n\n"
            f"First wrong line: {line}\nWhat is wrong (for you only, never quote it to the student): {explanation}\n\n"
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
