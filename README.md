# Math-Hinter

A French maths study assistant that finds your first wrong step, without giving away the answer.

> **Status:** stage 1 of 6. Formula extraction works and is measured; the agent is not built yet.
> See the [design](docs/design.md).

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
| Poppler `pdftotext` | 0.648 | 2% |
| Font-aware extractor | 0.941 | 57% |

What these numbers don't show:

- **Only 44 of 60 formulas were scored.** The rest were crops the detector cut off or merged with other content,
  often matrices and multi-line displays, so those layouts are probably worse than this.
- **Exact match is the number that matters for checking answers.** One wrong symbol can change the mathematics.
- **It relies on these books' fonts.** It works on TeX-typeset PDFs, not on scans.
- **The transcriptions used for scoring were made by Claude** from page images and aren't yet fully checked by a person.
- **It hasn't been compared with OCR models** such as Marker or MinerU yet. Their models couldn't be downloaded in the
  environment used for this run.

## The books aren't in this repository

They are published works. Everything derived from them stays in `data/private`, which git ignores, and a test checks
that nothing from it gets committed. Reports contain numbers only, and CI runs on a small PDF written for the tests, so
the report itself can only be regenerated with a copy of the books.

## Run it

```bash
pip install -r requirements-dev.txt
pytest -q

# with your own copies of the books (the sample and hand transcription come first)
PYTHONPATH=src python scripts/eval_extraction.py --books vol1.pdf vol2.pdf vol3.pdf \
    --gold data/private/gold_formulas_test.jsonl --name test
python scripts/report_extraction.py
```

## Licence

Code: [MIT](LICENSE).
