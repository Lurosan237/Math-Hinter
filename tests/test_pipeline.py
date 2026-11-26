import json

from mathhinter.pipeline.orchestrate import PipelineTutor, line_marks

ATTEMPT = "On pose $f(x)=e^x$.\n$f'(x)=xe^{x-1}$\nDonc $f'(0)=0$."
CLAIMS = {"claims": [{"type": "other", "line": 0, "text": "définition"},
                     {"type": "derivative", "line": 1, "function": "e^x", "variable": "x", "result": "xe^{x-1}"},
                     {"type": "theorem", "line": 2, "name": "dérivée de l'exponentielle"},
                     {"type": "equality", "line": 9, "left": "1", "right": "1"}]}
ANSWER = {"action": "answer", "verdict": "wrong", "first_wrong_line": 1, "explanation": "e", "hint": "Revoyez $f'$.",
          "citations": []}


class Fake:
    def __init__(self):
        self.sent = []

    def chat(self, model, messages, temperature=0.0, max_tokens=0):
        self.sent.append((model, messages))
        reply = CLAIMS if len(self.sent) == 1 else ANSWER
        return {"choices": [{"message": {"content": json.dumps(reply)}}], "usage": {"total_tokens": 100}}


def test_the_judge_sees_the_computations_and_the_page_gets_line_marks():
    fake, steps = Fake(), []
    tutor = PipelineTutor(fake, "judge-model", None, on_step=steps.append, formalise_model="reader-model")
    review = tutor.pipeline("Dériver $e^x$.", ATTEMPT)
    assert [m for m, _ in fake.sent] == ["reader-model", "judge-model"]
    task = fake.sent[1][1][1]["content"]
    assert "line 1: derivative (function: e^x, result: xe^{x-1}) -> réfuté (computed: e^{x})" in task
    assert review.verdict == "wrong" and review.first_wrong_line == 1 and review.tokens == 200
    assert review.marks == ["unchecked", "refuted", "unchecked"]  # the claim on a missing line 9 is dropped
    assert [s["step"] for s in steps] == ["transcribing", "checked", "reading"]


def test_a_failed_transcription_still_gets_a_review():
    class Broken(Fake):
        def chat(self, model, messages, temperature=0.0, max_tokens=0):
            self.sent.append((model, messages))
            content = "not json" if len(self.sent) == 1 else json.dumps(ANSWER)
            return {"choices": [{"message": {"content": content}}], "usage": {"total_tokens": 1}}
    review = PipelineTutor(Broken(), "j", None).pipeline("E", ATTEMPT)
    assert review.verdict == "wrong" and review.tool_calls[0]["status"].startswith("failed")


def test_line_marks():
    checks = [{"line": 0, "status": "vérifié"}, {"line": 0, "status": "réfuté"}, {"line": 1, "status": "vérifié"}]
    assert line_marks(checks, 3) == ["refuted", "verified", "unchecked"]
