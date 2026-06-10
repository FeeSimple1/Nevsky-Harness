"""Regression tests for three defects found in an independent review pass on
top of the Rule 5.2 work:

BUG 1 (HIGH): a failed Storm that wipes an attacker to zero units never
  removed the Lord (1.5.1 / 4.4.4 "lord_with_zero_units: permanently
  remove"), unlike the failed-Sally path. A unit-less cylinder lingered
  Mustered, so Rule 5.2 could never see that side reach zero Lords.
BUG 2 (MEDIUM): when BOTH sides reach zero Mustered Lords at once,
  _apply_immediate_campaign_victory left meta.winner = None while
  determine_scenario_winner returned a concrete 5.3 result.
BUG 3 (MEDIUM): _populate_event_args attached direction="left" to T1/T12
  even when no target existed, corrupting the only enumerated move into an
  always-rejected one -> driver deadlock in Levy Arts of War.
"""

from __future__ import annotations

import importlib.util

import pytest

from nevsky.actions import _apply_immediate_campaign_victory, apply_action
from nevsky.event_args import _populate_event_args
from nevsky.scenarios import determine_scenario_winner, load_scenario
from nevsky.static_data import load_lords


# --------------------------------------------------------------------------
# BUG 1: failed Storm removes a zero-unit attacker and fires Rule 5.2
# --------------------------------------------------------------------------
def _storm_setup(seed: int):
    s = load_scenario("pleskau", seed=seed)
    teu = next(lid for lid, l in s.lords.items()
               if l.side == "teutonic" and l.state == "mustered")
    # Make `teu` the LAST Mustered Teutonic Lord.
    for lid, l in s.lords.items():
        if l.side == "teutonic" and l.state == "mustered" and lid != teu:
            l.state = "disbanded"                       # type: ignore[assignment]
    rus = next(lid for lid, l in s.lords.items()
               if l.side == "russian" and l.state == "mustered")
    s.lords[rus].location = "pskov"
    s.lords[rus].in_stronghold = True
    s.lords[rus].forces = {"militia": 6, "archers": 2}  # strong garrison
    s.locales["pskov"].siege_markers = 1
    s.lords[teu].location = "pskov"
    s.lords[teu].in_stronghold = False
    s.lords[teu].forces = {"militia": 1}                # weak; gets wiped
    s.meta.phase = "campaign"                           # type: ignore[assignment]
    s.meta.campaign_step = "command"                    # type: ignore[assignment]
    s.meta.active_player = "teutonic"
    s.campaign_turn.next_to_reveal = "teutonic"
    s.campaign_turn.active_card = teu
    s.campaign_turn.active_lord = teu
    s.campaign_turn.actions_remaining = int(load_lords()[teu]["ratings"]["command"])
    s.campaign_turn.in_feed_pay_disband = False
    s.lords[teu].moved_fought = False
    return s, teu, rus


@pytest.mark.parametrize("seed", [0, 1, 2, 3, 4])
def test_failed_storm_wipes_last_attacker_triggers_5_2(seed: int) -> None:
    s, teu, rus = _storm_setup(seed)
    apply_action(s, {"type": "cmd_storm", "side": "teutonic",
                     "args": {"lord_id": teu}})
    # The wiped attacker is permanently removed (not a ghost Mustered cylinder).
    assert s.lords[teu].state == "removed"
    assert s.lords[teu].forces == {}
    # Rule 5.2: Teutons now have zero Mustered Lords -> Russia wins, terminal.
    assert sum(1 for l in s.lords.values()
               if l.side == "teutonic" and l.state == "mustered") == 0
    assert s.meta.game_over is True
    assert s.meta.campaign_step == "done"
    assert s.meta.winner == "russian"
    assert determine_scenario_winner(s)["applied_override"] == "campaign_victory"


