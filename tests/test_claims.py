import pytest

from mathhinter.check.equality import REFUTED, UNVERIFIABLE, VERIFIED
from mathhinter.pipeline.claims import check_claim

CASES = [
    ({"type": "derivative", "function": "x^2e^x", "variable": "x", "result": "2xe^x+x^2e^x"}, VERIFIED),
    ({"type": "derivative", "function": "e^x", "variable": "x", "result": "xe^{x-1}"}, REFUTED),
    ({"type": "antiderivative", "function": "xe^x", "variable": "x", "result": "(x-1)e^x"}, VERIFIED),
    ({"type": "antiderivative", "function": "xe^x", "variable": "x", "result": "(x+1)e^x"}, REFUTED),
    ({"type": "integral", "function": "xe^x", "variable": "x", "lower": "0", "upper": "1", "result": "1"}, VERIFIED),
    ({"type": "integral", "function": "xe^x", "variable": "x", "lower": "0", "upper": "1", "result": "2e-1"}, REFUTED),
    ({"type": "limit", "function": r"\frac{e^x-1-x}{x^2}", "variable": "x", "point": "0", "result": r"\frac{1}{2}"},
     VERIFIED),
    ({"type": "limit", "function": r"\frac{e^x-1-x}{x^2}", "variable": "x", "point": "0", "result": "1"}, REFUTED),
    ({"type": "limit", "function": r"\frac{1}{x}", "variable": "x", "point": r"+\infty", "result": "0"}, VERIFIED),
    ({"type": "limit", "function": "x^2", "variable": "x", "point": r"+\infty", "result": r"+\infty"}, VERIFIED),
    ({"type": "sum", "term": "2^k", "index": "k", "start": "0", "end": "n", "result": "2^{n+1}-1"}, VERIFIED),
    ({"type": "sum", "term": "2^k", "index": "k", "start": "0", "end": "n", "result": "2^n-1"}, REFUTED),
    ({"type": "solution", "equations": ["y=2x+1", "y=3x-2"], "values": {"x": "3", "y": "7"}}, VERIFIED),
    ({"type": "solution", "equations": ["y=2x+1", "y=3x-3"], "values": {"x": "3", "y": "7"}}, REFUTED),
    ({"type": "ode", "equation": "y'+2y=0", "function": "y", "variable": "x", "solution": "3e^{-2x}"}, VERIFIED),
    ({"type": "ode", "equation": "y'+2y=0", "function": "y", "variable": "x", "solution": "3e^{2x}"}, REFUTED),
    ({"type": "equality", "left": "x", "right": "3"}, UNVERIFIABLE),  # may follow from earlier lines
    ({"type": "theorem", "name": "Rolle"}, UNVERIFIABLE),
    ({"type": "derivative", "function": r"\frac{", "variable": "x", "result": "1"}, UNVERIFIABLE),
    ({"type": "integral", "function": "x", "variable": "x"}, UNVERIFIABLE),
]


@pytest.mark.parametrize("claim,status", CASES)
def test_claims_are_checked_by_computation(claim, status):
    assert check_claim(claim).status == status


def test_a_refuted_claim_says_what_was_computed():
    check = check_claim({"type": "limit", "function": r"\frac{e^x-1-x}{x^2}", "variable": "x", "point": "0",
                         "result": "1"})
    assert check.computed == r"\frac{1}{2}"
