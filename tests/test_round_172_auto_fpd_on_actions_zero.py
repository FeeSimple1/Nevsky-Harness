"""SMOKE-110 (Round 172): FPD did not auto-fire when actions
reached 0 via non-entire-card commands; the next command_reveal
popped the next card and FPD was silently skipped.

Per rule 4.8: Feed/Pay/Disband fires after every Command card. Pre-
fix the harness only fired FPD when a handler explicitly called
`_enter_feed_pay_disband` — Pass cards, entire-card commands
(Tax/Sail/Storm/Sally/Siege), and the March-into-siege branch.

Non-entire-card commands that exhaust actions naturally
(Forage/Ravage/Supply/March/Raiders Ravage) left
`actions_remaining=0` without firing FPD. Subsequent
`command_reveal` then succeeded (actions==0, not in_fpd → legal)
and popped a fresh card — FPD skipped silently. Per-card 4.8
processing was missed.

Found via scripts/self_play.py running return_of_the_prince
seed=3, which hit `plan_empty: russian Plan stack is empty` after
the agent revealed a card, did 2 marches, and tried to reveal
again with no FPD between (and Russian's plan exhausted).

Same audit pattern as SMOKE-106/107/109 (state-set-but-unreachable):
the harness moved into a state where the next legal action couldn't
include the missing step.

Fix in `_consume_actions`: when actions reach 0 AND we're in
campaign command step AND not already in_fpd AND no combat_pending
AND there's an active_lord, auto-fire `_enter_feed_pay_disband`.
"""
from __future__ import annotations

import inspect

import nevsky.actions  # noqa: F401
import nevsky.campaign as camp


def test_smoke_110_marker_present():
    src = inspect.getsource(camp._consume_actions)
    assert "SMOKE-110" in src
    assert "_enter_feed_pay_disband" in src


def test_smoke_110_skips_when_combat_pending():
    """The auto-FPD must NOT fire when combat_pending is set —
    combat resolution will fire FPD after the response."""
    src = inspect.getsource(camp._consume_actions)
    assert "combat_pending is None" in src


def test_smoke_110_skips_when_already_in_fpd():
    src = inspect.getsource(camp._consume_actions)
    assert "not state.campaign_turn.in_feed_pay_disband" in src


def test_smoke_110_requires_active_lord():
    """Pass cards already auto-FPD; auto-fire should require active_lord."""
    src = inspect.getsource(camp._consume_actions)
    assert "active_lord is not None" in src


def test_smoke_110_only_in_command_step():
    """Auto-FPD only fires in the campaign command step — not in
    other phases that might also reach actions_remaining=0."""
    src = inspect.getsource(camp._consume_actions)
    assert 'campaign_step == "command"' in src
    assert 'phase == "campaign"' in src


def test_smoke_110_behavior_forage_exhausts_actions_fires_fpd():
    """Integration: Forage uses 1 action; if it's the last action,
    FPD fires automatically."""
    from nevsky.scenarios import load_scenario
    from nevsky.actions import apply_action
    s = load_scenario("watland", seed=1)
    # Set up Lord with 1 action remaining at his own seat in summer (box 4).
    teu = next(lid for lid, l in s.lords.items()
               if l.side == "teutonic" and l.state == "mustered")
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.active_player = "teutonic"
    s.campaign_turn.active_card = teu
    s.campaign_turn.active_lord = teu
    s.campaign_turn.actions_remaining = 1
    s.campaign_turn.in_feed_pay_disband = False
    s.combat_pending = None
    # Make Lord at a friendly stronghold in summer to make Forage legal.
    from nevsky.static_data import load_lords
    seat = load_lords()[teu]["primary_seats"][0]
    s.lords[teu].location = seat
    # Clear any provender so forage adds 1.
    s.lords[teu].assets.pop("provender", None)
    # Ensure locale is not ravaged.
    s.locales[seat].russian_ravaged = False
    s.locales[seat].teutonic_ravaged = False

    res = apply_action(s, {"type": "cmd_forage", "side": "teutonic",
                            "args": {"lord_id": teu}})
    # After Forage uses last action, FPD should be in progress.
    assert s.campaign_turn.actions_remaining == 0
    assert s.campaign_turn.in_feed_pay_disband is True


def test_smoke_110_behavior_forage_with_remaining_actions_no_auto_fpd():
    """If Forage leaves actions > 0, FPD must NOT auto-fire."""
    from nevsky.scenarios import load_scenario
    from nevsky.actions import apply_action
    s = load_scenario("watland", seed=1)
    teu = next(lid for lid, l in s.lords.items()
               if l.side == "teutonic" and l.state == "mustered")
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.active_player = "teutonic"
    s.campaign_turn.active_card = teu
    s.campaign_turn.active_lord = teu
    s.campaign_turn.actions_remaining = 3  # plenty remaining
    s.campaign_turn.in_feed_pay_disband = False
    s.combat_pending = None
    from nevsky.static_data import load_lords
    seat = load_lords()[teu]["primary_seats"][0]
    s.lords[teu].location = seat
    s.lords[teu].assets.pop("provender", None)
    s.locales[seat].russian_ravaged = False
    s.locales[seat].teutonic_ravaged = False

    apply_action(s, {"type": "cmd_forage", "side": "teutonic",
                      "args": {"lord_id": teu}})
    assert s.campaign_turn.actions_remaining == 2
    assert s.campaign_turn.in_feed_pay_disband is False
