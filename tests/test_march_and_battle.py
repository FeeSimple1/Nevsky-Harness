"""Tests for 4.3 March, 4.3.4 Avoid/Withdraw, 4.3.5 begin Siege, 4.4 Battle."""

from __future__ import annotations

import pytest

from nevsky.actions import IllegalAction, apply_action
from nevsky.battle import resolve_battle
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


# --- 4.3 March ---------------------------------------------------------------


def test_march_unladen_costs_one_action() -> None:
    """4.3 + 4.3.2: Unladen March costs 1 Command action per Locale."""
    s = load_scenario("watland", seed=1)
    s.meta.box = 1
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    # Find an adjacent locale (any).
    from nevsky.static_data import load_ways
    src = s.lords[teu].location
    dest = None
    for w in load_ways():
        if w["a"] == src:
            dest = w["b"]; break
        if w["b"] == src:
            dest = w["a"]; break
    assert dest is not None
    # Make sure dest has no enemy Lord/Stronghold/Conquered.
    if any(l.location == dest and l.side != "teutonic" for l in s.lords.values()):
        pytest.skip("adjacent locale has enemy lord")
    s.lords[teu].assets.pop("loot", None)
    s.lords[teu].assets.pop("provender", None)
    _start_command_with(s, teu)
    pre_actions = s.campaign_turn.actions_remaining
    apply_action(s, {"type": "cmd_march", "side": "teutonic",
                     "args": {"lord_id": teu, "to": dest}})
    assert s.lords[teu].location == dest
    assert s.campaign_turn.actions_remaining == pre_actions - 1


def test_march_laden_costs_two_actions() -> None:
    """4.3.2: Laden March (carrying Loot) costs 2 actions."""
    s = load_scenario("watland", seed=1)
    s.meta.box = 1
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    from nevsky.static_data import load_ways
    src = s.lords[teu].location
    dest = None
    for w in load_ways():
        if (w["a"] == src or w["b"] == src):
            dest = w["b"] if w["a"] == src else w["a"]
            if not any(l.location == dest and l.side != "teutonic" for l in s.lords.values()):
                break
            dest = None
    if dest is None:
        pytest.skip("no clear adjacent locale")
    s.lords[teu].assets["loot"] = 1  # makes Lord Laden
    _start_command_with(s, teu)
    pre = s.campaign_turn.actions_remaining
    if pre < 2:
        pytest.skip("not enough actions for Laden March")
    apply_action(s, {"type": "cmd_march", "side": "teutonic",
                     "args": {"lord_id": teu, "to": dest}})
    assert s.campaign_turn.actions_remaining == pre - 2


def test_march_into_enemy_stronghold_begins_siege() -> None:
    """4.3.5: Marching into a Locale of an Unbesieged enemy Stronghold begins Siege."""
    s = load_scenario("pleskau", seed=1)
    s.meta.box = 1
    # Set up: a Teutonic Lord adjacent to pskov (Russian city).
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    s.lords[teu].location = "izborsk"  # adjacent to pskov
    # Remove all enemy Lords from pskov (just need the Stronghold).
    for lid, l in s.lords.items():
        if l.location == "pskov" and l.side == "russian":
            l.location = "novgorod"
    # Ensure pskov is not yet Conquered by Teutons or Besieged.
    s.locales["pskov"].teutonic_conquered = 0
    s.locales["pskov"].siege_markers = 0
    _start_command_with(s, teu)
    res = apply_action(s, {"type": "cmd_march", "side": "teutonic",
                            "args": {"lord_id": teu, "to": "pskov"}})
    assert res["placed_siege"] is True
    assert s.locales["pskov"].siege_markers == 1


def test_march_into_enemy_lord_triggers_combat_pending() -> None:
    """4.3.4 / 4.4: Marching into enemy-Lord locale sets combat_pending."""
    s = load_scenario("watland", seed=1)
    s.meta.box = 1
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    rus = next(lid for lid, l in s.lords.items() if l.side == "russian" and l.state == "mustered")
    # Co-place: Teu at izborsk, Rus at pskov (adjacent).
    s.lords[teu].location = "izborsk"
    s.lords[rus].location = "pskov"
    s.lords[teu].assets.pop("loot", None)
    _start_command_with(s, teu)
    apply_action(s, {"type": "cmd_march", "side": "teutonic",
                     "args": {"lord_id": teu, "to": "pskov"}})
    assert s.combat_pending is not None
    assert s.combat_pending.attacker_side == "teutonic"
    assert s.combat_pending.defender_side == "russian"
    assert rus in s.combat_pending.defender_lords


# --- 4.3.4 Avoid Battle ------------------------------------------------------


