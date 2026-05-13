"""Round 65 — SMOKE-056 regression tests.

Hold-event play handlers must verify that the card's `side` matches
the playing side. Per 1.9.1 / 3.4.4, Russian cards are for Russians,
Teutonic for Teutons. The harness previously trusted holds-list
membership but never side-checked the card.
"""

import pytest

import nevsky.actions  # noqa
from nevsky.scenarios import load_scenario
from nevsky.actions import apply_action, IllegalAction


def test_teu_cannot_play_russian_r3_pogost():
    """Teutonic player with R3 Pogost in holds is rejected."""
    st = load_scenario("watland", seed=1)
    st.decks.teutonic.holds.append("R3")
    rus_lord = next(lid for lid, L in st.lords.items() if L.side == "russian" and L.state == "mustered")
    with pytest.raises(IllegalAction) as exc:
        apply_action(st, {"type": "aow_play_hold", "side": "teutonic",
                          "args": {"card_id": "R3", "target": rus_lord}})
    assert exc.value.code == "wrong_side"


def test_rus_cannot_play_teutonic_t3():
    """Russian player with T3 Vodian Treachery in holds is rejected."""
    st = load_scenario("watland", seed=1)
    st.decks.russian.holds.append("T3")
    with pytest.raises(IllegalAction) as exc:
        apply_action(st, {"type": "aow_play_hold", "side": "russian",
                          "args": {"card_id": "T3", "target": "kaibolovo"}})
    assert exc.value.code == "wrong_side"


def test_own_side_hold_still_allowed():
    """Sanity: own-side Hold still plays normally (R3 by Russian)."""
    st = load_scenario("watland", seed=1)
    st.decks.russian.holds.append("R3")
    rus_lord = next(lid for lid, L in st.lords.items() if L.side == "russian" and L.state == "mustered")
    res = apply_action(st, {"type": "aow_play_hold", "side": "russian",
                           "args": {"card_id": "R3", "target": rus_lord}})
    assert res["card"] == "R3"


def test_lordship_plus_2_side_check_teu_plays_russian():
    """Lordship +2 Hold handler also rejects cross-side play."""
    st = load_scenario("watland", seed=1)
    st.decks.teutonic.holds.append("R8")
    rus_lord = next(lid for lid, L in st.lords.items() if L.side == "russian" and L.state == "mustered")
    st.meta.phase = "levy"
    st.meta.levy_step = "muster"
    st.meta.active_player = "teutonic"
    with pytest.raises(IllegalAction) as exc:
        apply_action(st, {"type": "aow_lordship_plus_2", "side": "teutonic",
                          "args": {"card_id": "R8", "lord_id": rus_lord, "mode": "lordship"}})
    assert exc.value.code == "wrong_side"
