import pytest

from mathhinter.check.equality import REFUTED, UNVERIFIABLE, VERIFIED, check_equality
from mathhinter.check.parser import Unparseable, parse


@pytest.mark.parametrize("left,right", [
    ("(x+y)^{2}", "x^{2}+2xy+y^{2}"),
    (r"\frac{1}{2}+\frac{1}{3}", r"\frac{5}{6}"),
    ("sin^{2}(t)+cos^{2}(t)", "1"),
    (r"\sqrt{4}", "2"),
    ("f(x)+g(x)", "g(x)+f(x)"),
    ("A+B", "B+A"),
    ("x_{1}+x_{2}", "x_{2}+x_{1}"),
    ("f'(x)-f'(x)", "0"),
    ("3!", "6"),
])
def test_true_identities_are_verified(left, right):
    assert check_equality(left, right).status == VERIFIED


def test_false_arithmetic_is_refuted():
    assert check_equality("2+2", "5").status == REFUTED


@pytest.mark.parametrize("left,right", [
    ("AB", "BA"),  # matrices need not commute
    ("x", "3"),  # may be true because of an earlier line
    ("f(x+y)", "f(x)+f(y)"),
    (r"\sqrt{x^{2}}", "x"),  # false for negative x
    ("x_{1}", "x_{2}"),
])
def test_it_never_verifies_what_isnt_an_identity(left, right):
    assert check_equality(left, right).status == UNVERIFIABLE


@pytest.mark.parametrize("latex", [
    r"\sum_{i}x_{i}", r"\int_{0}^{1}x", "x,y", "0etx", "|x|", "__import__('os')", "x+", r"\mathbb{R}",
    "f^{(n-1)}(0)", "f*g",
])
def test_anything_unclear_is_refused(latex):
    with pytest.raises(Unparseable):
        parse(latex)


def test_text_cannot_run_as_code(tmp_path):
    marker = tmp_path / "ran"
    verdict = check_equality(f"__import__('pathlib').Path('{marker}').touch()", "1")
    assert verdict.status == UNVERIFIABLE and not marker.exists()


def test_subscripts_keep_variables_apart():
    assert parse("x_{1}") != parse("x_{2}")



def test_a_letter_before_brackets_is_read_as_a_function():
    # A known limit, kept so the evaluated checker stays the one the reports describe: write x\cdot(x+2).
    assert check_equality("2xe^x+x^2e^x", "x(x+2)e^x").status == UNVERIFIABLE
    assert check_equality("2xe^x+x^2e^x", r"x\cdot(x+2)e^x").status == VERIFIED
