"""Round 41 — End-Campaign Reset (4.9.5) completeness.

SMOKE-028: ``_h_end_campaign_resolve`` was missing three rule-required
cleanups during the Reset step:

  (a) Serfs not removed from Russian Lord mats back to the Smerdi
      Capability card / pool on every End Campaign.
  (b) Crusade Capability (T11) not auto-discarded when advancing to
      box 5 or box 13 (the year's first Late Winter 40 Days).
  (c) Summer Crusaders Special Vassal not Disbanded at the same
      transition.

Reference: ``reference/Nevsky Calender and Veche Reference.txt`` lines
173-189, the RESET (4.9.5) section. Quote (lines 175-176, 187-189):

    Remove all Serfs from Russian mats (even if Besieged) to the
    Smerdi Capability card.
    ...
    If the new 40 Days is the year's first Late Winter (box 5 or
    box 13), discard the Crusade Capability if in play and Disband
    the Summer Crusaders Special Vassal.

The fix lives in ``src/nevsky/campaign.py::_h_end_campaign_resolve``.
"""
from __future__ import annotations

from nevsky.actions import apply_action
from nevsky.scenarios import load_scenario


def _drive_to_end_campaign(state, box: int, side_first: str = "teutonic") -> None:
    """Force the state into ready-to-resolve end_campaign at given box."""
    state.meta.box = box
    for cb in state.calendar.boxes:
        cb.has_levy_campaign_marker = (cb.box == box)
        cb.levy_campaign_face = "campaign" if cb.box == box else None
    state.meta.phase = "campaign"
    state.meta.campaign_step = "end_campaign"
    state.meta.active_player = side_first
    state.meta.end_campaign_completed_t = False
    state.meta.end_campaign_completed_r = False


def _run_both_sides(state):
    res_t = apply_action(state, {"type": "end_campaign_resolve",
                                  "side": "teutonic", "args": {}})
    res_r = apply_action(state, {"type": "end_campaign_resolve",
                                  "side": "russian", "args": {}})
    return res_t, res_r


# --- SMOKE-028a: Serfs return to Smerdi pool on every End-Campaign Reset ---

def test_smoke_028a_serfs_returned_on_reset():
    """Russian Lord with 3 Serfs has them removed at End-Campaign Reset
    regardless of which calendar box is reached. (4.9.5)."""
    s = load_scenario("crusade_on_novgorod", seed=42)
    # Find a Mustered Russian Lord, give him 3 serfs.
    target = next(lid for lid, l in s.lords.items()
                   if l.side == "russian" and l.state == "mustered")
    s.lords[target].forces["serfs"] = 3
    _drive_to_end_campaign(s, box=2)
    _, res_r = _run_both_sides(s)
    assert s.lords[target].forces.get("serfs", 0) == 0
    # serfs_returned should appear on the Russian side result.
    sr = res_r.get("serfs_returned", [])
    assert any(item["lord_id"] == target and item["count"] == 3 for item in sr)


def test_smoke_028a_serfs_returned_even_when_besieged():
    """Per rule text 'even if Besieged': Serfs return regardless of
    in_stronghold status. (4.9.5)."""
    s = load_scenario("crusade_on_novgorod", seed=42)
    target = next(lid for lid, l in s.lords.items()
                   if l.side == "russian" and l.state == "mustered")
    s.lords[target].forces["serfs"] = 2
    # Besiege the Lord (in_stronghold=True with siege markers at his locale).
    loc = s.lords[target].location
    s.lords[target].in_stronghold = True
    s.locales[loc].siege_markers = 1
    _drive_to_end_campaign(s, box=2)
    _run_both_sides(s)
    assert s.lords[target].forces.get("serfs", 0) == 0


def test_smoke_028a_serfs_returned_from_multiple_lords():
    """Multiple Russian Lords each return their serfs."""
    s = load_scenario("crusade_on_novgorod", seed=42)
    russians = [lid for lid, l in s.lords.items()
                 if l.side == "russian" and l.state == "mustered"]
    assert len(russians) >= 2
    for lid in russians[:2]:
        s.lords[lid].forces["serfs"] = 1
    _drive_to_end_campaign(s, box=2)
    _, res_r = _run_both_sides(s)
    for lid in russians[:2]:
        assert s.lords[lid].forces.get("serfs", 0) == 0
    assert len(res_r.get("serfs_returned", [])) == 2


