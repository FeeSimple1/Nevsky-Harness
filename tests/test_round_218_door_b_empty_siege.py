"""Round 218 — Inferno Advisory #2, Door B completeness + Door C guard.

Door B (marker lifecycle): R215 cleared Siege markers + the inside
defender's flag when the last besieger departs a DEFENDED Stronghold. But
the helper no-op'd for an EMPTY besieged Stronghold (a besieger that
marched into an undefended enemy Stronghold, placed a Siege marker, then
departed) -- leaving a stale marker (RoP 4.3.5: a besieged Stronghold free
of enemy Lords loses its Siege markers, empty or not). Fixed in R218.

Door C (placement): confirm Muster gates contested Seats (no fix needed;
guard test so the gate can't silently regress).
"""
from __future__ import annotations

import nevsky.actions  # noqa: F401
from nevsky.actions import IllegalAction, apply_action, _lift_siege_if_no_besiegers
import nevsky.campaign as camp
from nevsky.scenarios import load_scenario
from nevsky.static_data import load_locales, load_lords, load_ways


def _russian_fort():
    return next(k for k, v in load_locales().items()
               if v.get("type") == "fort" and v.get("territory") == "russian")


def test_empty_besieged_stronghold_lifts_when_besieger_departs():
    s = load_scenario("crusade_on_novgorod", seed=1)
    fort = _russian_fort()
    for l in s.lords.values():
        if l.location == fort:
            l.location = None
    s.locales[fort].siege_markers = 1  # empty fort, besieger already gone
    assert _lift_siege_if_no_besiegers(s, fort) is True
    assert s.locales[fort].siege_markers == 0


def test_empty_besieged_stronghold_not_lifted_while_besieger_present():
    s = load_scenario("crusade_on_novgorod", seed=1)
    fort = _russian_fort()
    for l in s.lords.values():
        if l.location == fort:
            l.location = None
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    s.lords[teu].location = fort
    s.lords[teu].in_stronghold = False
    s.locales[fort].siege_markers = 1
    assert _lift_siege_if_no_besiegers(s, fort) is False
    assert s.locales[fort].siege_markers == 1


def test_defended_case_preserved_r215():
    s = load_scenario("crusade_on_novgorod", seed=1)
    fort = _russian_fort()
    rus = next(lid for lid, l in s.lords.items() if l.side == "russian" and l.state == "mustered")
    s.lords[rus].location = fort
    s.lords[rus].in_stronghold = True
    s.locales[fort].siege_markers = 2
    # besieger gone -> lift + clear defender flag
    assert _lift_siege_if_no_besiegers(s, fort) is True
    assert s.locales[fort].siege_markers == 0
    assert s.lords[rus].in_stronghold is False


def test_empty_siege_cleared_on_march_out_end_to_end():
    s = load_scenario("crusade_on_novgorod", seed=1)
    fort = _russian_fort()
    for l in s.lords.values():
        if l.location == fort:
            l.location = None
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    s.lords[teu].location = fort
    s.lords[teu].in_stronghold = False
    s.lords[teu].assets.pop("provender", None)
    s.lords[teu].assets.pop("loot", None)
    s.locales[fort].siege_markers = 1
    # march to a legal adjacent locale free of enemies
    dest = None
    for w in load_ways():
        cand = w["b"] if w["a"] == fort else (w["a"] if w["b"] == fort else None)
        if cand is None:
            continue
        if any(o.state == "mustered" and o.location == cand and o.side == "russian"
               for o in s.lords.values()):
            continue
        dest = cand
        break
    assert dest is not None
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.active_player = "teutonic"
    s.campaign_turn.active_lord = teu
    s.campaign_turn.next_to_reveal = "teutonic"
    s.campaign_turn.in_feed_pay_disband = False
    s.campaign_turn.actions_remaining = camp._effective_command_rating(s, teu)
    apply_action(s, {"type": "cmd_march", "side": "teutonic", "args": {"lord_id": teu, "to": dest}})
    assert s.locales[fort].siege_markers == 0, "stale empty-stronghold siege not cleared on march-out"


# Door C guard --------------------------------------------------------------

def test_free_seats_excludes_enemy_occupied_and_conquered():
    """Door C gate (_free_seats_for, used by every placement path:
    muster_lord, Legate 2a, Veche option B): a Seat that is enemy-occupied
    or enemy-Conquered is not a Free Seat, so an ordinary Lord cannot be
    placed there."""
    from nevsky.actions import _free_seats_for
    s = load_scenario("crusade_on_novgorod", seed=1)
    rus = next(lid for lid, l in s.lords.items()
               if l.side == "russian" and lid != "aleksandr")
    seats = load_lords()[rus]["primary_seats"]
    assert seats, "lord has no primary seat to test"
    seat = seats[0]
    base = _free_seats_for(s, rus)
    # 1) enemy Lord on the Seat -> excluded
    s.lords["heinrich"].state = "mustered"
    s.lords["heinrich"].location = seat
    assert seat not in _free_seats_for(s, rus)
    s.lords["heinrich"].location = None
    s.lords["heinrich"].state = "ready"
    # 2) enemy Conquered marker on the Seat -> excluded
    s.locales[seat].teutonic_conquered = 1
    assert seat not in _free_seats_for(s, rus)
