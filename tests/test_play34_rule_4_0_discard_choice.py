"""PLAY-34 regression tests: 4.0 excess side-Capability discard is a choice.

Rule 4.0 CAPABILITY DISCARD: "The players (Teutonic first) must SELECT
and discard any Capability cards they have in excess of their number of
Mustered Lords -- not including any 'This Lord' Capabilities (3.4.4)."

The owner acts before Plan. A referee replay can supply explicit choices
in the final Call to Arms advance.
"""
from __future__ import annotations

import pytest

from nevsky.actions import IllegalAction, apply_action
from nevsky.legal_moves import legal_moves
from nevsky.scenarios import load_scenario


def _one_teuton_mustered(s, caps):
    for lid, l in s.lords.items():
        if l.side == "teutonic":
            if lid == "andreas":
                l.state = "mustered"
                l.location = "dorpat"
                # A Mustered Lord needs a regular Force to remain after
                # Crusade's Special Vassals leave (1.6).
                l.forces = {"knights": 1}
            else:
                l.state = "ready"
                l.location = None
    s.decks.teutonic.capabilities_in_play = list(caps)


def _advance_out_of_levy(s, russian_args=None):
    s.meta.phase = "levy"
    s.meta.levy_step = "call_to_arms"
    s.meta.active_player = "teutonic"
    s.meta.levy_step_completed_t = False
    s.meta.levy_step_completed_r = False
    apply_action(s, {"type": "advance_step", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "advance_step", "side": "russian",
                     "args": russian_args or {}})


def _discard(s, card, side="teutonic"):
    return apply_action(s, {"type": "discard_excess_capability", "side": side,
                            "args": {"card_id": card}})


def test_referee_can_replay_both_explicit_discards():
    s = load_scenario("crusade_on_novgorod", seed=42)
    _one_teuton_mustered(s, ["T1", "T12", "T11"])
    _advance_out_of_levy(s, {"rule_4_0_discards": {"teutonic": ["T1", "T12"]}})
    assert s.decks.teutonic.capabilities_in_play == ["T11"]
    assert "T1" in s.decks.teutonic.discard
    assert "T12" in s.decks.teutonic.discard


def test_partial_referee_selection_leaves_remaining_player_choice():
    s = load_scenario("crusade_on_novgorod", seed=42)
    _one_teuton_mustered(s, ["T1", "T12", "T11"])
    _advance_out_of_levy(s, {"rule_4_0_discards": {"teutonic": ["T1"]}})
    assert s.decks.teutonic.capabilities_in_play == ["T12", "T11"]
    assert s.meta.campaign_step == "capability_discard"
    _discard(s, "T11")
    assert s.decks.teutonic.capabilities_in_play == ["T12"]
    assert s.meta.campaign_step == "plan"


def test_each_side_discards_until_its_live_capability_limit_is_met():
    s = load_scenario("crusade_on_novgorod", seed=42)
    _one_teuton_mustered(s, ["T1", "T12", "T11"])
    s.decks.russian.capabilities_in_play = ["R7", "R8", "R9", "R10", "R15"]
    russian_count = sum(lord.state == "mustered" and lord.side == "russian"
                        for lord in s.lords.values())
    _advance_out_of_levy(s)
    assert s.meta.active_player == "teutonic"
    assert [move["args"]["card_id"] for move in legal_moves(s)] == ["T1", "T12", "T11"]
    _discard(s, "T12")
    assert s.meta.active_player == "teutonic"
    _discard(s, "T1")
    assert s.decks.teutonic.capabilities_in_play == ["T11"]
    assert s.meta.active_player == "russian"
    while len(s.decks.russian.capabilities_in_play) > russian_count:
        _discard(s, s.decks.russian.capabilities_in_play[0], "russian")
    assert s.meta.campaign_step == "plan" and s.meta.active_player == "teutonic"


def test_named_discard_cascades_cleanup():
    """Choosing T11 (Crusade) runs the SMOKE-031 cascade: Summer
    Crusaders Disband when their card leaves play."""
    s = load_scenario("crusade_on_novgorod", seed=42)
    _one_teuton_mustered(s, ["T1", "T12", "T11"])
    vid = "andreas_summer_crusaders_1"
    s.lords["andreas"].vassals[vid].mustered = True
    s.lords["andreas"].vassals[vid].ready = True
    pre_k = s.lords["andreas"].forces.get("knights", 0)
    s.lords["andreas"].forces["knights"] = pre_k + 3

    _advance_out_of_levy(s, {"rule_4_0_discards": {"teutonic": ["T11", "T12"]}})
    assert s.decks.teutonic.capabilities_in_play == ["T1"]
    vs = s.lords["andreas"].vassals[vid]
    assert vs.mustered is False and vs.ready is False
    assert s.lords["andreas"].forces.get("knights", 0) == pre_k


def test_validation_not_in_play_over_count_duplicates():
    for bad in (
        {"teutonic": ["T9"]},           # not in play
        {"teutonic": ["T1", "T12", "T11"]},  # 3 named, excess only 2
        {"teutonic": ["T1", "T1"]},     # duplicate
        "T1",                            # wrong shape
    ):
        s = load_scenario("crusade_on_novgorod", seed=42)
        _one_teuton_mustered(s, ["T1", "T12", "T11"])
        with pytest.raises(IllegalAction):
            _advance_out_of_levy(s, {"rule_4_0_discards": bad})


def test_no_excess_side_may_not_name_discards():
    """4.0 discards only the excess; with no excess, naming cards is an
    error (no voluntary discard through this window)."""
    s = load_scenario("crusade_on_novgorod", seed=42)
    _one_teuton_mustered(s, ["T1"])  # 1 cap, 1 Mustered Lord -> no excess
    with pytest.raises(IllegalAction):
        _advance_out_of_levy(s, {"rule_4_0_discards": {"teutonic": ["T1"]}})
