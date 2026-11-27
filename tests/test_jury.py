import json

from mathhinter.jury import JURORS, ask_juror, decide, tally


def vote(verdict, line=None, failure=""):
    return {"verdict": verdict, "line": line, "failure": failure}


def test_votes_are_counted_by_line_and_failures_dont_vote():
    votes = [vote("wrong", 2), vote("wrong", 2), vote("correct"), vote("wrong", 4), vote("wrong", 2, "api: x")]
    assert tally(votes) == {2: 2, None: 1, 4: 1}
    assert decide(votes, 2) == ("wrong", 2, 2)
    assert decide(votes, 3) == ("correct", None, 1)
    assert decide([vote("wrong", 3), vote("wrong", 1)], 1) == ("wrong", 1, 1)  # a tie goes to the earlier line


class Fake:
    def __init__(self):
        self.calls = []

    def chat(self, model, messages, temperature=0.0, max_tokens=0, extra=None):
        self.calls.append((model, temperature, extra))
        answer = {"action": "answer", "verdict": "wrong", "first_wrong_line": 1, "explanation": "e", "hint": "h",
                  "citations": []}
        return {"choices": [{"message": {"content": json.dumps(answer)}}], "usage": {"total_tokens": 7}}


def test_jurors_differ_only_by_model_effort_and_seed():
    fake = Fake()
    out = ask_juror(fake, JURORS["120b-high"], "E", "a\nb")
    assert out["verdict"] == "wrong" and out["line"] == 1 and out["tokens"] == 7
    ask_juror(fake, JURORS["120b"], "E", "a\nb")
    assert fake.calls == [("openai/gpt-oss-120b", 0.0, {"reasoning_effort": "high"}), ("openai/gpt-oss-120b", 0.0, None)]
