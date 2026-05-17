"""SMOKE-100 (Round 120): Sail doesn't honor 1.7.2 voluntary asset
discard. Per rule 1.7.2 Greed, Lords MAY discard Loot and Provender
when Sailing (4.7.3 listed alongside March/Avoid/Retreat). Before
this fix the Sail handler had no discard arg, so a Lord with extra
assets and a Ship budget too tight could not voluntarily drop
assets to fit; Sail failed with insufficient_ships.

Fix: accept args.discard_excess_provender and args.discard_excess_loot
(True=all, int=cap). Discard happens BEFORE the ship-budget check
so the check uses post-discard totals. Loot is discarded first
(2 Ships saved per discard) then Provender.
"""
from __future__ import annotations

import inspect

import nevsky.actions  # noqa: F401
from nevsky.actions import apply_action, IllegalAction
import nevsky.campaign as camp
from nevsky.scenarios import load_scenario


def _setup_sail_state(prov, loot, ships):
    s = load_scenario("watland", seed=11)
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "teutonic", "args": {}})
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    s.lords[teu].location = "riga"
    s.lords[teu].forces.clear()
    s.lords[teu].forces["men_at_arms"] = 1  # foot only — no horse cost
    s.lords[teu].assets = {"provender": prov, "loot": loot, "ship": ships}
    s.meta.box = 1  # Summer
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.active_player = "teutonic"
    s.campaign_turn.active_lord = teu
    s.campaign_turn.actions_remaining = 1
    s.campaign_turn.next_to_reveal = "teutonic"
    s.campaign_turn.in_feed_pay_disband = False
    return s, teu


def test_sail_discard_provender_lets_sail_succeed():
    # Prov=5, Loot=0, Ships=3 — need 5 ships for prov, have 3.
    # Discard 2 Provender → need 3, have 3 → SUCCEED.
    s, teu = _setup_sail_state(prov=5, loot=0, ships=3)
    apply_action(s, {
        "type": "cmd_sail", "side": "teutonic",
        "args": {"lord_id": teu, "destination": "reval", "group": [teu],
                 "discard_excess_provender": True},
    })
    assert s.lords[teu].location == "reval"
    assert s.lords[teu].assets.get("provender", 0) == 0


def test_sail_discard_loot_lets_sail_succeed():
    # Loot=2, Ships=3 — need 4 ships for loot, have 3.
    # Discard 1 Loot → need 2, have 3 → SUCCEED.
    s, teu = _setup_sail_state(prov=0, loot=2, ships=3)
    apply_action(s, {
        "type": "cmd_sail", "side": "teutonic",
        "args": {"lord_id": teu, "destination": "reval", "group": [teu],
                 "discard_excess_loot": True},
    })
    assert s.lords[teu].location == "reval"
    assert s.lords[teu].assets.get("loot", 0) == 0


def test_sail_without_discard_still_fails_when_insufficient():
    """Without discard arg, Sail still fails when ships are short."""
    s, teu = _setup_sail_state(prov=5, loot=0, ships=2)
    try:
        apply_action(s, {
            "type": "cmd_sail", "side": "teutonic",
            "args": {"lord_id": teu, "destination": "reval", "group": [teu]},
        })
        assert False, "should have raised insufficient_ships"
    except IllegalAction as e:
        assert str(e.args[0]).startswith("insufficient_ships")


def test_sail_handler_documents_smoke100():
    src = inspect.getsource(camp._h_cmd_sail)
    assert "SMOKE-100" in src
    assert "discard_excess_provender" in src
    assert "discard_excess_loot" in src
