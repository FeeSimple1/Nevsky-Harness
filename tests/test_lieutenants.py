"""Tests for 4.1.3 Lieutenants."""

from __future__ import annotations

import pytest

from nevsky.actions import IllegalAction, apply_action
from nevsky.scenarios import load_scenario


def _enter_plan(s) -> None:
    s.meta.phase = "campaign"
    s.meta.campaign_step = "plan"
    s.meta.active_player = "teutonic"


def test_place_lieutenant_pairs_two_co_located_lords() -> None:
    """4.1.3: Lieutenant + Lower Lord at same Locale."""
    s = load_scenario("watland", seed=1)
    _enter_plan(s)
    s.lords["andreas"].location = "fellin"
    s.lords["yaroslav"].location = "fellin"  # co-locate
    apply_action(s, {"type": "place_lieutenant", "side": "teutonic",
                     "args": {"lieutenant": "andreas", "lower_lord": "yaroslav"}})
    assert s.lords["andreas"].has_lower_lord == "yaroslav"
    assert s.lords["yaroslav"].lieutenant_of == "andreas"


def test_place_lieutenant_rejects_different_locales() -> None:
    s = load_scenario("watland", seed=1)
    _enter_plan(s)
    # andreas @ fellin; yaroslav @ pskov.
    with pytest.raises(IllegalAction) as exc:
        apply_action(s, {"type": "place_lieutenant", "side": "teutonic",
                          "args": {"lieutenant": "andreas", "lower_lord": "yaroslav"}})
    assert exc.value.code == "not_co_located"


def test_place_lieutenant_rejects_chains() -> None:
    """4.1.3: Lower Lord cannot also be a Lieutenant."""
    s = load_scenario("watland", seed=1)
    _enter_plan(s)
    s.lords["andreas"].location = "fellin"
    s.lords["yaroslav"].location = "fellin"
    s.lords["knud_and_abel"].location = "fellin"
    apply_action(s, {"type": "place_lieutenant", "side": "teutonic",
                     "args": {"lieutenant": "andreas", "lower_lord": "yaroslav"}})
    with pytest.raises(IllegalAction) as exc:
        apply_action(s, {"type": "place_lieutenant", "side": "teutonic",
                          "args": {"lieutenant": "yaroslav", "lower_lord": "knud_and_abel"}})
    assert exc.value.code == "no_chains"


def test_lower_lord_card_resolves_as_pass() -> None:
    """4.2.3: Revealing a Lower Lord's card resolves as Pass."""
    s = load_scenario("watland", seed=1)
    _enter_plan(s)
    s.lords["andreas"].location = "fellin"
    s.lords["yaroslav"].location = "fellin"
    apply_action(s, {"type": "place_lieutenant", "side": "teutonic",
                     "args": {"lieutenant": "andreas", "lower_lord": "yaroslav"}})
    # Set up Plan with yaroslav (Lower Lord) card to reveal.
    from nevsky.campaign import _plan_target_size
    target = _plan_target_size(s.meta.box)
    s.decks.teutonic.plan = ["yaroslav"] + ["pass"] * (target - 1)
    s.decks.russian.plan = ["pass"] * target
    apply_action(s, {"type": "finalize_plan", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "finalize_plan", "side": "russian", "args": {}})
    res = apply_action(s, {"type": "command_reveal", "side": "teutonic", "args": {}})
    assert res["outcome"] == "pass_lower_lord"
    assert res["lieutenant_of"] == "andreas"


def test_end_campaign_unstacks_lieutenants() -> None:
    """4.9.5 reset: Lieutenants and Lower Lords unstack at End Campaign."""
    s = load_scenario("watland", seed=1)
    s.lords["andreas"].location = "fellin"
    s.lords["yaroslav"].location = "fellin"
    s.lords["andreas"].has_lower_lord = "yaroslav"
    s.lords["yaroslav"].lieutenant_of = "andreas"
    s.meta.phase = "campaign"
    s.meta.campaign_step = "end_campaign"
    s.meta.active_player = "teutonic"
    s.meta.end_campaign_completed_t = False
    s.meta.end_campaign_completed_r = False
    apply_action(s, {"type": "end_campaign_resolve", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "end_campaign_resolve", "side": "russian", "args": {}})
    assert s.lords["andreas"].has_lower_lord is None
    assert s.lords["yaroslav"].lieutenant_of is None
