"""Run the night's jobs in order, each to the end, waiting whenever Groq's free quota runs out.

    python scripts/night.py

1. Rebuild the textbook solutions step by step (scripts/rebuild_bench.py rebuild), then plant the errors.
2. ProcessBench sample: every juror's verdict (scripts/run_panel.py).
3. The rebuilt development exercises: every juror's verdict.
Everything is resumable: stop the window whenever, run it again later.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JURORS = "120b,120b-high,20b,qwen-low,120b-s1,120b-s2"
JOBS = [
    ("Rebuild solutions step by step", ["scripts/rebuild_bench.py", "rebuild"]),
    ("Plant errors in the rebuilt solutions", ["scripts/rebuild_bench.py", "plant"]),
    ("ProcessBench jury", ["scripts/run_panel.py", "--dataset", "processbench", "--name", "panel-pb",
                           "--jurors", JURORS]),
    ("Clean development set jury", ["scripts/run_panel.py", "--dataset", "clean", "--split", "dev",
                                    "--name", "panel-clean-dev", "--jurors", JURORS]),
]
DEFAULT_WAIT = 600


def run(arguments: list[str]) -> str:
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "PYTHONIOENCODING": "utf-8"}
    process = subprocess.Popen([sys.executable, "-u", *arguments], cwd=ROOT, env=env, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
    lines = []
    for line in process.stdout:
        lines.append(line)
        print("   ", line.rstrip(), flush=True)
    process.wait()
    return "".join(lines)


def main() -> None:
    for title, arguments in JOBS:
        print(f"== {title}", flush=True)
        while True:
            output = run(arguments)
            if "FINISHED" in output or "exercises with a planted error" in output:
                break
            waits = [int(s) for s in re.findall(r"try again in (\d+)s", output)]
            if "STOPPED" not in output and not waits:
                print(output[-1500:])
                sys.exit(f"'{title}' failed for another reason; see above.")
            wait = min(max(min(waits) + 30, 120), 3600) if waits else DEFAULT_WAIT
            print(f"[{time.strftime('%H:%M')}] Groq quota reached: waiting {wait // 60} min, then continuing.",
                  flush=True)
            time.sleep(wait)
    print("All done. Tell Claude: the night's results are ready.")


if __name__ == "__main__":
    main()
