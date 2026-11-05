from mathhinter.corpus.graph import build_index, find_references
from mathhinter.corpus.structure import normalise, page_offset, pair_exercises, parse_book, parse_header


def block(md, top=100.0, size=10.9, bold=0):
    return {"md": md, "top": top, "size": size, "bold": bold, "kind": "text", "n": len(md), "x0": 50, "x1": 400,
            "bottom": top}


def page(number, *blocks, wide_rules=()):
    return {"page": number, "blocks": list(blocks), "wide_rules": list(wide_rules)}


def header(text):
    return block(text, top=40, size=8.2, bold=20)


BOOK = [
    page(10, header("5 II.1 $\\bullet$ Suites"), block("Théorème 7. Toute suite bornée", 100), block("Un mot.", 120)),
    page(11, header("1 Limites 6"),
         block("Exercice 3.", 100, bold=10), block("Calculer la limite.", 112),
         block("Solution. Elle vaut 0 (cf. le théorème 7 de la page 5).", 130, bold=8), block("Fin.", 142),
         block("Le texte reprend ici.", 170), wide_rules=[90, 155]),
    page(12, header("Exercices 7"), block("II.1.1 Montrer que.", 100), block("II.1.2 Montrer encore.", 120)),
]


def test_header_gives_the_printed_page_and_module():
    parsed = parse_header(BOOK[0]["blocks"])
    assert (parsed["printed"], parsed["module"]) == (5, "II.1")


def test_offset_fills_in_printed_pages():
    assert page_offset(BOOK) == 5


def test_labels_become_units():
    kinds = [u.kind for u in parse_book(1, BOOK)]
    assert kinds[:3] == ["theorem", "exercise", "solution"]


def test_wide_rule_ends_a_solution():
    units = parse_book(1, BOOK)
    solution = next(u for u in units if u.kind == "solution")
    assert "Fin." in solution.text() and "reprend" not in solution.text()


def test_exercise_pairs_with_following_solution():
    units = parse_book(1, BOOK)
    assert [(a.number, b.kind) for a, b in pair_exercises(units)] == [("3", "solution")]


def test_end_of_module_exercises_are_split():
    numbers = [u.number for u in parse_book(1, BOOK) if u.kind == "exercise_end"]
    assert numbers == ["II.1.1", "II.1.2"]


def test_ligatures_do_not_hide_definitions():
    assert normalise("Déﬁnition") == "Définition"
    units = parse_book(1, [page(10, header("5 II.1 $\\bullet$ Suites"), block("Déﬁnition 2. Une suite"))])
    assert units[0].kind == "definition"


def records():
    return [(f"u{i}", u) for i, u in enumerate(parse_book(1, BOOK))]


def test_reference_links_to_its_target():
    items = records()
    references = find_references(dict(items), build_index(items))
    assert [(r.kind, r.status) for r in references] == [("theorem", "linked")]
    target = dict(items)[references[0].target]
    assert (target.kind, target.number) == ("theorem", "7")


def test_reference_to_another_book_is_external():
    book = [page(10, header("5 II.1 $\\bullet$ Suites"), block("Démonstration. Voir [Serre], théorème 7 de la page 5.",
                                                               bold=8))]
    items = [(f"u{i}", u) for i, u in enumerate(parse_book(1, book))]
    assert find_references(dict(items), build_index(items))[0].status == "external"


def test_polynomial_ring_is_not_a_book():
    book = [page(10, header("5 II.1 $\\bullet$ Suites"), block("Théorème 7. Un fait", 100),
                 block("Démonstration. Dans K[X], voir le théorème 7 de la page 5.", 120, bold=8))]
    items = [(f"u{i}", u) for i, u in enumerate(parse_book(1, book))]
    assert find_references(dict(items), build_index(items))[0].status == "linked"
