"""Collect independent jurors' verdicts on held-out attempts, one by one, for comparing voting rules offline.

    PYTHONPATH=src python scripts/run_panel.py --split dev --count 20 --name panel-dev --jurors qwen,20b
    PYTHONPATH=src python scripts/run_panel.py --dataset processbench --name panel-pb --jurors 120b,20b

Results go to data/private/agent_runs/<name>/jurors.jsonl; finished verdicts are skipped, so it is safe to stop.
A juror whose model runs out of quota is skipped for the rest of the run.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from mathhinter.jury import JURORS, ask_juror  # noqa: E402
from mathhinter.llm.client import Client, QuotaExhausted, read_env  # noqa: E402
from run_agent import sample  # noqa: E402

PRIVATE = ROOT / "data/private"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="books", choices=["books", "processbench"])
    parser.add_argument("--split", default="dev")
    parser.add_argument("--count", type=int, default=20)
    parser.add_argument("--name", default="panel-dev")
    parser.add_argument("--jurors", required=True)
    parser.add_argument("--stop-after", type=float, default=0)
    args = parser.parse_args()
    jurors = [JURORS[name] for name in args.jurors.split(",")]
    if args.dataset == "processbench":
        items = json.loads((ROOT / "data/external/processbench/sample.json").read_text(encoding="utf-8"))["items"]
        attempts = [{"exercise": i["id"], "kind": "none" if i["wrong_line"] is None else "error", "text": i["attempt"],
                     "wrong_line": i["wrong_line"]} for i in items]
        units = {i["id"]: {"text": i["problem"]} for i in items}
        exercises = [i["id"] for i in items]
    else:
        attempts = [json.loads(line) for line in
                    (PRIVATE / "attempts.jsonl").read_text(encoding="utf-8").splitlines()]
        units = {json.loads(line)["id"]: json.loads(line)
                 for line in (PRIVATE / "units.jsonl").read_text(encoding="utf-8").splitlines()}
        exercises = sample(attempts, args.split, args.count)
    out = PRIVATE / "agent_runs" / args.name / "jurors.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if out.exists():
        for line in out.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            done.add((row["juror"], row["exercise"], row["kind"]))
    client = Client(read_env(ROOT / ".env")["GROQ_API_KEY"], PRIVATE / "llm_cache")
    exhausted: set[str] = set()
    started = time.time()
    lock = threading.Lock()

    def run(juror, exercise, attempt):
        if juror.model in exhausted:
            return
        try:
            vote = ask_juror(client, juror, units[exercise]["text"], attempt["text"])
        except QuotaExhausted as error:
            print(f"quota: {juror.model} {error}", flush=True)
            exhausted.add(juror.model)
            return
        row = {"exercise": exercise, "kind": attempt["kind"], "wrong_line": attempt["wrong_line"], **vote}
        with lock, out.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(juror.name, exercise, attempt["kind"], vote["verdict"], vote["line"], attempt["wrong_line"],
              vote["tokens"], vote["failure"] or "", flush=True)

    # One worker per model: each model has its own rate limit, so they can run side by side.
    queues: dict[str, list] = {}
    for exercise in exercises:
        for attempt in [a for a in attempts if a["exercise"] == exercise]:
            for juror in jurors:
                if (juror.name, exercise, attempt["kind"]) not in done:
                    queues.setdefault(juror.model, []).append((juror, exercise, attempt))

    def worker(tasks):
        for task in tasks:
            if args.stop_after and time.time() - started > args.stop_after:
                return
            run(*task)

    threads = [threading.Thread(target=worker, args=(tasks,)) for tasks in queues.values()]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    if any(queues.values()) and args.stop_after and time.time() - started > args.stop_after:
        print("PAUSED: time limit, run again to continue", flush=True)
        return
    print("STOPPED: some models out of quota" if exhausted else "FINISHED")


if __name__ == "__main__":
    main()
