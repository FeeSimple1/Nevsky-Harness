"""Bounded subsystem fuzz tests (deterministic).

Runs small slices of the targeted subsystem fuzzers (scripts/fuzz_subsystems.py)
inside the normal pytest run so regressions in combat resolution, Arts-of-War
event handling, or the Veche are caught without a separate CI step. CI runs a
deeper sweep via the script directly. Scale locally with FUZZ_SEEDS.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

_PATH = Path(__file__).resolve().parent.parent / "scripts" / "fuzz_subsystems.py"
_spec = importlib.util.spec_from_file_location("_nevsky_fuzz_subsystems", str(_PATH))
fs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fs)  # type: ignore[union-attr]


def _seeds(default="1-2"):
    return list(fs._fi._parse_seeds(os.environ.get("FUZZ_SEEDS", default)))


def test_combat_invariants():
    issues = fs.fuzz_combat(iters=150)
    assert not issues, "\n".join(issues[:20])


def test_arts_of_war_event_invariants():
    # Every Event card (T1-T18, R1-R18) implemented populated + bare.
    issues = fs.fuzz_aow_events(seeds=_seeds("1-2"))
    assert not issues, "\n".join(issues[:20])


def test_veche_invariants():
    issues = fs.fuzz_veche(seeds=_seeds("1-3"))
    assert not issues, "\n".join(issues[:20])
