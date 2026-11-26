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
    assert request["attempt"] == "ligne 1\n ligne 2" and request["config"] == "pipeline" and request["key"] == ""
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
    status, out = service.review(read_request(body(config="rag")), "1.2.3.4")
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


SEARCH = {"action": "search_course", "query": "dérivée exponentielle"}


def test_progress_reports_searches_with_readable_sources_and_changes_nothing():
    steps = []
    fake = Fake(SEARCH, ANSWER)
    service = Service(UNITS, site_key="gsk_site", limiter=Limiter(5, 40), client_factory=fake)
    status, out = service.review(read_request(body(config="agent")), "a", on_step=steps.append)
    assert status == 200 and out["review"]["verdict"] == "wrong"
    tool = next(s for s in steps if s["step"] == "tool")
    assert tool["query"] == "dérivée exponentielle" and tool["found"][0].startswith("Exo7")
    quiet = Service(UNITS, site_key="gsk_site", limiter=Limiter(5, 40), client_factory=Fake(SEARCH, ANSWER))
    assert quiet.review(read_request(body(config="agent")), "a")[1]["review"] == out["review"]


def hint_body(**fields):
    base = {"statement": "Dériver $e^x$.", "attempt": "On a\n$(e^x)'=xe^{x-1}$", "line": 1,
            "hints": ["Pourquoi ?"], "explanation": "La dérivée de exp est exp.", "citations": ["t", "nope"]}
    return json.dumps({**base, **fields}).encode()


class HintFake(Fake):
    def chat(self, model, messages, temperature=0.0, max_tokens=0):
        self.sent.append(messages)
        return super().chat(model, messages, temperature, max_tokens)


def test_further_hints_get_more_explicit_and_stop_at_the_third():
    fake = HintFake({"hint": "Regardez l'exposant."}, {"hint": "La dérivée de $e^x$ suit une règle du cours."})
    fake.sent = []
    service = Service(UNITS, site_key="gsk_site", client_factory=fake)
    status, out = service.hint(hint_body(), "a")
    assert status == 200 and out == {"hint": "Regardez l'exposant.", "level": 2, "last": False}
    system, task = fake.sent[0][0]["content"], fake.sent[0][1]["content"]
    assert "Say WHERE to look, never WHAT" in system and "Never give the answer" in system
    assert "Exo7, Dérivée, Calcul" in task and "Pourquoi ?" in task
    status, out = service.hint(hint_body(hints=["Pourquoi ?", "Regardez l'exposant."]), "a")
    assert out["level"] == 3 and out["last"] and "general form" in fake.sent[1][0]["content"]
    for bad in [hint_body(hints=["a", "b", "c"]), hint_body(hints=[]), hint_body(line=9), b"{}", b"x"]:
        assert service.hint(bad, "a")[0] == 400


def test_streaming_sends_steps_then_the_result(monkeypatch):
    import importlib.util
    import threading
    import urllib.request
    from http.server import ThreadingHTTPServer
    from pathlib import Path

    spec = importlib.util.spec_from_file_location("api_review", Path(__file__).parent.parent / "api" / "review.py")
    api = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(api)
    api.SERVICE = Service(UNITS, site_key="gsk_site", limiter=Limiter(5, 40), client_factory=Fake(SEARCH, ANSWER))
    server = ThreadingHTTPServer(("127.0.0.1", 0), api.handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        request = urllib.request.Request(f"http://127.0.0.1:{server.server_port}/api/review",
                                         data=body(config="agent", stream=True), method="POST")
        lines = [json.loads(x) for x in urllib.request.urlopen(request, timeout=10).read().splitlines()]
    finally:
        server.shutdown()
    assert [x["step"]["step"] for x in lines[:-1]] == ["reading", "tool", "reading"]
    assert lines[-1]["status"] == 200 and lines[-1]["body"]["review"]["verdict"] == "wrong"


def test_hints_count_lines_from_one_like_the_page():
    from mathhinter.hints import messages
    task = messages("E", "a\nb\nc", 1, ["h"], "x", [])[1]["content"]
    assert "1: a\n2: b\n3: c" in task and "First wrong line: 2" in task


def test_the_site_reviews_with_the_pipeline_by_default():
    claims = {"claims": [{"type": "derivative", "line": 1, "function": "e^x", "variable": "x", "result": "xe^{x-1}"}]}
    fake = Fake(claims, ANSWER, {"decision": "confirmed", "reason": "ok"})
    service = Service(UNITS, site_key="gsk_site", limiter=Limiter(5, 40), client_factory=fake)
    status, out = service.review(read_request(body()), "a")
    assert status == 200 and out["review"]["config"] == "pipeline" and out["review"]["marks"] == ["unchecked", "refuted"]
