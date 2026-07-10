"""PLAY-32 regression tests: 4.8.2 grants Pay after EVERY Command card.

Rule 4.8.2 (2E): "Next, any Teutonic then Russian Lords may receive Pay
as per Levy (3.2). Then all Lords on both sides must check for Disband
per their Service limit (3.3)."

Before PLAY-32 the harness opened the per-card Pay window only when Feed
had left a pending Disband (a harness artifact of the BUG-4/R203 fix).
The window must open whenever the side has a payable resource, pending
Disband or not. Pay remains optional ("may"): args.decline_pay completes
Feed -> Disband in one fpd_resolve call.
"""
from __future__ import annotations

from nevsky.actions import IllegalAction, apply_action
import nevsky.campaign as camp
from nevsky.legal_moves import legal_moves
from nevsky.scenarios import load_scenario
from nevsky.state import GameState


def _side_types(s: GameState, side: str) -> set[str]:
    return {m["type"] for m in legal_moves(s, with_previews=False) if m.get("side") == side}


def _put_levy_and_service(s: GameState, lord_id: str, levy_box: int, sm_box: int):
    for cb in s.calendar.boxes:
        if cb.has_levy_campaign_marker:
            cb.has_levy_campaign_marker = False
            cb.levy_campaign_face = None
        if lord_id in cb.service_markers:
            cb.service_markers.remove(lord_id)
    if lord_id in s.calendar.off_right:
        s.calendar.off_right.remove(lord_id)
    s.calendar.boxes[levy_box - 1].has_levy_campaign_marker = True
    s.calendar.boxes[levy_box - 1].levy_campaign_face = "campaign"
    s.calendar.boxes[sm_box - 1].service_markers.append(lord_id)


def _enter_fpd(s: GameState, teu_lord: str, *, coin: int = 0) -> None:
    """Put the game in the 4.8 sub-step with NO pending Disband for the
    Teutons (Service marker well right of the Levy marker)."""
    _put_levy_and_service(s, teu_lord, 2, 10)
    s.lords[teu_lord].moved_fought = False
    for l in s.lords.values():
        if l.state == "mustered":
            l.assets.pop("coin", None)
            l.assets.pop("loot", None)
    s.veche.coin = 0
    if coin:
        s.lords[teu_lord].assets["coin"] = coin
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.active_player = "teutonic"
    s.campaign_turn.in_feed_pay_disband = True
    s.campaign_turn.fpd_completed_t = False
    s.campaign_turn.fpd_completed_r = False
    s.campaign_turn.fpd_pay_window_side = None


def test_pay_window_opens_without_pending_disband():
    """The core PLAY-32 fix: side can Pay, NO Disband pending -> the Pay
    window still opens (old code skipped straight to the Disband check)."""
    s = load_scenario("watland", seed=1)
    teu = next(lid for lid, l in s.lords.items()
               if l.side == "teutonic" and l.state == "mustered")
    _enter_fpd(s, teu, coin=2)

    res = apply_action(s, {"type": "fpd_resolve", "side": "teutonic", "args": {}})
    assert res.get("pay_window") is True
    assert s.campaign_turn.fpd_pay_window_side == "teutonic"
    # Palette parity: window offers Pay plus fpd_resolve to continue.
    types = _side_types(s, "teutonic")
    assert "pay_with_coin" in types
    assert "fpd_resolve" in types

    # Pay shifts Service right even though no Disband was pending.
    before = camp._find_service_marker_box(s, teu)
    apply_action(s, {
        "type": "pay_with_coin", "side": "teutonic",
        "args": {"from": f"lord:{teu}", "target_lord": teu, "units": 1},
    })
    assert camp._find_service_marker_box(s, teu) == before + 1

    # Second fpd_resolve completes the side: Disband check + 4.8.3.
    res2 = apply_action(s, {"type": "fpd_resolve", "side": "teutonic", "args": {}})
    assert res2.get("pay_window") is None
    assert "disbanded" in res2
    assert s.campaign_turn.fpd_pay_window_side is None
    assert s.campaign_turn.fpd_completed_t is True
    assert s.meta.active_player == "russian"


