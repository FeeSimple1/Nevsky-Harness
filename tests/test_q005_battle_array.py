"""Q-005 regression tests: 2E Battle Array (three Front positions),
Reposition, Flanking, scripted_decisions protocol.

All tests pin operator decisions via BattleDecisionContext(scripted=...)
or rely on the deterministic leftmost-fallback. No live randomness in
operator choices.
"""

from __future__ import annotations

import pytest

from nevsky.battle import (
    BattleDecisionContext,
    _init_battle_array,
    _remove_routed_from_array,
    _reposition,
    _strike_target,
    resolve_battle,
)
from nevsky.scenarios import load_scenario


# ---------------------------------------------------------------------------
# Init Array
# ---------------------------------------------------------------------------


def test_q005_active_attacker_at_front_center() -> None:
    """4.4.1: 'The Active Lord must start at Front center.'"""
    s = load_scenario("watland", seed=1)
    teus = [lid for lid, l in s.lords.items()
            if l.side == "teutonic" and l.state == "mustered"]
    rus = [lid for lid, l in s.lords.items()
           if l.side == "russian" and l.state == "mustered"]
    active = teus[0]
    ctx = BattleDecisionContext()
    atk_pos, def_pos = _init_battle_array(s, teus, rus, active, ctx)
    assert atk_pos[active] == "center"


def test_q005_attacker_one_extra_lord_left_or_right() -> None:
    """4.4.1: Attacker with 1 non-Active Lord places that Lord at Front
    left OR right (operator decision)."""
    s = load_scenario("watland", seed=1)
    teus = [lid for lid, l in s.lords.items()
            if l.side == "teutonic" and l.state == "mustered"]
    rus = [lid for lid, l in s.lords.items()
           if l.side == "russian" and l.state == "mustered"]
    # Force exactly two Teutons.
    teus = teus[:2]
    active = teus[0]
    extra = teus[1]
    # Scripted: pick "right" for the extra Lord.
    ctx = BattleDecisionContext(scripted=[
        {"type": "initial_placement_attacker", "chosen": "right",
         "rationale": "test pick"},
    ])
    atk_pos, def_pos = _init_battle_array(s, teus, rus, active, ctx)
    assert atk_pos[active] == "center"
    assert atk_pos[extra] == "right"


def test_q005_defender_fills_center_first_then_left_then_right() -> None:
    """4.4.1: 'The Defender must put one Lord directly opposite each
    Front Attacking Lord, first in the center, then left and/or right.'"""
    s = load_scenario("watland", seed=1)
    # Attackers at all three Front slots.
    teus = [lid for lid, l in s.lords.items()
            if l.side == "teutonic" and l.state == "mustered"][:3]
    # Russian side: force 2 mustered defenders so we can verify center+left.
    rus = [lid for lid, l in s.lords.items() if l.side == "russian"]
    # Ensure exactly two Russian Mustered Lords.
    for i, lid in enumerate(rus):
        s.lords[lid].state = "mustered" if i < 2 else s.lords[lid].state
        if i < 2:
            s.lords[lid].location = "novgorod"
    rus_mustered = [lid for lid in rus if s.lords[lid].state == "mustered"][:2]
    active = teus[0]
    ctx = BattleDecisionContext()  # leftmost fallback
    atk_pos, def_pos = _init_battle_array(s, teus, rus_mustered, active, ctx)
    # Attacker has 3 Lords -> all 3 Front slots filled.
    assert set(atk_pos.values()) == {"center", "left", "right"}
    # Defender has 2 Lords, fills center first then left.
    fill_order = sorted(def_pos.items(), key=lambda kv: kv[0])
    slots_used = sorted(def_pos.values())
    assert "center" in slots_used
    assert "left" in slots_used
    assert "right" not in slots_used


# ---------------------------------------------------------------------------
# Reposition
# ---------------------------------------------------------------------------


