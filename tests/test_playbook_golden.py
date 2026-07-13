"""Playbook golden tests (Background Book "Examples of Play", pp. 3-10).

These replay the designer's own worked Watland example against the
engine -- an EXTERNAL correctness check, unlike the internal-consistency
sweeps. Where the 1E Background Book (2019) conflicts with the 2E rules
(2023), the 2E reading is asserted and the divergence is noted inline
(project rule: Rules of Play 2E trump).

Known 1E-vs-2E adaptations in this file:
  - 2E Watland setup starts BOTH Domash (Novgorod) and Vladislav
    (Ladoga) Mustered ("6.0 Some scenarios are adjusted"); the 1E
    example's "Russians begin with just one Lord Mustered" and its
    Veche-B muster of Vladislav are outdated. The Veche-B vignette is
    replayed with Karelians (Ready in box 4) instead.
  - 2E 4.7.2: Ravage costs TWO actions when an Unbesieged enemy Lord
    is adjacent (the 1E example charges one).
"""
from __future__ import annotations

import pytest

import nevsky.actions  # noqa: F401
from nevsky.actions import IllegalAction, apply_action, _seats_of
from nevsky.scenarios import load_scenario
from nevsky.state import GameState

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _playbook_rolls import script_rolls  # noqa: E402


# ------------------------- Setup (pp. 3, 2E 6.0) -------------------------

def test_watland_setup_matches_2e_printed_setup():
    """Golden: the engine's Watland equals the 2E rulebook setup text."""
    s = load_scenario("watland", seed=1)
    assert s.meta.box == 4
    mustered = {lid: l.location for lid, l in s.lords.items()
                if l.state == "mustered"}
    assert mustered == {
        "andreas": "fellin", "knud_and_abel": "wesenberg",
        "yaroslav": "pskov",                       # Teutons
        "domash": "novgorod", "vladislav": "ladoga",  # Russians (2E)
    }
    # Calendar per the printed list.
    def _box(n):
        return s.calendar.boxes[n - 1]
    assert set(_box(4).cylinders) == {"heinrich", "rudolf", "karelians"}
    assert _box(5).cylinders == ["andrey"] and _box(5).service_markers == ["yaroslav"]
    assert set(_box(6).service_markers) == {"knud_and_abel", "vladislav"}
    assert _box(7).cylinders == ["aleksandr"]
    assert set(_box(7).service_markers) == {"andreas", "domash"}
    assert _box(8).cylinders == ["hermann"]
    # Veche: one white 1VP Conquered, Coin x1.
    assert s.veche.vp_markers == 1 and s.veche.coin == 1
    # Markers on map: Conquered at Izborsk (1) and Pskov (2); Ravaged
    # at Pskov and Dubrovno (all black = Teutonic).
    assert s.locales["izborsk"].teutonic_conquered == 1
    assert s.locales["pskov"].teutonic_conquered == 2
    assert s.locales["pskov"].teutonic_ravaged is True
    assert s.locales["dubrovno"].teutonic_ravaged is True
    # Gavrilo removed from play.
    assert s.lords["gavrilo"].state != "mustered"
    assert "gavrilo" not in [c for cb in s.calendar.boxes for c in cb.cylinders]


# ------------------- Levy / Muster (pp. 5-6, printed rolls) -------------------

def _muster_step(s: GameState, side: str):
    s.meta.phase = "levy"
    s.meta.levy_step = "muster"
    s.meta.active_player = side


