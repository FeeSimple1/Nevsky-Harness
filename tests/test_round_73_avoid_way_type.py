"""SMOKE-068 (Round 73): Avoid Battle must respect agent-specified
args.way_type when src<->dest has parallel Ways.

The 4.3.4 restriction "may not Avoid across the Way the enemy used to
Approach" applies per Way, not per Locale-pair. For parallel Ways
(dorpat<->odenpah has trackway + waterway), the defender retains the
parallel Way as a legal Avoid Way even when the attacker approached
via the other Way. Previously _h_avoid_battle picked the first Way via
_way_type_between, which blocked the defender from picking the
non-approach Way.
"""
from __future__ import annotations

import pytest

import nevsky.actions  # noqa: F401
from nevsky.actions import IllegalAction, apply_action
from nevsky.scenarios import load_scenario
from nevsky.state import CombatPending


def _setup_combat(state, attacker_from, defender_at, way_type):
    """Stage Russian attacker into Teutonic defender at dorpat.

    Russian (yaroslav) approached dorpat from odenpah (in the test
    scenario yaroslav is at attacker_from = odenpah pre-move; for the
    Avoid path we model the combat as if yaroslav has Marched into
    dorpat). Teutonic defender hermann at dorpat may Avoid to odenpah
    (own friendly castle) provided the chosen Way is NOT the approach
    Way.
    """
    h = state.lords["hermann"]
    h.state = "mustered"
    h.location = defender_at  # defender at to_locale
    y = state.lords["yaroslav"]
    y.state = "mustered"
    y.location = defender_at  # attacker has moved in
    y.assets = {"boat": 2, "cart": 2}
    state.combat_pending = CombatPending(
        attacker_side="russian",
        attacker_group=["yaroslav"],
        from_locale=attacker_from,
        to_locale=defender_at,
        way_type=way_type,
        defender_side="teutonic",
        defender_lords=["hermann"],
        pending_response_by="teutonic",
        laden=False,
    )


def test_avoid_block_back_along_approach_way_no_arg():
    """Without args.way_type: legacy behavior — Avoid back to
    attacker source via the approach Way is blocked."""
    s = load_scenario("crusade_on_novgorod", seed=1)
    _setup_combat(s, "odenpah", "dorpat", "trackway")
    with pytest.raises(IllegalAction) as e:
        apply_action(s, {"type": "avoid_battle", "side": "teutonic",
                          "args": {"to": "odenpah"}})
    assert e.value.code == "approach_way_blocked"


def test_avoid_allowed_via_parallel_way():
    """With args.way_type=waterway: Teutonic defender Avoids back to
    odenpah (own Castle) via the parallel waterway Way (Russian
    attacker came via trackway)."""
    s = load_scenario("crusade_on_novgorod", seed=1)
    _setup_combat(s, "odenpah", "dorpat", "trackway")
    r = apply_action(s, {"type": "avoid_battle", "side": "teutonic",
                          "args": {"to": "odenpah", "way_type": "waterway"}})
    assert s.lords["hermann"].location == "odenpah"


def test_avoid_rejects_bad_way_type():
    """args.way_type not among Ways between src/dest → bad_way_type."""
    s = load_scenario("crusade_on_novgorod", seed=1)
    _setup_combat(s, "odenpah", "dorpat", "trackway")
    with pytest.raises(IllegalAction) as e:
        apply_action(s, {"type": "avoid_battle", "side": "teutonic",
                          "args": {"to": "odenpah", "way_type": "sea"}})
    assert e.value.code == "bad_way_type"


def test_avoid_blocks_when_explicit_way_matches_approach():
    """args.way_type explicitly matches the attacker's approach Way —
    still blocked."""
    s = load_scenario("crusade_on_novgorod", seed=1)
    _setup_combat(s, "odenpah", "dorpat", "trackway")
    with pytest.raises(IllegalAction) as e:
        apply_action(s, {"type": "avoid_battle", "side": "teutonic",
                          "args": {"to": "odenpah", "way_type": "trackway"}})
    assert e.value.code == "approach_way_blocked"
