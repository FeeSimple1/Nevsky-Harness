"""Round 27: random-action fuzzing. At each step, pick a random legal
action and apply it. Run for N steps with strict invariant checks
between each step. Catches state-machine paths a heuristic agent never
reaches.

Bounded to keep pytest budget reasonable. The fuzzer doesn't try to
finish a scenario; it just hammers the engine with random choices and
verifies invariants hold."""
from __future__ import annotations

import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from _playthrough_round26_multi_seed import check_invariants  # noqa: E402

from nevsky.actions import apply_action, IllegalAction
from nevsky.legal_moves import legal_moves
from nevsky.scenarios import load_scenario


@pytest.mark.parametrize("scenario,seed,steps", [
    ("pleskau", 1, 80),
    ("pleskau", 7, 80),
    ("watland", 1, 80),
    ("peipus", 1, 80),
])
def test_random_action_fuzz_holds_invariants(scenario, seed, steps):
    """Fuzz: random legal action each step. Invariants must never fail."""
    rng = random.Random(seed * 7919)
    s = load_scenario(scenario, seed=seed)
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "russian", "args": {}})
    issues = check_invariants(s, "after setup")
    assert not issues, f"setup invariants failed: {issues}"

    last_seq = -1
    null_iters = 0
    for step_n in range(steps):
        # If we've reached scenario end, stop.
        if s.meta.phase == "campaign" and s.meta.campaign_step == "done":
            break

        moves = legal_moves(s, with_previews=False)
        if not moves:
            null_iters += 1
            if null_iters >= 3:
                break  # nothing to do; legitimate stopping condition
            continue
        null_iters = 0

        # Pick a random legal move. Bias slightly against advance_step
        # (otherwise the fuzzer just runs through phase changes without
        # exercising substep actions).
        non_advance = [m for m in moves if m["type"] != "advance_step"]
        if non_advance and rng.random() < 0.7:
            chosen = rng.choice(non_advance)
        else:
            chosen = rng.choice(moves)

        # Some entries lack 'args' (use args_template fallback). Skip
        # those — fuzzing the unfilled-template path isn't useful here.
        if "args" not in chosen:
            continue

        try:
            apply_action(s, chosen)
        except IllegalAction:
            # Random legal-moves output may include actions that fail at
            # apply time (race conditions in sub-state). Skip and try
            # another move.
            continue
        except Exception as e:
            # Unexpected exception — fail.
            pytest.fail(
                f"step {step_n}: unexpected {type(e).__name__}: {e} "
                f"on action {chosen}"
            )

        # Check invariants after each successful action.
        issues = check_invariants(s, f"step {step_n} action {chosen.get('type')}")
        assert not issues, (
            f"step {step_n} action {chosen.get('type')} {chosen.get('args')} "
            f"violated invariants:\n  " + "\n  ".join(issues)
        )

        # Sequence must be monotonic non-decreasing.
        assert s.meta.sequence >= last_seq, (
            f"sequence regressed: {last_seq} -> {s.meta.sequence}"
        )
        last_seq = s.meta.sequence


def test_random_fuzz_diverse_seeds_no_engine_exception():
    """Five different fuzz seeds — no engine-internal exception should
    surface. IllegalAction is fine (random actions can be invalid in
    some sub-states); other exceptions are bugs."""
    failed = []
    for seed in (11, 22, 33, 44, 55):
        rng = random.Random(seed)
        s = load_scenario("pleskau", seed=seed)
        apply_action(s, {"type": "confirm_all_setup_transports", "side": "teutonic", "args": {}})
        apply_action(s, {"type": "confirm_all_setup_transports", "side": "russian", "args": {}})
        for _ in range(50):
            moves = legal_moves(s, with_previews=False)
            if not moves: break
            chosen = rng.choice(moves)
            if "args" not in chosen: continue
            try:
                apply_action(s, chosen)
            except IllegalAction:
                pass
            except Exception as e:
                failed.append((seed, type(e).__name__, str(e)[:80], chosen.get("type")))
                break
    assert not failed, "Random fuzz raised non-IllegalAction exception(s):\n  " + "\n  ".join(
        f"seed={s}: {tp}: {msg!r} on {act}" for s, tp, msg, act in failed
    )
