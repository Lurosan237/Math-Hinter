import json

from mathhinter.steps import needs_splitting, split_and_repair, split_faithfully

PROSE = "On pose $u=x$ et $v'=e^x$. Donc $u'=1$ et $v=e^x$. Ainsi $I=[xe^x]_0^1+\\int_0^1 e^x\\,dx=2e-1$."


class Fake:
    def __init__(self, reply):
        self.reply, self.calls = reply, []

    def chat(self, model, messages, temperature=0.0, max_tokens=0, extra=None):
        self.calls.append((model, extra))
        return {"choices": [{"message": {"content": json.dumps(self.reply)}}], "usage": {"total_tokens": 5}}


def test_only_long_or_crowded_write_ups_are_split():
    assert needs_splitting(PROSE)
    assert not needs_splitting("$f'(x)=2x$\nDonc $f'(1)=2$.")
    assert needs_splitting("x" * 200)


def test_faithful_splitting_keeps_every_character():
    steps = ["On pose $u=x$ et $v'=e^x$.", "Donc $u'=1$ et $v=e^x$.",
             "Ainsi $I=[xe^x]_0^1+\\int_0^1 e^x\\,dx=2e-1$."]
    assert split_faithfully(Fake({"steps": steps}), "E", PROSE) == (steps, True)


def test_a_split_that_fixes_the_student_is_refused():
    fixed = ["On pose $u=x$ et $v'=e^x$.", "Donc $u'=1$ et $v=e^x$.", "Ainsi $I=[xe^x]_0^1-\\int_0^1 e^x\\,dx=1$."]
    assert split_faithfully(Fake({"steps": fixed}), "E", PROSE) == ([PROSE], False)
    assert split_faithfully(Fake("not json"), "E", PROSE) == ([PROSE], False)


def test_repairs_are_marked():
    reply = {"steps": [{"text": "Soit $t=\\frac{r}{r+r'}$.", "repaired": True, "note": "fraction aplatie"},
                       {"text": "Donc $0<t<1$.", "repaired": False}], "doubtful": False}
    fake = Fake(reply)
    out = split_and_repair(fake, "E", "Soit t = r r + r'. Donc 0<t<1.")
    assert out["steps"][0]["repaired"] and out["steps"][1]["note"] == ""
    assert fake.calls[0][1]["reasoning_effort"] == "none"
