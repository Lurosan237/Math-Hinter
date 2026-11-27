"""Download ProcessBench (Qwen, Apache-2.0) at a pinned version and draw the sample used to compare reviewer designs.

    python scripts/get_processbench.py

Writes data/external/processbench/sample.json: 20 items from each source (GSM8K, MATH, OlympiadBench, Omni-MATH),
half with a labelled first error and half without. ProcessBench: Zheng et al., "ProcessBench: Identifying Process
Errors in Mathematical Reasoning", ACL 2025, https://huggingface.co/datasets/Qwen/ProcessBench.
"""

from __future__ import annotations

import json
import random
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FOLDER = ROOT / "data/external/processbench"
REVISION = "3bdcd5371ed567559a78f559c01c13a6deee7604"
SOURCES = ("gsm8k", "math", "olympiadbench", "omnimath")
PER_SOURCE = 20
SEED = 2412


def download() -> None:
    FOLDER.mkdir(parents=True, exist_ok=True)
    for name in SOURCES:
        target = FOLDER / f"{name}.json"
        if not target.exists():
            url = f"https://huggingface.co/datasets/Qwen/ProcessBench/resolve/{REVISION}/{name}.json"
            with urllib.request.urlopen(url, timeout=120) as response:
                target.write_bytes(response.read())


def draw() -> list[dict]:
    rng = random.Random(SEED)
    chosen = []
    for name in SOURCES:
        items = json.loads((FOLDER / f"{name}.json").read_text(encoding="utf-8"))
        with_error = [i for i in items if i["label"] >= 0]
        without = [i for i in items if i["label"] < 0]
        for item in rng.sample(with_error, PER_SOURCE // 2) + rng.sample(without, PER_SOURCE // 2):
            # One step per line, as the tutor numbers lines; steps keep their own words.
            steps = [" ".join(step.split()) for step in item["steps"]]
            chosen.append({"id": f"pb:{item['id']}", "source": name, "problem": item["problem"],
                           "attempt": "\n".join(steps), "wrong_line": item["label"] if item["label"] >= 0 else None})
    return chosen


def main() -> None:
    download()
    sample = draw()
    (FOLDER / "sample.json").write_text(json.dumps({"revision": REVISION, "license": "Apache-2.0", "seed": SEED,
                                                     "items": sample}, ensure_ascii=False, indent=1),
                                        encoding="utf-8")
    print(len(sample), "items:", sum(i["wrong_line"] is not None for i in sample), "with an error")


if __name__ == "__main__":
    main()
