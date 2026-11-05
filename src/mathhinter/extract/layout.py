"""Find formulas on a page and render a page as Markdown with LaTeX maths."""

from __future__ import annotations

from dataclasses import dataclass

from .latex import MATH_FONT, to_latex
from .pdfchars import Glyph, PageContent, Rule


@dataclass(frozen=True)
class Line:
    glyphs: tuple[Glyph, ...]
    top: float
    bottom: float

    @property
    def math_share(self) -> float:
        visible = [g for g in self.glyphs if g.text.strip()]
        return sum(bool(MATH_FONT.match(g.font)) for g in visible) / max(len(visible), 1)


def split_lines(glyphs: tuple[Glyph, ...]) -> list[Line]:
    """One line per text baseline; scripts and hanging symbols join the nearest one.

    PDF glyph boxes come from whole-font metrics, so they overlap across lines and can't be used here.
    """
    visible = [g for g in glyphs if g.text.strip() or g.name]
    if not visible:
        return []
    sizes: dict[float, int] = {}
    for g in visible:
        sizes[round(g.size, 1)] = sizes.get(round(g.size, 1), 0) + 1
    body = max(sizes, key=sizes.get)
    anchors: list[float] = []
    for g in sorted(visible, key=lambda g: g.baseline):
        if g.size >= body * 0.9 and not g.font.startswith("CMEX"):
            if not anchors or g.baseline - anchors[-1] > body * 0.3:
                anchors.append(g.baseline)
    if not anchors:
        anchors = [min(g.baseline for g in visible)]
    groups: dict[float, list[Glyph]] = {a: [] for a in anchors}
    for g in visible:
        probe = g.baseline + (g.size * 0.5 if g.font.startswith("CMEX") else 0)
        groups[min(anchors, key=lambda a: abs(a - probe))].append(g)
    lines = [Line(tuple(sorted(gr, key=lambda x: x.x0)), min(x.top for x in gr), max(x.bottom for x in gr))
             for gr in groups.values() if gr]
    return sorted(lines, key=lambda line: line.top)


@dataclass(frozen=True)
class Formula:
    page: int
    x0: float
    top: float
    x1: float
    bottom: float
    glyphs: tuple[Glyph, ...]
    rules: tuple[Rule, ...]

    def latex(self) -> str:
        return to_latex(list(self.glyphs), list(self.rules))


def display_formulas(page: PageContent, min_math_share: float = 0.8, min_glyphs: int = 5) -> list[Formula]:
    """Stand-alone formulas: lines that are mostly maths, merged when limits or fractions span several."""
    lines = [line for line in split_lines(page.glyphs)]
    merged: list[list[Line]] = []
    for line in lines:
        if line.math_share < min_math_share:
            continue
        if merged and _baseline(line) - _baseline(merged[-1][-1]) < 13:
            merged[-1].append(line)
        else:
            merged.append([line])
    out = []
    for group in merged:
        glyphs = tuple(g for line in group for g in line.glyphs)
        if len(glyphs) < min_glyphs:
            continue
        x0, x1 = min(g.x0 for g in glyphs), max(g.x1 for g in glyphs)
        top, bottom = min(g.baseline - 0.75 * g.size for g in glyphs), max(_ink_bottom(g) for g in glyphs)
        rules = tuple(r for r in page.rules if r.x0 >= x0 - 3 and r.x1 <= x1 + 3 and top - 2 <= r.y <= bottom + 2)
        out.append(Formula(page.number, x0, top, x1, bottom, glyphs, rules))
    return out


def _baseline(line: Line) -> float:
    counts: dict[float, int] = {}
    for g in line.glyphs:
        counts[round(g.baseline)] = counts.get(round(g.baseline), 0) + 1
    return max(counts, key=counts.get)


def _ink_bottom(g: Glyph) -> float:
    return g.baseline + (2.3 if g.font.startswith("CMEX") else 0.25) * g.size


def page_markdown(page: PageContent) -> str:
    """The page as text, with runs of maths wrapped in $...$."""
    rendered = []
    for line in split_lines(page.glyphs):
        chunks: list[str] = []
        run: list[Glyph] = []
        text = ""
        previous: Glyph | None = None

        def flush() -> None:
            nonlocal run, text
            if run:
                # keep rules out of inline text; display fractions are handled by display_formulas
                text += "$" + to_latex(run) + "$"
                run = []

        for g in line.glyphs:
            if previous is not None and g.x0 - previous.x1 > max(previous.size * 0.2, 1.2):
                if not (MATH_FONT.match(g.font) and run):
                    flush()
                    text += " "
            if MATH_FONT.match(g.font) and not (g.font.startswith(("CMR", "CMBX")) and g.text.isalpha() and not run):
                run.append(g)
            else:
                flush()
                text += g.text
            previous = g
        flush()
        chunks.append(text)
        rendered.append("".join(chunks).strip())
    return "\n".join(rendered)
