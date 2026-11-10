import json

import pytest

from mathhinter.llm.client import LLMError, QuotaExhausted
from mathhinter.web import BadRequest, Limiter, Service, read_request

UNITS = [
    {"id": "h", "kind": "heading", "text": "Dérivée", "volume": "Exo7", "module": "derivee", "section": "1",
     "printed_page": None, "label": "Exo7, Dérivée"},
    {"id": "t", "kind": "theorem", "text": "Théorème. La dérivée de exp est exp.", "volume": "Exo7",
     "module": "derivee", "section": "1", "printed_page": None, "label": "Exo7, Dérivée, Calcul"},
]
ANSWER = {"action": "answer", "verdict": "wrong", "first_wrong_line": 1, "explanation": "e", "hint": "Pourquoi ?",
          "citations": ["t"]}


class Fake:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.keys = []

    def __call__(self, key):
        self.keys.append(key)
        return self

    def chat(self, model, messages, temperature=0.0, max_tokens=0):
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return {"choices": [{"message": {"content": json.dumps(reply)}}], "usage": {"total_tokens": 10}}


def body(**fields):
    return json.dumps({"statement": "Dériver $e^x$.", "attempt": "On a\n$(e^x)'=xe^{x-1}$", **fields}).encode()


def test_requests_are_checked_and_tidied():
    request = read_request(body(attempt="  ligne 1  \n\n ligne 2 "))
    assert request["attempt"] == "ligne 1\n ligne 2" and request["config"] == "rag" and request["key"] == ""
    for bad in [b"not json", body(statement=""), body(attempt=" "), body(config="rag_leak"),
                body(attempt="x\n" * 50), body(key="sk-wrong")]:
        with pytest.raises(BadRequest):
            read_request(bad)


def test_limiter_counts_visitors_and_the_site_and_resets_each_day():
    now = [0.0]
    limiter = Limiter(visitor_limit=2, site_limit=3, clock=lambda: now[0])
    assert [limiter.take("a"), limiter.take("a"), limiter.take("a")] == [None, None, "visitor"]
    assert limiter.take("b") is None and limiter.take("c") == "site"
    now[0] = 86400.0
    assert limiter.take("a") is None
    assert set(limiter.counts) == {"*", limiter.counts and next(k for k in limiter.counts if k != "*")}
    assert all(len(k) == 16 for k in limiter.counts if k != "*")  # addresses are kept only as hashes


def test_a_review_returns_the_cited_passages_and_counts_against_the_site():
    fake = Fake(ANSWER)
    service = Service(UNITS, site_key="gsk_site", limiter=Limiter(5, 40), client_factory=fake)
    status, out = service.review(read_request(body()), "1.2.3.4")
    assert status == 200 and out["review"]["verdict"] == "wrong" and out["passages"]["t"]["label"].startswith("Exo7")
    assert out["remaining"] == 4 and fake.keys == ["gsk_site"]
    assert "gsk_site" not in json.dumps(out)


def test_a_visitor_key_is_used_once_and_skips_the_site_limit():
    fake = Fake(ANSWER)
    service = Service(UNITS, site_key="gsk_site", limiter=Limiter(0, 0), client_factory=fake)
    status, out = service.review(read_request(body(key="gsk_mine", config="llm_only")), "1.2.3.4")
    assert status == 200 and fake.keys == ["gsk_mine"] and "remaining" not in out
    assert "gsk_mine" not in json.dumps(out)


def test_limits_and_api_failures_become_plain_messages():
    service = Service(UNITS, site_key="gsk_site", limiter=Limiter(0, 5), client_factory=Fake())
    assert service.review(read_request(body()), "a")[0] == 429
    service = Service(UNITS, site_key="gsk_site", limiter=Limiter(5, 5), client_factory=Fake(QuotaExhausted("x")))
    assert service.review(read_request(body(config="llm_only")), "a")[1]["code"] == "groq"
    service = Service(UNITS, site_key="", client_factory=Fake())
    assert service.review(read_request(body()), "a")[0] == 503
    service = Service(UNITS, site_key="", client_factory=Fake(LLMError("HTTP 401: bad")))
    status, out = service.review(read_request(body(key="gsk_bad", config="llm_only")), "a")
    assert status == 502 and "refusée" in out["error"]