def test_andreas_ordensburgen_then_heinrich_musters_at_fellin(monkeypatch):
    """Andreas (Lordship 3): Levy T12 Ordensburgen, then Muster Heinrich
    (Fealty 3) -- printed rolls: '5' fails, '2' succeeds. Heinrich lands
    at FELLIN, legal only via the T12 Commandery Seat, and his Service
    marker goes 4 boxes ahead into box 8 (Service 4)."""
    s = load_scenario("watland", seed=1)
    _muster_step(s, "teutonic")
    rolls = script_rolls(monkeypatch, [5, 2])

    # Fellin is NOT a Heinrich Seat without Ordensburgen.
    assert "fellin" not in _seats_of(s, "heinrich")
    res = apply_action(s, {"type": "levy_capability", "side": "teutonic",
                           "args": {"by_lord": "andreas", "card_id": "T12"}})
    assert "T12" in s.decks.teutonic.capabilities_in_play
    assert "fellin" in _seats_of(s, "heinrich")

    r1 = apply_action(s, {"type": "muster_lord", "side": "teutonic",
                          "args": {"by_lord": "andreas",
                                   "target_lord": "heinrich",
                                   "seat": "fellin"}})
    assert r1.get("outcome") == "fealty_failed"  # printed roll: 5 > Fealty 3
    assert s.lords["heinrich"].state != "mustered"
    r2 = apply_action(s, {"type": "muster_lord", "side": "teutonic",
                          "args": {"by_lord": "andreas",
                                   "target_lord": "heinrich",
                                   "seat": "fellin"}})
    assert r2.get("outcome") == "mustered"       # printed roll: 2 <= 3
    assert rolls.rolls == []                    # exactly two rolls consumed
    assert s.lords["heinrich"].state == "mustered"
    assert s.lords["heinrich"].location == "fellin"
    # Service marker: 4 boxes ahead of current box 4 -> box 8.
    assert "heinrich" in s.calendar.boxes[8 - 1].service_markers
    # Andreas spent all 3 Lordship (1 Levy + 2 Muster attempts).
    assert s.lords["andreas"].lordship_used == 3
    # A Lord Mustered this segment may not use his own Lordship (3.4).
    with pytest.raises(IllegalAction):
        apply_action(s, {"type": "levy_transport", "side": "teutonic",
                         "args": {"by_lord": "heinrich", "transport_type": "sled"}})


def test_knud_abel_stensby_vassal_and_sled():
    """Knud & Abel (Lordship 3): Levy T1 Treaty of Stensby, Muster the
    Vassal Dietrich von Kivel (+1 Knights +1 Men-at-Arms), add 1 Sled."""
    s = load_scenario("watland", seed=1)
    _muster_step(s, "teutonic")
    ka = s.lords["knud_and_abel"]
    pre = dict(ka.forces)
    apply_action(s, {"type": "levy_capability", "side": "teutonic",
                     "args": {"by_lord": "knud_and_abel", "card_id": "T1"}})
    assert "T1" in s.decks.teutonic.capabilities_in_play
    apply_action(s, {"type": "muster_vassal", "side": "teutonic",
                     "args": {"by_lord": "knud_and_abel",
                              "vassal_id": "knud_and_abel_dietrich_von_kivel"}})
    assert ka.forces.get("knights", 0) == pre.get("knights", 0) + 1
    assert ka.forces.get("men_at_arms", 0) == pre.get("men_at_arms", 0) + 1
    apply_action(s, {"type": "levy_transport", "side": "teutonic",
                     "args": {"by_lord": "knud_and_abel", "transport_type": "sled"}})
    assert ka.assets.get("sled", 0) == 1
    assert ka.lordship_used == 3
    # Lordship exhausted: a fourth action is illegal.
    with pytest.raises(IllegalAction):
        apply_action(s, {"type": "levy_transport", "side": "teutonic",
                         "args": {"by_lord": "knud_and_abel",
                                  "transport_type": "sled"}})


def test_yaroslav_levies_raiders_as_this_lord():
    """Yaroslav (Lordship 1) Levies T2 Raiders -- a This Lord card tucked
    at HIS mat, not the board edge."""
    s = load_scenario("watland", seed=1)
    _muster_step(s, "teutonic")
    apply_action(s, {"type": "levy_capability", "side": "teutonic",
                     "args": {"by_lord": "yaroslav", "card_id": "T2"}})
    assert "T2" in s.lords["yaroslav"].this_lord_capabilities
    assert "T2" not in s.decks.teutonic.capabilities_in_play
    assert s.lords["yaroslav"].lordship_used == 1


def test_veche_b_auto_musters_ready_lord():
    """Veche Option B (pp. 6): spend the 1VP marker to auto-Muster a
    Ready Russian Lord, no Fealty roll. 2E adaptation: Vladislav already
    starts Mustered, so the Ready Karelians (cylinder in box 4) Muster
    at their Seat of Ladoga instead. Costs the Veche VP marker and the
    white Victory point."""
    s = load_scenario("watland", seed=1)
    s.meta.phase = "levy"
    s.meta.levy_step = "call_to_arms"
    s.meta.active_player = "russian"
    s.veche.acted_this_call_to_arms = False
    pre_vp = s.calendar.russian_vp
    res = apply_action(s, {"type": "veche_action", "side": "russian",
                           "args": {"option": "B", "target_lord": "karelians",
                                    "seat": "ladoga"}})
    assert s.lords["karelians"].state == "mustered"
    assert s.lords["karelians"].location == "ladoga"
    # Service marker: Service 2 -> box 4 + 2 = 6.
    assert "karelians" in s.calendar.boxes[6 - 1].service_markers
    assert s.veche.vp_markers == 0
    assert s.calendar.russian_vp == pre_vp - 1.0


