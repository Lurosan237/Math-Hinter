import random

from mathhinter.evalset.corrupt import apply, control, corrupt, first_wrong_line, formula_edits
from mathhinter.evalset.quality import is_computation, rejection

GOOD = "Exercice 3.\nMontrer que toute suite croissante majorée converge vers sa borne supérieure."
SOLUTION = "Solution. Soit $u$ une telle suite. On pose $\\ell:=\\sup u$ et le résultat suit de la définition."


def kinds(formula):
    return {e.kind for e in formula_edits(formula)}


def test_kinds_of_formula_slip():
    assert "sign" in kinds("a+b")
    assert "exponent" in kinds("x^{2}")
    assert "number" in kinds("x=3")
    assert "inverted_fraction" in kinds(r"\frac{a}{b}")
    assert "wrong_function" in kinds("sin(x)")
    assert "inequality" in kinds(r"a\leqslant b")
    assert "quantifier" in kinds(r"\forall x")


def test_subscripts_are_left_alone():
    assert not formula_edits("x_{1}")
    assert not formula_edits("x_{i+1}")


def test_edit_changes_only_its_token():
    formula = r"x^{2}"
    edit = next(e for e in formula_edits(formula) if e.kind == "exponent")
    assert apply(formula, edit) == "x^{3}"


TEXT = ("Solution. On commence ici par une assez longue phrase sans aucun calcul.\n"
        "Puis on trouve $a+b=c$ et la suite est bornée.\nDonc $x^{2}=4.$")


def test_corruption_is_recorded_exactly():
    attempt = corrupt(TEXT, random.Random(1))
    assert attempt.text != TEXT
    assert attempt.text[attempt.start : attempt.end] == attempt.corrupted
    assert TEXT[attempt.start : attempt.start + len(attempt.original)] == attempt.original
    assert first_wrong_line(attempt) in (1, 2)


def test_corruption_is_repeatable():
    assert corrupt(TEXT, random.Random(5)) == corrupt(TEXT, random.Random(5))


def test_earliest_text_is_not_changed():
    assert corrupt("$a+b$", random.Random(1)) is None


def test_control_is_unchanged_and_has_no_wrong_line():
    attempt = control(TEXT)
    assert attempt.text == TEXT and first_wrong_line(attempt) is None


def test_good_exercise_is_kept():
    assert rejection(GOOD, SOLUTION) is None


def test_rejection_reasons():
    assert rejection("Exercice 1. Court.", SOLUTION) == "too_short"
    assert rejection(GOOD, "Solution. Oui.") == "solution_too_short"
    assert rejection(GOOD.replace("suite", "su�te"), SOLUTION) == "unreadable_characters"
    assert rejection(GOOD + " Reprendre la question précédente.", SOLUTION) == "needs_earlier_context"
    assert rejection("Exercice 1.\n$$ n $$\n" + GOOD, SOLUTION) == "stray_formula_fragment"
    assert rejection(GOOD + r" $x^{}$", SOLUTION) == "broken_formula"
    assert rejection(GOOD + " $x", SOLUTION) == "unbalanced_formula"


def test_computation_is_told_from_proof():
    assert is_computation("Exercice 1. Calculer la somme.")
    assert not is_computation(GOOD)
