# Math-Hinter

A French maths study assistant that finds your first wrong step, without giving away the answer.

> **Status:** between stages 3 and 4. The books are parsed and searchable, and the test set and maths checker exist.
> The agent itself is not built yet. See the [design](docs/design.md).

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

## Stage 3: finding the right passage

Search is scored on labels the books supply: when a proof or solution cites a numbered result, the statement is the
query and the cited result is the right answer. That gives 306 test questions that nobody hand-picked. Settings were chosen on
one half of the modules and run once on the other ([full report](reports/retrieval.md)).

| | Recall@5 | Recall@10 | MRR |
|---|---|---|---|
| Nearest earlier units (baseline) | 0.050 | 0.146 | 0.055 |
| Word vectors | 0.081 | 0.093 | 0.070 |
| BM25 over definitions and results | 0.238 | 0.327 | 0.187 |
| Plus section titles and position in the book | 0.344 | 0.494 | 0.215 |

- **Search misses most of what a proof needs.** Even the best setup finds about half of the cited results in the top 10.
  A proof often cites a result that shares few words with the statement. Other useful passages count as misses, so
  these are lower bounds.
- **Across modules it barely works:** recall@10 is 0.150. Position in the book also helps only with exercises from the
  book, not a student's own question.
- **Word vectors did worst.** That's a weak test of dense retrieval: modern French embedding models couldn't be
  downloaded in this environment, so they are still untested.
- **Hiding the solution matters, but less than expected.** Unhidden, search would hand over an exercise's own solution
  first 15% of the time and in the top 5 31% of the time.

**Cross-volume links.** Using earlier volumes' indexes, 172 of 300 Licence 2 exercises and 106 of 158 Licence 3 exercises get a link
to an earlier definition. In a blind hand check, the statement really used the linked concept in 26 of 40 index links
and 18 of 40 search links. Those intervals overlap, so this doesn't show the index is better. A correct link also isn't
necessarily what a student is missing, so the tracer shouldn't present these as a diagnosis.

## Preparing to test the agent

These parts need no LLM, so they are measured on their own ([full report](reports/evalset.md)).

**Test set.** 531 of 755 worked exercises pass a filter for garbled or context-dependent statements, each with a wrong
attempt holding one known error and an unchanged control. In a hand check, 24 of 30 kept exercises were usable and 24 of 30
errors made a false statement. So about a fifth of this set is noise. Later lines also stay correct after the error, unlike
a real student's work, which is why real attempts will be a separate test.

**Maths checker.** It parses LaTeX directly into SymPy, with no `eval`, and answers `vérifié`, `réfuté` or `non vérifiable`.
On 3000 equalities from the books' proofs and solutions:

| Verdict | Count |
|---|---|
| vérifié | 70 |
| réfuté | 10 |
| non vérifiable | 2920 |

- **It can check very little of this maths: about 2%.** Most equalities depend on earlier lines or use notation it won't guess at.
  The result: Python checks can't carry the first-wrong-step task on these books, as the design had hoped.
- **`vérifié` isn't proof.** By hand, 61 of 70 were sound. The others treat things like group elements as commuting numbers.
- **`réfuté` isn't either.** All 10 were false alarms on correct equalities, mostly from notation such as Legendre symbols.
- **When it can check, it catches slips.** Of 38 corrupted copies of verified equalities, 3 stayed verified, all harmless ones.

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
PYTHONPATH=src python scripts/parse_indexes.py --books vol1.pdf vol2.pdf vol3.pdf
PYTHONPATH=src python scripts/eval_crosslinks.py

# word vectors need requirements-eval.txt
PYTHONPATH=src python scripts/eval_retrieval.py --split test --k1 2.2 --b 0.9
python scripts/report_retrieval.py

PYTHONPATH=src python scripts/build_evalset.py
PYTHONPATH=src python scripts/eval_checker.py --split test --limit 3000
python scripts/report_evalset.py

# the formula report also needs the private hand transcriptions
PYTHONPATH=src python scripts/eval_extraction.py --books vol1.pdf vol2.pdf vol3.pdf \
    --gold data/private/gold_formulas_test2.jsonl --name test
python scripts/report_extraction.py
```

## Licence

Code: [MIT](LICENSE).
