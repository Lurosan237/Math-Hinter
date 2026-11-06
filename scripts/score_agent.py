"""Score the reviews in data/private/agent_runs/<name> and write reports/agent.json (numbers only)."""

import argparse
import json
from collections import Counter
from pathlib import Path

from mathhinter.agent.scoring import chance_exact_line, difference_interval, proportion_interval, summarise

PRIVATE = Path("data/private")
CONFIGS = ("llm_only", "rag", "agent", "rag_leak")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", default="test")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    folder = PRIVATE / "agent_runs" / args.name
    rows = [json.loads(line) for line in (folder / "reviews.jsonl").open(encoding="utf-8")]
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    # Only exercises every main configuration finished, so each is compared on the same work.
    needed = {(c, k) for c in ("llm_only", "rag", "agent") for k in (True, False)}
    seen: dict[str, set] = {}
    for row in rows:
        seen.setdefault(row["exercise"], set()).add((row["config"], row["kind"] == "none"))
    complete = {e for e, done in seen.items() if needed <= done}
    rows = [r for r in rows if r["exercise"] in complete]
    report: dict = {"model": manifest["model"], "exercises": len(complete), "sampled": len(manifest["exercises"]),
                    "configs": {}}
    by_config = {c: [r for r in rows if r["config"] == c] for c in CONFIGS}
    for config, part in by_config.items():
        if not part:
            continue
        leak_pairs = {r["exercise"] for r in part}
        report["configs"][config] = {
            **summarise(part), "both_right_ci95": proportion_interval(part), "exercises": len(leak_pairs),
            "tokens_per_review": round(sum(r["tokens"] for r in part) / len(part)),
            "calls_per_review": round(sum(r["llm_calls"] for r in part) / len(part), 2),
            "failures": dict(Counter((r["failure"] or "").split(":")[0] for r in part if r["failure"])),
        }
    if by_config["llm_only"]:
        report["chance_exact_line"] = chance_exact_line(by_config["llm_only"])
        report["rag_minus_llm_only"] = difference_interval(by_config["rag"], by_config["llm_only"])
        report["agent_minus_llm_only"] = difference_interval(by_config["agent"], by_config["llm_only"])
        agent = by_config["agent"]
        shown_ok = [c in r["shown"] for r in agent for c in r["citations"]]
        report["agent_usage"] = {
            "reviews_with_a_citation": sum(bool(r["citations"]) for r in agent),
            "citations": len(shown_ok), "citations_to_passages_shown": sum(shown_ok),
            "searches": sum(c["tool"] == "search_course" for r in agent for c in r["tool_calls"]),
            "equality_checks": sum(c["tool"] == "check_equality" for r in agent for c in r["tool_calls"]),
            "check_outcomes": dict(Counter(c.get("status") for r in agent for c in r["tool_calls"]
                                           if c["tool"] == "check_equality")),
        }
        report["own_solution_shown"] = {c: sum(r["solution"] in r["shown"] for r in by_config[c])
                                        for c in ("rag", "agent", "rag_leak") if by_config[c]}
    print(json.dumps(report, indent=1))
    if args.write:
        Path("reports/agent.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
