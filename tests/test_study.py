import json

import pytest

from mathhinter.seal import BadSeal, seal, unseal
from mathhinter.study import check_answer
from mathhinter.web import Limiter, Service

UNITS = [{"id": "t", "kind": "theorem", "text": "Théorème.", "volume": "Exo7", "module": "int", "section": "1",
          "printed_page": None, "label": "Exo7, Intégrales"}]
EXERCISE = {"statement": "Calculer $\\int_0^1 xe^{2x}\\,dx$.", "skill": "intégration par parties",
            "answer_label": "la valeur de l'intégrale",
            "check": {"type": "integral", "function": "xe^{2x}", "variable": "x", "lower": "0", "upper": "1",
                      "result": "\\frac{e^{2}+1}{4}"}}
WRONG = {**EXERCISE, "check": {**EXERCISE["check"], "result": "\\frac{e^{2}}{4}"}}


class Fake:
    def __init__(self, *replies):
        self.replies, self.models = list(replies), []

    def __call__(self, key):
        return self

    def chat(self, model, messages, temperature=0.0, max_tokens=0):
        self.models.append(model)
        reply = self.replies.pop(0)
        return {"choices": [{"message": {"content": reply if isinstance(reply, str) else json.dumps(reply)}}],
                "usage": {"total_tokens": 10}}


def test_seals_hide_and_protect_their_content():
    token = seal({"result": "\\frac{e^{2}+1}{4}"}, "s3cret")
    assert "frac" not in token and unseal(token, "s3cret") == {"result": "\\frac{e^{2}+1}{4}"}
    with pytest.raises(BadSeal):
        unseal(token, "other")
    with pytest.raises(BadSeal):
        unseal(token[:-4] + "AAAA", "s3cret")


def test_answers_are_checked_by_computation():
    claim = EXERCISE["check"]
    assert check_answer(claim, "\\frac{e^2+1}{4}") == "vérifié"
    assert check_answer(claim, "\\frac{1}{4}+\\frac{e^{2}}{4}") == "vérifié"
    assert check_answer(claim, "\\frac{e^2}{4}") == "réfuté"


def test_a_similar_exercise_is_kept_only_when_its_answer_checks_out():
    fake = Fake(WRONG, EXERCISE)  # the first proposal's answer is wrong, so it is asked again
    service = Service(UNITS, site_key="gsk_site", client_factory=fake)
    request = json.dumps({"statement": "Calculer $\\int_0^1 xe^x dx$.", "line": "$=e+(e-1)$",
                          "explanation": "signe"}).encode()
    status, out = service.similar(request, "a")
    assert status == 200 and len(fake.models) == 2 and "frac" not in json.dumps(out)
    status, checked = service.answer(json.dumps({"token": out["token"], "answer": "(e^2+1)/4"}).encode())
    assert status == 200 and checked["status"] == "vérifié"
    status, checked = service.answer(json.dumps({"token": out["token"], "answer": "e^2/4"}).encode())
    assert checked["status"] == "réfuté"
    assert service.answer(json.dumps({"token": "forged", "answer": "1"}).encode())[0] == 400


def test_explain_keeps_a_short_conversation():
    fake = Fake("Que vaut la dérivée de $e^x$ ?")
    service = Service(UNITS, site_key="gsk_site", limiter=Limiter(5, 5), client_factory=fake)
    request = {"statement": "Dériver.", "attempt": "a\nb", "line": 1, "explanation": "e",
               "history": [{"role": "student", "text": "Je ne comprends pas"}]}
    status, out = service.explain(json.dumps(request).encode(), "a")
    assert status == 200 and out["reply"].startswith("Que vaut") and fake.models == ["openai/gpt-oss-20b"]
    long = {**request, "history": [{"role": "student", "text": "?"}] * 20}
    assert service.explain(json.dumps(long).encode(), "a")[0] == 400
    assert service.explain(json.dumps({"statement": "x"}).encode(), "a")[0] == 400