def test_q005_reposition_advances_reserve_into_empty_front() -> None:
    """4.4.2 Reposition: Reserves advance into empty Front slots."""
    s = load_scenario("watland", seed=1)
    teus = [lid for lid, l in s.lords.items()
            if l.side == "teutonic" and l.state == "mustered"][:2]
    positions = {teus[0]: "center", teus[1]: "reserve"}
    # Wipe the center Lord's forces -> Routed.
    s.lords[teus[0]].forces = {}
    _remove_routed_from_array(s, positions)
    assert positions[teus[0]] == "routed"
    # After Reposition, Reserve advances into the empty center slot.
    ctx = BattleDecisionContext()
    moves = _reposition(s, positions, "attacker", ctx)
    # The Reserve Lord ends up at center (only empty slot, only one Reserve).
    assert positions[teus[1]] == "center"
    assert any(m["lord"] == teus[1] for m in moves["moves"])


def test_q005_reposition_center_fill_from_left_or_right() -> None:
    """4.4.2 Reposition: if center remains empty after Advance, slide
    one Lord from left or right to fill center."""
    s = load_scenario("watland", seed=1)
    teus = [lid for lid, l in s.lords.items()
            if l.side == "teutonic" and l.state == "mustered"][:3]
    positions = {teus[0]: "center", teus[1]: "left", teus[2]: "right"}
    # Rout the center Lord.
    s.lords[teus[0]].forces = {}
    _remove_routed_from_array(s, positions)
    # No Reserves available; center fill should slide left or right
    # (operator picks; leftmost fallback -> left Lord moves to center).
    ctx = BattleDecisionContext()
    _reposition(s, positions, "attacker", ctx)
    assert positions[teus[1]] == "center"
    # The right Lord stays put.
    assert positions[teus[2]] == "right"


# ---------------------------------------------------------------------------
# Flanking
# ---------------------------------------------------------------------------


def test_q005_directly_opposed_target() -> None:
    """4.4.2 Strike: same-slot Lord is the direct target."""
    s = load_scenario("watland", seed=1)
    teus = [lid for lid, l in s.lords.items()
            if l.side == "teutonic" and l.state == "mustered"][:1]
    rus = [lid for lid, l in s.lords.items()
           if l.side == "russian" and l.state == "mustered"][:1]
    enemy_pos = {rus[0]: "center"}
    target = _strike_target("center", enemy_pos, BattleDecisionContext(),
                             "attacker", s)
    assert target == rus[0]


def test_q005_flanking_picks_closest_in_row() -> None:
    """4.4.2: 'Whenever a Lord facing an enemy row has no enemy Lord
    directly opposite ... his Lord's units Strike the closest enemy
    Lord in that row.'"""
    s = load_scenario("watland", seed=1)
    rus = [lid for lid, l in s.lords.items()
           if l.side == "russian" and l.state == "mustered"][:2]
    # Striker at left (slot 0); enemy at center (slot 1) and right (slot 2).
    # Closest is center (distance 1 vs 2).
    enemy_pos = {rus[0]: "center", rus[1]: "right"}
    target = _strike_target("left", enemy_pos, BattleDecisionContext(),
                             "attacker", s)
    assert target == rus[0]


def test_q005_flanking_tie_break_via_decision() -> None:
    """4.4.2: striker at center, enemy center empty, both flanks
    occupied -> tie at distance 1, operator picks."""
    s = load_scenario("watland", seed=1)
    rus_mustered: list[str] = []
    for lid, l in s.lords.items():
        if l.side == "russian":
            l.state = "mustered"
            l.location = "novgorod"
            l.forces = {"militia": 1}  # ensure Unrouted
            rus_mustered.append(lid)
            if len(rus_mustered) == 2:
                break
    enemy_pos = {rus_mustered[0]: "left", rus_mustered[1]: "right"}
    # Scripted: pick the right-side Lord.
    ctx = BattleDecisionContext(scripted=[
        {"type": "flanker_target", "chosen": rus_mustered[1],
         "rationale": "test pick"},
    ])
    target = _strike_target("center", enemy_pos, ctx, "attacker", s)
    assert target == rus_mustered[1]


