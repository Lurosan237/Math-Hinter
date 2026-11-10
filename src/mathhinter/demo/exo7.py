"""Read Exo7's course sources (LaTeX, CC BY-NC-SA 3.0 FR) into the same units as the books.

The demo can't use the licensed books, so it uses this openly licensed course instead. Reading the LaTeX directly
means no PDF extraction, so the demo shows the tutor on clean text.
"""

from __future__ import annotations

import re
from pathlib import Path

# Chapters of the books "Analyse 1" and "Algèbre 1", plus the improper integrals chapter. Others in the repository
# either aren't course material for a first or second year, or carry no licence page.
BOOKS = {
    "Exo7 Analyse 1": ["reels", "suites", "fonctions", "usuelles", "derivee", "int", "dl", "courbes", "equadiff"],
    "Exo7 Algèbre 1": ["logique", "ensembles", "complexes", "arithmetique", "polynomes", "groupes", "syslin",
                       "matrices", "erene", "ev", "dimension", "matlin", "determinants"],
    "Exo7 Analyse 2": ["intimp"],
}
CHAPTERS = [name for chapters in BOOKS.values() for name in chapters]
BOOK_OF = {name: book for book, chapters in BOOKS.items() for name in chapters}
KINDS = {"definition": "definition", "theoreme": "theorem", "proposition": "proposition", "corollaire": "corollary",
         "lemme": "lemma", "exemple": "example", "proof": "proof"}
_ENV = re.compile(r"\\begin\{(" + "|".join(KINDS) + r")\}(\[[^\]]*\])?(.*?)\\end\{\1\}", re.S)
_HEADING = re.compile(r"\\(chapitre|section|subsection)\*?(?:\[[^\]]*\])?\{((?:[^{}]|\{[^{}]*\})*)\}")
MACROS = {r"\Rr": r"\mathbb{R}", r"\Nn": r"\mathbb{N}", r"\Zz": r"\mathbb{Z}", r"\Qq": r"\mathbb{Q}",
          r"\Cc": r"\mathbb{C}", r"\Kk": r"\mathbb{K}", r"\dd": r"\mathrm{d}", r"\ms": "", r"\sauteligne": "",
          r"\pause": "", r"\displaystyle": "", r"\ii": r"\mathrm{i}", r"\sh": r"\operatorname{sh}",
          r"\ch": r"\operatorname{ch}", r"\Argsh": r"\operatorname{argsh}", r"\R": r"\mathbb{R}",
          r"\Z": r"\mathbb{Z}", r"\id": r"\mathrm{id}", r"\og": "«", r"\fg": "»", r"\Pass": r"\mathrm{P}",
          **{f"\\{name}": f"\\operatorname{{{name}}}" for name in
             ["Mat", "pgcd", "ppcm", "Ker", "Card", "Vect", "rg", "Tr", "tr", "Id", "GL", "Arg", "Re", "Im", "deg",
              "Argch", "Argth", "th", "cotan", "Sp", "Com", "sgn", "pgcd"]}}
_UNWRAP = re.compile(r"\\(defi|evidence|centerline|myboxinline|alenvers|emph|textbf|textit)\{((?:[^{}]|\{[^{}]*\})*)\}")
_DROP = re.compile(r"\\(index|label|insertvideo|insertfiche|myfigure|tikzinput|vspace|hspace|ref|eqref)"
                   r"(\{[^{}]*\})+|\\(medskip|bigskip|smallskip|noindent|newpage|centering)\b")


def unwrap(tex: str, name: str) -> str:
    """Replace \\name{...} by its argument, matching braces at any depth."""
    token = "\\" + name + "{"
    while (start := tex.find(token)) >= 0:
        depth, end = 1, start + len(token)
        while end < len(tex) and depth:
            depth += {"{": 1, "}": -1}.get(tex[end], 0)
            end += 1
        tex = tex[:start] + tex[start + len(token):end - 1] + tex[end:]
    return tex


def clean(tex: str) -> str:
    tex = re.sub(r"(?<!\\)%.*", "", tex)
    tex = _DROP.sub("", tex)
    tex = re.sub(r"\\mybox\{", "{", tex)
    tex = re.sub(r"\\assertion\{((?:[^{}]|\{[^{}]*\})*)\}", r"« \1 »", tex)
    for macro, value in sorted(MACROS.items(), key=lambda item: -len(item[0])):
        tex = re.sub(re.escape(macro) + r"(?![A-Za-z])", lambda _m, v=value: v, tex)
    tex = re.sub(r"\\couleurnb\{((?:[^{}]|\{[^{}]*\})*)\}\{(?:[^{}]|\{[^{}]*\})*\}", r"\1", tex)
    for _ in range(2):
        tex = _UNWRAP.sub(r"\2", tex)
    tex = unwrap(tex, "myboxinline")
    tex = re.sub(r"\\textcolor\{[^{}]*\}", "", tex)
    tex = re.sub(r"\\color\{[^{}]*\}", "", tex)
    tex = re.sub(r"\\begin\{(itemize|enumerate)\}|\\end\{(itemize|enumerate)\}", "", tex)
    tex = re.sub(r"\\item\b\s*", "- ", tex)
    return re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n", tex)).strip()


def read_chapter(folder: Path, name: str, start: int) -> list[dict]:
    """Units of one chapter, in reading order. Each knows its chapter and section, which search uses."""
    tex = (folder / name / f"ch_{name}.tex").read_text(encoding="utf-8")
    tex = re.sub(r"(?<!\\)%.*", "", tex)
    events = [(m.start(), "heading", m) for m in _HEADING.finditer(tex)]
    events += [(m.start(), "env", m) for m in _ENV.finditer(tex)]
    units: list[dict] = []
    chapter = section = ""
    for _, kind, match in sorted(events, key=lambda e: e[0]):
        if kind == "heading":
            level, title = match[1], re.sub(r"\s*\\\\\s*", " ", clean(match[2]))
            if level == "chapitre":
                chapter, section = title, ""
            elif level == "section":
                section = title
            units.append(_unit(start + len(units), "heading", title, chapter, section, name))
            continue
        env, option, body = match[1], (match[2] or "").strip("[]"), clean(match[3])
        label = {"definition": "Définition", "theoreme": "Théorème", "proposition": "Proposition",
                 "corollaire": "Corollaire", "lemme": "Lemme", "exemple": "Exemple", "proof": "Démonstration"}[env]
        title = f"{label} ({clean(option)})" if option else label
        units.append(_unit(start + len(units), KINDS[env], f"{title}. {body}", chapter, section, name))
    return units


def _unit(index: int, kind: str, text: str, chapter: str, section: str, folder: str) -> dict:
    return {"id": f"exo7:{index:04d}", "kind": kind, "text": text, "volume": BOOK_OF.get(folder, "Exo7"),
            "module": folder, "section": section, "printed_page": None,
            "label": ", ".join(p for p in ("Exo7", chapter, section) if p),
            "number": None, "region": "body"}


def read_course(folder: Path) -> list[dict]:
    units: list[dict] = []
    for name in CHAPTERS:
        units += read_chapter(folder, name, len(units))
    return units