def test_failed_storm_does_not_remove_attacker_that_keeps_units() -> None:
    """Control: an attacker that still has units after a failed Storm is NOT
    removed (the sweep only removes zero-unit Lords)."""
    # Two attackers: one wiped (1 unit), one strong (kept off the routed
    # path by giving it many units so survivors remain). Use a seed where
    # the strong Lord retains at least one unit.
    s = load_scenario("pleskau", seed=1)
    teu_list = [lid for lid, l in s.lords.items()
                if l.side == "teutonic" and l.state == "mustered"]
    strong = teu_list[0]
    rus = next(lid for lid, l in s.lords.items()
               if l.side == "russian" and l.state == "mustered")
    s.lords[rus].location = "pskov"; s.lords[rus].in_stronghold = True
    s.lords[rus].forces = {"militia": 6, "archers": 2}
    s.locales["pskov"].siege_markers = 1
    s.lords[strong].location = "pskov"; s.lords[strong].in_stronghold = False
    s.lords[strong].forces = {"militia": 8}             # many -> some survive
    s.meta.phase = "campaign"; s.meta.campaign_step = "command"
    s.meta.active_player = "teutonic"; s.campaign_turn.next_to_reveal = "teutonic"
    s.campaign_turn.active_card = strong; s.campaign_turn.active_lord = strong
    s.campaign_turn.actions_remaining = int(load_lords()[strong]["ratings"]["command"])
    s.campaign_turn.in_feed_pay_disband = False; s.lords[strong].moved_fought = False
    apply_action(s, {"type": "cmd_storm", "side": "teutonic",
                     "args": {"lord_id": strong}})
    # If the Lord kept any units it must remain on the map; if (rarely) all 8
    # routed and were lost, removal is correct. The invariant is: removed iff
    # zero units.
    if s.lords[strong].forces:
        assert s.lords[strong].state == "mustered"
    else:
        assert s.lords[strong].state == "removed"


# --------------------------------------------------------------------------
# BUG 2: both sides at zero records the canonical winner (no None)
# --------------------------------------------------------------------------
@pytest.mark.parametrize("scenario", ["watland", "pleskau"])
def test_both_sides_zero_records_canonical_winner(scenario: str) -> None:
    s = load_scenario(scenario, seed=1)
    s.meta.phase = "campaign"; s.meta.campaign_step = "command"
    s.calendar.teutonic_vp = 4.0
    s.calendar.russian_vp = 1.0
    for l in s.lords.values():
        if l.state == "mustered":
            l.state = "disbanded"                       # type: ignore[assignment]
    fired = _apply_immediate_campaign_victory(s)
    assert fired is True
    assert s.meta.game_over is True
    assert s.meta.winner is not None
    assert s.meta.winner == determine_scenario_winner(s)["winner"]


# --------------------------------------------------------------------------
# BUG 3: T1/T12 with no Calendar target does not corrupt the bare implement
# --------------------------------------------------------------------------
def test_t1_no_target_leaves_args_bare() -> None:
    s = load_scenario("pleskau", seed=1)
    # In pleskau neither Aleksandr nor Andrey is on the Calendar.
    out = _populate_event_args(s, "T1", {"card_id": "T1"})
    assert "target" not in out
    assert "direction" not in out, "direction must NOT be set without a target"


def test_t12_no_target_leaves_args_bare() -> None:
    s = load_scenario("pleskau", seed=1)
    out = _populate_event_args(s, "T12", {"card_id": "T12"})
    assert "target" not in out
    assert "direction" not in out


def test_selfplay_pleskau_no_t1_deadlock() -> None:
    """The project's own self-play driver previously deadlocked at the T1
    implement step on pleskau; it must now run to a terminal state."""
    spec = importlib.util.spec_from_file_location("sp", "scripts/self_play.py")
    sp = spec.loader  # type: ignore[assignment]
    import importlib.util as _u
    mod = _u.module_from_spec(spec)
    spec.loader.exec_module(mod)                         # type: ignore[union-attr]
    res = mod.step_self_play("pleskau", seed=1, max_steps=600)
    assert res.get("error") is None, f"driver error: {res.get('error')}"
    assert res.get("terminal") is True
