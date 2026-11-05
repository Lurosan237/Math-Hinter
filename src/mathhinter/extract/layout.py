"""Split a page into text lines and display formulas, and render it as Markdown with LaTeX."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mode

from .latex import MATH_FONT, to_latex
from .pdfchars import Glyph, PageContent, Rule

# Book pages use about 12-13pt leading, so anything closer to a text line than this is part of it.
ATTACH_DISTANCE = 9.5
SCRIPT_DISTANCE = 4.5
LIMIT_DISTANCE = 12.5
# A gap this many body sizes wide separates two formulas; matrix and system rows sit closer than that.
BLOCK_GAP = 2.0
MIN_TEXT_LETTERS = 10
MIN_FORMULA_GLYPHS = 5
FRAGMENT_REACH = 18.0


def _visible(glyphs) -> list[Glyph]:
    return [g for g in glyphs if g.text.strip() or g.name]


def _is_cmex(g: Glyph) -> bool:
    return g.font.startswith("CMEX")


def _is_text_letter(g: Glyph) -> bool:
    return not MATH_FONT.match(g.font) and g.text.isalpha()


def _rows(glyphs: list[Glyph]) -> list[list[Glyph]]:
    """Group glyphs sharing a baseline. Hanging symbols are placed by where they are centred."""
    rows: list[list[Glyph]] = []
    for g in sorted(glyphs, key=_row_position):
        if rows and _row_position(g) - _row_position(rows[-1][0]) < 1.2:
            rows[-1].append(g)
        else:
            rows.append([g])
    return rows


def _row_position(g: Glyph) -> float:
    """The baseline a glyph belongs to. TeX hangs its big symbols below the baseline, centred on the math axis."""
    return g.baseline + (g.size * (_cmex_depth(g) / 2 + 0.25) if _is_cmex(g) else 0)


def _row_is_text(row: list[Glyph]) -> bool:
    letters = sum(_is_text_letter(g) for g in row)
    math = sum(bool(MATH_FONT.match(g.font)) for g in row)
    return letters >= MIN_TEXT_LETTERS or (letters >= 4 and letters >= 2 * math)


def _attaches(row: list[Glyph], line: float, rules: tuple[Rule, ...], body: float, line_glyphs: list[Glyph]) -> bool:
    """Whether a row off a text line belongs to it: a script, part of an inline fraction, or a limit."""
    position = _row_position(row[0])
    distance = abs(position - line)
    if distance < SCRIPT_DISTANCE:
        return True
    x0, x1 = min(g.x0 for g in row), max(g.x1 for g in row)
    if 0 < position - line < LIMIT_DISTANCE and len(row) < 12 and all(g.size < 0.85 * body for g in row):
        if any(_is_cmex(g) and g.x0 - 6 <= x1 and x0 <= g.x1 + 6 for g in line_glyphs):
            return True  # the limit under an inline sum
    if distance >= ATTACH_DISTANCE:
        return False
    if len(row) < MIN_FORMULA_GLYPHS:
        return False  # decided by _place_fragment, which can see the whole page
    # An inline fraction's bar sits just above the line it belongs to.
    return any(abs(r.y - line) <= 4 and r.x0 <= x1 and x0 <= r.x1 for r in rules)


@dataclass(frozen=True)
class Block:
    kind: str  # "text" or "math"
    glyphs: tuple[Glyph, ...]
    rules: tuple[Rule, ...]
    page: int

    @property
    def x0(self) -> float:
        return min(g.x0 for g in self.glyphs)

    @property
    def x1(self) -> float:
        return max(g.x1 for g in self.glyphs)

    @property
    def top(self) -> float:
        tops = [g.baseline - 0.75 * g.size for g in self.glyphs]
        return min([*tops, *(r.y for r in self.rules)]) - 0.5

    @property
    def bottom(self) -> float:
        ends = [g.baseline + (_cmex_depth(g) if _is_cmex(g) else 0.25) * g.size for g in self.glyphs]
        return max([*ends, *(r.y for r in self.rules)]) + 0.5

    def latex(self) -> str:
        return to_latex(list(self.glyphs), list(self.rules))

    def markdown(self) -> str:
        if self.kind == "math":
            return f"$$ {self.latex()} $$"
        return _text_line(self)


def _cmex_depth(g: Glyph) -> float:
    name = g.name or ""
    if name.startswith(("integraldisplay", "contintegraldisplay")):
        return 2.22
    for suffix, depth in (("bigg", 2.4), ("Bigg", 3.0), ("Big", 1.8), ("big", 1.2), ("display", 1.4), ("text", 1.0)):
        if name.endswith(suffix):
            return depth
    return 1.8


def page_blocks(page: PageContent) -> list[Block]:
    """Text lines and display formulas in reading order."""
    glyphs = _visible(page.glyphs)
    if not glyphs:
        return []
    body = mode(round(g.size, 1) for g in glyphs)
    rows = _rows(glyphs)
    anchors = [row for row in rows if _row_is_text(row)]
    lines = [_row_position(row[0]) for row in anchors]
    members: dict[float, list[Glyph]] = {line: [] for line in lines}
    loose: list[list[Glyph]] = []
    fragments: list[list[Glyph]] = []
    for row in rows:
        position = _row_position(row[0])
        nearest = min(lines, key=lambda line: abs(line - position), default=None)
        if nearest is not None and abs(position - nearest) < SCRIPT_DISTANCE:
            members[nearest].extend(row)
        elif nearest is not None and _attaches(row, nearest, page.rules, body, _line_glyphs(rows, nearest)):
            members[nearest].extend(row)
        elif len(row) < MIN_FORMULA_GLYPHS and not _row_is_text(row):
            fragments.append(row)
        else:
            loose.append(row)
    for fragment in fragments:
        _place_fragment(fragment, members, loose)
    blocks = [_block("text", members[line], page) for line in lines]
    # Loose rows between two text lines form formulas, split where the vertical gap is wide.
    group: list[list[Glyph]] = []
    for row in sorted(loose, key=lambda row: _row_position(row[0])):
        between = group and any(_row_position(group[-1][0]) < line < _row_position(row[0]) for line in lines)
        if group and (between or _row_position(row[0]) - _row_position(group[-1][0]) > BLOCK_GAP * body):
            blocks.append(_block("math", [g for r in group for g in r], page))
            group = []
        group.append(row)
    if group:
        blocks.append(_block("math", [g for r in group for g in r], page))
    return sorted(blocks, key=lambda block: block.top)


def _line_glyphs(rows: list[list[Glyph]], line: float) -> list[Glyph]:
    return [g for row in rows if abs(_row_position(row[0]) - line) < SCRIPT_DISTANCE for g in row]


def _place_fragment(fragment: list[Glyph], members: dict[float, list[Glyph]], loose: list[list[Glyph]]) -> None:
    """Give a few stray glyphs to the big operator they sit over or under, else to the nearest row.

    Without this, the limits of an integral end up inside whatever line of text happens to be closest.
    """
    position = _row_position(fragment[0])
    x0, x1 = min(g.x0 for g in fragment), max(g.x1 for g in fragment)
    rows = [*members.values(), *loose]

    def has_operator_nearby(row: list[Glyph]) -> bool:
        return any(_is_cmex(g) and g.x0 - 10 <= x1 and x0 <= g.x1 + 10
                   and abs(_row_position(g) - position) < FRAGMENT_REACH for g in row)

    def distance(row: list[Glyph]) -> float:
        return min(abs(_row_position(g) - position) for g in row) if row else float("inf")

    candidates = [row for row in rows if has_operator_nearby(row)] or rows
    best = min(candidates, key=distance, default=None)
    if best is None or distance(best) > FRAGMENT_REACH:
        loose.append(fragment)
    else:
        best.extend(fragment)


def _block(kind: str, glyphs: list[Glyph], page: PageContent) -> Block:
    x0, x1 = min(g.x0 for g in glyphs), max(g.x1 for g in glyphs)
    top = min(g.baseline - g.size for g in glyphs)
    bottom = max(g.baseline + (_cmex_depth(g) if _is_cmex(g) else 0.3) * g.size for g in glyphs)
    rules = tuple(r for r in page.rules if r.x0 >= x0 - 3 and r.x1 <= x1 + 3 and top - 2 <= r.y <= bottom + 2)
    return Block(kind, tuple(sorted(glyphs, key=lambda g: g.x0)), rules, page.number)


def display_formulas(page: PageContent, min_glyphs: int = MIN_FORMULA_GLYPHS) -> list[Block]:
    return [b for b in page_blocks(page) if b.kind == "math" and len(b.glyphs) >= min_glyphs]


def _text_line(block: Block) -> str:
    text = ""
    run: list[Glyph] = []
    previous: Glyph | None = None

    def flush() -> None:
        nonlocal text, run
        if run:
            x0, x1 = min(g.x0 for g in run), max(g.x1 for g in run)
            rules = [r for r in block.rules if r.x0 >= x0 - 2 and r.x1 <= x1 + 2]
            text += f"${to_latex(run, rules)}$"
            run = []

    for g in block.glyphs:
        # A text letter in a maths-capable font (a roman CMR word) stays with the text unless a run is open.
        is_math = bool(MATH_FONT.match(g.font)) or (bool(run) and not g.text.isalpha() and not g.text.isspace())
        gap = previous is not None and g.x0 - previous.x1 > max(previous.size * 0.2, 1.2)
        if is_math:
            if gap and not run:
                text += " "
            run.append(g)
        else:
            flush()
            if gap and not text.endswith(" "):
                text += " "
            text += g.text
        previous = g
    flush()
    return text.strip()


def page_markdown(page: PageContent) -> str:
    return "\n".join(block.markdown() for block in page_blocks(page))
