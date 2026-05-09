"""Round 26 regression: a smaller version of the multi-seed sweep
that runs under pytest and fails on any exception or invariant
violation. Catches regressions in long-form play.

The full sweep lives in tests/_playthrough_round26_multi_seed.py
(test fixture, not auto-run). This pytest version uses a small but
non-trivial seed count per scenario to keep the suite under a few
seconds while still exercising state-transition correctness."""
from __future__ import annotations

import pytest

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _playthrough_round26_multi_seed import play  # noqa: E402


@pytest.mark.parametrize("scenario,trials", [
    ("pleskau", 5),
    ("watland", 3),
    ("peipus", 3),
    ("return_of_the_prince", 2),
    ("crusade_on_novgorod", 1),
])
def test_multi_seed_no_exceptions_or_invariant_violations(scenario, trials):
    """Run scenario with `trials` seeds; assert zero exceptions and
    zero invariant violations."""
    results = []
    for seed in range(1, trials + 1):
        r = play(scenario, seed)
        results.append(r)
    exceptions = [r for r in results if r["exception"]]
    violations = [(r["seed"], v) for r in results for v in r["invariant_violations"]]
    assert not exceptions, (
        f"{scenario} had exceptions in {len(exceptions)}/{trials} seeds: "
        + "; ".join(f"seed={r['seed']}: {r['exception'][:120]}" for r in exceptions)
    )
    assert not violations, (
        f"{scenario} had invariant violations: " + "; ".join(
            f"seed={s}: {v}" for s, v in violations[:10]
        )
    )
