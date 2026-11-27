"""A jury of independent reviewers that vote on the first wrong line.

Each juror gets exactly the "LLM alone" prompt; jurors differ by model, reasoning effort or sampling seed. Their
verdicts are kept one by one, so voting rules can be compared afterwards without new calls.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from .agent.tutor import ANSWER_FORMAT, MAX_TOKENS, ROLE, Review, Tutor, _fill, last_action, parse_action
from .llm.client import LLMError, QuotaExhausted


@dataclass(frozen=True)
class Juror:
    name: str
    model: str
    temperature: float = 0.0
    extra: dict = field(default_factory=dict)


JURORS = {j.name: j for j in [
    Juror("120b", "openai/gpt-oss-120b"),
    Juror("120b-high", "openai/gpt-oss-120b", extra={"reasoning_effort": "high"}),
    Juror("120b-s1", "openai/gpt-oss-120b", 0.7, {"seed": 1}),
    Juror("120b-s2", "openai/gpt-oss-120b", 0.7, {"seed": 2}),
    Juror("20b", "openai/gpt-oss-20b"),
    Juror("20b-high", "openai/gpt-oss-20b", extra={"reasoning_effort": "high"}),
    Juror("20b-s1", "openai/gpt-oss-20b", 0.7, {"seed": 1}),
    Juror("20b-s2", "openai/gpt-oss-20b", 0.7, {"seed": 2}),
    Juror("qwen", "qwen/qwen3.8-27b", extra={"reasoning_effort": "medium"}),
    Juror("qwen-s1", "qwen/qwen3.8-27b", 0.7, {"reasoning_effort": "medium", "seed": 1}),
    Juror("qwen-s2", "qwen/qwen3.8-27b", 0.7, {"reasoning_effort": "medium", "seed": 2}),
]}


def ask_juror(client, juror: Juror, statement: str, attempt: str) -> dict:
    """One juror's verdict with the "LLM alone" prompt. Quota errors propagate; other failures are recorded."""
    review = Review(f"juror:{juror.name}")
    messages = [{"role": "system", "content": f"{ROLE}\n\n{ANSWER_FORMAT}"},
                {"role": "user", "content": Tutor._task(statement, attempt)}]
    try:
        response = client.chat(juror.model, messages, temperature=juror.temperature, max_tokens=MAX_TOKENS,
                               extra=juror.extra or None)
    except QuotaExhausted:
        raise
    except LLMError as error:
        review.failure = f"api: {error}"[:200]
    else:
        review.llm_calls, review.tokens = 1, (response.get("usage") or {}).get("total_tokens", 0)
        message = response["choices"][0]["message"]
        action = parse_action(message.get("content") or last_action(message.get("reasoning")))
        if action is None:
            review.failure = "unparseable reply"
        else:
            _fill(review, action, attempt.count("\n") + 1)
    return {"juror": juror.name, "verdict": review.verdict, "line": review.first_wrong_line,
            "explanation": review.explanation, "hint": review.hint, "tokens": review.tokens,
            "failure": review.failure}


def tally(votes: list[dict]) -> Counter:
    """Votes per answer: a line number, or None for "no error". Failed jurors don't vote."""
    return Counter(None if v["verdict"] == "correct" else v["line"] for v in votes
                   if not v["failure"] and v["verdict"] in ("correct", "wrong"))


def decide(votes: list[dict], needed: int) -> tuple[str, int | None, int]:
    """("wrong", line, support) when at least `needed` jurors name the same line, else ("correct", None, support)."""
    counts = tally(votes)
    lines = [(n, line) for line, n in counts.items() if line is not None]
    if lines:
        support, line = max(lines, key=lambda t: (t[0], -t[1]))
        if support >= needed:
            return "wrong", line, support
    return "correct", None, counts.get(None, 0)
