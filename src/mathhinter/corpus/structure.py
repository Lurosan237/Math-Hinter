"""Find the book's structure: running headers, sections, theorems, exercises and their solutions."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

MODULE_HEADER = re.compile(r"^(\d+) ([IVX]+\.\d+) \$\\bullet\$ (.+)$")
SECTION_HEADER = re.compile(r"^(\d+(?:\.\d+)*) (.+?)\s*\$?(?:\s|\\mathbb\{[A-Z]\})*(\d+)\$?$")
_SPECIAL = "Exercices|Indications|INDEX|Bibliographie|Solutions?"
SPECIAL_HEADER = re.compile(rf"^(?:({_SPECIAL}) (\d+)|(\d+) ({_SPECIAL}))$")

NUMBERED = {"Théorème": "theorem", "Définition": "definition", "Proposition": "proposition", "Lemme": "lemma",
            "Corollaire": "corollary", "Exercice": "exercise"}
_NUMBERED = "|".join(NUMBERED)
LABEL = re.compile(rf"^(?P<kind>{_NUMBERED})\s+(?P<number>\d+)\s*(?:\.|\((?=[^)]*\)\s*\.)|$)")
UNNUMBERED = re.compile(r"^(?P<kind>Démonstration|Solution|Remarques?|Exemples?|Point Méthode)\b\s*\.?")
UNNUMBERED_KIND = {"Démonstration": "proof", "Solution": "solution", "Remarque": "remark", "Remarques": "remark",
                   "Exemple": "example", "Exemples": "example", "Point Méthode": "method"}
HEADING = re.compile(r"^(\d+(?:\.\d+){0,2})\s+[A-ZÉÀ]")
END_ITEM = re.compile(r"^(?P<id>[IVX]+\.\d+\.\d+)\b")
BODY_SIZE_MAX = 11.5


LIGATURES = str.maketrans({"ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl"})


def normalise(text: str) -> str:
    return text.translate(LIGATURES)


@dataclass
class Unit:
    volume: int
    kind: str
    module: str | None
    section: str | None
    pdf_page: int
    printed_page: int | None
    number: str | None = None
    lines: list[str] = field(default_factory=list)
    last_pdf_page: int = 0
    region: str = "body"  # body, exercises (end of module) or indications

    def text(self) -> str:
        return "\n".join(self.lines)

    def closes_on_rule(self) -> bool:
        return bool(self.lines)

    def record(self, index: int) -> dict:
        data = asdict(self)
        data["id"] = f"v{self.volume}:{index:05d}"
        data["text"] = data.pop("lines")
        data["text"] = "\n".join(data["text"])
        return data


def parse_header(blocks: list[dict]) -> dict:
    """Read the running header at the top of a page: its printed number and where it sits in the book."""
    for block in blocks[:2]:
        if block["size"] > 9 or block["top"] > 70:
            continue
        md = block["md"].strip()
        if m := MODULE_HEADER.match(md):
            return {"printed": int(m[1]), "module": m[2], "title": m[3], "block": block}
        if m := SPECIAL_HEADER.match(md):
            return {"printed": int(m[2] or m[3]), "special": (m[1] or m[4]).lower(), "block": block}
        if m := re.match(r"^(\d+(?:\.\d+)?) (.*?)\s*\$?(\d{1,4})\$?$", md):
            return {"printed": int(m[3]), "section_title": m[2], "block": block}
        if m := re.match(r"^(.+?) (\d{1,4})$", md):
            return {"printed": int(m[2]), "block": block}
    return {}


def _start(line: str, bold: int, size: float) -> tuple[str, str | None] | None:
    if m := LABEL.match(line):
        return NUMBERED[m["kind"]], m["number"]
    if (m := UNNUMBERED.match(line)) and bold >= 3:
        return UNNUMBERED_KIND[m["kind"]], None
    if m := re.match(r"^Démonstration\b\.", line):
        return "proof", None
    if m := re.match(r"^Solution\s*\.", line):
        return "solution", None
    if m := HEADING.match(line):
        if size > BODY_SIZE_MAX:
            return "heading", m[1]
    return None


def page_offset(pages: list[dict]) -> int:
    """PDF index minus printed number. Blank-headed pages can then still be given a printed number."""
    offsets = [page["page"] - h["printed"] for page in pages if "printed" in (h := parse_header(page["blocks"]))]
    return max(set(offsets), key=offsets.count)


def parse_book(volume: int, pages: list[dict]) -> list[Unit]:
    """Cut a book's pages into units. A unit runs until the next label or heading."""
    offset = page_offset(pages)
    units: list[Unit] = []
    module: str | None = None
    section: str | None = None
    region = "front"
    current: Unit | None = None

    def begin(kind, number, page, printed) -> Unit:
        unit = Unit(volume, kind, module, section, page, printed, number, last_pdf_page=page, region=region)
        units.append(unit)
        return unit

    for page in pages:
        blocks = page["blocks"]
        header = parse_header(blocks)
        printed = page["page"] - offset
        if "module" in header:
            if header["module"] != module:
                module, section, current = header["module"], None, None
                region = "body"
            elif region == "front":
                region = "body"
        if special := header.get("special"):
            new = {"exercices": "exercises", "indications": "indications", "index": "back",
                   "bibliographie": "back", "solution": "exercises", "solutions": "exercises"}[special]
            if new != region:
                region, current = new, None
        elif region == "exercises" and "module" not in header and "section_title" in header:
            region, current = "body", None
        elif region == "front" and "section_title" in header:
            region = "body"
        if region in ("front", "back"):
            current = None
            continue
        rules = list(page.get("wide_rules", []))
        for block in blocks:
            if header.get("block") is block:
                continue
            # A full-width rule closes an exercise or its solution: what follows is the book's own text.
            while rules and rules[0] <= block["top"] + 2:
                rules.pop(0)
                if current is not None and current.kind in ("exercise", "solution") and current.closes_on_rule():
                    current = None
            md = normalise(block["md"]).strip()
            if not md:
                continue
            if region in ("exercises", "indications") and (m := END_ITEM.match(md)):
                kind = "exercise_end" if region == "exercises" else "indication"
                current = begin(kind, m["id"], page["page"], printed)
                if m["id"].count(".") == 2:
                    current.module = m["id"].rsplit(".", 1)[0]
            elif started := _start(md, block["bold"], block["size"]):
                kind, number = started
                if kind == "heading":
                    section = number
                current = begin(kind, number, page["page"], printed)
                current.section = section
            elif current is None:
                current = begin("prose", None, page["page"], printed)
                current.section = section
            current.lines.append(md)
            current.last_pdf_page = page["page"]
    return units


def pair_exercises(units: list[Unit]) -> list[tuple[Unit, Unit]]:
    """Each worked exercise with the solution that directly follows it."""
    pairs = []
    for first, second in zip(units, units[1:], strict=False):
        if first.kind == "exercise" and second.kind == "solution":
            pairs.append((first, second))
    return pairs
