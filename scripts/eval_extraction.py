"""Score extractors against the hand-transcribed formulas and write reports/extraction.{json,md}.

The gold file and crops contain book content and stay in data/private. The report holds numbers only.
"""

import argparse
import json
import random
import statistics
import subprocess
from hashlib import sha256
from pathlib import Path

from mathhinter.extract.latex import glyph_latex, to_latex
from mathhinter.extract.pdfchars import Glyph, read_pages
from mathhinter.extract.score import similarity, tokens


def in_box(g: Glyph, box) -> bool:
    x = (g.x0 + g.x1) / 2
    return box[0] - 1 <= x <= box[2] + 1 and box[1] - 1 <= g.baseline <= box[3] + 1


def poppler(book: str, page: int, box) -> str:
    x, y, w, h = int(box[0]) - 2, int(box[1]) - 2, int(box[2] - box[0]) + 4, int(box[3] - box[1]) + 4
    args = ["pdftotext", "-r", "72", "-f", str(page + 1), "-l", str(page + 1), "-x", str(x), "-y", str(y),
            "-W", str(w), "-H", str(h), book, "-"]
    return subprocess.run(args, capture_output=True, text=True, check=True).stdout


def bootstrap(values: list[float], seed: int = 7, rounds: int = 4000) -> list[float]:
    rng = random.Random(seed)
    means = sorted(statistics.fmean(rng.choices(values, k=len(values))) for _ in range(rounds))
    return [means[int(0.025 * rounds)], means[int(0.975 * rounds)]]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--books", nargs=3, required=True)
    parser.add_argument("--gold", default="data/private/gold_formulas.jsonl")
    parser.add_argument("--name", default="test", help="tuning or test: the part of the report to write")
    parser.add_argument("--ocr", default="", help="optional JSON of {formula id: LaTeX} from an OCR tool")
    args = parser.parse_args()
    rows = [json.loads(line) for line in open(args.gold, encoding="utf-8")]
    excluded = [r for r in rows if "excluded" in r]
    rows = [r for r in rows if "latex" in r]
    ocr = json.loads(Path(args.ocr).read_text()) if args.ocr else {}
    tools: dict[str, dict[str, str]] = {"poppler": {}, "font_aware": {}, "font_symbols_no_layout": {}}
    if ocr:
        tools["pix2tex"] = ocr
    for r in rows:
        book = args.books[r["volume"] - 1]
        page = next(read_pages(book, [r["page"]]))
        box = r["bbox"]
        glyphs = [g for g in page.glyphs if in_box(g, box)]
        rules = [q for q in page.rules if box[0] - 3 <= q.x0 and q.x1 <= box[2] + 3 and box[1] - 2 <= q.y <= box[3] + 2]
        tools["font_aware"][r["id"]] = to_latex(glyphs, rules)
        tools["font_symbols_no_layout"][r["id"]] = "".join(glyph_latex(g) for g in sorted(glyphs, key=lambda g: g.x0))
        tools["poppler"][r["id"]] = poppler(book, r["page"], box)
    report: dict = {"gold_sha256": sha256(Path(args.gold).read_bytes()).hexdigest(),
                    "formulas_sampled": len(rows) + len(excluded), "scored": len(rows),
                    "excluded_detection_errors": len(excluded), "per_tool": {}}
    for name, results in tools.items():
        structure = [similarity(results.get(r["id"], ""), r["latex"]) for r in rows]
        symbols = [similarity(results.get(r["id"], ""), r["latex"], structure=False) for r in rows]
        exact = [tokens(results.get(r["id"], "")) == tokens(r["latex"]) for r in rows]
        report["per_tool"][name] = {
            "structure_similarity": round(statistics.fmean(structure), 3),
            "structure_ci95": [round(v, 3) for v in bootstrap(structure)],
            "symbol_similarity": round(statistics.fmean(symbols), 3),
            "symbol_ci95": [round(v, 3) for v in bootstrap(symbols)],
            "exact_share": round(sum(exact) / len(exact), 3),
            "by_volume_structure": {
                str(v): round(statistics.fmean(s for s, r in zip(structure, rows, strict=True) if r["volume"] == v), 3)
                for v in (1, 2, 3)
            },
        }
    Path("reports").mkdir(exist_ok=True)
    target = Path("reports/extraction.json")
    full = json.loads(target.read_text()) if target.exists() else {}
    full[args.name] = report
    target.write_text(json.dumps(full, indent=2) + "\n")
    outputs = Path(f"data/private/extraction_outputs_{args.name}.json")
    outputs.write_text(json.dumps(tools, indent=1, ensure_ascii=False))
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
