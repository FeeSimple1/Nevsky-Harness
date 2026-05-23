"""Round 219 — SMOKE-156 (found by the OpenAI/mock self-play driver).

Veche option A (slide a Lord's cylinder LEFT, 3.5.2) was enumerated for
any Russian Lord whose cylinder was `_find_cylinder_box is not None`, but
_h_veche_action rejects `no_cylinder` unless the cylinder is ON the
Calendar in boxes 1..16 (not off-left=0, not off-right>=17). Off-board
cylinders were over-enumerated. The enumerator now matches the handler.
"""
from __future__ import annotations

from nevsky.actions import IllegalAction, apply_action
from nevsky.legal_moves import legal_moves
from nevsky.scenarios import load_scenario
from nevsky.state import GameState


def _option_a_targets(s: GameState):
    return {m["args"].get("target_lord")
            for m in legal_moves(s, with_previews=False)
            if m.get("type") == "veche_action" and m["args"].get("option") == "A"}


def _setup_cta(seed=1):
    s = load_scenario("peipus", seed=seed)
    s.meta.phase = "levy"
    s.meta.levy_step = "call_to_arms"
    s.meta.active_player = "russian"
    s.veche.acted_this_call_to_arms = False
    if s.veche.vp_markers < 1:
        s.veche.vp_markers = 2
    return s


def _clear_cylinder(s: GameState, lid: str):
    for cb in s.calendar.boxes:
        if lid in cb.cylinders:
            cb.cylinders.remove(lid)
    if lid in s.calendar.off_left:
        s.calendar.off_left.remove(lid)
    if lid in s.calendar.off_right:
        s.calendar.off_right.remove(lid)


def test_option_a_not_offered_for_off_right_cylinder():
    s = _setup_cta()
    rus = next(lid for lid, l in s.lords.items() if l.side == "russian")
    _clear_cylinder(s, rus)
    s.calendar.off_right.append(rus)  # off the right edge -> handler rejects
    assert rus not in _option_a_targets(s)


def test_option_a_not_offered_for_off_left_cylinder():
    s = _setup_cta()
    rus = next(lid for lid, l in s.lords.items() if l.side == "russian")
    _clear_cylinder(s, rus)
    s.calendar.off_left.append(rus)  # off the left edge (box 0) -> handler rejects
    assert rus not in _option_a_targets(s)


def test_option_a_offered_for_on_calendar_cylinder_and_applies():
    s = _setup_cta()
    rus = next(lid for lid, l in s.lords.items() if l.side == "russian")
    _clear_cylinder(s, rus)
    s.calendar.boxes[4].cylinders.append(rus)  # box 5, on Calendar
    assert rus in _option_a_targets(s)
    apply_action(s, {"type": "veche_action", "side": "russian",
                     "args": {"option": "A", "target_lord": rus}})  # no raise


def test_every_enumerated_option_a_is_applicable():
    """The general alignment guarantee: every enumerated option-A move
    applies without no_cylinder."""
    for seed in range(1, 6):
        s = _setup_cta(seed)
        for tgt in _option_a_targets(s):
            s2 = _setup_cta(seed)
            try:
                apply_action(s2, {"type": "veche_action", "side": "russian",
                                  "args": {"option": "A", "target_lord": tgt}})
            except IllegalAction as e:
                raise AssertionError(f"enumerated option-A for {tgt} rejected: {e.args[0]}")
