"""PLAY-37 regression tests: Veche-A / Legate-2b slides use 2.2.3
off-edge placement.

Rule 2.2.3: "If a Service marker or Lord's cylinder would be placed or
shifted below (left of) box 1 or beyond (right of) box 16, set the
marker or cylinder just off the board on the corresponding side: ignore
further shifts in that direction. The first shift back toward the
Calendar places the marker into box 1 or box 16, respectively."

Before PLAY-37:
  - Veche Option A (slide a cylinder 2 left, 3.5.2) clamped at box 1 --
    a box-1 target was a VP-burning literal no-op the palette still
    offered -- and rejected off-right cylinders entirely;
  - Legate 2b (slide a cylinder 1 left, 3.5.1) rejected box-1
    ("cylinder_at_left_edge") and off-right cylinders.
Now a leftward slide past box 1 puts the cylinder just OFF-LEFT, and an
off-right cylinder slides back onto the Calendar (first box back = 16;
Veche A's second box continues to 15). Off-left cylinders remain
non-targets: 2.2.3 ignores further left shifts, so the action would be
a guaranteed no-op cost.
"""
from __future__ import annotations

import pytest

from nevsky.actions import IllegalAction, apply_action, _seats_of
from nevsky.legal_moves import legal_moves
from nevsky.scenarios import load_scenario
from nevsky.state import GameState


def _clear_cylinder(s: GameState, lid: str):
    for cb in s.calendar.boxes:
        if lid in cb.cylinders:
            cb.cylinders.remove(lid)
    if lid in s.calendar.off_left:
        s.calendar.off_left.remove(lid)
    if lid in s.calendar.off_right:
        s.calendar.off_right.remove(lid)


def _put_cylinder(s: GameState, lid: str, box: int):
    _clear_cylinder(s, lid)
    if box == 0:
        s.calendar.off_left.append(lid)
    elif box >= 17:
        s.calendar.off_right.append(lid)
    else:
        s.calendar.boxes[box - 1].cylinders.append(lid)


# ----------------------------- Veche Option A -----------------------------

def _cta_russian(seed=1):
    s = load_scenario("peipus", seed=seed)
    s.meta.phase = "levy"
    s.meta.levy_step = "call_to_arms"
    s.meta.active_player = "russian"
    s.veche.acted_this_call_to_arms = False
    s.veche.vp_markers = 2
    s.calendar.russian_vp = max(s.calendar.russian_vp, 2.0)
    return s


def test_veche_a_from_box_2_goes_off_left():
    s = _cta_russian()
    rus = next(lid for lid, l in s.lords.items() if l.side == "russian")
    _put_cylinder(s, rus, 2)
    res = apply_action(s, {"type": "veche_action", "side": "russian",
                           "args": {"option": "A", "target_lord": rus}})
    assert res["to_box"] == 0
    assert rus in s.calendar.off_left
    assert not any(rus in cb.cylinders for cb in s.calendar.boxes)


def test_veche_a_from_box_1_goes_off_left_not_noop():
    """The old clamp made this a VP-burning no-op (box 1 -> box 1)."""
    s = _cta_russian()
    rus = next(lid for lid, l in s.lords.items() if l.side == "russian")
    _put_cylinder(s, rus, 1)
    res = apply_action(s, {"type": "veche_action", "side": "russian",
                           "args": {"option": "A", "target_lord": rus}})
    assert res["to_box"] == 0
    assert rus in s.calendar.off_left


def test_veche_a_from_box_3_lands_on_1():
    s = _cta_russian()
    rus = next(lid for lid, l in s.lords.items() if l.side == "russian")
    _put_cylinder(s, rus, 3)
    res = apply_action(s, {"type": "veche_action", "side": "russian",
                           "args": {"option": "A", "target_lord": rus}})
    assert res["to_box"] == 1
    assert rus in s.calendar.boxes[0].cylinders


def test_veche_a_off_left_still_rejected():
    s = _cta_russian()
    rus = next(lid for lid, l in s.lords.items() if l.side == "russian")
    _put_cylinder(s, rus, 0)
    with pytest.raises(IllegalAction) as exc:
        apply_action(s, {"type": "veche_action", "side": "russian",
                         "args": {"option": "A", "target_lord": rus}})
    assert exc.value.code == "no_cylinder"


# ------------------------------- Legate 2b -------------------------------

def _cta_teutonic_2b(seed=1):
    """CtA with the Legate pawn at a Seat of a Teutonic Lord whose
    cylinder we control."""
    s = load_scenario("crusade_on_novgorod", seed=seed)
    s.meta.phase = "levy"
    s.meta.levy_step = "call_to_arms"
    s.meta.active_player = "teutonic"
    s.legate.william_of_modena_in_play = True
    s.legate.acted_this_call_to_arms = False
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic")
    seat = _seats_of(s, teu)[0]
    s.legate.location = "locale"
    s.legate.locale_id = seat
    return s, teu


def test_legate_2b_from_box_1_goes_off_left():
    s, teu = _cta_teutonic_2b()
    _put_cylinder(s, teu, 1)
    res = apply_action(s, {"type": "legate_use", "side": "teutonic",
                           "args": {"sub_option": "2b", "target_lord": teu}})
    assert res["to_box"] == 0
    assert teu in s.calendar.off_left


def test_legate_2b_off_right_slides_to_16():
    s, teu = _cta_teutonic_2b()
    _put_cylinder(s, teu, 17)
    res = apply_action(s, {"type": "legate_use", "side": "teutonic",
                           "args": {"sub_option": "2b", "target_lord": teu}})
    assert res["to_box"] == 16
    assert teu in s.calendar.boxes[15].cylinders
    assert teu not in s.calendar.off_right


def test_legate_2b_off_left_rejected_and_not_enumerated():
    s, teu = _cta_teutonic_2b()
    _put_cylinder(s, teu, 0)
    with pytest.raises(IllegalAction) as exc:
        apply_action(s, {"type": "legate_use", "side": "teutonic",
                         "args": {"sub_option": "2b", "target_lord": teu}})
    assert exc.value.code == "no_cylinder"
    targets = {m["args"].get("target_lord")
               for m in legal_moves(s, with_previews=False)
               if m.get("type") == "legate_use"
               and m["args"].get("sub_option") == "2b"}
    assert teu not in targets


def test_legate_2b_palette_offers_box1_and_off_right():
    """Palette parity: the newly-legal edge targets are enumerated."""
    s, teu = _cta_teutonic_2b()
    for box in (1, 17):
        _put_cylinder(s, teu, box)
        targets = {m["args"].get("target_lord")
                   for m in legal_moves(s, with_previews=False)
                   if m.get("type") == "legate_use"
                   and m["args"].get("sub_option") == "2b"}
        assert teu in targets, f"box {box} target missing from palette"
