"""Round 203 regression tests for the Crusade-on-Novgorod seed-1
LLM-playthrough findings:

BUG-1  R18 Stone Kremlin was never enumerated in legal_moves, so a player
       driving off legal_actions could never use the capability.
BUG-2  Entire-card Commands (Siege/Storm/Sally/Tax/Sail) lacked the
       "no other action" guard, allowing March-then-Storm on one card.
       Adjudicated (RULES_DECISIONS): entire_card == sole action.
BUG-3  scripts/llm_self_play._concrete_actions silently dropped templated
       cmd_sail / cmd_supply (empty expansion, not an exception).
BUG-4  The per-card 4.8 Feed/Pay/Disband cycle skipped the 4.8.2 Pay
       sub-step, disbanding service-limited Lords with no recourse even
       when the side held Coin/Loot.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

from nevsky.actions import IllegalAction, apply_action
import nevsky.campaign as camp
from nevsky.legal_moves import legal_moves
from nevsky.scenarios import load_scenario
from nevsky.state import GameState
from nevsky.static_data import load_locales


def _side_types(s: GameState, side: str) -> set[str]:
    return {m["type"] for m in legal_moves(s, with_previews=False) if m.get("side") == side}


def _russian_walls_locale() -> str:
    locs = load_locales()
    return next(
        k for k, v in locs.items()
        if v.get("territory") == "russian" and v.get("type") in ("fort", "city", "novgorod")
    )


def _setup_kremlin_state(actions_offset: int = 0):
    s = load_scenario("crusade_on_novgorod", seed=1)
    rus = next(lid for lid, l in s.lords.items() if l.side == "russian" and l.state == "mustered")
    target = _russian_walls_locale()
    s.lords[rus].this_lord_capabilities = ["R18"]
    s.lords[rus].location = target
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.active_player = "russian"
    s.campaign_turn.active_lord = rus
    s.campaign_turn.next_to_reveal = "russian"
    s.campaign_turn.in_feed_pay_disband = False
    s.campaign_turn.actions_remaining = camp._effective_command_rating(s, rus) - actions_offset
    s.locales[target].walls_plus_one = False
    s.locales[target].teutonic_castle = False
    s.locales[target].russian_castle = False
    return s, rus, target


# BUG-1 -------------------------------------------------------------------

def test_bug1_stone_kremlin_enumerated_when_pristine():
    s, rus, target = _setup_kremlin_state()
    assert "cmd_stone_kremlin" in _side_types(s, "russian")
    apply_action(s, {"type": "cmd_stone_kremlin", "side": "russian", "args": {"lord_id": rus}})
    assert s.locales[target].walls_plus_one is True


def test_bug1_stone_kremlin_not_enumerated_without_capability():
    s, rus, _ = _setup_kremlin_state()
    s.lords[rus].this_lord_capabilities = []
    assert "cmd_stone_kremlin" not in _side_types(s, "russian")


def test_bug1_stone_kremlin_not_enumerated_when_walls_already_present():
    s, rus, target = _setup_kremlin_state()
    s.locales[target].walls_plus_one = True
    assert "cmd_stone_kremlin" not in _side_types(s, "russian")


# BUG-2 -------------------------------------------------------------------

def test_bug2_entire_card_moves_suppressed_when_not_pristine():
    s, _, _ = _setup_kremlin_state(actions_offset=1)
    types = _side_types(s, "russian")
    # Q-010 (2026-07-06): Storm/Sally are one-action, NOT entire-card, so
    # they are no longer in the pristine-gated suppression set.
    for t in ("cmd_stone_kremlin", "cmd_tax", "cmd_sail", "cmd_siege"):
        assert t not in types, f"{t} should be suppressed on a non-pristine card"


def test_bug2_handler_rejects_entire_card_when_not_pristine():
    s, rus, _ = _setup_kremlin_state(actions_offset=1)
    try:
        apply_action(s, {"type": "cmd_stone_kremlin", "side": "russian", "args": {"lord_id": rus}})
        raise AssertionError("expected must_be_full_card")
    except IllegalAction as e:
        assert str(e.args[0]).startswith("must_be_full_card")


def test_bug2_entire_card_allowed_when_pristine():
    s = load_scenario("crusade_on_novgorod", seed=1)
    rus = next(lid for lid, l in s.lords.items() if l.side == "russian" and l.state == "mustered")
    from nevsky.static_data import load_lords
    seat = load_lords()[rus]["primary_seats"][0]
    s.lords[rus].location = seat
    s.lords[rus].assets["coin"] = 0
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.active_player = "russian"
    s.campaign_turn.active_lord = rus
    s.campaign_turn.next_to_reveal = "russian"
    s.campaign_turn.in_feed_pay_disband = False
    s.campaign_turn.actions_remaining = camp._effective_command_rating(s, rus)
    apply_action(s, {"type": "cmd_tax", "side": "russian", "args": {"lord_id": rus}})
    assert s.lords[rus].assets.get("coin", 0) == 1


# BUG-3 -------------------------------------------------------------------

def _load_llm_self_play():
    spec = importlib.util.spec_from_file_location(
        "llm_self_play_mod",
        Path(__file__).resolve().parent.parent / "scripts" / "llm_self_play.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_bug3_sail_and_supply_remain_in_concrete_palette():
    llm = _load_llm_self_play()
    s = load_scenario("watland", seed=1)
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "teutonic", "args": {}})
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    s.lords[teu].location = "riga"
    s.lords[teu].assets = {"ship": 4, "provender": 1}
    s.meta.box = 1
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.active_player = "teutonic"
    s.campaign_turn.active_lord = teu
    s.campaign_turn.next_to_reveal = "teutonic"
    s.campaign_turn.in_feed_pay_disband = False
    s.campaign_turn.actions_remaining = camp._effective_command_rating(s, teu)
    palette = {m["type"] for m in llm._concrete_actions(s, "teutonic")}
    assert "cmd_sail" in palette
    assert "cmd_supply" in palette


# BUG-4 -------------------------------------------------------------------

def _put_levy_and_service(s: GameState, lord_id: str, box: int):
    for cb in s.calendar.boxes:
        if cb.has_levy_campaign_marker:
            cb.has_levy_campaign_marker = False
            cb.levy_campaign_face = None
        if lord_id in cb.service_markers:
            cb.service_markers.remove(lord_id)
    if lord_id in s.calendar.off_right:
        s.calendar.off_right.remove(lord_id)
    s.calendar.boxes[box - 1].has_levy_campaign_marker = True
    s.calendar.boxes[box - 1].levy_campaign_face = "campaign"
    s.calendar.boxes[box - 1].service_markers.append(lord_id)


def test_bug4_pay_window_opens_and_pay_averts_disband():
    s = load_scenario("watland", seed=1)
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    _put_levy_and_service(s, teu, 5)
    s.lords[teu].moved_fought = False
    s.lords[teu].assets.pop("provender", None)
    s.lords[teu].assets.pop("loot", None)
    s.lords[teu].assets["coin"] = 3
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.active_player = "teutonic"
    s.campaign_turn.in_feed_pay_disband = True
    s.campaign_turn.fpd_completed_t = False
    s.campaign_turn.fpd_completed_r = False

    res = apply_action(s, {"type": "fpd_resolve", "side": "teutonic", "args": {}})
    assert res.get("pay_window") is True
    assert s.campaign_turn.fpd_pay_window_side == "teutonic"
    assert s.meta.active_player == "teutonic"
    assert "pay_with_coin" in _side_types(s, "teutonic")

    before = camp._find_service_marker_box(s, teu)
    apply_action(s, {
        "type": "pay_with_coin", "side": "teutonic",
        "args": {"from": f"lord:{teu}", "target_lord": teu, "units": 1},
    })
    after = camp._find_service_marker_box(s, teu)
    assert after == before + 1

    res2 = apply_action(s, {"type": "fpd_resolve", "side": "teutonic", "args": {}})
    assert teu not in [d["lord_id"] for d in res2.get("disbanded", [])]
    assert s.lords[teu].state == "mustered"
    assert s.campaign_turn.fpd_pay_window_side is None


def test_bug4_no_pay_window_when_side_cannot_pay():
    s = load_scenario("watland", seed=1)
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    _put_levy_and_service(s, teu, 5)
    s.lords[teu].moved_fought = False
    for l in s.lords.values():
        if l.side == "teutonic" and l.state == "mustered":
            l.assets.pop("coin", None)
            l.assets.pop("loot", None)
            l.assets.pop("provender", None)
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.active_player = "teutonic"
    s.campaign_turn.in_feed_pay_disband = True
    s.campaign_turn.fpd_completed_t = False
    s.campaign_turn.fpd_completed_r = False
    res = apply_action(s, {"type": "fpd_resolve", "side": "teutonic", "args": {}})
    assert res.get("pay_window") is None
    assert "disbanded" in res
    assert s.campaign_turn.fpd_pay_window_side is None
