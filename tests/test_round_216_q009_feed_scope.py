"""Round 216 — Q-009 adjudication (D-Q009): Feed (4.8.1) applies only to
Moved/Fought Lords. The Moved/Fought marker is set ONLY by March, Avoid
Battle, Battle, Siege, Storm, Sail (SoP glossary L38; Misc Rules L451).
Stationary Commands (Tax, Forage, Ravage, Raiders-Ravage, Supply,
Muster-Serf, Stone Kremlin, Stonemasons) must NOT set moved_fought and
therefore do not trigger Feed -- fixing the mid-game starvation spiral
the Crusade seed-1 playthrough hit.
"""
from __future__ import annotations

from nevsky.actions import apply_action
import nevsky.campaign as camp
from nevsky.scenarios import load_scenario
from nevsky.state import GameState
from nevsky.static_data import load_lords, load_locales, load_ways


def _command_state(s: GameState, lord_id: str, side: str):
    s.lords[lord_id].moved_fought = False
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.active_player = side
    s.campaign_turn.active_lord = lord_id
    s.campaign_turn.next_to_reveal = side
    s.campaign_turn.in_feed_pay_disband = False
    s.campaign_turn.actions_remaining = camp._effective_command_rating(s, lord_id)


def test_tax_does_not_set_moved_fought():
    s = load_scenario("crusade_on_novgorod", seed=1)
    rus = next(l for l, o in s.lords.items() if o.side == "russian" and o.state == "mustered")
    seat = load_lords()[rus]["primary_seats"][0]
    s.lords[rus].location = seat
    s.lords[rus].assets["coin"] = 0
    _command_state(s, rus, "russian")
    apply_action(s, {"type": "cmd_tax", "side": "russian", "args": {"lord_id": rus}})
    assert s.lords[rus].moved_fought is False


def test_muster_serf_does_not_set_moved_fought():
    s = load_scenario("crusade_on_novgorod", seed=1)
    rus = next(l for l, o in s.lords.items() if o.side == "russian" and o.state == "mustered")
    target = next(k for k, v in load_locales().items() if v.get("territory") == "russian")
    s.decks.russian.capabilities_in_play = ["R4"]
    s.lords[rus].location = target
    _command_state(s, rus, "russian")
    apply_action(s, {"type": "cmd_muster_serf", "side": "russian", "args": {"lord_id": rus}})
    assert s.lords[rus].moved_fought is False


def test_stone_kremlin_does_not_set_moved_fought():
    s = load_scenario("crusade_on_novgorod", seed=1)
    rus = next(l for l, o in s.lords.items() if o.side == "russian" and o.state == "mustered")
    target = next(k for k, v in load_locales().items()
                  if v.get("territory") == "russian" and v.get("type") in ("fort", "city", "novgorod"))
    s.lords[rus].this_lord_capabilities = ["R18"]
    s.lords[rus].location = target
    s.locales[target].walls_plus_one = False
    s.locales[target].teutonic_castle = False
    s.locales[target].russian_castle = False
    _command_state(s, rus, "russian")
    apply_action(s, {"type": "cmd_stone_kremlin", "side": "russian", "args": {"lord_id": rus}})
    assert s.lords[rus].moved_fought is False


def test_march_still_sets_moved_fought():
    s = load_scenario("crusade_on_novgorod", seed=1)
    teu = next(l for l, o in s.lords.items() if o.side == "teutonic" and o.state == "mustered")
    here = s.lords[teu].location
    dest = next(w["b"] if w["a"] == here else w["a"]
                for w in load_ways() if here in (w["a"], w["b"]))
    s.lords[teu].assets.pop("provender", None)
    s.lords[teu].assets.pop("loot", None)
    _command_state(s, teu, "teutonic")
    apply_action(s, {"type": "cmd_march", "side": "teutonic", "args": {"lord_id": teu, "to": dest}})
    assert s.lords[teu].moved_fought is True


def test_tax_garrison_survives_fpd_no_unfed():
    """End-to-end: a 7+ unit garrison that only Taxes is NOT fed and so
    is NOT Unfed -> its Service marker does not drift (the spiral fix)."""
    s = load_scenario("crusade_on_novgorod", seed=1)
    rus = next(l for l, o in s.lords.items() if o.side == "russian" and o.state == "mustered")
    seat = load_lords()[rus]["primary_seats"][0]
    s.lords[rus].location = seat
    s.lords[rus].assets["coin"] = 0
    s.lords[rus].assets.pop("provender", None)
    s.lords[rus].assets.pop("loot", None)
    s.lords[rus].forces.clear()
    s.lords[rus].forces["men_at_arms"] = 8  # 7+ units -> would need 2 Feed
    _command_state(s, rus, "russian")
    sm_before = camp._find_service_marker_box(s, rus)
    apply_action(s, {"type": "cmd_tax", "side": "russian", "args": {"lord_id": rus}})
    # Tax ends the card -> FPD runs. With no Moved/Fought, no Feed, no Unfed.
    # Drive FPD to completion (handle the possible 4.8.2 Pay window).
    guard = 0
    while s.campaign_turn.in_feed_pay_disband and guard < 10:
        guard += 1
        apply_action(s, {"type": "fpd_resolve", "side": s.meta.active_player, "args": {}})
    assert s.lords[rus].state == "mustered"
    assert camp._find_service_marker_box(s, rus) == sm_before  # no Unfed drift
