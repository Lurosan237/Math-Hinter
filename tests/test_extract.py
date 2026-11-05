from pathlib import Path

import pytest

from mathhinter.extract.latex import glyph_latex, to_latex
from mathhinter.extract.layout import display_formulas, split_lines
from mathhinter.extract.pdfchars import Glyph, Rule, read_pages
from mathhinter.extract.score import similarity, tokens

FIXTURE = Path(__file__).parent / "fixtures" / "formulas.pdf"


def glyph(text, x0, baseline=100.0, size=10.0, font="CMMI10", name=None, width=5.0):
    return Glyph(text, name, font, size, x0, x0 + width, baseline - size, baseline + 2, baseline)


@pytest.fixture(scope="module")
def formulas():
    page = next(read_pages(FIXTURE, [0]))
    return [f.latex() for f in display_formulas(page)]


def test_named_glyphs_are_read_from_the_pdf():
    page = next(read_pages(FIXTURE, [0]))
    names = {g.name for g in page.glyphs if g.font.startswith(("CMEX", "CMSY", "MSAM"))}
    assert {"summationdisplay", "lessorequalslant", "integraldisplay"} <= names


def test_fixture_formulas_round_trip(formulas):
    assert len(formulas) == 3
    assert formulas[0] == r"\sum_{i=1}^{n}x_{i}^{2}\leqslant\frac{a+b}{c}"
    assert similarity(formulas[1], r"\forall x\in\mathbb{R},\int_{0}^{1}f(t)dt\geqslant0") == 1
    assert similarity(formulas[2], r"\lim_{n\to+\infty}\sqrt{u_{n}}=\ell") == 1


def test_font_decides_the_alphabet():
    assert glyph_latex(glyph("R", 0, font="MSBM10")) == r"\mathbb{R}"
    assert glyph_latex(glyph("A", 0, font="CMSY10", name="A")) == r"\mathcal{A}"
    assert glyph_latex(glyph("�", 0, font="MSAM10", name="lessorequalslant")) == r"\leqslant"


def test_pieces_of_tall_symbols_are_dropped():
    assert glyph_latex(glyph("?", 0, font="CMEX10", name="parenleftex")) == ""


def test_scripts_attach_to_the_previous_symbol():
    glyphs = [glyph("x", 0), glyph("2", 5, baseline=96.5, size=7, font="CMR7"), glyph("i", 5, baseline=101.5, size=7)]
    assert to_latex(glyphs) == "x_{i}^{2}"


def test_fraction_from_a_rule():
    glyphs = [glyph("a", 10, baseline=93), glyph("b", 10, baseline=107)]
    assert to_latex(glyphs, [Rule(9, 16, 98)]) == r"\frac{a}{b}"


def test_two_rows_stay_separate():
    glyphs = [glyph("a", 0, baseline=100), glyph("b", 5, baseline=100), glyph("c", 0, baseline=114),
              glyph("d", 5, baseline=114)]
    assert to_latex(glyphs) == "abcd"


def test_lines_keep_their_scripts():
    glyphs = (glyph("x", 0), glyph("2", 5, baseline=96.5, size=7, font="CMR7"), glyph("y", 0, baseline=120))
    assert [len(line.glyphs) for line in split_lines(glyphs)] == [2, 1]


def test_score_treats_spellings_alike():
    assert tokens(r"\le \rightarrow x_{1}") == tokens(r"\leqslant\to x_1")
    assert similarity(r"\lim_{x}", "lim_{x}") == 1
    assert similarity("abcd", "abce") == 0.75


def test_score_can_ignore_structure():
    assert similarity("x_{1}^{2}", "x12", structure=False) == 1
    assert similarity("x_{1}^{2}", "x12") < 1
