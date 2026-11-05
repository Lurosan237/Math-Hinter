"""Read a book's index, so terms can link across volumes where its numbered references don't."""

from __future__ import annotations

import re

from ..extract.layout import page_blocks
from ..extract.pdfchars import Glyph, PageContent

_ENTRY = re.compile(r"^(?P<term>.*?)[, ]+(?P<pages>\d+(?:\s*,\s*\d+)*)\.?$")


def _column(page: PageContent, left: bool) -> PageContent:
    middle = page.width / 2

    def keep(g: Glyph) -> bool:
        return ((g.x0 + g.x1) / 2 < middle) == left

    return PageContent(page.number, page.width, page.height, tuple(g for g in page.glyphs if keep(g)), page.rules)


def parse_index_page(page: PageContent) -> list[dict]:
    """Entries of one index page. Indented lines are sub-entries of the last head term."""
    entries: list[dict] = []
    for left in (True, False):
        blocks = page_blocks(_column(page, left))
        if not blocks:
            continue
        margin = min(b.x0 for b in blocks)
        head = ""
        for block in blocks:
            text = block.markdown().strip().replace("$$", "").strip()
            if block.top < 70 or not text:
                continue
            indented = block.x0 > margin + 8
            match = _ENTRY.match(text)
            term = (match["term"] if match else text).strip(" ,")
            if not indented:
                head = term
            if match:
                pages = [int(p) for p in match["pages"].split(",")]
                entries.append({"head": head, "sub": term if indented else "", "pages": pages})
    return entries


def full_term(entry: dict) -> str:
    """The whole phrase an entry stands for: "relation d'—" under "équivalence" is "relation d'équivalence"."""
    head, sub = entry["head"], entry["sub"]
    head = re.sub(r"\(.*$", "", head).strip()
    head = re.sub(r"\(s\)", "", head)
    if not sub:
        inside = re.search(r"\((.*)—\)", entry["head"])
        if inside:
            return f"{inside[1].strip()} {head}".strip()
        return head
    if "—" in sub:
        return re.sub(r"\s*—\s*", f" {head} ", sub).replace("d’ ", "d’").strip()
    return f"{head} {sub}".strip()
