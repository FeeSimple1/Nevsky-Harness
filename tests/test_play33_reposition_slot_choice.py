"""PLAY-33 regression tests: 4.4.2 Reposition Advance slot choice.

Rule 4.4.2 REPOSITION: "Advance Lords. Attacker then Defender slide any
Unrouted Lords in Reserve into ANY empty Front positions (one each)."

Before PLAY-33 the engine iterated empty slots left-to-right and a lone
Reserve Lord was forced into the LEFTMOST empty slot with no choice.
When empty Front slots outnumber the Reserves, which slot each advancing
Lord takes is the owner's choice: a `reserve_advance_slot` decision.
When Reserves >= empty slots every slot fills, so the existing per-slot
which-Lord decision already reaches every pairing (protocol unchanged).
The leftmost fallback preserves pre-PLAY-33 behavior for non-scripted
play.
"""
from __future__ import annotations

import nevsky.actions  # noqa: F401  (import order: actions before campaign/battle)
from nevsky.battle import (
    BattleDecisionContext,
    _remove_routed_from_array,
    _reposition,
)
from nevsky.scenarios import load_scenario


def _three_teutons(s):
    return [lid for lid, l in s.lords.items()
            if l.side == "teutonic" and l.state == "mustered"][:3]


def test_lone_reserve_chooses_slot_when_slots_outnumber_reserves():
    """1 Reserve, 2 open slots (center occupied): the owner picks RIGHT,
    which the old leftmost-forced code could never produce."""
    s = load_scenario("crusade_on_novgorod", seed=1)
    a, b, c = _three_teutons(s)
    positions = {a: "center", b: "left", c: "reserve"}
    s.lords[b].forces = {}  # Rout the left Lord.
    _remove_routed_from_array(s, positions)
    assert positions[b] == "routed"

    ctx = BattleDecisionContext(scripted=[
        {"type": "reserve_advance_slot", "chosen": "right"},
    ])
    res = _reposition(s, positions, "attacker", ctx)
    assert positions[c] == "right"
    assert positions[a] == "center"  # center occupied: no center-fill drag
    assert {"step": "advance", "lord": c, "to": "right"} in res["moves"]
    # The slot decision was logged with the open slots as options.
    slot_entries = [e for e in ctx.log if e["type"] == "reserve_advance_slot"]
    assert len(slot_entries) == 1
    assert slot_entries[0]["options"] == ["left", "right"]


def test_lone_reserve_fallback_keeps_leftmost():
    """No script: fallback advances the lone Reserve to the leftmost open
    slot (pre-PLAY-33 behavior preserved)."""
    s = load_scenario("crusade_on_novgorod", seed=1)
    a, b, c = _three_teutons(s)
    positions = {a: "center", b: "left", c: "reserve"}
    s.lords[b].forces = {}
    _remove_routed_from_array(s, positions)

    ctx = BattleDecisionContext()
    _reposition(s, positions, "attacker", ctx)
    assert positions[c] == "left"


def test_two_reserves_three_open_slots_full_choice():
    """2 Reserves, 3 open slots: which Lord AND which slot are both
    choices; left may deliberately stay empty. (Center-fill then does
    not fire because center is taken directly.)"""
    s = load_scenario("crusade_on_novgorod", seed=1)
    a, b, c = _three_teutons(s)
    positions = {a: "reserve", b: "reserve", c: "left"}
    s.lords[c].forces = {}  # Rout the only Front Lord -> all 3 slots open.
    _remove_routed_from_array(s, positions)

    ctx = BattleDecisionContext(scripted=[
        {"type": "reserve_advance", "chosen": b},
        {"type": "reserve_advance_slot", "chosen": "right"},
        # Second advance: lone remaining Reserve (a) -- no which-Lord
        # decision; slot choice among the two still-open slots.
        {"type": "reserve_advance_slot", "chosen": "center"},
    ])
    _reposition(s, positions, "attacker", ctx)
    assert positions[b] == "right"
    assert positions[a] == "center"
    # Left deliberately left empty; nobody was dragged there.
    assert "left" not in (positions[a], positions[b])


def test_reserves_at_least_slots_keeps_per_slot_protocol():
    """2 Reserves, 2 open slots: no reserve_advance_slot decision is
    asked (every slot fills; which-Lord-per-slot reaches all pairings)."""
    s = load_scenario("crusade_on_novgorod", seed=1)
    a, b, c = _three_teutons(s)
    positions = {a: "center", b: "reserve", c: "reserve"}

    ctx = BattleDecisionContext(scripted=[
        {"type": "reserve_advance", "chosen": c},  # c takes left
    ])
    _reposition(s, positions, "attacker", ctx)
    assert positions[c] == "left"
    assert positions[b] == "right"  # forced: last Reserve, last slot
    assert not any(e["type"] == "reserve_advance_slot" for e in ctx.log)