def test_avoid_battle_unladen_to_safe_neighbor() -> None:
    """4.3.4: defender Avoids to adjacent locale free of enemy."""
    s = load_scenario("watland", seed=1)
    s.meta.box = 1
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    rus = next(lid for lid, l in s.lords.items() if l.side == "russian" and l.state == "mustered")
    # Clear ALL Russian Lord assets that could trigger Laden status.
    for lid, lord in s.lords.items():
        if lord.side == "russian":
            lord.assets.pop("loot", None)
            lord.assets.pop("provender", None)
    s.lords[teu].location = "izborsk"
    s.lords[rus].location = "pskov"
    s.lords[teu].assets.pop("loot", None)
    s.lords[teu].assets.pop("provender", None)
    _start_command_with(s, teu)
    apply_action(s, {"type": "cmd_march", "side": "teutonic",
                     "args": {"lord_id": teu, "to": "pskov"}})
    # Pick an adjacent locale to pskov that is friendly to Russian.
    from nevsky.static_data import load_ways
    target = None
    for w in load_ways():
        if w["a"] == "pskov":
            cand = w["b"]
        elif w["b"] == "pskov":
            cand = w["a"]
        else:
            continue
        # Skip locales with enemy Lords.
        if any(l.location == cand and l.side == "teutonic" for l in s.lords.values()):
            continue
        target = cand
        break
    if target is None:
        pytest.skip("no clear avoid target")
    apply_action(s, {"type": "avoid_battle", "side": "russian", "args": {"to": target}})
    assert s.lords[rus].location == target
    assert s.combat_pending is None


def test_avoid_battle_blocked_when_laden() -> None:
    """4.3.4: Laden defender cannot Avoid."""
    s = load_scenario("watland", seed=1)
    s.meta.box = 1
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    rus = next(lid for lid, l in s.lords.items() if l.side == "russian" and l.state == "mustered")
    s.lords[teu].location = "izborsk"
    s.lords[rus].location = "pskov"
    s.lords[rus].assets["loot"] = 1  # makes defender Laden
    s.lords[teu].assets.pop("loot", None)
    _start_command_with(s, teu)
    apply_action(s, {"type": "cmd_march", "side": "teutonic",
                     "args": {"lord_id": teu, "to": "pskov"}})
    with pytest.raises(IllegalAction) as exc:
        apply_action(s, {"type": "avoid_battle", "side": "russian",
                         "args": {"to": "novgorod"}})
    assert exc.value.code == "laden_cannot_avoid"


# --- 4.4 Battle resolution ---------------------------------------------------


def test_battle_resolves_with_one_winner() -> None:
    """4.4: Battle eventually ends with one side fully Routed (or stalemate)."""
    s = load_scenario("watland", seed=42)
    s.meta.box = 1
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    rus = next(lid for lid, l in s.lords.items() if l.side == "russian" and l.state == "mustered")
    res = resolve_battle(s, "teutonic", [teu], [rus])
    assert res["winner"] in ("teutonic", "russian")
    assert res["loser"] != res["winner"]
    assert res["rounds"] >= 1


def test_battle_strikes_in_initiative_order() -> None:
    """4.4.2: Battle initiative -- archery defender, archery attacker,
    melee horse defender/attacker, melee foot defender/attacker.
    Round log records all six steps in order."""
    s = load_scenario("watland", seed=3)
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    rus = next(lid for lid, l in s.lords.items() if l.side == "russian" and l.state == "mustered")
    res = resolve_battle(s, "teutonic", [teu], [rus])
    expected = [
        "archery_defender", "archery_attacker",
        "melee_horse_defender", "melee_horse_attacker",
        "melee_foot_defender", "melee_foot_attacker",
    ]
    first_round_steps = [step["step"] for step in res["log"][0]["steps"]]
    # Should be a prefix of `expected` (battle may end mid-round).
    assert first_round_steps == expected[:len(first_round_steps)]


def test_stand_battle_resolves_and_clears_pending() -> None:
    """stand_battle action runs Battle; clears combat_pending; ends card."""
    s = load_scenario("watland", seed=7)
    s.meta.box = 1
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    rus = next(lid for lid, l in s.lords.items() if l.side == "russian" and l.state == "mustered")
    s.lords[teu].location = "izborsk"
    s.lords[rus].location = "pskov"
    s.lords[teu].assets.pop("loot", None)
    s.lords[rus].assets.pop("loot", None)
    _start_command_with(s, teu)
    apply_action(s, {"type": "cmd_march", "side": "teutonic",
                     "args": {"lord_id": teu, "to": "pskov"}})
    res = apply_action(s, {"type": "stand_battle", "side": "russian", "args": {}})
    assert s.combat_pending is None
    assert s.campaign_turn.in_feed_pay_disband is True
    assert res["winner"] in ("teutonic", "russian")


def test_battle_loser_retreats_or_is_removed() -> None:
    """4.4.3: loser Lord either Retreats or is permanently removed if no
    forces remain or no retreat path."""
    s = load_scenario("watland", seed=11)
    s.meta.box = 1
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    rus = next(lid for lid, l in s.lords.items() if l.side == "russian" and l.state == "mustered")
    s.lords[teu].location = "izborsk"
    s.lords[rus].location = "pskov"
    s.lords[teu].assets.pop("loot", None)
    s.lords[rus].assets.pop("loot", None)
    _start_command_with(s, teu)
    apply_action(s, {"type": "cmd_march", "side": "teutonic",
                     "args": {"lord_id": teu, "to": "pskov"}})
    res = apply_action(s, {"type": "stand_battle", "side": "russian", "args": {}})
    # Loser Lord(s) either retreated or removed.
    loser_side = res["loser"]
    loser_ids = res["battle"]["attacker_lords"] if loser_side == "teutonic" else res["battle"]["defender_lords"]
    for lid in loser_ids:
        if lid in s.lords:
            lord = s.lords[lid]
            # Lord either retreated (state still mustered) or got removed.
            assert lord.state in ("mustered", "removed", "disbanded")