# ---------------------------------------------------------------------------
# Scripted decisions integration
# ---------------------------------------------------------------------------


def test_q005_scripted_decisions_logged_in_battle_result() -> None:
    """The decision trace appears under result['decisions'] for
    auditability."""
    s = load_scenario("watland", seed=1)
    teus = [lid for lid, l in s.lords.items()
            if l.side == "teutonic" and l.state == "mustered"][:2]
    rus = [lid for lid, l in s.lords.items()
           if l.side == "russian" and l.state == "mustered"][:1]
    # Co-locate.
    s.lords[rus[0]].location = "fellin"
    for t in teus:
        s.lords[t].location = "fellin"
    # Clobber forces to small values so the battle resolves quickly.
    s.lords[teus[0]].forces = {"knights": 2}
    s.lords[teus[1]].forces = {"sergeants": 2}
    s.lords[rus[0]].forces = {"militia": 2}
    ctx = BattleDecisionContext(scripted=[
        {"type": "initial_placement_attacker", "chosen": "left",
         "rationale": "test left placement"},
    ])
    res = resolve_battle(
        s, attacker_side="teutonic",
        attacker_lords=teus, defender_lords=rus,
        active_attacker=teus[0], decision_ctx=ctx,
    )
    decisions = res["decisions"]
    # At least the placement decision must appear.
    placements = [d for d in decisions
                  if d["type"] == "initial_placement_attacker"]
    assert placements, f"expected placement decision in {decisions}"
    assert placements[0]["chosen"] == "left"
    # Result includes positions.
    assert "attacker_positions" in res
    assert "defender_positions" in res


def test_q005_leftmost_fallback_when_no_scripted_decisions() -> None:
    """No scripted_decisions and no callback -> deterministic leftmost
    fallback. Test verifies the engine doesn't error and produces a
    consistent result."""
    s = load_scenario("watland", seed=1)
    teus = [lid for lid, l in s.lords.items()
            if l.side == "teutonic" and l.state == "mustered"][:2]
    rus = [lid for lid, l in s.lords.items()
           if l.side == "russian" and l.state == "mustered"][:1]
    s.lords[rus[0]].location = "fellin"
    for t in teus:
        s.lords[t].location = "fellin"
    s.lords[teus[0]].forces = {"knights": 2}
    s.lords[teus[1]].forces = {"sergeants": 2}
    s.lords[rus[0]].forces = {"militia": 2}
    res = resolve_battle(
        s, attacker_side="teutonic",
        attacker_lords=teus, defender_lords=rus,
        active_attacker=teus[0],
    )
    # Battle resolved without error.
    assert res["winner"] in ("teutonic", "russian")
    # Decisions log is present (even if empty for a 1v1 case it should
    # at least record the attacker's placement decision).
    assert "decisions" in res


def test_q005_scripted_decision_type_mismatch_raises() -> None:
    """If the test scripts a decision of the wrong type, the engine
    raises immediately (catches bad test setup)."""
    s = load_scenario("watland", seed=1)
    teus = [lid for lid, l in s.lords.items()
            if l.side == "teutonic" and l.state == "mustered"][:2]
    rus = [lid for lid, l in s.lords.items()
           if l.side == "russian" and l.state == "mustered"][:1]
    s.lords[rus[0]].location = "fellin"
    for t in teus:
        s.lords[t].location = "fellin"
    ctx = BattleDecisionContext(scripted=[
        {"type": "flanker_target", "chosen": "anyone"},  # wrong type
    ])
    with pytest.raises(ValueError, match="scripted decision type mismatch"):
        resolve_battle(
            s, attacker_side="teutonic",
            attacker_lords=teus, defender_lords=rus,
            active_attacker=teus[0], decision_ctx=ctx,
        )
