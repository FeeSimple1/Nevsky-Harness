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
    """4.1.3: Lieutenant + Lower Lord at same Locale.

    Q-003: pair non-Marshal Lords (yaroslav + knud_and_abel) so the
    Marshal-exclusion check does not block the basic happy-path test.
    """
    s = load_scenario("watland", seed=1)
    _enter_plan(s)
    s.lords["yaroslav"].location = "fellin"
    s.lords["knud_and_abel"].location = "fellin"
    apply_action(s, {"type": "place_lieutenant", "side": "teutonic",
                     "args": {"lieutenant": "yaroslav", "lower_lord": "knud_and_abel"}})
    assert s.lords["yaroslav"].has_lower_lord == "knud_and_abel"
    assert s.lords["knud_and_abel"].lieutenant_of == "yaroslav"


def test_place_lieutenant_rejects_different_locales() -> None:
    s = load_scenario("watland", seed=1)
    _enter_plan(s)
    # andreas @ fellin; yaroslav @ pskov.
    with pytest.raises(IllegalAction) as exc:
        apply_action(s, {"type": "place_lieutenant", "side": "teutonic",
                          "args": {"lieutenant": "andreas", "lower_lord": "yaroslav"}})
    assert exc.value.code == "not_co_located"


def test_place_lieutenant_rejects_chains() -> None:
    """4.1.3: Lower Lord cannot also be a Lieutenant. Q-003: rebuild
    using non-Marshal Lords. We need three co-located non-Marshal
    Teutonic Lords; force-Muster heinrich at fellin to round out the
    set."""
    s = load_scenario("watland", seed=1)
    _enter_plan(s)
    # Force heinrich Mustered at fellin to have three non-Marshals there.
    s.lords["heinrich"].state = "mustered"
    s.lords["heinrich"].location = "fellin"
    s.lords["yaroslav"].location = "fellin"
    s.lords["knud_and_abel"].location = "fellin"
    apply_action(s, {"type": "place_lieutenant", "side": "teutonic",
                     "args": {"lieutenant": "yaroslav", "lower_lord": "heinrich"}})
    with pytest.raises(IllegalAction) as exc:
        apply_action(s, {"type": "place_lieutenant", "side": "teutonic",
                          "args": {"lieutenant": "heinrich", "lower_lord": "knud_and_abel"}})
    assert exc.value.code == "no_chains"


def test_lower_lord_card_resolves_as_pass() -> None:
    """4.2.3: Revealing a Lower Lord's card resolves as Pass. Q-003:
    use non-Marshal Lieutenant (yaroslav) over non-Marshal Lower Lord
    (knud_and_abel)."""
    s = load_scenario("watland", seed=1)
    _enter_plan(s)
    s.lords["yaroslav"].location = "fellin"
    s.lords["knud_and_abel"].location = "fellin"
    apply_action(s, {"type": "place_lieutenant", "side": "teutonic",
                     "args": {"lieutenant": "yaroslav", "lower_lord": "knud_and_abel"}})
    # Set up Plan with knud_and_abel (Lower Lord) card to reveal.
    from nevsky.campaign import _plan_target_size
    target = _plan_target_size(s.meta.box)
    s.decks.teutonic.plan = ["knud_and_abel"] + ["pass"] * (target - 1)
    s.decks.russian.plan = ["pass"] * target
    apply_action(s, {"type": "finalize_plan", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "finalize_plan", "side": "russian", "args": {}})
    res = apply_action(s, {"type": "command_reveal", "side": "teutonic", "args": {}})
    assert res["outcome"] == "pass_lower_lord"
    assert res["lieutenant_of"] == "yaroslav"


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


# ---------------------------------------------------------------------------
# Q-003 regression tests: Marshal-exclusion in Lieutenant pairings (4.1.3)
# ---------------------------------------------------------------------------


