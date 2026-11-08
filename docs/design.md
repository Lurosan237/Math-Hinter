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

The built-in checker only decides about 2% of the books' equalities, and its verdicts need care: `vérifié` assumes
lower-case letters are numbers, and `réfuté` can come from notation. So it is one piece of evidence for the agent,
never the verdict shown to a student on its own, and first-wrong-step detection can't rely on it.

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
Earlier volumes' indexes do reach across, but a blind check found about a third of those links wrong, and many correct
ones point at basics. So the tracer offers them as "this may be worth revisiting", states which kind of link it
followed, and treats a book's own citation as stronger evidence. Whether it finds what a student is really missing is
still untested and needs real attempts.

## Retrieval

Search uses BM25 over stemmed French words and maths symbols, with section titles, restricted to definitions and
results, and hides the exercise's own solution. For exercises from the book it also uses position in the book.
Dense embeddings remain to be tested on a machine that can download them. Recall is modest, so the agent must be able
to say it found nothing useful rather than build on a weak passage.

## What the evaluation changed

On injected errors, retrieval and tools gave no measurable benefit over the model alone, and the agent never chose
to use the checker. The next version should test whether the course helps where the model alone is weakest: real
student mistakes, misuse of a specific theorem, and the book's own conventions. Until then, the plainest honest
design is the model alone with a hint, plus retrieval only to show the student where to read.

## Running on no budget

Free LLM tiers change without notice, so every response is cached and committed where the licence allows, the final
numbers use one pinned model, and limits are checked in each console before relying on them. Providers that may
train on prompts aren't used for course material or classmates' work. The demo is static, with Python running in
the browser and an optional live mode using the visitor's own key.

## Build order

1. Formula extraction (done, see `reports/extraction.md`).
2. Corpus: structure, exercise pairs, prerequisite graph (done, see `reports/corpus.md`).
3. Retrieval, with the leak protection (done, see `reports/retrieval.md`).
4. Agent loop (done, see `reports/agent.md`).
5. Full evaluation.
6. Public demo.