def test_smoke_028a_no_serfs_no_op():
    """No Russian Lord with serfs -> serfs_returned is empty."""
    s = load_scenario("crusade_on_novgorod", seed=42)
    _drive_to_end_campaign(s, box=2)
    _, res_r = _run_both_sides(s)
    assert res_r.get("serfs_returned", []) == []


# --- SMOKE-028b: Crusade Capability (T11) auto-discard at box 5 / 13 ---

def test_smoke_028b_crusade_discarded_at_box_5():
    """T11 (Crusade) in capabilities_in_play -> moved to discard pile
    when advancing to box 5 (first Late Winter of year 1). (4.9.5)."""
    s = load_scenario("crusade_on_novgorod", seed=42)
    s.decks.teutonic.capabilities_in_play.append("T11")
    _drive_to_end_campaign(s, box=4)
    _, res_r = _run_both_sides(s)
    assert s.meta.box == 5
    assert "T11" not in s.decks.teutonic.capabilities_in_play
    assert "T11" in s.decks.teutonic.discard
    assert res_r.get("crusade_auto_discarded") is True


def test_smoke_028b_crusade_discarded_at_box_13():
    """Same at box 13 (first Late Winter of year 2)."""
    s = load_scenario("crusade_on_novgorod", seed=42)
    s.decks.teutonic.capabilities_in_play.append("T11")
    _drive_to_end_campaign(s, box=12)
    _, res_r = _run_both_sides(s)
    assert s.meta.box == 13
    assert "T11" not in s.decks.teutonic.capabilities_in_play
    assert "T11" in s.decks.teutonic.discard
    assert res_r.get("crusade_auto_discarded") is True


def test_smoke_028b_crusade_not_discarded_at_other_transitions():
    """T11 must NOT auto-discard at non-(5,13) box transitions
    (e.g., box 2 -> 3, box 8 -> 9)."""
    for from_box in (2, 8, 10):
        s = load_scenario("crusade_on_novgorod", seed=42)
        s.decks.teutonic.capabilities_in_play.append("T11")
        _drive_to_end_campaign(s, box=from_box)
        _, res_r = _run_both_sides(s)
        assert "T11" in s.decks.teutonic.capabilities_in_play, (
            f"T11 spuriously discarded at box {from_box} -> {s.meta.box}"
        )
        assert res_r.get("crusade_auto_discarded") is False


def test_smoke_028b_crusade_not_in_play_no_op():
    """No T11 in play -> no auto-discard fired."""
    s = load_scenario("crusade_on_novgorod", seed=42)
    # Ensure T11 absent.
    if "T11" in s.decks.teutonic.capabilities_in_play:
        s.decks.teutonic.capabilities_in_play.remove("T11")
    _drive_to_end_campaign(s, box=4)
    _, res_r = _run_both_sides(s)
    assert s.meta.box == 5
    assert res_r.get("crusade_auto_discarded") is False


# --- SMOKE-028c: Summer Crusaders Special Vassal Disband at box 5 / 13 ---

def test_smoke_028c_summer_crusaders_disbanded_at_box_5():
    """A Mustered Summer Crusaders Vassal is Disbanded (forces returned,
    mustered=False, ready=False) when advancing to box 5. (4.9.5)."""
    s = load_scenario("crusade_on_novgorod", seed=42)
    # Andreas carries andreas_summer_crusaders_1 (3 knights).
    andreas = s.lords["andreas"]
    andreas.state = "mustered"
    andreas.location = "dorpat"
    vid = "andreas_summer_crusaders_1"
    andreas.vassals[vid].mustered = True
    andreas.vassals[vid].ready = True
    pre_knights = andreas.forces.get("knights", 0)
    andreas.forces["knights"] = pre_knights + 3  # vassal's contribution
    _drive_to_end_campaign(s, box=4)
    _, res_r = _run_both_sides(s)
    assert s.meta.box == 5
    vs = s.lords["andreas"].vassals[vid]
    assert vs.mustered is False
    assert vs.ready is False
    # Knights count returned to pre-vassal level (3 returned).
    assert s.lords["andreas"].forces.get("knights", 0) == pre_knights
    disbanded = res_r.get("summer_crusaders_disbanded", [])
    assert any(d["vassal_id"] == vid and d["forces_returned"].get("knights") == 3
               for d in disbanded)


