"""Run the three tutor configurations on the public demo exercises and record them for the demo page.

The course is the Exo7 corpus in site/data/corpus.json and the exercises are data/demo/exercises.json, both public.
Finished runs are kept in site/data/runs.json and skipped next time, so the script is safe to stop.
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from mathhinter.agent.course import CourseSearch  # noqa: E402
from mathhinter.agent.tutor import Tutor  # noqa: E402
from mathhinter.llm.client import Client, QuotaExhausted, read_env  # noqa: E402

CONFIGS = ("llm_only", "rag", "agent")
OUT = ROOT / "site" / "data" / "runs.json"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="openai/gpt-oss-120b")
    parser.add_argument("--limit", type=int, default=99, help="stop after this many new reviews")
    args = parser.parse_args()
    units = json.loads((ROOT / "site/data/corpus.json").read_text(encoding="utf-8"))["units"]
    exercises = json.loads((ROOT / "data/demo/exercises.json").read_text(encoding="utf-8"))["exercises"]
    runs = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {"model": args.model, "reviews": []}
    done = {(r["exercise"], r["attempt"], r["config"]) for r in runs["reviews"]}
    client = Client(read_env(ROOT / ".env")["GROQ_API_KEY"], ROOT / "data/private/llm_cache")
    tutor = Tutor(client, args.model, CourseSearch(units))
    new = 0
    for exercise in exercises:
        for attempt in exercise["attempts"]:
            for config in CONFIGS:
                key = (exercise["id"], attempt["kind"], config)
                if key in done or new >= args.limit:
                    continue
                statement, text, ident = exercise["statement"], attempt["text"], exercise["id"]
                try:
                    if config == "llm_only":
                        review = tutor.llm_only(statement, text)
                    elif config == "rag":
                        review = tutor.rag(statement, text, ident, solution="")
                    else:
                        review = tutor.agent(statement, text, ident, solution="")
                except QuotaExhausted as error:
                    print(f"quota reached, stopping: {error}")
                    OUT.write_text(json.dumps(runs, ensure_ascii=False, indent=1), encoding="utf-8")
                    return
                runs["reviews"].append({"exercise": ident, "attempt": attempt["kind"], **review.record()})
                new += 1
                print(ident, attempt["kind"], config, review.verdict, review.first_wrong_line, review.failure)
                OUT.write_text(json.dumps(runs, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
