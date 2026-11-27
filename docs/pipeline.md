# Check first, judge second

Stage 4 showed that a model left to choose its tools doesn't check anything: the agent searched the course 50 times
and never called the equality checker, and it scored below the model alone. The pipeline fixes the order instead of
asking the model to choose it.

1. **Transcribe.** A model (`qwen/qwen3.8-27b`) turns each line into typed claims: an equality, a derivative, a
   primitive, an integral, a limit, a sum, a solution of equations, a solution of a differential equation, the use
   of a theorem, or "other". It is told to copy the student's mistakes, never to fix them.
2. **Compute.** SymPy checks every claim it can (`src/mathhinter/pipeline/claims.py`): vérifié, réfuté or non
   vérifiable. Nothing is evaluated with `eval`, and anything that may depend on context stays non vérifiable.
3. **Judge.** The reviewer (`openai/gpt-oss-120b`) gets the same instructions as the evaluated "LLM alone"
   reviewer, plus the computations and the course statement of any theorem the student uses.
4. **Second opinion.** When the judge flags a line, another model checks that claim alone; if it rejects it, the
   flag is withdrawn.

On the site, lines whose calculations were redone get a ✓, the flagged line a ✗, and the student can correct the
line and recheck, talk it through ("Explique-moi"), practise a similar exercise whose answer the computer has
verified, and keep a notebook of their mistakes on their device.

## Development results

20 development exercises (not the test set), each with a wrong attempt and a correct one. Exploratory: these
guided the design, so they are not an estimate of performance.

| Version | Fully right | Right line found | False alarms on correct copies |
|---|---|---|---|
| Model alone | 3 | 9 | 10 |
| Pipeline | 5 | 8 | 8 |
| Pipeline + second opinion | 6 | 6 | 0 |

On these textbook solutions, extracted from PDFs, the computer verified 13 of 75 claims and refuted none: most
claims were unreadable (absolute values, words inside formulas) or depended on earlier lines. The gain came from
the second opinion, which removed every false alarm and two true detections. Clean typed or photographed student
work should give the computation more to check; the real-photo evaluation will tell.

## Test result

One run of the frozen pipeline on the 25 test exercises ([report](../reports/pipeline.md)): both right 0.32,
against 0.52 for the model alone (difference -0.20, 95% CI -0.44 to 0.00). False alarms fell from 0.20 to 0.04, but
the exact line was found only 0.32 of the time, against 0.68.

The second opinion caused it: it withdrew 10 flags that were the planted error and 6 that were false alarms. Read
after the fact, the judge alone scores the same as the model alone, so the computations gave it nothing to work with
on these textbook solutions (8 claims verified, 1 refuted, out of 156). The second opinion, tuned on 20 development
exercises where it removed every false alarm, did not carry over.

What this means for the site: "Vérifiée" trades missed errors for far fewer false alarms. Doubtful lines that the
second opinion withdrew are still shown to the student as a doubt to check, not as an error.