# --------------- March, Laden, Ravage (pp. 7-8, Winter) ---------------

def _andreas_card(s: GameState, group_at: str = "dorpat"):
    """Andreas active on his Command card at Dorpat with Heinrich."""
    for lid in ("andreas", "heinrich"):
        s.lords[lid].state = "mustered"
        s.lords[lid].location = group_at
        s.lords[lid].moved_fought = False
    # Heinrich's mat as Mustered (his starting three units, pp. 6).
    s.lords["heinrich"].forces = {"knights": 1, "sergeants": 1,
                                  "men_at_arms": 1}
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.active_player = "teutonic"
    s.campaign_turn.active_card = "andreas"
    s.campaign_turn.active_lord = "andreas"
    s.campaign_turn.actions_remaining = 3   # Andreas Command 3
    s.campaign_turn.in_feed_pay_disband = False


def test_winter_laden_march_costs_double_and_discard_restores():
    """4 Sleds vs 6 Provender group: Laden March = 2 actions; after
    discarding 2 Provender the group is Unladen and Marches for 1."""
    s = load_scenario("watland", seed=1)
    _andreas_card(s)
    s.lords["andreas"].assets = {"sled": 2, "provender": 2}
    s.lords["heinrich"].assets = {"sled": 2, "provender": 4}

    s2 = s.model_copy(deep=True)
    # Laden March: 6 provender > 4 usable Sleds (Winter, any Way).
    r = apply_action(s2, {"type": "cmd_march", "side": "teutonic",
                          "args": {"lord_id": "andreas", "to": "gdov",
                                   "group": ["andreas", "heinrich"]}})
    assert s2.campaign_turn.actions_remaining == 1   # 3 - 2 (Laden)
    assert s2.lords["andreas"].location == "gdov"

    # PLAY-40 (1.7.2 "March Unladen"): discard down to the group's 4
    # usable Sleds and March for ONE action -- the choice the example
    # walks through, which the harness previously could not express.
    r = apply_action(s, {"type": "cmd_march", "side": "teutonic",
                         "args": {"lord_id": "andreas", "to": "gdov",
                                  "group": ["andreas", "heinrich"],
                                  "discard_to_unladen": True}})
    total_prov = (s.lords["andreas"].assets.get("provender", 0)
                  + s.lords["heinrich"].assets.get("provender", 0))
    assert total_prov == 4
    assert s.campaign_turn.actions_remaining == 2    # 3 - 1 (Unladen)


def test_march_group_always_includes_the_active_lord():
    """PLAY-39 (found by this golden test): a `group` omitting the
    active Lord previously moved the others while he stayed behind --
    4.3/4.3.1 has the Marshal bring Lords "with him". The active Lord
    is now always normalized into the moving group."""
    s = load_scenario("watland", seed=1)
    _andreas_card(s)
    s.lords["andreas"].assets = {"sled": 2, "provender": 2}
    s.lords["heinrich"].assets = {"sled": 2, "provender": 2}
    apply_action(s, {"type": "cmd_march", "side": "teutonic",
                     "args": {"lord_id": "andreas", "to": "gdov",
                              "group": ["heinrich"]}})   # omits andreas
    assert s.lords["andreas"].location == "gdov"          # he moves anyway
    assert s.lords["heinrich"].location == "gdov"


