import base64
import json

import pytest

from mathhinter.llm.client import QuotaExhausted
from mathhinter.transcribe import BadImage, check_images, messages, parse, transcribe
from mathhinter.web import Limiter, PhotoService

JPEG = "data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8 fake jpeg").decode()
REPLY = {"statement": "Calculer $\\int_0^1 xe^x\\,dx$.", "lines": ["On int\\`egre par parties.", "$=e+(e-1)$", " "],
         "unclear": [1, 7]}


class Fake:
    def __init__(self, *replies):
        self.replies, self.keys, self.sent = list(replies), [], []

    def __call__(self, key):
        self.keys.append(key)
        return self

    def chat(self, model, messages, temperature=0.0, max_tokens=0):
        self.sent.append(messages)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return {"choices": [{"message": reply}], "usage": {"total_tokens": 900}}


def test_images_must_be_small_data_urls_of_photos():
    assert check_images([JPEG]) == [JPEG]
    for bad in [None, [], [JPEG] * 4, ["https://example.com/a.jpg"], ["data:image/gif;base64,R0lG"],
                ["data:image/jpeg;base64,***"],
                ["data:image/jpeg;base64," + base64.b64encode(b"x" * 1_600_000).decode()]]:
        with pytest.raises(BadImage):
            check_images(bad)


def test_the_prompt_forbids_corrections_and_sends_every_page():
    sent = messages([JPEG, JPEG])[0]["content"]
    assert "ne corrige rien" in sent[0]["text"] and [p["type"] for p in sent] == ["text", "image_url", "image_url"]


def test_replies_are_parsed_from_fences_and_tidied():
    result = parse("```json\n" + json.dumps(REPLY) + "\n```")
    assert result["lines"] == ["On intègre par parties.", "$=e+(e-1)$"] and result["unclear"] == [1]
    assert result["statement"] == "Calculer $\\int_0^1 xe^x\\,dx$."
    with pytest.raises(ValueError):
        parse("Je ne peux pas lire cette image.")


def test_json_only_in_the_reasoning_is_used():
    fake = Fake({"content": "", "reasoning": "Voici : " + json.dumps(REPLY)})
    assert transcribe(fake, [JPEG])["lines"][1] == "$=e+(e-1)$"


def body(**fields):
    return json.dumps({"images": [JPEG], **fields}).encode()


def test_photo_service_counts_photos_and_accepts_a_visitor_key():
    fake = Fake({"content": json.dumps(REPLY)}, {"content": json.dumps(REPLY)})
    service = PhotoService("gsk_site", limiter=Limiter(1, 10), client_factory=fake)
    status, out = service.read_photos(body(), "1.2.3.4")
    assert status == 200 and out["lines"][0] == "On intègre par parties." and fake.keys == ["gsk_site"]
    assert service.read_photos(body(), "1.2.3.4")[0] == 429
    status, out = service.read_photos(body(key="gsk_mine"), "1.2.3.4")
    assert status == 200 and fake.keys[-1] == "gsk_mine"


def test_photo_failures_become_plain_messages():
    service = PhotoService("gsk_site", client_factory=Fake({"content": "illisible"}))
    assert service.read_photos(body(), "a")[1]["code"] == "unreadable"
    service = PhotoService("gsk_site", client_factory=Fake(QuotaExhausted("x")))
    assert service.read_photos(body(), "a")[1]["code"] == "groq"
    assert PhotoService("", client_factory=Fake()).read_photos(body(), "a")[0] == 503
    assert PhotoService("gsk_site", client_factory=Fake()).read_photos(b"{}", "a")[0] == 400


def test_latex_with_single_backslashes_is_repaired():
    raw = '{"statement": "Calculer \\int_0^1 f", "lines": ["$\\frac{1}{2}\\times 3$", "$a\\neq b$, $\\beta$"]}'
    result = parse(raw)
    assert result["statement"] == "Calculer \\int_0^1 f"
    assert result["lines"] == ["$\\frac{1}{2}\\times 3$", "$a\\neq b$, $\\beta$"]
    proper = json.dumps({"lines": ["$\\frac{1}{2}$ et \\\"x\\\""]})
    assert parse(proper)["lines"] == ['$\\frac{1}{2}$ et \\"x\\"']


def test_hints_are_parsed_even_with_raw_latex():
    from mathhinter.hints import parse as parse_hint
    assert parse_hint('{"hint": "Quel est le signe ?"}') == "Quel est le signe ?"
    assert parse_hint('```json\n{"hint": "Regardez $\\frac{1}{2}$."}\n```') == "Regardez $\\frac{1}{2}$."
    with pytest.raises(ValueError):
        parse_hint('{"hint": ""}')
