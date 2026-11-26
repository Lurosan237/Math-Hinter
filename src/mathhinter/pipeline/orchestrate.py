"""The check-first pipeline: transcribe lines into claims, compute what can be computed, then let the model judge
with that evidence and the course statement of any theorem used.

The judge has the same instructions as the evaluated "LLM alone" reviewer, plus the evidence, so a difference in
results comes from the evidence. The computer never overrules the judge: a refuted claim can come from a misread line.
"""

from __future__ import annotations

from ..agent.tutor import ANSWER_FORMAT, ROLE, Review, Tutor, _fill, format_passages, parse_action
from ..check.equality import REFUTED, VERIFIED
from ..llm.client import LLMError, QuotaExhausted
from .claims import CHECKED_TYPES, check_claim
from .formalise import FORMALISE_MODEL, formalise

EVIDENCE = """Before you, a transcriber turned the lines into claims and a computer algebra system checked them:
- "vérifié": computed exactly; the computation in that line is right as transcribed.
- "réfuté": computed to be false. This is strong evidence of an error in that line, unless the transcription misread
  the line (garbled text, a limit read as an equality, a value fixed by earlier lines). Read the line yourself.
Lines without a check rely on your own reading. The first error can be on a line before a refuted one, if the
refuted claim only reveals an earlier mistake: find the line where the error is first written."""

FIELDS = {"equality": ("left", "right"), "derivative": ("function", "result"), "antiderivative": ("function", "result"),
          "integral": ("function", "lower", "upper", "result"), "limit": ("function", "point", "result"),
          "sum": ("term", "start", "end", "result"), "solution": ("equations", "values"),
          "ode": ("equation", "solution")}


def describe(claim: dict) -> str:
    kind = claim["type"]
    if kind == "equality":
        return f"{claim.get('left')} = {claim.get('right')}"
    parts = ", ".join(f"{name}: {claim.get(name)}" for name in FIELDS.get(kind, ()))
    return f"{kind} ({parts})"


def line_marks(checks: list[dict], lines: int) -> list[str]:
    """For the page: "verified" if a line's computations hold, "refuted" if one fails, "unchecked" otherwise."""
    marks = ["unchecked"] * lines
    for item in checks:
        at = item["line"]
        if item["status"] == REFUTED:
            marks[at] = "refuted"
        elif item["status"] == VERIFIED and marks[at] != "refuted":
            marks[at] = "verified"
    return marks


class PipelineTutor(Tutor):
    """A Tutor with one more configuration, "pipeline". Course search is used only to look up theorems."""

    def __init__(self, client, model: str, course, on_step=None, formalise_model: str = FORMALISE_MODEL):
        super().__init__(client, model, course, on_step)
        self.formalise_model = formalise_model

    def pipeline(self, statement: str, attempt: str, exercise: str = "web", solution: str | None = None) -> Review:
        review = Review("pipeline")
        lines = attempt.count("\n") + 1
        hidden = {exercise} | ({solution} if solution else set())
        self._report(step="transcribing")
        try:
            claims, tokens = formalise(self.client, statement, attempt, self.formalise_model)
            review.llm_calls += 1
            review.tokens += tokens or 0
        except QuotaExhausted:
            raise
        except (LLMError, ValueError) as error:
            claims = []
            review.tool_calls.append({"tool": "formalise", "status": f"failed: {type(error).__name__}"})
        checks = []
        for claim in claims:
            if claim["type"] in CHECKED_TYPES:
                result = check_claim(claim)
                checks.append({"line": claim["line"], "claim": describe(claim), "status": result.status,
                               "reason": result.reason, "computed": result.computed})
        review.tool_calls.append({"tool": "checks", "claims": len(claims), "checked": len(checks),
                                  "verified": sum(c["status"] == VERIFIED for c in checks),
                                  "refuted": sum(c["status"] == REFUTED for c in checks)})
        self._report(step="checked", marks=line_marks(checks, lines),
                     checks=[{k: c[k] for k in ("line", "status")} for c in checks])
        passages = []
        if self.course is not None:
            for claim in claims:
                if claim["type"] == "theorem" and claim.get("name"):
                    found = self.course.search(str(claim["name"]), exercise, hidden=hidden, k=1)
                    passages += [p for p in found if p["id"] not in {q["id"] for q in passages}]
            passages = passages[:3]
            review.shown = [p["id"] for p in passages]
            if passages:
                self._report(step="passages", found=review.shown)
        evidence = "\n".join(
            f"line {c['line']}: {c['claim']} -> {c['status']}"
            + (f" (computed: {c['computed']})" if c["status"] == REFUTED and c["computed"] else "")
            for c in checks if c["status"] in (VERIFIED, REFUTED))
        course = f"Course statements of the theorems used:\n{format_passages(passages)}\n\n" if passages else ""
        task = f"{course}{self._task(statement, attempt)}\n\nComputer checks:\n{evidence or 'none could be computed'}"
        messages = [{"role": "system", "content": f"{ROLE}\n\n{EVIDENCE}\n\n{ANSWER_FORMAT}"},
                    {"role": "user", "content": task}]
        self._report(step="reading")
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
            _fill(review, action, lines)
        review.checks = checks
        review.marks = line_marks(checks, lines)
        return review
