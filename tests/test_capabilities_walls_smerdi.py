"""Tests for Phase 4a Stone Kremlin / Stonemasons / Trebuchets / Smerdi."""

from __future__ import annotations

import pytest

from nevsky.actions import IllegalAction, apply_action
from nevsky.scenarios import load_scenario
from nevsky.state import GameState


def _start_command_with(s: GameState, lord_id: str) -> None:
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.active_player = s.lords[lord_id].side
    s.campaign_turn.next_to_reveal = s.lords[lord_id].side
    s.campaign_turn.active_card = lord_id
    s.campaign_turn.active_lord = lord_id
    from nevsky.campaign import _effective_command_rating
    s.campaign_turn.actions_remaining = _effective_command_rating(s, lord_id)
    s.campaign_turn.in_feed_pay_disband = False
    s.lords[lord_id].moved_fought = False


def test_stone_kremlin_marks_walls_plus_one() -> None:
    """R18: Stone Kremlin: full Command at Russian Fort/City/Novgorod adds Walls +1."""
    s = load_scenario("watland", seed=1)
    rus = next(lid for lid, l in s.lords.items() if l.side == "russian" and l.state == "mustered")
    s.lords[rus].location = "novgorod"
    s.lords[rus].this_lord_capabilities = ["R18"]
    _start_command_with(s, rus)
    apply_action(s, {"type": "cmd_stone_kremlin", "side": "russian", "args": {"lord_id": rus}})
    assert s.locales["novgorod"].walls_plus_one is True


def test_stone_kremlin_rejected_at_non_russian_locale() -> None:
    s = load_scenario("watland", seed=1)
    rus = next(lid for lid, l in s.lords.items() if l.side == "russian" and l.state == "mustered")
    s.lords[rus].location = "riga"  # Teutonic
    s.lords[rus].this_lord_capabilities = ["R18"]
    _start_command_with(s, rus)
    with pytest.raises(IllegalAction) as exc:
        apply_action(s, {"type": "cmd_stone_kremlin", "side": "russian", "args": {"lord_id": rus}})
    assert exc.value.code == "not_russian_locale"


def test_stonemasons_converts_fort_to_castle() -> None:
    """T17: Stonemasons builds a Castle at an Unbesieged Fort/Town in Rus, full card + 6 Provender."""
    s = load_scenario("watland", seed=1)
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    # Move Teu to a Russian Fort.
    fort = next(lid for lid, info in __import__("nevsky.static_data", fromlist=["load_locales"]).load_locales().items()
                if info.get("type") == "fort" and info.get("territory") == "russian")
    s.lords[teu].location = fort
    s.lords[teu].this_lord_capabilities = ["T17"]
    s.lords[teu].assets["provender"] = 6
    _start_command_with(s, teu)
    apply_action(s, {"type": "cmd_stonemasons", "side": "teutonic", "args": {"lord_id": teu}})
    assert s.locales[fort].teutonic_castle is True
    assert s.lords[teu].assets.get("provender", 0) == 0


def test_smerdi_musters_serf() -> None:
    """R4: Smerdi action; Russian Lord Unbesieged in Rus +1 Serf, costs 1 action."""
    s = load_scenario("watland", seed=1)
    rus = next(lid for lid, l in s.lords.items() if l.side == "russian" and l.state == "mustered")
    s.lords[rus].location = "novgorod"
    s.decks.russian.capabilities_in_play = ["R4"]
    _start_command_with(s, rus)
    pre = s.lords[rus].forces.get("serfs", 0)
    pre_actions = s.campaign_turn.actions_remaining
    apply_action(s, {"type": "cmd_muster_serf", "side": "russian", "args": {"lord_id": rus}})
    assert s.lords[rus].forces["serfs"] == pre + 1
    assert s.campaign_turn.actions_remaining == pre_actions - 1


def test_smerdi_rejected_outside_rus() -> None:
    s = load_scenario("watland", seed=1)
    rus = next(lid for lid, l in s.lords.items() if l.side == "russian" and l.state == "mustered")
    s.lords[rus].location = "riga"
    s.decks.russian.capabilities_in_play = ["R4"]
    _start_command_with(s, rus)
    with pytest.raises(IllegalAction) as exc:
        apply_action(s, {"type": "cmd_muster_serf", "side": "russian", "args": {"lord_id": rus}})
    assert exc.value.code == "not_in_rus"


def test_walls_plus_one_increases_storm_walls_max() -> None:
    """R18: Walls +1 marker raises a Walls 1-3 to 1-4 in Storm.

    Smoke: just verify cmd_storm at a Walls+1 locale doesn't crash and
    the marker is removed if Sacked. Because Storm outcome is RNG, we
    don't assert the winner here -- only that on attacker win the
    marker is cleared."""
    s = load_scenario("pleskau", seed=7)
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    s.lords[teu].location = "pskov"
    rus = next(lid for lid, l in s.lords.items() if l.side == "russian" and l.state == "mustered")
    s.lords[rus].location = "pskov"
    s.lords[rus].in_stronghold = True
    s.locales["pskov"].siege_markers = 3
    s.locales["pskov"].walls_plus_one = True
    _start_command_with(s, teu)
    res = apply_action(s, {"type": "cmd_storm", "side": "teutonic", "args": {"lord_id": teu}})
    # Whichever side wins, the test should run cleanly.
    if res["battle"]["winner"] == "attacker":
        assert s.locales["pskov"].walls_plus_one is False
    else:
        # Walls +1 stays.
        assert s.locales["pskov"].walls_plus_one is True