def test_ravage_gdov_2e_costs_two_with_enemy_adjacent():
    """Ravage of Gdov awards the marker + 1 Provender + 1 Loot (4.7.2).
    2E DIVERGENCE from the 1E example: Domash sits adjacent (Plyussa R.),
    so the Ravage costs TWO actions, not one."""
    s = load_scenario("watland", seed=1)
    _andreas_card(s, group_at="gdov")
    s.lords["andreas"].assets = {"sled": 2, "provender": 2}
    s.lords["heinrich"].assets = {"sled": 2, "provender": 2}
    s.lords["domash"].location = "plyussa_river"   # adjacent Unbesieged enemy
    pre_actions = s.campaign_turn.actions_remaining
    r = apply_action(s, {"type": "cmd_ravage", "side": "teutonic",
                         "args": {"lord_id": "andreas"}})
    assert s.locales["gdov"].teutonic_ravaged is True
    assert s.lords["andreas"].assets.get("provender", 0) == 3   # +1
    assert s.lords["andreas"].assets.get("loot", 0) == 1        # Town: +1 Loot
    assert pre_actions - s.campaign_turn.actions_remaining == 2  # 2E cost


# ---------------- Avoid Battle + Feed (pp. 8-9, printed math) ----------------

def _approach_plyussa(s: GameState):
    """Andreas (+Heinrich) March from Gdov onto Domash at Plyussa R."""
    _andreas_card(s, group_at="gdov")
    s.lords["andreas"].assets = {"sled": 2, "provender": 2}
    s.lords["heinrich"].assets = {"sled": 2, "provender": 2}
    d = s.lords["domash"]
    d.location = "plyussa_river"
    d.assets = {"sled": 3, "provender": 4}
    # "All those Mustered Novgorod Militia bring his Forces total up to
    # nine": Muster two Novgorod vassals (+4 Militia) onto his 5 units.
    d.forces = {"sergeants": 1, "men_at_arms": 2, "light_horse": 1,
                "militia": 5}
    apply_action(s, {"type": "cmd_march", "side": "teutonic",
                     "args": {"lord_id": "andreas", "to": "plyussa_river",
                              "group": ["andreas", "heinrich"]}})
    assert s.combat_pending is not None
    assert s.combat_pending.pending_response_by == "russian"
    s.meta.active_player = "russian"


def test_avoid_gates_match_example():
    """Domash may NOT Avoid to Gdov (the Approach Way) nor toward Knud
    & Abel at Narwia (Unbesieged enemy Lord); Zheltsy is legal."""
    s = load_scenario("watland", seed=1)
    _approach_plyussa(s)
    s.lords["knud_and_abel"].location = "narwia"
    with pytest.raises(IllegalAction) as e1:
        apply_action(s, {"type": "avoid_battle", "side": "russian",
                         "args": {"to": "gdov"}})
    assert e1.value.code == "approach_way_blocked"
    with pytest.raises(IllegalAction) as e2:
        apply_action(s, {"type": "avoid_battle", "side": "russian",
                         "args": {"to": "narwia"}})
    assert e2.value.code == "dest_blocked"


def test_avoid_discard_spoils_and_feed_math():
    """Domash (3 Sleds, 4 Provender) discards 1 Provender to Avoid to
    Zheltsy; the Provender goes to the Approaching Teutons. Feed then
    consumes 1 each from Andreas (4 units) and Heinrich (3), and 2 from
    Domash (9 units); nobody goes Unfed."""
    s = load_scenario("watland", seed=1)
    _approach_plyussa(s)
    r = apply_action(s, {"type": "avoid_battle", "side": "russian",
                         "args": {"to": "zheltsy"}})
    d = s.lords["domash"]
    assert d.location == "zheltsy"
    assert d.moved_fought is True
    assert d.assets.get("provender", 0) == 3
    assert r["spoils_to_attacker"]["provender"] == 1
    # Attacker group received it (Andreas first).
    assert s.lords["andreas"].assets.get("provender", 0) == 3

    # End Andreas's card, then Feed (4.8.1): T then R, no Pay wanted.
    s.meta.active_player = "teutonic"
    apply_action(s, {"type": "end_card", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "fpd_resolve", "side": "teutonic",
                     "args": {"decline_pay": True}})
    apply_action(s, {"type": "fpd_resolve", "side": "russian",
                     "args": {"decline_pay": True}})
    assert s.lords["andreas"].assets.get("provender", 0) == 2   # 3 - 1
    assert s.lords["heinrich"].assets.get("provender", 0) == 1  # 2 - 1
    assert d.assets.get("provender", 0) == 1                    # 3 - 2 (9 units)
    # No Unfed shift: Domash's Service marker still in box 7.
    assert "domash" in s.calendar.boxes[7 - 1].service_markers
