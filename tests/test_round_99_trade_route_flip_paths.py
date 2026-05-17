"""SMOKE-091 (Round 99): Trade-Route auto-flip not triggered on Avoid
Battle / Battle Retreat / Sally Retreat movements.

Per Strongholds reference (SMOKE-020): "Trade Routes ... flip simply
by an enemy Lord's presence with no friendly Lord contesting."

R34/SMOKE-020 wired `_flip_trade_route_if_uncontested` for cmd_march
and cmd_sail. But three other movement paths also place a Lord on a
new locale and were missed:

  - `_h_avoid_battle` — defender Avoids to a non-enemy-Lord locale,
    which could be a Russian trade_route (Avoid permits trade_route
    as dest since `_has_enemy_stronghold_at` returns False for
    trade_route per the SMOKE-020 design).
  - Battle Aftermath Retreat — loser Lord moves to `target`.
  - Sally Aftermath Retreat — besieger retreats to a clear neighbor.

In all three cases, if the target is an enemy trade_route with no
contesting friendly Lord, the flip should fire.

Fix: add `_flip_trade_route_if_uncontested(state, dest, side)` after
each location assignment.
"""
from __future__ import annotations

import inspect

import nevsky.actions  # noqa: F401
import nevsky.campaign as camp


def test_avoid_battle_calls_trade_route_flip():
    src = inspect.getsource(camp._h_avoid_battle)
    assert "SMOKE-091" in src
    assert "_flip_trade_route_if_uncontested" in src


def test_battle_retreat_calls_trade_route_flip():
    src = inspect.getsource(camp._h_stand_battle)
    # Should appear in Battle Retreat path
    assert "SMOKE-091" in src
    # check the specific flip call is present
    flip_count = src.count("_flip_trade_route_if_uncontested(state, target, lord.side)")
    assert flip_count >= 1


def test_sally_retreat_calls_trade_route_flip():
    src = inspect.getsource(camp._h_cmd_sally)
    assert "SMOKE-091" in src
    flip_count = src.count("_flip_trade_route_if_uncontested(state, target, l.side)")
    assert flip_count >= 1


def test_end_to_end_avoid_into_russian_trade_route_flips():
    """Functional end-to-end: Teutonic defender Avoids into a Russian
    trade_route via Waterway, the auto-flip fires."""
    from nevsky.scenarios import load_scenario
    from nevsky.state import CombatPending
    from nevsky.actions import apply_action

    s = load_scenario("crusade_on_novgorod", seed=1)
    s.meta.box = 1
    hermann = s.lords["hermann"]
    hermann.location = "kaibolovo"
    hermann.state = "mustered"
    hermann.in_stronghold = False
    aleksandr = s.lords["aleksandr"]
    aleksandr.location = "kaibolovo"
    aleksandr.state = "mustered"
    aleksandr.in_stronghold = False
    s.combat_pending = CombatPending(
        attacker_side="russian", attacker_group=["aleksandr"],
        from_locale="vod", to_locale="kaibolovo", way_type="trackway",
        defender_side="teutonic", defender_lords=["hermann"],
        pending_response_by="teutonic", laden=False,
    )
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.active_player = "teutonic"
    s.campaign_turn.active_lord = "aleksandr"
    s.campaign_turn.actions_remaining = 0
    s.campaign_turn.in_feed_pay_disband = False

    assert s.locales["luga"].teutonic_conquered == 0
    apply_action(s, {"type": "avoid_battle", "side": "teutonic",
                      "args": {"to": "luga", "way_type": "waterway"}})
    # Trade-route should have flipped on entry.
    assert s.locales["luga"].teutonic_conquered == 1
