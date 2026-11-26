"""Run an evaluation to the end, however long Groq's limits make it: wait when a quota runs out, then carry on.

    python scripts/overnight.py --split test --count 25 --name pipeline-test --configs pipeline

Finished reviews are kept in data/private/agent_runs/<name>/reviews.jsonl, so stopping and starting again is safe.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WAIT_DEFAULT = 600


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", default="test")
    parser.add_argument("--count", default="25")
    parser.add_argument("--name", required=True)
    parser.add_argument("--configs", default="pipeline")
    args = parser.parse_args()
    command = [sys.executable, str(ROOT / "scripts/run_agent.py"), "--split", args.split, "--count", args.count,
               "--name", args.name, "--configs", args.configs]
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "PYTHONIOENCODING": "utf-8"}
    while True:
        started = time.strftime("%H:%M")
        result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8")
        output = result.stdout + result.stderr
        done = sum(1 for line in output.splitlines() if line.split(" ")[0] in args.configs.split(","))
        print(f"[{started}] {done} reviews done this round", flush=True)
        if "FINISHED" in output:
            print("All done. Results:", ROOT / "data/private/agent_runs" / args.name / "reviews.jsonl")
            return
        if "STOPPED" not in output:
            print(output[-2000:])
            sys.exit("The run failed for another reason; see above.")
        found = re.search(r"try again in (\d+)s", output)
        wait = min(int(found[1]) + 30, 3600) if found else WAIT_DEFAULT
        print(f"Groq limit reached: waiting {wait // 60} min, then continuing.", flush=True)
        time.sleep(wait)


if __name__ == "__main__":
    main()