def test_decline_pay_completes_in_one_call():
    """Pay is optional (4.8.2 "may"). decline_pay skips the window and the
    side completes Feed -> Disband -> 4.8.3 in a single fpd_resolve."""
    s = load_scenario("watland", seed=1)
    teu = next(lid for lid, l in s.lords.items()
               if l.side == "teutonic" and l.state == "mustered")
    _enter_fpd(s, teu, coin=2)
    s.lords[teu].moved_fought = True
    s.lords[teu].assets["provender"] = 2

    res = apply_action(s, {"type": "fpd_resolve", "side": "teutonic",
                           "args": {"decline_pay": True}})
    assert res.get("pay_window") is None
    assert "disbanded" in res
    assert s.campaign_turn.fpd_pay_window_side is None
    assert s.campaign_turn.fpd_completed_t is True
    assert s.lords[teu].moved_fought is False       # 4.8.3 ran
    assert s.lords[teu].assets.get("coin") == 2     # nothing spent


def test_no_pay_window_when_side_cannot_pay():
    """No payable resource -> no pause (unchanged from BUG-4 behavior)."""
    s = load_scenario("watland", seed=1)
    teu = next(lid for lid, l in s.lords.items()
               if l.side == "teutonic" and l.state == "mustered")
    _enter_fpd(s, teu, coin=0)
    res = apply_action(s, {"type": "fpd_resolve", "side": "teutonic", "args": {}})
    assert res.get("pay_window") is None
    assert "disbanded" in res
    assert s.campaign_turn.fpd_pay_window_side is None


def test_russian_window_opens_on_veche_coin():
    """_fpd_can_pay includes Novgorod Veche Coin (3.2.1) for the Russians."""
    s = load_scenario("watland", seed=1)
    teu = next(lid for lid, l in s.lords.items()
               if l.side == "teutonic" and l.state == "mustered")
    _enter_fpd(s, teu, coin=0)
    # Complete the Teutons (no resources): one call.
    apply_action(s, {"type": "fpd_resolve", "side": "teutonic", "args": {}})
    assert s.meta.active_player == "russian"
    # Russians hold no mat Coin/Loot but DO have Veche Coin.
    s.veche.coin = 1
    res = apply_action(s, {"type": "fpd_resolve", "side": "russian", "args": {}})
    assert res.get("pay_window") is True
    assert s.campaign_turn.fpd_pay_window_side == "russian"
    res2 = apply_action(s, {"type": "fpd_resolve", "side": "russian", "args": {}})
    assert res2.get("pay_window") is None
    assert s.campaign_turn.in_feed_pay_disband is False  # both sides done


def test_loot_at_friendly_locale_opens_window():
    """Loot can Pay only at a Friendly Locale (3.2.2); Loot elsewhere must
    NOT open the window."""
    s = load_scenario("watland", seed=1)
    teu = next(lid for lid, l in s.lords.items()
               if l.side == "teutonic" and l.state == "mustered")
    _enter_fpd(s, teu, coin=0)
    s.lords[teu].assets["loot"] = 1
    assert camp._is_friendly_locale(s, s.lords[teu].location, "teutonic")
    res = apply_action(s, {"type": "fpd_resolve", "side": "teutonic", "args": {}})
    assert res.get("pay_window") is True

    # Same Lord, same Loot, UNFRIENDLY Locale -> no window.
    s2 = load_scenario("watland", seed=1)
    _enter_fpd(s2, teu, coin=0)
    s2.lords[teu].assets["loot"] = 1
    s2.lords[teu].location = "sablia"
    assert not camp._is_friendly_locale(s2, "sablia", "teutonic")
    res2 = apply_action(s2, {"type": "fpd_resolve", "side": "teutonic", "args": {}})
    assert res2.get("pay_window") is None
