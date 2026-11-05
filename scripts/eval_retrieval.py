"""Compare rankers on questions labelled by the books' own citations. Writes reports/retrieval.json for --split test.

Each question hides its own statement and its own solution or proof. Book text stays in data/private.
"""

import argparse
import json
import re
import statistics
from pathlib import Path

import numpy as np

from mathhinter.retrieval.labels import TARGET_KINDS, build_questions, module_split
from mathhinter.retrieval.metrics import interval, recall_at, reciprocal_rank
from mathhinter.retrieval.search import BM25, rank, reciprocal_fusion
from mathhinter.retrieval.text import clean, tokens, word_tokens

PRIVATE = Path("data/private")


def word_vectors(texts: list[str]):
    import spacy

    nlp = spacy.load("fr_core_news_md", disable=["parser", "ner", "tagger", "lemmatizer", "attribute_ruler"])
    table = nlp.vocab.vectors
    frequency: dict[str, int] = {}
    tokenised = []
    for text in texts:
        words = [w for w in re.findall(r"[^\W\d_]{2,}", re.sub(r"\$.*?\$", " ", clean(text)).lower())]
        tokenised.append(words)
        for word in set(words):
            frequency[word] = frequency.get(word, 0) + 1
    matrix = np.zeros((len(texts), table.shape[1]))
    for row, words in enumerate(tokenised):
        for word in words:
            key = nlp.vocab.strings[word]
            if key in table:
                matrix[row] += table[key] * np.log(len(texts) / frequency[word])
    return matrix / (np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-9)


def proximity(position: int, size: int) -> np.ndarray:
    """Closest earlier unit first; later units follow, closest first."""
    distance = np.arange(size) - position
    return np.where(distance < 0, -distance.astype(float), size + distance.astype(float)) * -1.0


