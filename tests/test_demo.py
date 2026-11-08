import json
from pathlib import Path

from mathhinter.demo.exo7 import clean, unwrap

ROOT = Path(__file__).resolve().parent.parent


def test_course_macros_become_plain_latex():
    text = clean(r"Soit \defi{$f:\R\to\R$} \og continue\fg{} et $\ch x$\index{x}.")
    assert "\\defi" not in text and "\\mathbb{R}" in text and "«" in text and "\\index" not in text


def test_unwrap_keeps_nested_braces():
    assert unwrap(r"a \myboxinline{$\frac{1}{2}$} b", "myboxinline") == r"a $\frac{1}{2}$ b"


def test_demo_exercises_mark_one_wrong_line_and_a_control():
    exercises = json.loads((ROOT / "data/demo/exercises.json").read_text(encoding="utf-8"))["exercises"]
    for exercise in exercises:
        wrong, control = exercise["attempts"]
        lines = wrong["text"].split("\n")
        assert wrong["kind"] == "wrong" and 0 <= wrong["wrong_line"] < len(lines)
        assert control["kind"] == "control" and control["wrong_line"] is None
        # the two attempts agree before the error
        assert control["text"].split("\n")[:wrong["wrong_line"]] == lines[:wrong["wrong_line"]]


def test_demo_corpus_is_exo7_with_its_licence():
    corpus = json.loads((ROOT / "site/data/corpus.json").read_text(encoding="utf-8"))
    assert "CC BY-NC-SA" in corpus["notice"] or "BY-NC-SA" in corpus["notice"]
    assert all(u["id"].startswith("exo7:") for u in corpus["units"])


def test_site_builds_with_the_checker_and_the_evaluation(tmp_path, monkeypatch):
    import importlib.util
    spec = importlib.util.spec_from_file_location("build_site", ROOT / "scripts/build_site.py")
    build = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build)
    monkeypatch.setattr(build, "OUT", tmp_path / "_site")
    build.main()
    site = tmp_path / "_site"
    for name in ["index.html", "app.js", "data/exercises.json", "data/agent.json", "data/runs.json",
                 "py/mathhinter/check/equality.py"]:
        assert (site / name).exists(), name
