# Math-Hinter

A French maths study assistant that finds your first wrong step, without giving away the answer.

> **Status:** stage 2 of 6. The books are parsed into formulas, exercises and links between results, and each step is
> measured. The agent is not built yet. See the [design](docs/design.md).

## Stage 1: getting formulas out of the books

An assistant can't check maths it can't read. The textbooks here are text PDFs, yet standard extraction turns sums and
inequalities into junk: the maths fonts often have no usable Unicode map, and layout is lost.

Those fonts do still name their glyphs (`summationdisplay`, `lessorequalslant`). So the extractor reads the names,
then rebuilds LaTeX from each glyph's font and position, including scripts, limits, fractions and stacked delimiters.
It needs no GPU and no model, and it reads each symbol from the PDF rather than guessing it from pixels.

Results on 60 formulas drawn at random from the three volumes after the code was frozen
([full report](reports/extraction.md)):

| | Token similarity | Exact match |
|---|---|---|
| Poppler `pdftotext` | 0.708 | 11% |
| Font-aware extractor | 0.966 | 70% |

What these numbers don't show:

- **Exact match is the number that matters for checking answers.** One wrong symbol can change the mathematics, and
  about three formulas in ten still have at least one wrong token.
- **Only 56 of 60 formulas were scored.** The rest were cut off by the formula detector, and tall displays are
  the likely weak spot.
- **It relies on these books' fonts.** It works on TeX-typeset PDFs, not on scans.
- **The transcriptions used for scoring were made by Claude** from page images and aren't yet fully checked by a person.
- **It hasn't been compared with OCR models** such as Marker or MinerU. Their models couldn't be downloaded in the
  environment used for this run.

## Stage 2: finding the structure

The parser turns 2937 pages into labelled units using the books' own signals: running headers, numbered labels, and
the full-width rules that frame each exercise ([full report](reports/corpus.md)).

- **755 exercises paired with their solution,** which become the practice and test material. In a hand check,
  40 of 40 were paired correctly and 37 of 40 solutions stopped where they should.
- **1189 links between results,** from references like "théorème 167 de la page 333". 90% of the numbered
  references resolved, and 30 of 30 sampled links reached the right unit.

The most useful finding is a limit. **0 of those links cross from one volume to another**, and only 522 of 2587 proofs and
solutions contain a link at all. So the books' references can't by themselves trace a Licence 3 difficulty back to
Licence 1. That part needs another signal, which is the next thing to test.

## The books aren't in this repository

They are published works. Everything derived from them stays in `data/private`, which git ignores, and a test checks
that nothing from it gets committed. Reports contain numbers only, and CI runs on a small PDF written for the tests, so
the report itself can only be regenerated with a copy of the books.

## Run it

```bash
pip install -r requirements-dev.txt
pytest -q

# with your own copies of the books
PYTHONPATH=src python scripts/extract_pages.py --book vol1.pdf --volume 1   # and 2, 3
PYTHONPATH=src python scripts/build_corpus.py

# the formula report also needs the private hand transcriptions
PYTHONPATH=src python scripts/eval_extraction.py --books vol1.pdf vol2.pdf vol3.pdf \
    --gold data/private/gold_formulas_test2.jsonl --name test
python scripts/report_extraction.py
```

## Licence

Code: [MIT](LICENSE).