def score(questions, rankings, ids) -> dict:
    out = {}
    for name, fn in rankings.items():
        recall5, recall10, recall50, mrr = [], [], [], []
        for question in questions:
            ranked = [ids[i] for i in fn(question)]
            recall5.append(recall_at(ranked, question.gold, 5))
            recall10.append(recall_at(ranked, question.gold, 10))
            recall50.append(recall_at(ranked, question.gold, 50))
            mrr.append(reciprocal_rank(ranked, question.gold))
        out[name] = {"recall_5": round(statistics.fmean(recall5), 3), "recall_5_ci95": interval(recall5),
                     "recall_10": round(statistics.fmean(recall10), 3),
                     "recall_50": round(statistics.fmean(recall50), 3),
                     "mrr": round(statistics.fmean(mrr), 3), "mrr_ci95": interval(mrr)}
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=["dev", "test"], default="dev")
    parser.add_argument("--k1", type=float, default=1.4)
    parser.add_argument("--b", type=float, default=0.6)
    args = parser.parse_args()
    units = [json.loads(line) for line in (PRIVATE / "units.jsonl").open(encoding="utf-8")]
    edges = json.loads((PRIVATE / "edges.json").read_text(encoding="utf-8"))
    pairs = json.loads((PRIVATE / "pairs.json").read_text(encoding="utf-8"))
    ids = [u["id"] for u in units]
    position = {u["id"]: i for i, u in enumerate(units)}
    texts = [u["text"] for u in units]
    # Each unit also carries the title of its section: a theorem rarely repeats what its section is about.
    titles: dict = {}
    for u in units:
        if u["kind"] == "heading":
            titles[(u["volume"], u["module"], u["section"])] = u["text"].split("\n")[0]
    contextual = [f"{titles.get((u['volume'], u['module'], u['section']), '')}\n{u['text']}" for u in units]
    questions = [q for q in build_questions(units, edges) if module_split(units[position[q.query]]) == args.split]

    words_index = BM25([word_tokens(t) for t in texts], args.k1, args.b)
    full_index = BM25([tokens(t) for t in texts], args.k1, args.b)
    context_index = BM25([tokens(t) for t in contextual], args.k1, args.b)
    vectors = word_vectors(texts)
    query_cache: dict = {}

    def query(q, kind):
        text = texts[position[q.query]]
        key = (q.query, kind)
        if key not in query_cache:
            query_cache[key] = word_tokens(text) if kind == "words" else tokens(text)
        return query_cache[key]

    def hidden(q):
        return {position[q.query], position[q.answer]}

    def bm25_words(q):
        return rank(words_index.scores(query(q, "words")), hidden(q))

    def bm25_full(q):
        return rank(full_index.scores(query(q, "full")), hidden(q))

    def dense(q):
        return rank(vectors @ vectors[position[q.query]], hidden(q))

    def nearby(q):
        return rank(proximity(position[q.query], len(units)), hidden(q))

    results_only = np.array([u["kind"] in TARGET_KINDS for u in units])

    def bm25_results(q):
        keep = rank(full_index.scores(query(q, "full")), hidden(q))
        return keep[results_only[keep]]

    def context_results(q):
        keep = rank(context_index.scores(query(q, "full")), hidden(q))
        return keep[results_only[keep]]

    def context_plus_nearby(q):
        return rank(reciprocal_fusion([context_results(q), nearby(q)], len(units)), hidden(q))

    def hybrid(q):
        return rank(reciprocal_fusion([bm25_full(q), dense(q)], len(units)), hidden(q))

    def hybrid_results(q):
        keep = hybrid(q)
        return keep[results_only[keep]]

    def fused_with_nearby(q):
        return rank(reciprocal_fusion([hybrid_results(q), nearby(q)], len(units)), hidden(q))

    rankers = {"bm25_words": bm25_words, "bm25_words_math": bm25_full, "word_vectors": dense, "hybrid": hybrid,
               "bm25_results_only": bm25_results, "bm25_section_titles": context_results,
               "bm25_titles_plus_nearby": context_plus_nearby, "hybrid_results_only": hybrid_results,
               "nearby_units": nearby, "hybrid_plus_nearby": fused_with_nearby}
    report: dict = {"split": args.split, "questions": len(questions), "gold_links": sum(len(q.gold) for q in questions),
                    "parameters": {"k1": args.k1, "b": args.b}, "by_source": {}}
    report["all"] = score(questions, rankers, ids)
    for source in ("exercise", "result"):
        subset = [q for q in questions if q.source == source]
        report["by_source"][source] = {"questions": len(subset), "rankers": score(subset, rankers, ids)}
    far = []
    for q in questions:
        module = units[position[q.query]]["module"]
        away = frozenset(g for g in q.gold if units[position[g]]["module"] != module)
        if away:
            far.append(type(q)(q.query, q.answer, q.source, away))
    report["other_module"] = {"questions": len(far), "rankers": score(far, rankers, ids)}

    # The leak: how often search would simply hand over the answer if it weren't hidden.
    leak_questions = [(p["exercise"], p["solution"]) for p in pairs
                      if module_split(units[position[p["exercise"]]]) == args.split]
    top1, top5 = [], []
    for exercise, solution in leak_questions:
        ranking = rank(full_index.scores(tokens(texts[position[exercise]])), {position[exercise]})
        ranked = [ids[i] for i in ranking[:5]]
        top1.append(ranked[0] == solution)
        top5.append(solution in ranked)
    report["own_solution_if_not_hidden"] = {"exercises": len(leak_questions), "top_1": round(statistics.fmean(top1), 3),
                                            "top_5": round(statistics.fmean(top5), 3)}
    print(json.dumps({k: report[k] for k in ("split", "questions", "gold_links", "own_solution_if_not_hidden")}))
    for name, row in report["all"].items():
        print(f"{name:22} r5 {row['recall_5']} r10 {row['recall_10']} r50 {row['recall_50']} mrr {row['mrr']}")
    print("other module", report["other_module"]["questions"],
          {k: v["recall_10"] for k, v in report["other_module"]["rankers"].items()})
    print("exercises", report["by_source"]["exercise"]["questions"],
          {k: v["recall_10"] for k, v in report["by_source"]["exercise"]["rankers"].items()})
    if args.split == "test":
        Path("reports/retrieval.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