def test_q003_permanent_marshal_rejected_as_lieutenant() -> None:
    """4.1.3 + Q-003: a permanent-role Marshal (Andreas) cannot be
    Lieutenant, even when co-located with a non-Marshal candidate."""
    s = load_scenario("watland", seed=1)
    _enter_plan(s)
    s.lords["andreas"].location = "fellin"
    s.lords["yaroslav"].location = "fellin"
    with pytest.raises(IllegalAction) as exc:
        apply_action(s, {"type": "place_lieutenant", "side": "teutonic",
                          "args": {"lieutenant": "andreas", "lower_lord": "yaroslav"}})
    assert exc.value.code == "marshal_lieutenant"
    # Reverse role test: Andreas as Lower Lord also rejected.
    with pytest.raises(IllegalAction) as exc2:
        apply_action(s, {"type": "place_lieutenant", "side": "teutonic",
                          "args": {"lieutenant": "yaroslav", "lower_lord": "andreas"}})
    assert exc2.value.code == "marshal_lower_lord"


def test_q003_permanent_marshal_rejected_russian_side() -> None:
    """Same rule for Aleksandr (permanent Marshal, Russian)."""
    s = load_scenario("crusade_on_novgorod", seed=1)
    _enter_plan(s)
    s.meta.active_player = "russian"
    # Aleksandr starts off-map in crusade scenario; force-Muster him at neva.
    s.lords["aleksandr"].state = "mustered"
    s.lords["aleksandr"].location = "novgorod"
    s.lords["vladislav"].location = "novgorod"
    with pytest.raises(IllegalAction) as exc:
        apply_action(s, {"type": "place_lieutenant", "side": "russian",
                          "args": {"lieutenant": "aleksandr", "lower_lord": "vladislav"}})
    assert exc.value.code == "marshal_lieutenant"


def test_q003_secondary_marshal_accepted_when_inactive() -> None:
    """Q-003 permissive: a secondary-role Marshal (Hermann) is ACCEPTED
    in a Lieutenant pairing when not actively filling the Marshal role.
    Until Q-005 lands per-Lord Front position state, secondary
    Marshals are always treated as inactive.
    """
    s = load_scenario("watland", seed=1)
    _enter_plan(s)
    # Watland doesn't start Hermann mustered; do so by hand.
    s.lords["hermann"].state = "mustered"
    s.lords["hermann"].location = "fellin"
    s.lords["yaroslav"].location = "fellin"
    apply_action(s, {"type": "place_lieutenant", "side": "teutonic",
                     "args": {"lieutenant": "hermann", "lower_lord": "yaroslav"}})
    assert s.lords["hermann"].has_lower_lord == "yaroslav"
    assert s.lords["yaroslav"].lieutenant_of == "hermann"


def test_q003_non_marshal_lord_accepted() -> None:
    """Q-003: a Lord with marshal_role: null is never barred on
    Marshal grounds. Yaroslav + Knud&Abel pairing should succeed.
    """
    s = load_scenario("watland", seed=1)
    _enter_plan(s)
    s.lords["yaroslav"].location = "fellin"
    s.lords["knud_and_abel"].location = "fellin"
    apply_action(s, {"type": "place_lieutenant", "side": "teutonic",
                     "args": {"lieutenant": "yaroslav", "lower_lord": "knud_and_abel"}})
    assert s.lords["yaroslav"].has_lower_lord == "knud_and_abel"


def test_q003_is_currently_marshal_helper() -> None:
    """Direct unit test of the _is_currently_marshal helper: permanent
    Marshals (Andreas, Aleksandr) are always currently-Marshal once
    Mustered; secondary Marshals (Hermann, Andrey) are not (until
    Q-005); other Lords are not.
    """
    from nevsky.campaign import _is_currently_marshal
    s = load_scenario("watland", seed=1)
    s.lords["andreas"].state = "mustered"
    s.lords["andreas"].location = "fellin"
    s.lords["hermann"].state = "mustered"
    s.lords["hermann"].location = "fellin"
    s.lords["yaroslav"].state = "mustered"
    s.lords["yaroslav"].location = "fellin"
    assert _is_currently_marshal(s, "andreas") is True
    assert _is_currently_marshal(s, "hermann") is False  # secondary, treated inactive
    assert _is_currently_marshal(s, "yaroslav") is False
    # Off-map permanent Marshal: not currently a Marshal.
    s.lords["andreas"].state = "ready"
    s.lords["andreas"].location = None
    assert _is_currently_marshal(s, "andreas") is False
