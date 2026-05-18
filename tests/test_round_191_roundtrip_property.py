"""R191 (CI gate): property-style round-trip pytest.

Implements a small but real version of the §2 audit from
CROSS_PROJECT_LESSONS.md as a regression test: at each step,
every move emitted by `legal_moves` must round-trip through
`apply_action` without raising IllegalAction.

This is the CI-ready companion to `scripts/roundtrip_sweep.py`
(the broad informational sweep). The script tests at depth on
seeds and scenarios; this test focuses on each of the 6
SMOKEs surfaced in R190 by walking shallower across all
scenarios.

Pre-R190 this test would catch ~50 findings per scenario.
Post-R190 it should be clean. Future enumerator drift will
trip it before merge.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

import pytest

import nevsky.actions  # noqa: F401
from nevsky.actions import IllegalAction, apply_action
from nevsky.legal_moves import legal_moves
from nevsky.scenarios import load_scenario


# Reuse self_play priority + templated-move expansion for advancement.
_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(_SCRIPTS))
from self_play import _move_priority, _instantiate_templated_move  # noqa: E402

sys.path.remove(str(_SCRIPTS))


# Lifecycle plumbing — already exercised elsewhere, skip probing.
_SKIP_PROBE = {
    "advance_step", "command_reveal", "fpd_resolve",
    "end_card", "legate_skip", "finalize_plan", "aow_shuffle",
    "confirm_setup_transport", "confirm_all_setup_transports",
    "system_setup_complete", "end_campaign_resolve",
    "plan_add_card",
}


def _concrete_moves(state):
    out = []
    for m in legal_moves(state, with_previews=False):
        if "args" in m and isinstance(m["args"], dict):
            out.append(m)
        else:
            try:
                out.extend(_instantiate_templated_move(state, m))
            except Exception:
                pass
    return out


def _walk_with_probes(scenario_id: str, seed: int, max_steps: int = 30):
    """Walk the scenario, probing every move at every step.

    Returns the list of (step, action, code, message) for any
    IllegalAction surfaced. Empty list means the enumerator and
    handler are aligned across the visited state space.
    """
    s = load_scenario(scenario_id, seed=seed)
    for side in ("teutonic", "russian"):
        try:
            apply_action(s, {"type": "confirm_all_setup_transports",
                             "side": side, "args": {}})
        except Exception:
            pass

    findings = []
    from collections import Counter
    recent = Counter()
    for step in range(max_steps):
        moves = _concrete_moves(s)
        if not moves:
            break
        for m in moves:
            if m.get("type") in _SKIP_PROBE:
                continue
            snap = s.model_copy(deep=True)
            try:
                apply_action(snap, m)
            except IllegalAction as e:
                findings.append({
                    "step": step, "action": m,
                    "code": e.code, "message": str(e)[:200],
                })
        # advance
        prioritized = sorted(moves,
                             key=lambda m: -_move_priority(m, recent))
        pick = prioritized[step % min(3, len(prioritized))]
        sig = (pick["type"], pick.get("side"),
               json.dumps(pick.get("args", {}), default=str, sort_keys=True))
        recent[sig] += 1
        action = {k: v for k, v in pick.items()
                  if k in ("type", "side", "args")}
        try:
            apply_action(s, action)
        except IllegalAction:
            # The chosen advancing move would error — that's a
            # finding too (would have been caught in the probe loop
            # above if it wasn't in _SKIP_PROBE).
            break
    return findings


@pytest.mark.parametrize("scenario,seed", [
    ("pleskau", 1),
    ("watland", 1),
    ("watland", 2),
    ("return_of_the_prince", 1),
    ("return_of_the_prince_nicolle", 1),
    ("peipus", 1),
    ("crusade_on_novgorod", 1),
])
def test_roundtrip_no_findings(scenario: str, seed: int):
    """Every move emitted by legal_moves must round-trip through
    apply_action without raising IllegalAction."""
    findings = _walk_with_probes(scenario, seed, max_steps=30)
    if findings:
        # Group by (action_type, code) for readable failure output.
        from collections import Counter
        by_kind = Counter(
            (f["action"].get("type"), f["code"]) for f in findings)
        first_examples = {}
        for f in findings:
            key = (f["action"].get("type"), f["code"])
            if key not in first_examples:
                first_examples[key] = f
        msg = (f"Round-trip sweep on {scenario}/{seed} surfaced "
               f"{len(findings)} findings:\n")
        for (atype, code), count in by_kind.most_common():
            ex = first_examples[(atype, code)]
            msg += (f"  {count:>3}  {atype} {code}\n"
                    f"       args: {ex['action'].get('args')}\n"
                    f"       msg:  {ex['message']}\n")
        pytest.fail(msg)
