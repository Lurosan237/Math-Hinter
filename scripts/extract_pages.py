"""Extract every page of a book to data/private/pages-v<volume>.jsonl."""

import argparse
import json
from pathlib import Path

from mathhinter.extract.layout import page_blocks
from mathhinter.extract.pdfchars import read_pages

WIDE_RULE = 300  # points; the text block is about 400 wide


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", required=True)
    parser.add_argument("--volume", type=int, required=True)
    parser.add_argument("--out", default="data/private")
    args = parser.parse_args()
    target = Path(args.out) / f"pages-v{args.volume}.jsonl"
    with target.open("w", encoding="utf-8") as out:
        for page in read_pages(args.book):
            blocks = [{"kind": b.kind, "top": round(b.top, 1), "bottom": round(b.bottom, 1), "x0": round(b.x0, 1),
                       "x1": round(b.x1, 1), "size": round(max(g.size for g in b.glyphs), 1),
                       "bold": sum("Bold" in g.font or "BX" in g.font or "bold" in g.font for g in b.glyphs),
                       "n": len(b.glyphs), "md": b.markdown()} for b in page_blocks(page)]
            # Rules across the full text width frame the exercises, so the parser needs them.
            wide = sorted(round(r.y, 1) for r in page.rules if r.x1 - r.x0 > WIDE_RULE)
            record = {"page": page.number, "blocks": blocks, "wide_rules": wide}
            out.write(json.dumps(record, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
