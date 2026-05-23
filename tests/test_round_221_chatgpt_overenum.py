"""Round 221 — two over-enumerations found by GPT-5.5 self-play (the
ChatGPT-project path). Both: a concrete enumerated action the handler
rejects (enumerator/handler asymmetry, same class as R209/R219).

SMOKE-157: a Besieged active Lord may take ONLY Sally / Stone Kremlin /
Pass (Commands.txt); the palette wrongly included cmd_march etc.
SMOKE-158: Withdraw was offered to a defender even when the Battle-Locale
Stronghold is not Friendly to them (e.g. a Teuton at Russian Izborsk),
which the handler rejects with not_friendly.
"""
from __future__ import annotations

from nevsky.actions import IllegalAction, apply_action
import nevsky.campaign as camp
from nevsky.legal_moves import legal_moves
from nevsky.scenarios import load_scenario
from nevsky.state import CombatPending, GameState


def _types(s: GameState, side: str):
    return {m["type"] for m in legal_moves(s, with_previews=False) if m.get("side") == side}


# SMOKE-157 ----------------------------------------------------------------

def _besieged_command_state(cap=False):
    s = load_scenario("crusade_on_novgorod", seed=1)
    rus = "gavrilo"
    s.lords[rus].location = "pskov"
    s.lords[rus].in_stronghold = True
    s.locales["pskov"].siege_markers = 1
    if cap:
        s.lords[rus].this_lord_capabilities = ["R18"]  # Stone Kremlin
        s.locales["pskov"].walls_plus_one = False
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.active_player = "russian"
    s.campaign_turn.active_lord = rus
    s.campaign_turn.next_to_reveal = "russian"
    s.campaign_turn.in_feed_pay_disband = False
    s.campaign_turn.actions_remaining = camp._effective_command_rating(s, rus)
    return s, rus


def test_besieged_lord_palette_restricted():
    s, rus = _besieged_command_state()
    t = _types(s, "russian")
    assert "cmd_march" not in t and "cmd_tax" not in t and "cmd_forage" not in t
    assert t <= {"cmd_sally", "cmd_stone_kremlin", "cmd_pass", "end_card"}
    assert "cmd_sally" in t  # a besieged Lord with besiegers present can Sally


def test_besieged_lord_with_stone_kremlin_keeps_it():
    s, rus = _besieged_command_state(cap=True)
    t = _types(s, "russian")
    assert "cmd_stone_kremlin" in t  # explicitly allowed while Besieged
    assert "cmd_march" not in t


def test_besieged_march_would_be_rejected_by_handler():
    s, rus = _besieged_command_state()
    try:
        apply_action(s, {"type": "cmd_march", "side": "russian",
                         "args": {"lord_id": rus, "to": "izborsk"}})
        raise AssertionError("besieged Lord march should be rejected")
    except IllegalAction as e:
        assert str(e.args[0]).startswith("besieged")


# SMOKE-158 ----------------------------------------------------------------

def _approach(defender_side, defender, to_locale, from_locale):
    s = load_scenario("crusade_on_novgorod", seed=1)
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.active_player = defender_side  # the defender owes the Approach response
    s.lords[defender].state = "mustered"
    s.lords[defender].location = to_locale
    s.lords[defender].in_stronghold = False
    s.combat_pending = CombatPending(
        attacker_side=("russian" if defender_side == "teutonic" else "teutonic"),  # opponent attacks
        attacker_group=[], defender_side=defender_side, defender_lords=[defender],
        from_locale=from_locale, to_locale=to_locale, way_type="trackway",
        pending_response_by=defender_side)
    return s


def test_withdraw_not_offered_into_unfriendly_stronghold():
    teu = next(lid for lid, l in load_scenario("crusade_on_novgorod", seed=1).lords.items()
               if l.side == "teutonic" and l.state == "mustered")
    s = _approach("teutonic", teu, "izborsk", "ugaunia")  # Russian fort, not Teuton's
    assert "withdraw" not in _types(s, "teutonic")


def test_withdraw_offered_into_own_conquered_stronghold():
    teu = next(lid for lid, l in load_scenario("crusade_on_novgorod", seed=1).lords.items()
               if l.side == "teutonic" and l.state == "mustered")
    s = _approach("teutonic", teu, "izborsk", "ugaunia")
    s.locales["izborsk"].teutonic_conquered = 1  # Teutons hold it -> Friendly to them
    assert "withdraw" in _types(s, "teutonic")
    apply_action(s, {"type": "withdraw", "side": "teutonic", "args": {}})  # applies


def test_every_enumerated_withdraw_applies():
    """General alignment: an enumerated withdraw never raises not_friendly."""
    for defender_side, defender, to_loc in [
        ("russian", "gavrilo", "pskov"),       # Russian at own Russian city
    ]:
        s = _approach(defender_side, defender, to_loc, "izborsk")
        if "withdraw" in _types(s, defender_side):
            apply_action(s, {"type": "withdraw", "side": defender_side, "args": {}})
