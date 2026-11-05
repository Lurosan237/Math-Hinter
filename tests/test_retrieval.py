import numpy as np

from mathhinter.corpus.index_terms import full_term
from mathhinter.retrieval.crosslinks import document_frequency, link_statement, term_targets
from mathhinter.retrieval.labels import build_questions, module_split
from mathhinter.retrieval.metrics import interval, recall_at, reciprocal_rank
from mathhinter.retrieval.search import BM25, rank, reciprocal_fusion
from mathhinter.retrieval.text import clean, math_tokens, tokens, word_tokens


def test_book_pointers_are_not_search_terms():
    assert "page" not in clean("voir le théorème 47 de la page 522, donc")
    assert "47" not in clean("voir le théorème 47 de la page 522, donc")


def test_own_label_is_removed():
    assert clean("Exercice 12. Montrer").strip() == "Montrer"


def test_words_are_stemmed_and_folded():
    assert word_tokens("les matrices") == word_tokens("la matrice")
    assert word_tokens("déterminant") == ["determin"]


def test_maths_symbols_become_tokens():
    assert math_tokens(r"$\sum_{i}x\in\mathbb{R}$") == ["§sum", "§mathbb_R"]
    assert "§mathbb_R" in tokens(r"soit $x\in\mathbb{R}$")
    assert "§mathbb_R" not in tokens(r"soit $x\in\mathbb{R}$", use_math=False)


def test_bm25_prefers_the_rarer_shared_word():
    index = BM25([["fonction", "continu"], ["fonction", "derive"], ["fonction", "integrale"]])
    assert rank(index.scores(["fonction", "derive"]))[0] == 1


def test_unknown_query_scores_nothing():
    assert not BM25([["a"]]).scores(["z"]).any()


def test_hidden_units_never_appear():
    assert list(rank(np.array([3.0, 2.0, 1.0]), {0})) == [1, 2]


def test_fusion_rewards_agreement():
    total = reciprocal_fusion([np.array([0, 1, 2]), np.array([0, 2, 1])], 3)
    assert total.argmax() == 0


def test_metrics():
    assert recall_at(["a", "b", "c"], {"b", "z"}, 2) == 0.5
    assert reciprocal_rank(["a", "b"], {"b"}) == 0.5
    assert reciprocal_rank(["a"], {"b"}) == 0
    low, high = interval([0.0, 1.0] * 20)
    assert low < 0.5 < high


def unit(ident, kind, module="I.1", text="", volume=1, page=1, number=None):
    return {"id": ident, "kind": kind, "module": module, "text": text, "volume": volume, "printed_page": page,
            "number": number}


UNITS = [unit("t", "theorem"), unit("e", "exercise"), unit("s", "solution"), unit("p", "proposition"),
         unit("d", "proof"), unit("x", "exercise"), unit("y", "solution")]


def test_questions_come_from_citations():
    edges = [{"source": "s", "target": "t", "kind": "theorem"}, {"source": "d", "target": "t", "kind": "theorem"}]
    questions = {(q.query, q.answer, q.source): q.gold for q in build_questions(UNITS, edges)}
    assert questions == {("e", "s", "exercise"): {"t"}, ("p", "d", "result"): {"t"}}


def test_citing_an_exercise_is_not_a_prerequisite():
    assert build_questions(UNITS, [{"source": "s", "target": "x", "kind": "exercise"}]) == []


def test_split_keeps_a_module_together():
    assert module_split(unit("a", "exercise")) == module_split(unit("b", "theorem"))


def test_full_term_fills_in_the_dash():
    assert full_term({"head": "équivalence", "sub": "relation d’—", "pages": [1]}) == "relation d’équivalence"
    assert full_term({"head": "matrice(s)", "sub": "hermitienne", "pages": [1]}) == "matrice hermitienne"
    assert full_term({"head": "Frobenius (théorème de —)", "sub": "", "pages": [1]}) == "théorème de Frobenius"


def test_index_term_links_to_the_definition_on_its_page():
    units = [unit("d1", "definition", text="Une matrice hermitienne est...", page=7),
             unit("d2", "definition", text="Un autre objet", page=7)]
    targets = term_targets([{"head": "matrice(s)", "sub": "hermitienne", "pages": [7], "volume": 1}], units)
    frequency = document_frequency(list(targets), [("matrice", "hermitienne")])
    links = link_statement("Soit une matrice hermitienne.", targets, frequency, 10)
    assert [link["unit"] for link in links] == ["d1"]


def test_shorter_term_inside_a_longer_one_is_dropped():
    targets = {("matrice",): {"unit": "a"}, ("matrice", "hermitienne"): {"unit": "b"}}
    links = link_statement("une matrice hermitienne", targets, {}, 10)
    assert [link["unit"] for link in links] == ["b"]
