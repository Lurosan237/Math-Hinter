import json

import pytest

from mathhinter.agent.course import CourseSearch
from mathhinter.agent.scoring import chance_exact_line, difference_interval, pair_score, summarise
from mathhinter.agent.tutor import MAX_TOOL_CALLS, Tutor, number_lines, parse_action
from mathhinter.llm.client import LLMError, QuotaExhausted


def unit(ident, kind, text, section="1"):
    return {"id": ident, "kind": kind, "text": text, "volume": 1, "module": "I.1", "section": section,
            "printed_page": 3}


UNITS = [
    unit("h", "heading", "1 Les matrices"),
    unit("t", "theorem", "Théorème 1. Toute matrice inversible a un déterminant non nul."),
    unit("d", "definition", "Définition 2. Une matrice carrée est inversible si elle a une inverse."),
    unit("e", "exercise", "Exercice 3. Montrer que le déterminant de cette matrice inversible est non nul."),
    unit("s", "solution", "Solution. Le déterminant de la matrice inversible est non nul."),
]
ANSWER = {"action": "answer", "verdict": "wrong", "first_wrong_line": 1, "explanation": "x", "hint": "Pourquoi ?",
          "citations": ["t"]}


class Script:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.seen = []

    def chat(self, model, messages, temperature=0.0, max_tokens=0):
        self.seen.append(json.dumps(messages))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        text = reply if isinstance(reply, str) else json.dumps(reply)
        return {"choices": [{"message": {"content": text}}], "usage": {"total_tokens": 10}}


@pytest.fixture(scope="module")
def course():
    return CourseSearch(UNITS)


def test_own_solution_is_never_returned(course):
    found = course.search("déterminant matrice inversible", "e", hidden={"e", "s"}, results_only=False)
    assert "s" not in {p["id"] for p in found} and "e" not in {p["id"] for p in found}


def test_leak_variant_can_find_the_solution(course):
    found = course.search("déterminant matrice inversible", "e", hidden={"e"}, results_only=False)
    assert "s" in {p["id"] for p in found}


def test_results_only_returns_results(course):
    found = course.search("matrice", "e", hidden={"e", "s"})
    assert {p["kind"] for p in found} <= {"theorem", "definition"}


def test_rag_sends_passages_but_not_the_solution(course):
    script = Script(ANSWER)
    review = Tutor(script, "m", course).rag(UNITS[3]["text"], "a\nb", "e", "s")
    assert review.verdict == "wrong" and review.first_wrong_line == 1 and "[t]" in script.seen[0]
    assert UNITS[4]["text"] not in script.seen[0]


def test_llm_only_sees_no_course(course):
    script = Script(ANSWER)
    Tutor(script, "m", course).llm_only("Exercice", "a\nb")
    assert "Course passages" not in script.seen[0]


def test_agent_uses_tools_then_answers(course):
    script = Script({"action": "search_course", "query": "déterminant"},
                    {"action": "check_equality", "left": "(x+1)^{2}", "right": "x^{2}+2x+1"}, ANSWER)
    review = Tutor(script, "m", course).agent("Exercice", "a\nb", "e", "s")
    assert [c["tool"] for c in review.tool_calls] == ["search_course", "check_equality"]
    assert review.tool_calls[1]["status"] == "vérifié" and review.verdict == "wrong" and review.llm_calls == 3
    assert "t" in review.shown and "s" not in review.shown


def test_agent_is_sent_back_to_search_once_if_it_skips_the_course(course):
    script = Script(ANSWER, {"action": "search_course", "query": "matrice"}, ANSWER)
    review = Tutor(script, "m", course).agent("Exercice", "a\nb", "e", "s")
    assert review.llm_calls == 3 and review.tool_calls[0]["tool"] == "search_course"


def test_agent_stops_at_the_step_limit(course):
    script = Script(*[{"action": "search_course", "query": "x"}] * 20)
    review = Tutor(script, "m", course).agent("Exercice", "a\nb", "e", "s")
    assert review.failure == "no answer within the step limit" and len(review.tool_calls) == MAX_TOOL_CALLS


def test_invalid_replies_count_as_failures(course):
    tutor = Tutor(Script("pas de json"), "m", course)
    assert tutor.llm_only("E", "a").failure == "unparseable reply"
    tutor = Tutor(Script({**ANSWER, "first_wrong_line": 99}), "m", course)
    assert tutor.llm_only("E", "a").failure == "wrong without a valid line"


def test_api_error_is_recorded_but_quota_stops_the_run(course):
    assert Tutor(Script(LLMError("boom")), "m", course).llm_only("E", "a").failure.startswith("api")
    with pytest.raises(QuotaExhausted):
        Tutor(Script(QuotaExhausted("wait")), "m", course).llm_only("E", "a")


@pytest.mark.parametrize("text", [
    '{"hint": "$\\frac{1}{2}$"}', '{"hint": "$\\leqslant$"}', 'Voici:\n{"hint": "$\\in$"}\nfin',
])
def test_parse_survives_latex(text):
    assert "hint" in parse_action(text)


def test_parse_rejects_non_objects():
    assert parse_action("rien") is None and parse_action(None) is None


def test_lines_are_numbered_from_zero():
    assert number_lines("a\nb") == "0: a\n1: b"


def row(exercise, kind, verdict, line=None, gold=None, lines=10):
    return {"exercise": exercise, "kind": kind, "verdict": verdict, "first_wrong_line": line, "wrong_line": gold,
            "lines": lines}


def test_crying_wrong_always_fails_the_pair():
    rows = [row("a", "sign", "wrong", 2, 2), row("a", "none", "wrong", 1)]
    summary = summarise(rows)
    assert summary["exact_line"] == 1 and summary["false_alarm"] == 1 and summary["both_right"] == 0


def test_pair_needs_exact_line_and_quiet_control():
    assert pair_score({"wrong": row("a", "sign", "wrong", 2, 2), "control": row("a", "none", "correct")})
    assert not pair_score({"wrong": row("a", "sign", "wrong", 3, 2), "control": row("a", "none", "correct")})


def test_within_one_line_and_chance():
    rows = [row("a", "sign", "wrong", 3, 2), row("a", "none", "correct")]
    assert summarise(rows)["within_one_line"] == 1 and summarise(rows)["exact_line"] == 0
    assert chance_exact_line(rows) == 0.1


def test_difference_keeps_exercises_paired():
    good = [row("a", "sign", "wrong", 2, 2), row("a", "none", "correct")]
    bad = [row("a", "sign", "correct", None, 2), row("a", "none", "correct")]
    assert difference_interval(good, bad)["difference"] == 1
