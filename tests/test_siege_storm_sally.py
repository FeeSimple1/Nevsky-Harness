"""Tests for 4.5.1 Siege, 4.5.2 Storm, 4.5.3 Sally."""

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
    from nevsky.static_data import load_lords
    s.campaign_turn.actions_remaining = int(load_lords()[lord_id]["ratings"]["command"])
    s.campaign_turn.in_feed_pay_disband = False
    s.lords[lord_id].moved_fought = False


# --- 4.5.1 Siege ------------------------------------------------------------


def test_siege_requires_existing_siege_marker() -> None:
    """4.5.1: cmd_siege requires existing siege markers at the locale."""
    s = load_scenario("pleskau", seed=1)
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    s.lords[teu].location = "pskov"
    s.locales["pskov"].siege_markers = 0
    _start_command_with(s, teu)
    with pytest.raises(IllegalAction) as exc:
        apply_action(s, {"type": "cmd_siege", "side": "teutonic", "args": {"lord_id": teu}})
    assert exc.value.code == "no_siege"


def test_siege_surrender_succeeds_when_roll_le_siege_markers() -> None:
    """4.5.1: with no Besieged Lord inside, a 1d6 roll <= siege_markers
    Conquers the Stronghold. With siege_markers=4 we accept either
    outcome (roll 5 or 6 fails the surrender)."""
    s = load_scenario("pleskau", seed=1)
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    s.lords[teu].location = "pskov"
    # No Russian Lord at pskov (no in_stronghold defenders).
    for lid, l in s.lords.items():
        if l.location == "pskov" and l.side == "russian":
            l.location = "novgorod"
            l.in_stronghold = False
    s.locales["pskov"].siege_markers = 4
    s.locales["pskov"].russian_conquered = 0
    s.locales["pskov"].teutonic_conquered = 0
    _start_command_with(s, teu)
    pre_vp = s.calendar.teutonic_vp
    res = apply_action(s, {"type": "cmd_siege", "side": "teutonic", "args": {"lord_id": teu}})
    if res["surrender"]["conquered"]:
        # City worth 2 VP.
        assert s.locales["pskov"].teutonic_conquered == 2
        assert s.calendar.teutonic_vp == pre_vp + 2.0
    else:
        assert s.locales["pskov"].teutonic_conquered == 0


