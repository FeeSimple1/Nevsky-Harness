"""PLAY-27 (4.4.2): remaining Hits after a mid-step Rout follow the new
Flanking situation to the rest of the row; only a fully-Routed row
ignores them.

Rulebook 4.4.2 APPLY HITS TO LORDS / ROUT: "Whenever a Lord Routs to
create a new Flanking situation, apply remaining Hits accordingly ...
When an entire row Routs, ignore remaining Hits against that row."

Serfs are used as the target Forces: they never roll Protection (removed
whenever assigned a Hit), so Hit->Rout is deterministic.
"""

from __future__ import annotations

from nevsky.actions import apply_action
from nevsky.battle import BattleDecisionContext, _apply_row_spillover, resolve_battle
from nevsky.scenarios import load_scenario
from tests.test_cross_game_relief_retreat import place, position, stand
from tests.test_round7_combat_limits import _place_with_vassals


def _setup(dc_serfs=1, dl_serfs=2, atk_serfs=40, *, seed=1):
    s = load_scenario("watland", seed=seed)
    teu = [lid for lid, l in s.lords.items() if l.side == "teutonic"][0]
    rus = [lid for lid, l in s.lords.items() if l.side == "russian"][:2]
    for lid in [teu] + rus:
        s.lords[lid].state = "mustered"
        s.lords[lid].location = "pskov"
    # Attacker: a single Front-center Lord with an overwhelming Serf stack.
    s.lords[teu].forces = {"serfs": atk_serfs}
    # Defenders: center (small, Routs fast) and left (survivor in the row).
    s.lords[rus[0]].forces = {"serfs": dc_serfs}
    s.lords[rus[1]].forces = {"serfs": dl_serfs}
    return s, teu, rus


def test_leftover_hits_spill_to_flanking_lord_in_row():
    s, teu, rus = _setup(dc_serfs=1, dl_serfs=2, atk_serfs=40)
    dc, dl = rus
    res = resolve_battle(
        s, attacker_side="teutonic", attacker_lords=[teu], defender_lords=[dc, dl],
        max_rounds=1, decision_ctx=BattleDecisionContext(),
        attacker_positions={teu: "center"},
        defender_positions={dc: "center", dl: "left"},
    )
    # A spillover distribution entry must target the flanking (left) Lord,
    # even though no attacker Lord is directly opposite him.
    spill_entries = [
        e for st in res["log"][0]["steps"]
        for e in st.get("distribution", [])
        if e.get("spillover") and e.get("lord") == dl
    ]
    assert spill_entries, "expected leftover Hits to spill onto the flank Lord"
    # The flank Lord actually took Routs from the spillover.
    assert s.lords[dl].routed_units, "flank Lord should have Routed units"


def test_entire_row_rout_ignores_remaining_hits():
    """When no survivor remains in the row, remaining Hits are ignored
    (no crash, defender simply loses). _apply_row_spillover returns []
    for a fully-Routed row."""
    s, teu, rus = _setup()
    dc, dl = rus
    # Simulate: both defenders already Routed (no Forces) -> empty row.
    s.lords[dc].forces = {}
    s.lords[dl].forces = {}
    out = _apply_row_spillover(
        s, "center", [False] * 5, "melee", {dc: "center", dl: "left"},
        rounds=1, raven_rock_walls=False,
        attacker_side="teutonic",
        attacker_absorption_policy="weakest_first",
        defender_absorption_policy="weakest_first",
    )
    assert out == []


def test_spillover_helper_cascades_across_survivors():
    """Leftover larger than the nearest survivor cascades to the next."""
    s, teu, rus = _setup(dl_serfs=1)
    dc, dl = rus
    # Two survivors in the Front row, 1 serf each; 5 leftover Hits.
    s.lords[dc].forces = {"serfs": 1}
    s.lords[dl].forces = {"serfs": 1}
    out = _apply_row_spillover(
        s, "right", [False] * 5, "melee", {dc: "center", dl: "left"},
        rounds=1, raven_rock_walls=False,
        attacker_side="teutonic",
        attacker_absorption_policy="weakest_first",
        defender_absorption_policy="weakest_first",
    )
    # Both survivors Routed by the cascading leftover.
    assert s.lords[dc].forces == {}
    assert s.lords[dl].forces == {}
    assert {e["lord"] for e in out} == {dc, dl}


def test_crossbow_penalty_expires_when_only_an_ordinary_hit_remains():
    state, _, (center, left) = _setup(seed=5)
    for lord_id in (center, left):
        state.lords[lord_id].forces = {"knights": 1}
    spillover = _apply_row_spillover(
        state, "right", [True, False], "archery", {center: "center", left: "left"},
        rounds=1, raven_rock_walls=False, attacker_side="teutonic",
        attacker_absorption_policy="weakest_first", defender_absorption_policy="weakest_first",
    )

    # The Crossbow Hit rolls 3 and Routs the first Knight. The next roll
    # of 4 saves the second Knight against the remaining ordinary Hit.
    first, second = spillover
    assert first["lord"] == center and first["routed"] == [{"unit": "knights", "absorbed": False}]
    assert second["lord"] == left and second["routed"] == [{"unit": "knights", "absorbed": True}]


def test_walls_absorbed_hit_does_not_spill_again():
    state, _, (center, left) = _setup(seed=2)
    before_roll = state.meta.rng_state
    spillover = _apply_row_spillover(
        state, "right", [False], "melee", {center: "center", left: "left"},
        rounds=1, raven_rock_walls=True, attacker_side="teutonic",
        attacker_absorption_policy="weakest_first", defender_absorption_policy="weakest_first",
    )

    assert spillover == [{"lord": center, "target": "ravens_rock_walls",
                          "absorbed": 1, "spillover": True}]
    assert state.meta.rng_state == before_roll + 1


def test_crossbow_spillover_keeps_the_armor_penalty_in_battle():
    state = position(seed=5, box=9)
    andreas = _place_with_vassals(state, "andreas", "andreas_teutonic_vassals")
    andreas.location = "ostrov"
    andreas.forces = {"men_at_arms": andreas.forces["men_at_arms"]}
    andreas.this_lord_capabilities = ["T4"]
    state.decks.teutonic.deck.remove("T4")
    place(state, "hermann", {"militia": 1}).location = "ostrov"
    place(state, "gavrilo", {"militia": 1})
    place(state, "aleksandr", {"knights": 1})
    state.campaign_turn.active_card = state.campaign_turn.active_lord = "andreas"
    apply_action(state, {"type": "cmd_march", "side": "teutonic", "args": {
        "lord_id": "andreas", "to": "pskov", "way_type": "waterway", "group": ["hermann"],
    }})
    battle = stand(state, scripted_decisions=[
        {"type": "initial_placement_attacker", "chosen": "left"},
        {"type": "initial_placement_defender", "chosen": "gavrilo"},
    ])["battle"]

    archery = next(step for step in battle["log"][0]["steps"] if step["step"] == "archery_attacker")
    direct, spillover = archery["distribution"]
    assert direct["lord"] == "gavrilo" and direct["routed"] == [
        {"unit": "militia", "absorbed": False},
    ]
    assert spillover["lord"] == "aleksandr" and spillover["spillover"]
    # The second Crossbow Hit rolls 4, above the Knight's reduced Armor 1–2.
    assert spillover["routed"] == [{"unit": "knights", "absorbed": False}]
