"""Three ways to review an attempt, using the same model and the same answer format, so they can be compared."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from ..check.equality import check_equality
from ..llm.client import LLMError, QuotaExhausted
from .course import CourseSearch

MAX_TOOL_CALLS = 4
MAX_TOKENS = 2500

ANSWER_FORMAT = """Reply with one JSON object and nothing else:
{"action": "answer", "verdict": "correct" or "wrong", "first_wrong_line": <line number, or null if correct>,
 "explanation": "<in French, one or two sentences for the teacher: what is wrong and why>",
 "hint": "<in French, for the student: a question or pointer that helps them find the error themselves.
 Never state the corrected result or how to fix it. Empty if correct>",
 "citations": [<ids of the passages your judgement relies on, or an empty list>]}
Use backslashes in LaTeX as JSON requires. Only cite ids you were shown."""

ROLE = """You review a student's attempt at a French university maths exercise. Each line of the attempt is numbered.
Decide whether the attempt contains a mathematical error. The attempt may be entirely correct, so don't assume there is
an error. The text comes from PDF extraction, so ignore odd layout and judge the mathematics. If there is an error, find
the first line where a false statement appears."""

TOOLS = f"""You may use a tool first, by replying with exactly one JSON object:
{{"action": "search_course", "query": "<French keywords>"}} searches the course for definitions and results.
{{"action": "check_equality", "left": "<LaTeX>", "right": "<LaTeX>"}} checks an equality with a computer algebra system.
It answers "vérifié" (an identity if letters are ordinary numbers), "réfuté" (numbers differ, though notation can cause
this), or "non vérifiable". It's evidence, not proof, and most lines of a proof are "non vérifiable".
You have at most {MAX_TOOL_CALLS} tool calls. When ready, give your answer.
"""


@dataclass
class Review:
    config: str
    verdict: str | None = None
    first_wrong_line: int | None = None
    explanation: str = ""
    hint: str = ""
    citations: list[str] = field(default_factory=list)
    shown: list[str] = field(default_factory=list)  # ids of passages the model actually saw
    tool_calls: list[dict] = field(default_factory=list)
    llm_calls: int = 0
    tokens: int = 0
    failure: str | None = None

    def record(self) -> dict:
        return dict(self.__dict__)


def number_lines(text: str) -> str:
    return "\n".join(f"{i}: {line}" for i, line in enumerate(text.split("\n")))


def parse_action(text: str | None) -> dict | None:
    """The first JSON object in a reply. LaTeX backslashes that break JSON are repaired once."""
    if not text:
        return None
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    chunk = text[start : end + 1]
    for candidate in (chunk, re.sub(r'\\(?!["\\/bfnrtu])', r"\\\\", chunk), _double_all_latex(chunk)):
        try:
            value = json.loads(candidate, strict=False)
        except json.JSONDecodeError:
            continue
        return value if isinstance(value, dict) else None
    return None


def _double_all_latex(chunk: str) -> str:
    """\\frac starts with a valid JSON escape, \\f, so it needs doubling too."""
    return re.sub(r"(?<!\\)\\(?=[A-Za-z])", r"\\\\", chunk)


def format_passages(passages: list[dict]) -> str:
    return "\n\n".join(f"[{p['id']}] ({p['kind']}, tome {p['volume']}, p. {p['page']})\n{p['text']}" for p in passages)


def _fill(review: Review, action: dict, line_count: int) -> None:
    verdict = action.get("verdict")
    if verdict not in ("correct", "wrong"):
        review.failure = "bad verdict"
        return
    review.verdict = verdict
    line = action.get("first_wrong_line")
    if verdict == "wrong":
        if isinstance(line, int) and 0 <= line < line_count:
            review.first_wrong_line = line
        else:
            review.failure = "wrong without a valid line"
    review.explanation = str(action.get("explanation", ""))
    review.hint = str(action.get("hint", ""))
    citations = action.get("citations")
    review.citations = [str(c) for c in citations] if isinstance(citations, list) else []


class Tutor:
    def __init__(self, client, model: str, course: CourseSearch | None):
        self.client, self.model, self.course = client, model, course

    def _ask(self, review: Review, messages: list[dict]) -> str | None:
        response = self.client.chat(self.model, messages, temperature=0.0, max_tokens=MAX_TOKENS)
        review.llm_calls += 1
        review.tokens += (response.get("usage") or {}).get("total_tokens", 0)
        return response["choices"][0]["message"].get("content")

    @staticmethod
    def _task(statement: str, attempt: str) -> str:
        return f"Exercise:\n{statement}\n\nStudent's attempt:\n{number_lines(attempt)}"

    def _one_shot(self, config: str, statement: str, attempt: str, passages: list[dict]) -> Review:
        review = Review(config, shown=[p["id"] for p in passages])
        course = f"Course passages:\n{format_passages(passages)}\n\n" if passages else ""
        messages = [{"role": "system", "content": f"{ROLE}\n\n{ANSWER_FORMAT}"},
                    {"role": "user", "content": f"{course}{self._task(statement, attempt)}"}]
        try:
            action = parse_action(self._ask(review, messages))
        except QuotaExhausted:
            raise
        except LLMError as error:
            review.failure = f"api: {error}"[:200]
            return review
        if action is None:
            review.failure = "unparseable reply"
        else:
            _fill(review, action, attempt.count("\n") + 1)
        return review

    def llm_only(self, statement: str, attempt: str) -> Review:
        return self._one_shot("llm_only", statement, attempt, [])

    def rag(self, statement: str, attempt: str, exercise: str, solution: str) -> Review:
        return self._one_shot("rag", statement, attempt,
                              self.course.search(statement, exercise, hidden={exercise, solution}))

    def rag_leak(self, statement: str, attempt: str, exercise: str) -> Review:
        """The same, with the exercise's own solution left findable, to show how much hiding it matters."""
        return self._one_shot("rag_leak", statement, attempt,
                              self.course.search(statement, exercise, hidden={exercise}, results_only=False))

    def agent(self, statement: str, attempt: str, exercise: str, solution: str) -> Review:
        review = Review("agent")
        hidden = {exercise, solution}
        messages = [{"role": "system", "content": f"{ROLE}\n\n{TOOLS}\n{ANSWER_FORMAT}"},
                    {"role": "user", "content": self._task(statement, attempt)}]
        for _ in range(MAX_TOOL_CALLS + 2):
            try:
                reply = self._ask(review, messages)
            except QuotaExhausted:
                raise
            except LLMError as error:
                review.failure = f"api: {error}"[:200]
                return review
            action = parse_action(reply)
            if action is None:
                review.failure = "unparseable reply"
                return review
            if action.get("action") == "answer":
                review.failure = None
                _fill(review, action, attempt.count("\n") + 1)
                return review
            observation = self._use_tool(review, action, statement, exercise, hidden)
            messages += [{"role": "assistant", "content": reply}, {"role": "user", "content": observation}]
        review.failure = "no answer within the step limit"
        return review

    def _use_tool(self, review: Review, action: dict, statement: str, exercise: str, hidden: set[str]) -> str:
        if len(review.tool_calls) >= MAX_TOOL_CALLS:
            return f"No tool calls left. Answer now.\n{ANSWER_FORMAT}"
        name = action.get("action")
        review.tool_calls.append({"tool": name})
        if name == "search_course":
            passages = self.course.search(str(action.get("query") or statement), exercise, hidden=hidden, k=3)
            review.shown += [p["id"] for p in passages if p["id"] not in review.shown]
            return f"Course passages:\n{format_passages(passages)}" if passages else "Nothing found."
        if name == "check_equality":
            verdict = check_equality(str(action.get("left", "")), str(action.get("right", "")))
            review.tool_calls[-1]["status"] = verdict.status
            return f"{verdict.status}: {verdict.reason}"
        return f"Unknown action. {ANSWER_FORMAT}"
