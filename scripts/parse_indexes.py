"""Read each book's index pages into data/private/index_terms.json."""

import argparse
import json
import re
from pathlib import Path

from mathhinter.corpus.index_terms import parse_index_page
from mathhinter.extract.pdfchars import read_pages


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--books", nargs=3, required=True)
    args = parser.parse_args()
    entries = []
    for volume, book in enumerate(args.books, start=1):
        lines = Path(f"data/private/pages-v{volume}.jsonl").read_text(encoding="utf-8").splitlines()
        pages = [json.loads(line) for line in lines]
        wanted = [p["page"] for p in pages
                  if any(re.search(r"\bINDEX\b", b["md"][:30]) for b in p["blocks"][:2])]
        for page in read_pages(book, wanted):
            for entry in parse_index_page(page):
                entries.append({**entry, "volume": volume})
    Path("data/private/index_terms.json").write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
