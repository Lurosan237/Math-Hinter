"""Read every glyph of a PDF page with the name its font gives it.

Most text extractors keep only a Unicode guess. TeX maths fonts (CMEX, MSAM...) often have no
usable Unicode map, so sums and inequalities come out as junk. Their /Encoding usually still names
each glyph ("summationdisplay", "lessorequalslant"), and those names are what we keep.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pdfminer.converter import PDFLayoutAnalyzer
from pdfminer.layout import LTChar, LTCurve, LTFigure, LTImage, LTLine, LTPage, LTRect
from pdfminer.pdfinterp import PDFPageInterpreter, PDFResourceManager
from pdfminer.pdfpage import PDFPage
from pdfminer.pdftypes import resolve1
from pdfminer.psparser import PSLiteral


@dataclass(frozen=True)
class Glyph:
    text: str  # pdfminer's Unicode guess, may be junk for maths fonts
    name: str | None  # glyph name from the font's /Differences, if any
    font: str  # base font name without the subset prefix, e.g. "CMEX10"
    size: float
    x0: float
    x1: float
    top: float  # measured down from the top of the page
    bottom: float
    baseline: float  # measured down from the top of the page


@dataclass(frozen=True)
class Rule:
    """A thin horizontal line: a fraction bar, a radical's top, an overline."""

    x0: float
    x1: float
    y: float


@dataclass(frozen=True)
class PageContent:
    number: int  # 0-based
    width: float
    height: float
    glyphs: tuple[Glyph, ...]
    rules: tuple[Rule, ...]


# Plain pdfTeX output names no glyphs, so fall back to the standard TeX code tables.
_TEX_CODES = {
    "CMEX": {0: "parenleftbig", 1: "parenrightbig", 2: "bracketleftbig", 3: "bracketrightbig", 16: "parenleftBig",
             17: "parenrightBig", 18: "parenleftbigg", 19: "parenrightbigg", 32: "parenleftBigg", 33: "parenrightBigg",
             80: "summationtext", 81: "producttext", 82: "integraltext", 83: "uniontext", 84: "intersectiontext",
             88: "summationdisplay", 89: "productdisplay", 90: "integraldisplay", 91: "uniondisplay",
             92: "intersectiondisplay", 112: "radicalbig", 113: "radicalBig", 114: "radicalbigg", 115: "radicalBigg"},
    "MSAM": {54: "lessorequalslant", 62: "greaterorequalslant"},
}


def _tex_code_name(fontname: str, cid: int) -> str | None:
    return _TEX_CODES.get(fontname.split("+")[-1][:4], {}).get(cid)


def _differences(spec: dict) -> dict[int, str]:
    encoding = resolve1(spec.get("Encoding")) if spec else None
    if not isinstance(encoding, dict):
        return {}
    out: dict[int, str] = {}
    code = 0
    for item in resolve1(encoding.get("Differences")) or []:
        item = resolve1(item)
        if isinstance(item, int):
            code = item
        elif isinstance(item, PSLiteral):
            out[code] = item.name
            code += 1
    return out


class _Fonts(PDFResourceManager):
    """Keeps the glyph-name table of each font alongside the font itself."""

    def get_font(self, objid, spec):
        font = super().get_font(objid, spec)
        if not hasattr(font, "glyph_names"):
            font.glyph_names = _differences(spec)
        return font


class _Collector(PDFLayoutAnalyzer):
    def __init__(self, rsrcmgr):
        super().__init__(rsrcmgr, pageno=1, laparams=None)
        self.glyphs: list[tuple] = []
        self.page: LTPage | None = None

    def render_char(self, matrix, font, fontsize, scaling, rise, cid, ncs, graphicstate):
        adv = super().render_char(matrix, font, fontsize, scaling, rise, cid, ncs, graphicstate)
        item = self.cur_item._objs[-1]
        if isinstance(item, LTChar):
            name = getattr(font, "glyph_names", {}).get(cid) or _tex_code_name(item.fontname, cid)
            self.glyphs.append((item, name))
        return adv

    def receive_layout(self, ltpage):
        self.page = ltpage


def _rules(layout: LTPage) -> tuple[Rule, ...]:
    # Some of these books draw fraction bars as tiny bitmaps rather than lines, so images count too.
    out = []

    def walk(items) -> None:
        for obj in items:
            if isinstance(obj, LTFigure):
                walk(obj)
            elif isinstance(obj, LTRect | LTLine | LTCurve | LTImage) and obj.height < 1.5 and obj.width > 2:
                out.append(Rule(obj.x0, obj.x1, layout.height - (obj.y0 + obj.y1) / 2))

    walk(layout)
    return tuple(out)


def read_pages(path: str | Path, numbers: list[int] | None = None):
    """Yield PageContent for the given 0-based page numbers, or all pages."""
    fonts = _Fonts(caching=True)
    device = _Collector(fonts)
    interpreter = PDFPageInterpreter(fonts, device)
    wanted = set(numbers) if numbers is not None else None
    with open(path, "rb") as handle:
        for number, page in enumerate(PDFPage.get_pages(handle)):
            if wanted is not None and number not in wanted:
                continue
            device.glyphs = []
            interpreter.process_page(page)
            layout = device.page
            height = layout.height
            glyphs = tuple(
                Glyph(
                    text=item.get_text(),
                    name=name,
                    font=item.fontname.split("+")[-1],
                    size=item.size,
                    x0=item.x0,
                    x1=item.x1,
                    top=height - item.y1,
                    bottom=height - item.y0,
                    baseline=height - item.matrix[5],
                )
                for item, name in device.glyphs
            )
            yield PageContent(number, layout.width, height, glyphs, _rules(layout))
            if wanted is not None:
                wanted.discard(number)
                if not wanted:
                    return
