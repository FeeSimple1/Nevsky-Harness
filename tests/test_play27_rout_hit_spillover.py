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

from nevsky.battle import BattleDecisionContext, resolve_battle, _apply_row_spillover
from nevsky.scenarios import load_scenario


def _setup(dc_serfs=1, dl_serfs=2, atk_serfs=40):
    s = load_scenario("watland", seed=1)
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
        s, "center", 5, "melee", {dc: "center", dl: "left"},
        rounds=1, kind="melee_foot", raven_rock_walls=False,
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
        s, "right", 5, "melee", {dc: "center", dl: "left"},
        rounds=1, kind="melee_foot", raven_rock_walls=False,
        attacker_side="teutonic",
        attacker_absorption_policy="weakest_first",
        defender_absorption_policy="weakest_first",
    )
    # Both survivors Routed by the cascading leftover.
    assert s.lords[dc].forces == {}
    assert s.lords[dl].forces == {}
    assert {e["lord"] for e in out} == {dc, dl}
