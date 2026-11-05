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


def test_readme_numbers_come_from_the_report():
    test = json.loads((ROOT / "reports" / "extraction.json").read_text())["test"]
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for tool in ("poppler", "font_aware"):
        row = test["per_tool"][tool]
        assert f"{row['structure_similarity']:.3f}" in readme
        assert f"{100 * row['exact_share']:.0f}%" in readme
    assert f"{test['scored']} of {test['formulas_sampled']}" in readme
