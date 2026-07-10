"""PLAY-34 regression tests: 4.0 excess side-Capability discard is a choice.

Rule 4.0 CAPABILITY DISCARD: "The players (Teutonic first) must SELECT
and discard any Capability cards they have in excess of their number of
Mustered Lords -- not including any 'This Lord' Capabilities (3.4.4)."

Before PLAY-34 the engine silently popped the tail of
`capabilities_in_play` -- the owner never chose WHICH cards to lose.
`advance_step` (on the call that completes Call to Arms and enters
Campaign Plan) now accepts `args.rule_4_0_discards = {side: [card_id,
...]}` naming each side's discards. Named cards are validated (in play
for that side, no duplicates, at most the excess count) and discarded
first, with per-card cascade cleanup (SMOKE-031); any remaining excess
still falls back to the deterministic tail-drop.
"""
from __future__ import annotations

import pytest

from nevsky.actions import IllegalAction, apply_action
from nevsky.scenarios import load_scenario


def _one_teuton_mustered(s, caps):
    for lid, l in s.lords.items():
        if l.side == "teutonic":
            if lid == "andreas":
                l.state = "mustered"
                l.location = "dorpat"
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


def test_named_discards_override_tail_drop():
    """Excess 2 with caps [T1, T12, T11]: naming T1+T12 keeps T11 in
    play -- the old tail-drop could ONLY ever keep T1."""
    s = load_scenario("crusade_on_novgorod", seed=42)
    _one_teuton_mustered(s, ["T1", "T12", "T11"])
    _advance_out_of_levy(s, {"rule_4_0_discards": {"teutonic": ["T1", "T12"]}})
    assert s.decks.teutonic.capabilities_in_play == ["T11"]
    assert "T1" in s.decks.teutonic.discard
    assert "T12" in s.decks.teutonic.discard


def test_partial_selection_falls_back_to_tail_for_remainder():
    """Excess 2, name only T1: T1 goes by choice, then the tail (T11)
    goes by fallback; T12 survives."""
    s = load_scenario("crusade_on_novgorod", seed=42)
    _one_teuton_mustered(s, ["T1", "T12", "T11"])
    _advance_out_of_levy(s, {"rule_4_0_discards": {"teutonic": ["T1"]}})
    assert s.decks.teutonic.capabilities_in_play == ["T12"]


def test_default_tail_drop_unchanged():
    """No args: pre-PLAY-34 deterministic tail-drop (T11 then T12)."""
    s = load_scenario("crusade_on_novgorod", seed=42)
    _one_teuton_mustered(s, ["T1", "T12", "T11"])
    _advance_out_of_levy(s)
    assert s.decks.teutonic.capabilities_in_play == ["T1"]


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
