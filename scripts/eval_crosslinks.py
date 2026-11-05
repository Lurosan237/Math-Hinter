"""Propose cross-volume links from the indexes, compare with search, and draw a mixed sample to judge by hand."""

import json
import random
from math import sqrt
from pathlib import Path

from mathhinter.retrieval.crosslinks import _words, document_frequency, link_statement, term_targets
from mathhinter.retrieval.search import BM25, rank
from mathhinter.retrieval.text import tokens

PRIVATE = Path("data/private")


def wilson(good: int, total: int, z: float = 1.96) -> tuple[float, float]:
    share = good / total
    middle = share + z * z / (2 * total)
    spread = z * sqrt(share * (1 - share) / total + z * z / (4 * total * total))
    bottom = 1 + z * z / total
    return round((middle - spread) / bottom, 3), round((middle + spread) / bottom, 3)


def main() -> None:
    units = [json.loads(line) for line in (PRIVATE / "units.jsonl").open(encoding="utf-8")]
    entries = json.loads((PRIVATE / "index_terms.json").read_text(encoding="utf-8"))
    statements = [u for u in units if u["kind"] == "exercise" and u["volume"] > 1]
    earlier = [u for u in units if u["kind"] == "definition"]
    index = BM25([tokens(u["text"]) for u in earlier], 2.2, 0.9)
    docs = [_words(u["text"]) for u in units]
    links_by_volume, covered = {}, {}
    proposals = []
    for later in (2, 3):
        targets = term_targets([e for e in entries if e["volume"] < later], [u for u in units if u["volume"] < later])
        frequency = document_frequency(list(targets), docs)
        chosen = [s for s in statements if s["volume"] == later]
        have = 0
        for statement in chosen:
            links = link_statement(statement["text"], targets, frequency, len(docs))
            have += bool(links)
            for link in links:
                proposals.append({"method": "index", "source": statement["id"], "target": link["unit"],
                                  "term": link["term"]})
            blocked = [i for i, u in enumerate(earlier) if u["volume"] >= later]
            top = rank(index.scores(tokens(statement["text"])), blocked)[:3]
            for i in top:
                target = earlier[i]["id"]
                proposals.append({"method": "search", "source": statement["id"], "target": target, "term": ""})
        links_by_volume[later] = {"terms": len(targets), "statements": len(chosen)}
        covered[later] = have
    report: dict = {"volumes": {str(v): {**links_by_volume[v], "statements_with_a_link": covered[v]} for v in (2, 3)}}
    checks = Path("data/hand_checks/crosslinks.json")
    if checks.exists():
        judged = json.loads(checks.read_text(encoding="utf-8"))["links"]
        report["hand_check"] = {}
        for method in ("index", "search"):
            links = [j for j in judged if j["method"] == method]
            good = sum(j["uses_the_concept"] for j in links)
            report["hand_check"][method] = {"sampled": len(links), "uses_the_concept": good,
                                            "ci95": list(wilson(good, len(links)))}
    Path("reports/crosslinks.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (PRIVATE / "crosslink_proposals.json").write_text(json.dumps(proposals, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report))
    rng = random.Random(5150)
    sample = []
    for method in ("index", "search"):
        sample += rng.sample([p for p in proposals if p["method"] == method], 40)
    rng.shuffle(sample)
    (PRIVATE / "crosslink_sample.json").write_text(json.dumps(sample, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
