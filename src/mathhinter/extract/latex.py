"""Turn positioned glyphs back into LaTeX, from their fonts, names and geometry."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .pdfchars import Glyph, Rule

MATH_FONT = re.compile(r"^(CM(MI|R|SY|EX|BX|MIB|BSY|TI|SS)|MS(AM|BM)|EUFM|EUSM|EURM|rsfs|RSFS|wasy|LASY)")
SYMBOL_FONT = re.compile(r"^(CMMI|CMSY|CMEX|MSAM|MSBM|CMMIB|CMBSY|rsfs|RSFS|EUFM|EUSM|wasy|LASY)")

NAMES = {
    "minus": "-", "periodcentered": r"\cdot", "multiply": r"\times", "asteriskmath": "*", "divide": r"\div",
    "plusminus": r"\pm", "minusplus": r"\mp", "circleplus": r"\oplus", "circleminus": r"\ominus",
    "circlemultiply": r"\otimes", "circledivide": r"\oslash", "circledot": r"\odot", "openbullet": r"\circ",
    "bullet": r"\bullet", "star": r"\star", "asymptequal": r"\asymp", "equivalence": r"\equiv",
    "reflexsubset": r"\subseteq", "reflexsuperset": r"\supseteq", "lessequal": r"\leq", "greaterequal": r"\geq",
    "precedesequal": r"\preceq", "followsequal": r"\succeq", "similar": r"\sim", "approxequal": r"\approx",
    "propersubset": r"\subset", "propersuperset": r"\supset", "lessmuch": r"\ll", "greatermuch": r"\gg",
    "precedes": r"\prec", "follows": r"\succ", "arrowleft": r"\leftarrow", "arrowright": r"\to",
    "arrowup": r"\uparrow", "arrowdown": r"\downarrow", "arrowboth": r"\leftrightarrow",
    "arrownortheast": r"\nearrow", "arrowsoutheast": r"\searrow", "similarequal": r"\simeq",
    "arrowdblleft": r"\Leftarrow", "arrowdblright": r"\Rightarrow", "arrowdblup": r"\Uparrow",
    "arrowdbldown": r"\Downarrow", "arrowdblboth": r"\Leftrightarrow", "arrownorthwest": r"\nwarrow",
    "arrowsouthwest": r"\swarrow", "proportional": r"\propto", "prime": "'", "infinity": r"\infty",
    "element": r"\in", "owner": r"\ni", "triangle": r"\triangle", "triangleinv": r"\nabla",
    "negationslash": r"\not", "mapsto": r"\mapsto", "universal": r"\forall", "existential": r"\exists",
    "logicalnot": r"\neg", "emptyset": r"\emptyset", "Rfractur": r"\Re", "Ifractur": r"\Im", "latticetop": r"\top",
    "perpendicular": r"\perp", "aleph": r"\aleph", "union": r"\cup", "intersection": r"\cap", "unionmulti": r"\uplus",
    "logicaland": r"\wedge", "logicalor": r"\vee", "turnstileleft": r"\vdash", "turnstileright": r"\dashv",
    "floorleft": r"\lfloor", "floorright": r"\rfloor", "ceilingleft": r"\lceil", "ceilingright": r"\rceil",
    "braceleft": r"\{", "braceright": r"\}", "angbracketleft": r"\langle", "angbracketright": r"\rangle",
    "bar": "|", "bardbl": r"\|", "arrowbothv": r"\updownarrow", "backslash": r"\setminus", "wreathproduct": r"\wr",
    "radical": r"\sqrt", "coproduct": r"\amalg", "nabla": r"\nabla", "integral": r"\int", "unionsq": r"\sqcup",
    "intersectionsq": r"\sqcap", "subsetsqequal": r"\sqsubseteq", "supersetsqequal": r"\sqsupseteq",
    "section": r"\S", "dagger": r"\dagger", "daggerdbl": r"\ddagger", "paragraph": r"\P", "club": r"\clubsuit",
    "diamond": r"\diamondsuit", "heart": r"\heartsuit", "spade": r"\spadesuit",
    # MSAM
    "lessorequalslant": r"\leqslant", "greaterorequalslant": r"\geqslant", "triangleleft": r"\triangleleft",
    "triangleright": r"\triangleright", "complement": r"\complement", "square": r"\square",
    "squaresolid": r"\blacksquare", "lessorsimilar": r"\lesssim", "greaterorsimilar": r"\gtrsim",
    # CMEX big operators
    "summationtext": r"\sum", "summationdisplay": r"\sum", "producttext": r"\prod", "productdisplay": r"\prod",
    "integraltext": r"\int", "integraldisplay": r"\int", "contintegraltext": r"\oint", "contintegraldisplay": r"\oint",
    "uniontext": r"\bigcup", "uniondisplay": r"\bigcup", "intersectiontext": r"\bigcap",
    "intersectiondisplay": r"\bigcap", "logicalandtext": r"\bigwedge", "logicalanddisplay": r"\bigwedge",
    "logicalortext": r"\bigvee", "logicalordisplay": r"\bigvee", "circleplustext": r"\bigoplus",
    "circleplusdisplay": r"\bigoplus", "circlemultiplytext": r"\bigotimes", "circlemultiplydisplay": r"\bigotimes",
    "coproducttext": r"\coprod", "coproductdisplay": r"\coprod", "unionmultitext": r"\biguplus",
    "unionsqtext": r"\bigsqcup", "unionsqdisplay": r"\bigsqcup", "vextendsingle": "|", "vextenddouble": r"\|",
    "tildewide": r"\sim", "hatwide": "^", "similar1": r"\sim",
}
for _size in ("big", "Big", "bigg", "Bigg"):
    NAMES |= {
        f"parenleft{_size}": "(", f"parenright{_size}": ")", f"bracketleft{_size}": "[", f"bracketright{_size}": "]",
        f"braceleft{_size}": r"\{", f"braceright{_size}": r"\}", f"angbracketleft{_size}": r"\langle",
        f"angbracketright{_size}": r"\rangle", f"floorleft{_size}": r"\lfloor", f"floorright{_size}": r"\rfloor",
        f"ceilingleft{_size}": r"\lceil", f"ceilingright{_size}": r"\rceil", f"slash{_size}": "/",
        f"backslash{_size}": r"\setminus",
    }
for _size in ("big", "Big", "bigg", "Bigg"):
    NAMES[f"radical{_size}"] = r"\sqrt"
# Tall delimiters are stacked from pieces: keep one piece for the whole, drop the rest.
NAMES |= {"parenlefttp": "(", "parenrighttp": ")", "bracketlefttp": "[", "bracketrighttp": "]",
          "bracelefttp": r"\{", "bracerighttp": r"\}"}
DROP = {"parenleftbt", "parenrightbt", "parenleftex", "parenrightex", "bracketleftbt", "bracketrightbt",
        "bracketleftex", "bracketrightex", "braceleftbt", "bracerightbt", "braceleftmid", "bracerightmid", "braceex",
        "bracehtipdownleft", "bracehtipdownright", "bracehtipupleft", "bracehtipupright", "arrowvertex"}
LIMIT_OPS = {"lim", "max", "min", "sup", "inf", r"\sum", r"\prod",
             r"\bigcup", r"\bigcap", r"\bigwedge", r"\bigvee", r"\bigoplus", r"\bigotimes",
             r"\coprod", r"\biguplus", r"\bigsqcup"}

UNICODE = {
    "α": r"\alpha", "β": r"\beta", "γ": r"\gamma", "δ": r"\delta", "ε": r"\varepsilon", "ϵ": r"\epsilon",
    "ζ": r"\zeta", "η": r"\eta", "θ": r"\theta", "ϑ": r"\vartheta", "ι": r"\iota", "κ": r"\kappa", "λ": r"\lambda",
    "μ": r"\mu", "\u00b5": r"\mu", "ν": r"\nu", "ξ": r"\xi", "π": r"\pi", "ρ": r"\rho", "ϱ": r"\varrho", "σ": r"\sigma",
    "ς": r"\varsigma",
    "τ": r"\tau", "υ": r"\upsilon", "φ": r"\varphi", "ϕ": r"\phi", "χ": r"\chi", "ψ": r"\psi", "ω": r"\omega",
    "Γ": r"\Gamma", "Δ": r"\Delta", "Θ": r"\Theta", "Λ": r"\Lambda", "Ξ": r"\Xi", "Π": r"\Pi", "Σ": r"\Sigma",
    "Υ": r"\Upsilon", "Φ": r"\Phi", "Ψ": r"\Psi", "Ω": r"\Omega", "∂": r"\partial", "ℓ": r"\ell", "∅": r"\emptyset",
    "∈": r"\in", "→": r"\to", "−": "-", "·": r"\cdot", "∀": r"\forall", "∃": r"\exists", "′": "'", "∗": "*",
    "×": r"\times", "∞": r"\infty", "⊂": r"\subset", "◦": r"\circ", "∥": r"\|", "∩": r"\cap", "∪": r"\cup",

    "√": r"\sqrt", "⇒": r"\Rightarrow", "≺": r"\prec", "•": r"\bullet", "≤": r"\leq", "≥": r"\geq",
    "⩽": r"\leqslant", "⩾": r"\geqslant",
}


def is_math(glyph: Glyph) -> bool:
    return bool(MATH_FONT.match(glyph.font))


def glyph_latex(glyph: Glyph) -> str:
    """The LaTeX for one glyph; empty if it is only a piece of a taller symbol."""
    font, name, text = glyph.font, glyph.name, glyph.text
    if name in DROP:
        return ""
    if font.startswith("MSBM") and len(text) == 1 and text.isalpha():
        return rf"\mathbb{{{text}}}"
    if font.upper().startswith("RSFS") and len(text) == 1 and text.isalpha():
        return rf"\mathscr{{{text}}}"
    if font.startswith("EUF") and len(text) == 1 and text.isalpha():
        return rf"\mathfrak{{{text}}}"
    if font.startswith("CMSY") and name and len(name) == 1 and name.isalpha():
        return rf"\mathcal{{{name}}}"
    if font.startswith("CMSY") and not name and len(text) == 1 and text.isalpha():
        return rf"\mathcal{{{text}}}"
    if name in NAMES:
        return NAMES[name]
    if name and len(name) == 1:
        return name
    text = text.strip()
    return UNICODE.get(text, text)


@dataclass
class Atom:
    latex: str
    x0: float
    x1: float
    baseline: float
    size: float
    top: float
    bottom: float


# TeX's extension font hangs its symbols below the baseline. Depths are in units of the font size.
CMEX_DEPTH = {"big": 1.2, "Big": 1.8, "bigg": 2.4, "Bigg": 3.0, "text": 1.0, "display": 1.4}
AXIS = 0.25


def _cmex_depth(name: str | None) -> float:
    if not name:
        return 1.0
    if name.startswith(("integraldisplay", "contintegraldisplay")):
        return 2.22
    for suffix, depth in CMEX_DEPTH.items():
        if name.endswith(suffix):
            return depth
    return 1.0


def _atoms(glyphs: list[Glyph]) -> list[Atom]:
    out = []
    for g in glyphs:
        latex = glyph_latex(g)
        if not latex:
            continue
        if g.font.startswith("CMEX"):
            # Report the symbol as sitting on the text baseline, centred on the math axis as TeX does.
            depth = _cmex_depth(g.name) * g.size
            top, bottom = g.baseline, g.baseline + depth
            baseline = (top + bottom) / 2 + AXIS * g.size
        else:
            baseline = g.baseline
            top, bottom = g.baseline - 0.7 * g.size, g.baseline + 0.2 * g.size
        out.append(Atom(latex, g.x0, g.x1, baseline, g.size, top, bottom))
    return out


def _merge_stacks(atoms: list[Atom]) -> list[Atom]:
    """Tall bars are stacks of one repeated glyph: keep one, stretched over the whole stack."""
    out: list[Atom] = []
    for a in sorted(atoms, key=lambda a: (round(a.x0), a.top)):
        last = out[-1] if out else None
        if (last and a.latex == last.latex and a.latex in {"|", r"\|"} and abs(a.x0 - last.x0) < 1
                and a.top - last.bottom < a.size):
            last.bottom = max(last.bottom, a.bottom)
            last.baseline = (last.top + last.bottom) / 2 + AXIS * a.size
        else:
            out.append(Atom(a.latex, a.x0, a.x1, a.baseline, a.size, a.top, a.bottom))
    return out


WORD_OPS = ("lim", "max", "min", "sup", "inf")


def _merge_words(atoms: list[Atom]) -> list[Atom]:
    """lim, max... are roman letters that can carry limits underneath, so make them one symbol."""
    atoms = sorted(atoms, key=lambda a: a.x0)
    out: list[Atom] = []
    i = 0
    while i < len(atoms):
        for word in WORD_OPS:
            chunk = _word_at(atoms, i, word)
            if chunk:
                out.append(Atom(word, chunk[0].x0, chunk[-1].x1, chunk[0].baseline, chunk[0].size, chunk[0].top,
                                chunk[0].bottom))
                used = {id(a) for a in chunk}
                atoms = atoms[:i] + [a for a in atoms[i:] if id(a) not in used]
                break
        else:
            out.append(atoms[i])
            i += 1
    return out


def _word_at(atoms: list[Atom], i: int, word: str) -> list[Atom] | None:
    # Walk along the baseline only: limits sit between the letters when sorted by x.
    first = atoms[i]
    if first.latex != word[0]:
        return None
    found = [first]
    for a in atoms[i + 1:]:
        if len(found) == len(word) or a.x0 - found[-1].x1 > 1.5:
            break
        if abs(a.baseline - first.baseline) < 0.6 and a.latex == word[len(found)]:
            found.append(a)
    return found if len(found) == len(word) else None


def _take(atoms: list[Atom], chosen: list[Atom]) -> list[Atom]:
    ids = {id(a) for a in chosen}
    return [a for a in atoms if id(a) not in ids]


def _fold_fractions(atoms: list[Atom], rules: list[Rule]) -> list[Atom]:
    for rule in sorted(rules, key=lambda r: r.x1 - r.x0):  # inner fractions first
        inside = [a for a in atoms if a.x0 >= rule.x0 - 1.5 and a.x1 <= rule.x1 + 1.5]
        num = [a for a in inside if 0 < rule.y - a.baseline < 22]
        den = [a for a in inside if 0 < a.baseline - rule.y < 22]
        if num and den:
            # keep only the rows closest to the bar; anything further belongs to another line
            near_num = max(a.baseline for a in num)
            num = [a for a in num if near_num - a.baseline < 12]
            near_den = min(a.baseline for a in den)
            den = [a for a in den if a.baseline - near_den < 12]
            size = max(a.size for a in num + den)
            latex = rf"\frac{{{_linear(num)}}}{{{_linear(den)}}}"
            atoms = _take(atoms, num + den) + [Atom(latex, rule.x0, rule.x1, rule.y + AXIS * size, size,
                                                     min(a.top for a in num), max(a.bottom for a in den))]
        elif den:
            near_den = min(a.baseline for a in den)
            den = [a for a in den if a.baseline - near_den < 8]
            root = [a for a in atoms if a.latex == r"\sqrt" and -3 < rule.x0 - a.x1 < 4]
            word = r"\sqrt" if root else r"\overline"
            first = sorted(den, key=lambda a: -a.size)[0]
            atom = Atom(rf"{word}{{{_linear(den)}}}", (root[0].x0 if root else rule.x0), rule.x1, first.baseline,
                        first.size, rule.y, max(a.bottom for a in den))
            atoms = _take(atoms, den + root) + [atom]
    return atoms


def _fold_limits(atoms: list[Atom]) -> list[Atom]:
    for op in [a for a in atoms if a.latex in LIMIT_OPS]:
        centre = (op.x0 + op.x1) / 2
        span = max(op.x1 - op.x0, 4) * 1.4
        near = [a for a in atoms if a is not op and abs((a.x0 + a.x1) / 2 - centre) < span and a.size < op.size * 0.95]
        below = [a for a in near if op.bottom - 2 <= a.baseline <= op.bottom + 12]
        above = [a for a in near if op.top - 10 <= a.baseline <= op.top + 2]
        if not below and not above:
            continue
        # a limit is a connected group: extend to glyphs touching it on its own baseline
        for group in (below, above):
            if group:
                level = group[0].baseline
                grew = True
                while grew:
                    grew = False
                    for a in atoms:
                        if a is op or any(a is b for b in group) or a.size >= op.size * 0.95:
                            continue
                        if abs(a.baseline - level) < 3.5 and any(a.x0 - b.x1 < 2 and b.x0 - a.x1 < 2 for b in group):
                            group.append(a)
                            grew = True
        latex = op.latex
        if below:
            latex += f"_{{{_linear(below)}}}"
        if above:
            latex += f"^{{{_linear(above)}}}"
        chosen = below + above
        merged = Atom(latex, min(a.x0 for a in chosen + [op]), max(a.x1 for a in chosen + [op]),
                      op.baseline, op.size, min(a.top for a in chosen + [op]), max(a.bottom for a in chosen + [op]))
        atoms = _take(atoms, chosen + [op]) + [merged]
    return atoms


def _main_baseline(atoms: list[Atom]) -> float:
    big = max(a.size for a in atoms)
    votes: dict[float, float] = {}
    for a in atoms:
        if a.size >= big * 0.85:
            key = round(a.baseline)
            votes[key] = votes.get(key, 0) + (a.x1 - a.x0)
    best = max(votes, key=votes.get)
    return best


def _linear(atoms: list[Atom]) -> str:
    """Left-to-right; a run of smaller glyphs off the baseline becomes the scripts of what precedes it."""
    if not atoms:
        return ""
    base = _main_baseline(atoms)
    big = max(a.size for a in atoms)
    tolerance = max(big * 0.1, 0.7)
    atoms = sorted(atoms, key=lambda a: a.x0)

    def on_line(a: Atom) -> bool:
        return abs(a.baseline - base) <= tolerance or a.size >= big * 0.95 and abs(a.baseline - base) <= big * 0.3

    parts: list[str] = []
    i = 0
    while i < len(atoms):
        if on_line(atoms[i]):
            parts.append(atoms[i].latex)
            i += 1
            continue
        run = []
        while i < len(atoms) and not on_line(atoms[i]):
            run.append(atoms[i])
            i += 1
        sub = [a for a in run if a.baseline > base]
        sup = [a for a in run if a.baseline < base]
        primes = [a for a in sup if a.latex == "'"]
        sup = [a for a in sup if a.latex != "'"]
        parts.extend("'" for _ in primes)
        if sub:
            parts.append(f"_{{{_linear(sub)}}}")
        if sup:
            parts.append(f"^{{{_linear(sup)}}}")
    return _join(parts)


def _join(parts: list[str]) -> str:
    text = ""
    for part in parts:
        if text and re.search(r"\\[A-Za-z]+$", text) and re.match(r"[A-Za-z]", part):
            text += " "
        text += part
    return text


def _rows(atoms: list[Atom]) -> str:
    """Handle several full-size rows at once (matrices, systems, two lines picked up together)."""
    if not atoms:
        return ""
    big = max(a.size for a in atoms)
    tall = [a for a in atoms if a.bottom - a.top > 1.5 * big and a.latex in _DELIMITERS]
    spanned = {id(a) for a in tall}
    rest = [a for a in atoms if id(a) not in spanned]
    if not tall and not _multi_row(rest, big):
        return _linear(atoms)
    pieces: list[str] = []
    edges = sorted(tall, key=lambda a: a.x0)
    position = float("-inf")
    for edge in [*edges, None]:
        limit = edge.x0 if edge else float("inf")
        block = [a for a in rest if position <= (a.x0 + a.x1) / 2 < limit]
        if block:
            pieces.append(_block(block, big))
        if edge:
            pieces.append(edge.latex)
            position = edge.x1
    return _join(pieces)


_DELIMITERS = {"(", ")", "[", "]", r"\{", r"\}", "|", r"\|", r"\langle", r"\rangle"}


def _full_rows(atoms: list[Atom], big: float) -> list[float]:
    rows: list[float] = []
    for a in sorted((a for a in atoms if a.size >= big * 0.9), key=lambda a: a.baseline):
        if not rows or a.baseline - rows[-1] > big * 0.8:
            rows.append(a.baseline)
    return rows


def _multi_row(atoms: list[Atom], big: float) -> bool:
    return len(_full_rows(atoms, big)) > 1


def _block(atoms: list[Atom], big: float) -> str:
    rows = _full_rows(atoms, big)
    if len(rows) < 2:
        return _linear(atoms)
    groups: dict[float, list[Atom]] = {r: [] for r in rows}
    for a in atoms:
        groups[min(rows, key=lambda r: abs(r - a.baseline))].append(a)
    return "".join(_linear(g) for g in groups.values() if g)


def to_latex(glyphs: list[Glyph], rules: list[Rule] | None = None) -> str:
    """LaTeX for one formula given all of its glyphs and any rules among them."""
    atoms = _atoms(glyphs)
    if not atoms:
        return ""
    atoms = _merge_stacks(atoms)
    atoms = _merge_words(atoms)
    atoms = _fold_fractions(atoms, list(rules or []))
    atoms = _fold_limits(atoms)
    latex = _rows(atoms)
    latex = latex.replace(r"\cdot\cdot\cdot", r"\cdots").replace("...", r"\ldots")
    return re.sub(r"-\\to", r"\\to", latex)
