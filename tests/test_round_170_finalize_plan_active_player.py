"""SMOKE-109 (Round 170): `finalize_plan` did not switch active_player
when only one side had finalized, leaving the other side's Plan moves
unreachable.

`legal_moves` keys its enumeration off `state.meta.active_player`. The
Plan step (4.1) requires BOTH sides to finalize before advancing to
Command Activation. Pre-fix, after Teutonic called finalize_plan,
active_player stayed on "teutonic"; Russian's plan_add_card /
finalize_plan moves were not enumerated; the agent saw zero legal
moves and stalled.

Same audit pattern as SMOKE-106/107 (state-set-but-unreachable):
state.meta.plan_complete_t becomes True, but the path to set
plan_complete_r was blocked.

Fix: after a one-sided finalize, swap active_player to the other side
if the other side hasn't finalized yet. After BOTH finalize, the
existing transition to "command" + active_player=teutonic stays.

Discovered via self-play (R170 / scripts/self_play.py).
"""
from __future__ import annotations

import inspect

import nevsky.actions  # noqa: F401
import nevsky.campaign as camp
from nevsky.actions import apply_action
from nevsky.scenarios import load_scenario


def test_smoke_109_marker_present():
    src = inspect.getsource(camp._h_finalize_plan)
    assert "SMOKE-109" in src


def test_smoke_109_swap_to_russian_after_teutonic_finalizes():
    """After Teutonic finalize_plan, active_player switches to Russian
    (if Russian hasn't finalized)."""
    s = load_scenario("watland", seed=1)
    # Fast-forward to Plan step.
    s.meta.phase = "campaign"
    s.meta.campaign_step = "plan"
    s.meta.active_player = "teutonic"
    s.meta.plan_complete_t = False
    s.meta.plan_complete_r = False
    # Set Teutonic plan to target size (4 cards for box 4).
    target = camp._plan_target_size(s.meta.box)
    s.decks.teutonic.plan = ["pass"] * target
    apply_action(s, {"type": "finalize_plan", "side": "teutonic", "args": {}})
    assert s.meta.plan_complete_t is True
    assert s.meta.plan_complete_r is False
    assert s.meta.active_player == "russian"
    assert s.meta.campaign_step == "plan"  # not yet command


def test_smoke_109_swap_to_teutonic_after_russian_first_finalizes():
    """Mirror: if Russian finalizes first, active_player swaps to T."""
    s = load_scenario("watland", seed=1)
    s.meta.phase = "campaign"
    s.meta.campaign_step = "plan"
    s.meta.active_player = "russian"
    s.meta.plan_complete_t = False
    s.meta.plan_complete_r = False
    target = camp._plan_target_size(s.meta.box)
    s.decks.russian.plan = ["pass"] * target
    apply_action(s, {"type": "finalize_plan", "side": "russian", "args": {}})
    assert s.meta.plan_complete_r is True
    assert s.meta.plan_complete_t is False
    assert s.meta.active_player == "teutonic"


def test_smoke_109_both_finalize_advances_to_command():
    """After both sides finalize, transition to command, active=teutonic."""
    s = load_scenario("watland", seed=1)
    s.meta.phase = "campaign"
    s.meta.campaign_step = "plan"
    s.meta.active_player = "teutonic"
    s.meta.plan_complete_t = False
    s.meta.plan_complete_r = False
    target = camp._plan_target_size(s.meta.box)
    s.decks.teutonic.plan = ["pass"] * target
    s.decks.russian.plan = ["pass"] * target
    apply_action(s, {"type": "finalize_plan", "side": "teutonic", "args": {}})
    assert s.meta.active_player == "russian"
    apply_action(s, {"type": "finalize_plan", "side": "russian", "args": {}})
    assert s.meta.plan_complete_t is True
    assert s.meta.plan_complete_r is True
    assert s.meta.campaign_step == "command"
    assert s.meta.active_player == "teutonic"


def test_smoke_109_legal_moves_offer_russian_plan_after_teutonic_finalize():
    """Integration: legal_moves enumerates Russian plan options after
    Teutonic finalize."""
    from nevsky.legal_moves import legal_moves
    s = load_scenario("watland", seed=1)
    s.meta.phase = "campaign"
    s.meta.campaign_step = "plan"
    s.meta.active_player = "teutonic"
    s.meta.plan_complete_t = False
    s.meta.plan_complete_r = False
    target = camp._plan_target_size(s.meta.box)
    s.decks.teutonic.plan = ["pass"] * target
    apply_action(s, {"type": "finalize_plan", "side": "teutonic", "args": {}})
    moves = legal_moves(s, with_previews=False)
    # Now Russian must be active and offered Plan options.
    types = {m["type"] for m in moves if m.get("side") == "russian"}
    assert "plan_add_card" in types or "finalize_plan" in types
