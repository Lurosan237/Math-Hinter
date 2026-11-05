# Design

## What it is

A study tool for French-language university maths. You attempt an exercise, and the agent finds your first
wrong step, gives one hint at a time with a citation to the course, checks calculations in Python, and traces
what you are stuck on back to the prerequisite you are missing.

The question it has to answer: **does it help you find your own mistake without giving away the answer?**

## The loop

1. Pick an exercise and write an attempt.
2. Find the first wrong step, checking any calculation with Python.
3. Give hints in order: a question, then a course reference, then a worked step.
4. If you stay stuck, follow theorem dependencies back to the missing prerequisite.
5. Offer a similar exercise to confirm it.

## Material

- **Knowledge base (private):** *Mathématiques Tout-en-un pour la Licence*, volumes 1 to 3. These are published
  books, so neither they nor anything derived from them enter this repository or the public demo.
- **Exercises:** the worked exercises and solutions in those books. End-of-module exercises have their
  corrections on the publisher's site, so they can be practised but not scored.
- **Public demo:** recorded runs on openly licensed material only.
- **Later:** Len's MSI past papers and corrections, and real attempts from classmates, with consent.

## Agent

Small on purpose, so it can be evaluated and defended: `search_course`, `run_python`, `give_hint`,
`trace_prerequisite`, `abstain`, with a step limit. Every answer carries a verdict: `vérifié`, `réfuté` or
`non vérifiable`. Python checks test a result rather than recompute it the same way, for example by
differentiating an antiderivative.

## Evaluation rules

These exist because the easy version of each number would be meaningless.

1. **Hide each exercise's own solution** from retrieval. Otherwise the agent just finds the answer. Results are
   also reported with the leak, to show how much it inflates the score.
2. **Split by module**, so neighbouring exercises can't leak into the test set.
3. **Generated wrong attempts come first:** one known error injected into a correct solution, so the first wrong
   step is known exactly. They are not real student mistakes, and reports say so. Classmates' attempts become a
   separate test set.
4. **Same test set through every stage:** LLM alone, then RAG, then RAG with Python, then the full loop.
5. **An LLM judge is only trusted as far as its agreement with hand labels**, which is reported.
6. **Develop on one sample, report on another** that is drawn after the code is frozen.
7. **Every README number comes from a generated report**, and a test checks that they match.

Headline metrics: first-wrong-step accuracy, how often hints leak the answer, how often a wrong answer is marked
`vérifié`, the share of answers that can be checked at all, citation support, and abstention on trick questions.

## Prerequisite tracing

The books' explicit references link results within a volume, but none crosses volumes and most proofs have none.
Tracing across volumes needs a second signal. Candidates to test: each volume's index of terms, definitions shared
between volumes, and retrieval over definitions. Whichever is used gets its own hand-labelled score, and the tracer
reports which kind of link it followed, since a book's own reference is stronger evidence than a similar term.

## Running on no budget

Free LLM tiers change without notice, so every response is cached and committed where the licence allows, the final
numbers use one pinned model, and limits are checked in each console before relying on them. Providers that may
train on prompts aren't used for course material or classmates' work. The demo is static, with Python running in
the browser and an optional live mode using the visitor's own key.

## Build order

1. Formula extraction (done, see `reports/extraction.md`).
2. Corpus: structure, exercise pairs, prerequisite graph (done, see `reports/corpus.md`).
3. Retrieval, with the leak protection.
4. Agent loop.
5. Full evaluation.
6. Public demo.
