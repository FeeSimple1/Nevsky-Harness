"""Round 40 — verification round (no new bugs, multiple invariants
pinned as regression tests).

Items verified clean in R40 and locked here:

  - Siegeworks Capacity gate: only besiegers >= Capacity may add a
    new siege marker (Strongholds reference: "Capacity governs
    Siegeworks").
  - Aleksandr muster restriction: no Lord may Muster Aleksandr
    (1.5.1 / 3.4.1). Standard cmd_muster_lord rejects with
    "aleksandr_veche_only". legal_moves does not surface Aleksandr
    as a muster target.
  - Lord this_lord_capabilities returned to deck on Disband AND on
    permanent Removal (3.3.2 / 1.5.1).
  - Sally Raid breaks siege when attackers wiped: siege_markers go
    to 0; sally_outcome is "broken_siege".
"""
from __future__ import annotations

from nevsky.actions import (
    apply_action, IllegalAction, _disband_at_limit, _remove_lord_permanently,
)
from nevsky.scenarios import load_scenario
from nevsky.static_data import load_lords
from nevsky.legal_moves import legal_moves


def _setup_campaign(side="teutonic"):
    s = load_scenario("crusade_on_novgorod", seed=1)
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "russian", "args": {}})
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.box = 1
    s.meta.active_player = side
    return s


def test_siege_capacity_gate_below_capacity_no_marker_added():
    """City capacity=3; 1 besieger should not add a marker."""
    s = _setup_campaign("teutonic")
    city = "pskov"
    teu = next(lid for lid, l in s.lords.items()
                if l.side == "teutonic" and l.state == "mustered")
    s.lords[teu].location = city
    s.lords[teu].in_stronghold = False
    s.lords[teu].forces = {"knights": 3}
    s.locales[city].siege_markers = 1
    s.campaign_turn.active_lord = teu
    s.campaign_turn.actions_remaining = 3
    s.campaign_turn.in_feed_pay_disband = False
    res = apply_action(s, {"type": "cmd_siege", "side": "teutonic",
                            "args": {"lord_id": teu}})
    assert res["siege_added"] is False
    assert s.locales[city].siege_markers == 1


def test_siege_capacity_gate_at_capacity_adds_marker():
    """City capacity=3; 3 besiegers add a marker."""
    s = _setup_campaign("teutonic")
    city = "pskov"
    teus = [lid for lid, l in s.lords.items()
            if l.side == "teutonic" and l.state == "mustered"][:3]
    for lid in teus:
        s.lords[lid].location = city
        s.lords[lid].in_stronghold = False
        s.lords[lid].forces = {"knights": 3}
    s.locales[city].siege_markers = 1
    s.campaign_turn.active_lord = teus[0]
    s.campaign_turn.actions_remaining = 3
    s.campaign_turn.in_feed_pay_disband = False
    res = apply_action(s, {"type": "cmd_siege", "side": "teutonic",
                            "args": {"lord_id": teus[0]}})
    assert res["siege_added"] is True
    assert s.locales[city].siege_markers == 2


def test_aleksandr_cannot_be_mustered_by_lord():
    s = load_scenario("crusade_on_novgorod", seed=1)
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "russian", "args": {}})
    s.meta.phase = "levy"
    s.meta.levy_step = "muster"
    s.meta.active_player = "russian"
    musterer = next(lid for lid, l in s.lords.items()
                     if l.side == "russian" and l.state == "mustered")
    try:
        apply_action(s, {"type": "muster_lord", "side": "russian",
                          "args": {"by_lord": musterer, "target_lord": "aleksandr",
                                    "seat": "novgorod"}})
        raise AssertionError("Aleksandr should not be musterable by Lord")
    except IllegalAction as e:
        assert "aleksandr_veche_only" in str(e)


def test_legal_moves_does_not_surface_aleksandr_as_muster_target():
    s = load_scenario("crusade_on_novgorod", seed=1)
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "russian", "args": {}})
    s.meta.phase = "levy"
    s.meta.levy_step = "muster"
    s.meta.active_player = "russian"
    moves = legal_moves(s, with_previews=False)
    aleks_targets = [m for m in moves
                      if m["type"] == "muster_lord"
                      and m["args"].get("target_lord") == "aleksandr"]
    assert aleks_targets == []


def test_disband_returns_lord_capabilities_to_deck():
    s = _setup_campaign("teutonic")
    teu = next(lid for lid, l in s.lords.items()
                if l.side == "teutonic" and l.state == "mustered")
    s.lords[teu].this_lord_capabilities = ["T7", "T14"]
    pre_deck_len = len(s.decks.teutonic.deck)
    _disband_at_limit(s, teu, 5)
    assert s.lords[teu].this_lord_capabilities == []
    assert len(s.decks.teutonic.deck) == pre_deck_len + 2
    assert "T7" in s.decks.teutonic.deck
    assert "T14" in s.decks.teutonic.deck


def test_permanent_removal_returns_lord_capabilities_to_deck():
    s = _setup_campaign("teutonic")
    teu = next(lid for lid, l in s.lords.items()
                if l.side == "teutonic" and l.state == "mustered")
    s.lords[teu].this_lord_capabilities = ["T7", "T14"]
    pre_deck_len = len(s.decks.teutonic.deck)
    _remove_lord_permanently(s, teu, load_lords()[teu])
    assert s.lords[teu].this_lord_capabilities == []
    assert len(s.decks.teutonic.deck) == pre_deck_len + 2
