"""Run the tutor configurations on held-out attempts. Safe to stop: finished reviews are kept and skipped next time."""

import argparse
import json
import pickle
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from mathhinter.agent.course import CourseSearch  # noqa: E402
from mathhinter.agent.tutor import Tutor  # noqa: E402
from mathhinter.llm.client import Client, QuotaExhausted, read_env  # noqa: E402

PRIVATE = ROOT / "data" / "private"
MAX_ATTEMPT_CHARS = 2500
CONFIGS = ("llm_only", "rag", "rag_leak", "agent")
SAMPLE_SEED = 77
LEAK_EXERCISES = 10  # the leak check costs quota and needs fewer exercises


def sample(attempts: list[dict], split: str, count: int) -> list[str]:
    """Exercises with both a wrong attempt and a control, short enough to fit the free per-minute limit."""
    kinds: dict[str, set] = {}
    for attempt in attempts:
        if attempt["split"] == split and len(attempt["text"]) <= MAX_ATTEMPT_CHARS:
            kinds.setdefault(attempt["exercise"], set()).add(attempt["kind"] == "none")
    usable = sorted(e for e, seen in kinds.items() if seen == {True, False})
    random.Random(SAMPLE_SEED).shuffle(usable)
    return usable[:count]


def load_course(units: list[dict]) -> CourseSearch:
    """Building the search index takes about a minute on a small machine, so it's kept between runs."""
    path = PRIVATE / "course_index.pkl"
    if path.exists():
        with path.open("rb") as handle:
            return pickle.load(handle)
    course = CourseSearch(units)
    with path.open("wb") as handle:
        pickle.dump(course, handle)
    return course


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", default="dev", choices=["dev", "test"])
    parser.add_argument("--count", type=int, default=4)
    parser.add_argument("--model", default="openai/gpt-oss-120b")
    parser.add_argument("--name", default="dev")
    args = parser.parse_args()
    units = {}
    for line in (PRIVATE / "units.jsonl").open(encoding="utf-8"):
        unit = json.loads(line)
        units[unit["id"]] = unit
    attempts = [json.loads(line) for line in (PRIVATE / "attempts.jsonl").open(encoding="utf-8")]
    chosen = sample(attempts, args.split, args.count)
    work = [a for e in chosen for a in attempts if a["exercise"] == e]
    print(f"{len(chosen)} exercises, {len(work)} attempts", flush=True)
    key = read_env(ROOT / ".env")["GROQ_API_KEY"]
    client = Client(key, cache_dir=PRIVATE / "llm_cache")
    tutor = Tutor(client, args.model, load_course(list(units.values())))
    out_dir = PRIVATE / "agent_runs" / args.name
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "manifest.json").write_text(json.dumps({"exercises": chosen, "model": args.model}), encoding="utf-8")
    path = out_dir / "reviews.jsonl"
    done = set()
    if path.exists():
        for line in path.open(encoding="utf-8"):
            row = json.loads(line)
            done.add((row["config"], row["exercise"], row["kind"]))
    with path.open("a", encoding="utf-8") as out:
        for attempt in work:
            statement = units[attempt["exercise"]]["text"]
            for config in CONFIGS:
                if (config, attempt["exercise"], attempt["kind"]) in done:
                    continue
                if config == "rag_leak" and attempt["exercise"] not in chosen[:LEAK_EXERCISES]:
                    continue
                exercise, solution, text = attempt["exercise"], attempt["solution"], attempt["text"]
                try:
                    if config == "llm_only":
                        review = tutor.llm_only(statement, text)
                    elif config == "rag":
                        review = tutor.rag(statement, text, exercise, solution)
                    elif config == "rag_leak":
                        review = tutor.rag_leak(statement, text, exercise)
                    else:
                        review = tutor.agent(statement, text, exercise, solution)
                except QuotaExhausted as error:
                    print(f"STOPPED: {error}", flush=True)
                    return
                row = {**review.record(), "exercise": exercise, "solution": solution, "kind": attempt["kind"],
                       "wrong_line": attempt["wrong_line"], "lines": text.count("\n") + 1,
                       "at": time.strftime("%H:%M:%S")}
                out.write(json.dumps(row, ensure_ascii=False) + "\n")
                out.flush()
                print(config, exercise, attempt["kind"], review.verdict, review.first_wrong_line,
                      attempt["wrong_line"], review.tokens, review.failure or "", flush=True)
    print("FINISHED", flush=True)


if __name__ == "__main__":
    main()
