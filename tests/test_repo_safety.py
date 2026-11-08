"""The source books are licensed. Nothing derived from them may enter the repository."""

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent.parent


def tracked() -> list[str]:
    return subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.splitlines()


def test_only_the_test_fixture_pdf_is_tracked():
    assert [f for f in tracked() if f.lower().endswith(".pdf")] == ["tests/fixtures/formulas.pdf"]


def test_private_folder_is_empty_in_git():
    assert [f for f in tracked() if f.startswith("data/private/")] == ["data/private/.gitkeep"]


def test_report_holds_numbers_not_formulas():
    report = (ROOT / "reports" / "extraction.json").read_text()
    assert "\\" not in report
    assert "latex" not in json.loads(report)["test"]


def test_corpus_report_has_no_book_text():
    report = json.loads((ROOT / "reports" / "corpus.json").read_text())
    assert set(report) == {"volumes", "references", "hand_check", "totals"}


def test_hand_checks_hold_ids_not_text():
    checks = json.loads((ROOT / "data" / "hand_checks" / "structure.json").read_text())
    assert set(checks["links"][0]) == {"source", "target", "correct"}
    assert set(checks["exercise_solution_pairs"][0]) == {"exercise", "paired_correctly", "solution_ends_cleanly"}


def test_readme_corpus_numbers_come_from_the_report():
    report = json.loads((ROOT / "reports" / "corpus.json").read_text())
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert f"{report['totals']['exercise_solution_pairs']} exercises paired" in readme
    assert f"{report['references']['linked']} links between results" in readme
    assert f"{report['references']['across_volumes']} of those links cross" in readme


def test_readme_retrieval_numbers_come_from_the_report():
    report = json.loads((ROOT / "reports" / "retrieval.json").read_text())
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert f"{report['questions']} test questions" in readme
    best = report["all"]["bm25_titles_plus_nearby"]
    assert f"{best['recall_5']:.3f} | {best['recall_10']:.3f} | {best['mrr']:.3f}" in readme


def test_retrieval_reports_have_no_book_text():
    assert "$" not in (ROOT / "reports" / "retrieval.json").read_text()
    links = json.loads((ROOT / "data" / "hand_checks" / "crosslinks.json").read_text())["links"]
    assert set(links[0]) == {"method", "source", "target", "uses_the_concept"}


def test_readme_checker_numbers_come_from_the_report():
    report = json.loads((ROOT / "reports" / "checker.json").read_text())
    judged = json.loads((ROOT / "data" / "hand_checks" / "checker.json").read_text())
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert f"| vérifié | {report['book_equalities']['vérifié']} |" in readme
    assert f"| réfuté | {report['book_equalities']['réfuté']} |" in readme
    assert f"{judged['sound']} of {judged['verified']} were sound" in readme


def test_evalset_report_has_no_book_text():
    report = (ROOT / "reports" / "evalset.json").read_text()
    assert "$" not in report and "Solution" not in report
    assert "$" not in (ROOT / "data" / "hand_checks" / "evalset.json").read_text()
    assert "\\\\" not in (ROOT / "reports" / "checker.json").read_text()


def test_readme_agent_numbers_come_from_the_report():
    report = json.loads((ROOT / "reports" / "agent.json").read_text())
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for key, label in (("llm_only", "LLM alone"), ("rag", "RAG"), ("agent", "Agent")):
        row = report["configs"][key]
        low, high = row["both_right_ci95"]
        assert f"| {label} | {row['both_right']:.2f} ({low:.2f}-{high:.2f}) | {row['exact_line']:.2f} |" in readme
    assert f"same {report['exercises']} held-out exercises" in readme


def test_agent_hand_checks_hold_ids_not_text():
    hand = json.loads((ROOT / "data" / "hand_checks" / "agent.json").read_text())
    assert set(hand["hints"][0]) == {"config", "exercise", "kind", "points_at_the_error", "nearly_gives_the_answer",
                                     "states_the_correction"}
    assert "$" not in (ROOT / "reports" / "agent.json").read_text()


def test_readme_numbers_come_from_the_report():
    test = json.loads((ROOT / "reports" / "extraction.json").read_text())["test"]
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for tool in ("poppler", "font_aware"):
        row = test["per_tool"][tool]
        assert f"{row['structure_similarity']:.3f}" in readme
        assert f"{100 * row['exact_share']:.0f}%" in readme
    assert f"{test['scored']} of {test['formulas_sampled']}" in readme
