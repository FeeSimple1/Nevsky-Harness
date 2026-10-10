"""Bounded invariant checks must not masquerade as completed games."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "convergence_fuzz", Path(__file__).resolve().parents[1] / "scripts" / "fuzz_invariants.py"
)
fuzz = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fuzz)


def test_step_limit_is_explicit_and_not_completed():
    detail = {}
    assert fuzz.run_game("crusade_on_novgorod", 20261012, max_steps=0, details=detail) is None
    assert detail["stop_reason"] == "step_limit"
    assert detail["completed"] is False
    assert detail["actions"] == 2


def test_default_bounded_sweep_reports_incomplete_cases(tmp_path, capsys):
    report = tmp_path / "report.json"
    assert (
        fuzz.main(
            [
                "--scenarios",
                "pleskau",
                "--seeds",
                "1",
                "--max-steps",
                "0",
                "--report-json",
                str(report),
            ]
        )
        == 0
    )
    data = json.loads(report.read_text())
    assert data["completed"] == 0
    assert data["step_limited"] == 2
    text = capsys.readouterr().out
    assert "0/2 games ended" in text
    assert "games clean on all invariants" not in text


def test_strict_sweep_fails_without_any_completed_game(capsys):
    assert (
        fuzz.main(
            ["--scenarios", "pleskau", "--seeds", "1", "--max-steps", "0", "--require-completion"]
        )
        == 1
    )
    assert "INCOMPLETE" in capsys.readouterr().out


SUITE_SPEC = importlib.util.spec_from_file_location(
    "convergence_suite", Path(__file__).resolve().parents[1] / "scripts" / "convergence_suite.py"
)
suite = importlib.util.module_from_spec(SUITE_SPEC)
SUITE_SPEC.loader.exec_module(suite)


def clean_cases():
    return [
        {
            "seed": 10,
            "policy": policy,
            "terminal": True,
            "last_box": 16,
            "finding_groups": 0,
            "replay_errors": [],
        }
        for policy in suite.POLICIES
    ]


def test_clean_gate_requires_real_completions():
    rows = clean_cases()
    assert suite.evaluate_runs(rows, 3)["clean"]
    rows[0]["terminal"] = False
    assert not suite.evaluate_runs(rows, 2)["clean"]


def test_clean_gate_fails_on_findings_even_with_completed_games():
    rows = clean_cases()
    rows[0]["finding_groups"] = 1
    assert not suite.evaluate_runs(rows, 2)["clean"]


def test_clean_gate_requires_full_span_coverage_and_replay():
    rows = clean_cases()
    rows[0]["last_box"] = 4
    assert not suite.evaluate_runs(rows, 3)["clean"]
    rows[0]["replay_errors"] = ["different final state"]
    assert not suite.evaluate_runs(rows, 2)["clean"]