def test_siege_siegeworks_check_adds_marker_when_capacity_met() -> None:
    """4.5.1: besieger Lords >= Stronghold Capacity adds 1 Siege marker."""
    s = load_scenario("pleskau", seed=1)
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    s.lords[teu].location = "pskov"
    # Need a Lord BESIEGED inside (Russian) to skip surrender path.
    rus = next(lid for lid, l in s.lords.items() if l.side == "russian" and l.state == "mustered")
    s.lords[rus].location = "pskov"
    s.lords[rus].in_stronghold = True  # defender is Besieged inside
    s.locales["pskov"].siege_markers = 1
    # Move enough Teutonic Lords (capacity = 3 for City).
    teu_lords = [lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered"]
    for lid in teu_lords[:3]:
        s.lords[lid].location = "pskov"
    _start_command_with(s, teu)
    res = apply_action(s, {"type": "cmd_siege", "side": "teutonic", "args": {"lord_id": teu}})
    assert res["siege_added"] is True
    assert s.locales["pskov"].siege_markers == 2


def test_siege_below_capacity_no_marker_added() -> None:
    s = load_scenario("pleskau", seed=1)
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    s.lords[teu].location = "pskov"
    rus = next(lid for lid, l in s.lords.items() if l.side == "russian" and l.state == "mustered")
    s.lords[rus].location = "pskov"  # Lord inside -> skip surrender path
    s.lords[rus].in_stronghold = True
    s.locales["pskov"].siege_markers = 1
    # Only 1 Teutonic Lord at pskov; pskov City Capacity = 3.
    for lid, l in s.lords.items():
        if l.side == "teutonic" and l.state == "mustered" and lid != teu:
            l.location = "izborsk"
    _start_command_with(s, teu)
    res = apply_action(s, {"type": "cmd_siege", "side": "teutonic", "args": {"lord_id": teu}})
    assert res["siege_added"] is False


# --- 4.5.2 Storm ------------------------------------------------------------


def test_storm_trade_route_rejected() -> None:
    """4.5.2: Trade Routes cannot be Stormed (no Walls/Garrison)."""
    s = load_scenario("pleskau", seed=1)
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    # Find a Russian trade_route locale.
    from nevsky.static_data import load_locales
    locs = load_locales()
    tr = next(lid for lid, info in locs.items() if info.get("type") == "trade_route" and info.get("territory") == "russian")
    s.lords[teu].location = tr
    s.locales[tr].siege_markers = 1
    _start_command_with(s, teu)
    with pytest.raises(IllegalAction) as exc:
        apply_action(s, {"type": "cmd_storm", "side": "teutonic", "args": {"lord_id": teu}})
    assert exc.value.code == "no_storm"


def test_storm_resolves_with_winner() -> None:
    """4.5.2: Storm runs and produces an attacker or defender winner."""
    s = load_scenario("pleskau", seed=7)
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    s.lords[teu].location = "pskov"
    rus = next(lid for lid, l in s.lords.items() if l.side == "russian" and l.state == "mustered")
    s.lords[rus].location = "pskov"
    s.locales["pskov"].siege_markers = 3
    _start_command_with(s, teu)
    res = apply_action(s, {"type": "cmd_storm", "side": "teutonic", "args": {"lord_id": teu}})
    assert res["battle"]["winner"] in ("attacker", "defender")
    assert s.campaign_turn.in_feed_pay_disband is True


def test_storm_attacker_loss_storm_ends_siege_continues() -> None:
    """4.5.2: on attacker loss, storm ends and siege continues (no Spoils)."""
    s = load_scenario("pleskau", seed=1)
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    # Empty out attacker forces so attacker loses.
    s.lords[teu].location = "pskov"
    s.lords[teu].forces = {"militia": 1}
    rus = next(lid for lid, l in s.lords.items() if l.side == "russian" and l.state == "mustered")
    s.lords[rus].location = "pskov"
    s.locales["pskov"].siege_markers = 2
    _start_command_with(s, teu)
    res = apply_action(s, {"type": "cmd_storm", "side": "teutonic", "args": {"lord_id": teu}})
    if res["battle"]["winner"] == "defender":
        assert res.get("storm_failed") is True
        assert s.locales["pskov"].siege_markers >= 1  # siege continues


# --- 4.5.3 Sally ------------------------------------------------------------


def test_sally_requires_besieged_lord() -> None:
    """4.5.3: cmd_sally requires the active Lord to be Besieged."""
    s = load_scenario("pleskau", seed=1)
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    s.lords[teu].location = "izborsk"
    s.locales["izborsk"].siege_markers = 0  # not besieged
    _start_command_with(s, teu)
    with pytest.raises(IllegalAction) as exc:
        apply_action(s, {"type": "cmd_sally", "side": "teutonic", "args": {"lord_id": teu}})
    assert exc.value.code == "not_besieged"


def test_sally_loss_reduces_siege_to_one() -> None:
    """4.5.3: sallying side losing reduces siege markers to 1 (RAID)."""
    s = load_scenario("pleskau", seed=1)
    rus = next(lid for lid, l in s.lords.items() if l.side == "russian" and l.state == "mustered")
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    s.lords[rus].location = "pskov"
    s.lords[rus].in_stronghold = True
    s.lords[teu].location = "pskov"  # besieger
    # Make sallying side weak: 1 militia only.
    s.lords[rus].forces = {"militia": 1}
    s.locales["pskov"].siege_markers = 4
    _start_command_with(s, rus)
    res = apply_action(s, {"type": "cmd_sally", "side": "russian", "args": {"lord_id": rus}})
    if res["battle"]["loser"] == "russian":
        assert s.locales["pskov"].siege_markers == 1
        assert res["sally_outcome"] == "withdrew"


def test_sally_win_lifts_siege() -> None:
    """4.5.3: sallying side winning lifts the siege (markers removed)."""
    s = load_scenario("pleskau", seed=1)
    rus = next(lid for lid, l in s.lords.items() if l.side == "russian" and l.state == "mustered")
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    s.lords[rus].location = "pskov"
    s.lords[rus].in_stronghold = True
    s.lords[teu].location = "pskov"
    # Strong sallying force vs weak besieger.
    s.lords[rus].forces = {"knights": 5, "men_at_arms": 3}
    s.lords[teu].forces = {"militia": 1}
    s.locales["pskov"].siege_markers = 2
    _start_command_with(s, rus)
    res = apply_action(s, {"type": "cmd_sally", "side": "russian", "args": {"lord_id": rus}})
    if res["battle"]["loser"] == "teutonic":
        assert s.locales["pskov"].siege_markers == 0
        assert res["sally_outcome"] == "broken_siege"
