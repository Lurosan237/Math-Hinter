"""Draw a reproducible random sample of formulas and render crops for hand transcription.

Output goes to data/private because it contains book content.
"""

import argparse
import json
import random
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image, ImageDraw

from mathhinter.extract.layout import display_formulas
from mathhinter.extract.pdfchars import read_pages


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--books", nargs=3, required=True, help="the PDFs for volumes 1, 2 and 3")
    parser.add_argument("--out", default="data/private/formula_sample")
    parser.add_argument("--per-volume", type=int, default=20)
    parser.add_argument("--seed", type=int, default=2026)
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(args.seed)
    index = []
    for volume, book in enumerate(args.books, start=1):
        document = pdfium.PdfDocument(book)
        chosen = []
        for number in rng.sample(range(30, len(document) - 20), 3 * len(document) // 10):
            page = next(read_pages(book, [number]))
            found = [f for f in display_formulas(page) if len(f.glyphs) >= 8 and f.bottom < page.height - 40]
            if found:
                chosen.append(rng.choice(found))
            if len(chosen) == args.per_volume:
                break
        for i, formula in enumerate(chosen):
            scale = 3
            bitmap = document[formula.page].render(scale=scale).to_pil().convert("RGB")
            box = [max(formula.x0 - 6, 0) * scale, max(formula.top - 6, 0) * scale,
                   (formula.x1 + 6) * scale, (formula.bottom + 6) * scale]
            ident = f"v{volume}-{i:02d}"
            crop = bitmap.crop(tuple(int(v) for v in box))
            crop.save(out / f"{ident}.png")
            index.append({"id": ident, "volume": volume, "page": formula.page,
                          "bbox": [formula.x0, formula.top, formula.x1, formula.bottom]})
    (out / "index.json").write_text(json.dumps(index, indent=1))
    # contact sheets for reading
    per_sheet = 10
    for start in range(0, len(index), per_sheet):
        batch = index[start:start + per_sheet]
        images = [Image.open(out / f"{b['id']}.png") for b in batch]
        height = sum(min(im.height, 330) + 34 for im in images)
        sheet = Image.new("RGB", (1500, height), "white")
        draw = ImageDraw.Draw(sheet)
        y = 0
        for b, im in zip(batch, images, strict=True):
            draw.text((4, y + 8), b["id"], fill="red")
            im.thumbnail((1500, 330))
            sheet.paste(im, (0, y + 26))
            y += im.height + 34
        sheet.save(out / f"sheet-{start // per_sheet}.png")


if __name__ == "__main__":
    main()
