"""Self-play invariant fuzz test (bounded, deterministic).

Runs the shared invariant fuzzer (scripts/fuzz_invariants.py) over a small
fixed set of games so it executes as part of the normal `pytest` run and
guards against regressions in engine-level invariants -- Rule 5.2
termination, winner recording, turn-freeze, stranded Routed units, VP bounds
(see the module docstring for I1-I7).

CI runs a deeper sweep via the script directly; this keeps the in-suite cost
low. Bump coverage locally with FUZZ_SEEDS, e.g. FUZZ_SEEDS=1-30 pytest -k fuzz.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest

_FUZZ_PATH = Path(__file__).resolve().parent.parent / "scripts" / "fuzz_invariants.py"
_spec = importlib.util.spec_from_file_location("_nevsky_fuzz", str(_FUZZ_PATH))
fuzz = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fuzz)  # type: ignore[union-attr]


def _seeds():
    spec = os.environ.get("FUZZ_SEEDS", "1-2")
    return list(fuzz._parse_seeds(spec))


@pytest.mark.parametrize("scenario", list(fuzz.DEFAULT_SCENARIOS))
@pytest.mark.parametrize("policy", ["priority", "random"])
def test_self_play_invariants(scenario: str, policy: str) -> None:
    for seed in _seeds():
        violation = fuzz.run_game(scenario, seed, policy)
        assert violation is None, violation
