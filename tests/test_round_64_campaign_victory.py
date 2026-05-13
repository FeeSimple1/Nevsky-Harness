"""Round 64 — SMOKE-055 regression tests.

Rule 5.2: "If at any moment during a Campaign one side has zero
Mustered Lords on the map, the game ends immediately and the OTHER
side wins, regardless of VP." The harness's
determine_scenario_winner reports the correct 5.2 winner, but
previously the game state continued mutating until the natural
Campaign-end check. Fix: in _remove_lord_permanently, after the
removal, scan Mustered-Lord counts during Campaign phase; if either
side has 0, short-circuit campaign_step to "done".
"""

import nevsky.actions  # noqa
from nevsky.scenarios import load_scenario, determine_scenario_winner
from nevsky.actions import _remove_lord_permanently
from nevsky.static_data import load_lords


def _remove_all_side(st, side):
    for lid in list(st.lords.keys()):
        L = st.lords[lid]
        if L.side == side and L.state == "mustered":
            _remove_lord_permanently(st, lid, load_lords()[lid])


def test_remove_all_teutonic_during_campaign_ends_immediately():
    st = load_scenario("pleskau", seed=1)
    st.meta.phase = "campaign"
    st.meta.campaign_step = "command"
    _remove_all_side(st, "teutonic")
    assert st.meta.campaign_step == "done"
    assert st.campaign_turn.actions_remaining == 0
    result = determine_scenario_winner(st)
    assert result["winner"] == "russian"
    assert result["applied_override"] == "campaign_victory"


def test_remove_all_russian_during_campaign_ends_immediately():
    st = load_scenario("pleskau", seed=1)
    st.meta.phase = "campaign"
    st.meta.campaign_step = "command"
    _remove_all_side(st, "russian")
    assert st.meta.campaign_step == "done"
    result = determine_scenario_winner(st)
    assert result["winner"] == "teutonic"


def test_partial_remove_during_campaign_does_not_end():
    """Removing only some Lords (side still has 1+ Mustered) does not end campaign."""
    st = load_scenario("pleskau", seed=1)
    st.meta.phase = "campaign"
    st.meta.campaign_step = "command"
    # Remove just hermann
    _remove_lord_permanently(st, "hermann", load_lords()["hermann"])
    # Teutons still have yaroslav + knud_and_abel mustered
    assert st.meta.campaign_step == "command"


def test_remove_all_during_levy_does_not_end_game():
    """The 5.2 rule applies only during Campaign phase. Levy Disband
    can permanently remove Lords (3.3.1) but the game shouldn't auto-
    end mid-Levy."""
    st = load_scenario("pleskau", seed=1)
    st.meta.phase = "levy"
    st.meta.levy_step = "disband"
    _remove_all_side(st, "teutonic")
    # Levy continues, not immediate game-over
    assert st.meta.phase == "levy"


def test_remove_after_already_done_no_op():
    """If campaign_step is already 'done', subsequent removals don't
    flip state back."""
    st = load_scenario("pleskau", seed=1)
    st.meta.phase = "campaign"
    st.meta.campaign_step = "done"
    _remove_all_side(st, "teutonic")
    assert st.meta.campaign_step == "done"
