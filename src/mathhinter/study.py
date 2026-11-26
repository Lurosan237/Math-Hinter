"""Study features after a review: a similar exercise whose answer the computer has checked, and a short guided
conversation about one line ("Explique-moi") that asks questions instead of giving the answer."""

from __future__ import annotations

import re

from .pipeline.claims import CHECKED_TYPES, check_claim
from .transcribe import load_latex_json

STUDY_MODEL = "openai/gpt-oss-20b"  # its own Groq quota, so practice doesn't eat into reviews
MAX_TURNS = 8

SIMILAR_PROMPT = r"""A student made a mistake in a maths exercise. Write ONE new exercise, in French, that practises
exactly the skill they got wrong, at the same level, with different functions or numbers. It must have one short
final answer that a computer algebra system can check.

Reply only with JSON:
{"statement": "<the exercise, maths in LaTeX between $...$>",
 "skill": "<the skill practised, a few French words>",
 "answer_label": "<what to type, e.g. «la valeur de l'intégrale», «f'(x)»>",
 "check": <one claim giving the answer, in one of these forms, expressions in LaTeX without $>}

Claim forms:
{"type": "derivative", "function": "...", "variable": "x", "result": "<the answer>"}
{"type": "integral", "function": "...", "variable": "x", "lower": "...", "upper": "...", "result": "<the answer>"}
{"type": "limit", "function": "...", "variable": "x", "point": "...", "result": "<the answer>"}
{"type": "sum", "term": "...", "index": "k", "start": "...", "end": "n", "result": "<the answer>"}
{"type": "antiderivative", "function": "...", "variable": "x", "result": "<the answer>"}
{"type": "ode", "equation": "...", "function": "y", "variable": "x", "solution": "<the answer>"}
{"type": "equality", "left": "<the expression to compute>", "right": "<the answer>"}"""

EXPLAIN_PROMPT = r"""You are a patient maths tutor talking with a French university student about one line of their
work. Write in French, short (two to four sentences), maths in LaTeX between $...$.
Teach by questions: help the student see why the line is wrong and find the fix themselves. Never write the corrected
line, the result or the missing value, even if asked; if the student asks for the answer, give a smaller step instead.
If the student shows they have understood, say so and suggest they correct the line on their sheet.
Stay on this exercise; politely decline anything unrelated."""


def _reply(client, model: str, messages: list[dict], max_tokens: int) -> str:
    response = client.chat(model, messages, temperature=0.0, max_tokens=max_tokens)
    message = response["choices"][0]["message"]
    return message.get("content") or message.get("reasoning") or ""


def similar_exercise(client, statement: str, line: str, explanation: str, tries: int = 2) -> dict:
    """A new exercise on the same skill. Its answer is kept only if the computer verifies it; the answer itself is
    returned to the server, which keeps it to check the student's reply and never sends it to the page."""
    task = (f"Original exercise:\n{statement}\n\nThe student's wrong line:\n{line}\n\nWhat was wrong (for you only): "
            f"{explanation}")
    for attempt in range(tries):
        text = _reply(client, STUDY_MODEL, [{"role": "system", "content": SIMILAR_PROMPT},
                                            {"role": "user", "content": task + ("" if not attempt else
                                             "\n\nYour previous answer did not check out: compute it carefully.")}],
                      2500)
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            continue
        try:
            data = load_latex_json(match[0])
        except ValueError:
            continue
        claim = data.get("check") if isinstance(data.get("check"), dict) else None
        if not claim or claim.get("type") not in CHECKED_TYPES or not data.get("statement"):
            continue
        if check_claim(claim).status == "vérifié":
            return {"statement": str(data["statement"]), "skill": str(data.get("skill") or ""),
                    "answer_label": str(data.get("answer_label") or "votre réponse"), "check": claim}
    raise ValueError("no verified exercise")


def answer_field(claim: dict) -> str:
    return {"ode": "solution", "equality": "right"}.get(claim["type"], "result")


def check_answer(claim: dict, answer: str) -> str:
    """vérifié if the student's answer makes the exercise's claim hold, réfuté if it doesn't, else non vérifiable."""
    return check_claim({**claim, answer_field(claim): answer}).status


def explain(client, statement: str, attempt: str, line: int, explanation: str, history: list[dict]) -> str:
    numbered = "\n".join(f"{i}: {text}" for i, text in enumerate(attempt.split("\n"), 1))
    context = (f"Exercise:\n{statement}\n\nThe student's work (lines from 1):\n{numbered}\n\nThe line being discussed: "
               f"{line + 1}\nWhat is wrong there (for you only, never quote it as the answer): {explanation}")
    messages = [{"role": "system", "content": EXPLAIN_PROMPT + "\n\n" + context}]
    for turn in history[-MAX_TURNS:]:
        role = "assistant" if turn.get("role") == "tutor" else "user"
        messages.append({"role": role, "content": str(turn.get("text", ""))[:800]})
    reply = _reply(client, STUDY_MODEL, messages, 1500).strip()
    if not reply:
        raise ValueError("empty reply")
    return reply