def test_smoke_028c_summer_crusaders_disbanded_at_box_13():
    """Same at box 13 (year 2 first Late Winter), with Rudolf's vassal."""
    s = load_scenario("crusade_on_novgorod", seed=42)
    rudolf = s.lords["rudolf"]
    rudolf.state = "mustered"
    rudolf.location = "dorpat"
    vid = "rudolf_summer_crusaders"
    rudolf.vassals[vid].mustered = True
    rudolf.vassals[vid].ready = True
    pre_knights = rudolf.forces.get("knights", 0)
    rudolf.forces["knights"] = pre_knights + 2
    _drive_to_end_campaign(s, box=12)
    _, res_r = _run_both_sides(s)
    assert s.meta.box == 13
    vs = s.lords["rudolf"].vassals[vid]
    assert vs.mustered is False
    assert vs.ready is False
    assert s.lords["rudolf"].forces.get("knights", 0) == pre_knights


def test_smoke_028c_unmustered_summer_crusaders_still_flagged_unready():
    """If a Summer Crusaders Vassal is Ready (face-up) but not yet
    Mustered, the Disband still flips it to ready=False (the gating
    Crusade Capability is gone). No forces to return."""
    s = load_scenario("crusade_on_novgorod", seed=42)
    andreas = s.lords["andreas"]
    andreas.state = "mustered"
    andreas.location = "dorpat"
    vid = "andreas_summer_crusaders_1"
    andreas.vassals[vid].mustered = False
    andreas.vassals[vid].ready = True
    pre_knights = andreas.forces.get("knights", 0)
    _drive_to_end_campaign(s, box=4)
    _run_both_sides(s)
    vs = s.lords["andreas"].vassals[vid]
    assert vs.mustered is False
    assert vs.ready is False
    # No knights returned since none were mustered.
    assert s.lords["andreas"].forces.get("knights", 0) == pre_knights


def test_smoke_028c_no_disband_at_non_late_winter_box():
    """At non-(5,13) transitions, Summer Crusaders Vassal stays put."""
    s = load_scenario("crusade_on_novgorod", seed=42)
    andreas = s.lords["andreas"]
    andreas.state = "mustered"
    andreas.location = "dorpat"
    vid = "andreas_summer_crusaders_1"
    andreas.vassals[vid].mustered = True
    andreas.vassals[vid].ready = True
    _drive_to_end_campaign(s, box=2)
    _, res_r = _run_both_sides(s)
    assert s.meta.box == 3
    # Not disbanded.
    assert s.lords["andreas"].vassals[vid].mustered is True
    assert s.lords["andreas"].vassals[vid].ready is True
    assert res_r.get("summer_crusaders_disbanded", []) == []


# --- Composite invariant: all three cleanups fire together at box 5 ---

def test_smoke_028_composite_box_5_transition():
    """At box 4 -> box 5 with serfs, T11 in play, and a Mustered
    Summer Crusaders Vassal: all three cleanups fire together."""
    s = load_scenario("crusade_on_novgorod", seed=42)
    # Russian Lord with serfs.
    rtarget = next(lid for lid, l in s.lords.items()
                    if l.side == "russian" and l.state == "mustered")
    s.lords[rtarget].forces["serfs"] = 2
    # T11 in play.
    s.decks.teutonic.capabilities_in_play.append("T11")
    # Andreas mustered with Summer Crusaders mustered.
    andreas = s.lords["andreas"]
    andreas.state = "mustered"
    andreas.location = "dorpat"
    vid = "andreas_summer_crusaders_1"
    andreas.vassals[vid].mustered = True
    andreas.vassals[vid].ready = True
    pre_knights = andreas.forces.get("knights", 0)
    andreas.forces["knights"] = pre_knights + 3
    _drive_to_end_campaign(s, box=4)
    _, res_r = _run_both_sides(s)
    assert s.meta.box == 5
    assert s.lords[rtarget].forces.get("serfs", 0) == 0
    assert "T11" not in s.decks.teutonic.capabilities_in_play
    assert s.lords["andreas"].vassals[vid].mustered is False
    assert s.lords["andreas"].forces.get("knights", 0) == pre_knights
    assert res_r["crusade_auto_discarded"] is True
    assert len(res_r["summer_crusaders_disbanded"]) >= 1
    assert len(res_r["serfs_returned"]) >= 1
