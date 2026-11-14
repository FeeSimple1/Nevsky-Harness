"""Rule 3.5.3 discards both sides' Events after Call to Arms."""

import pytest

from nevsky.actions import IllegalAction, apply_action
from nevsky.legal_moves import legal_moves
from nevsky.scenarios import load_scenario


def _setup_call_to_arms(st):
    st.meta.phase = "levy"
    st.meta.levy_step = "call_to_arms"
    st.meta.active_player = "teutonic"
    st.meta.levy_step_completed_t = False
    st.meta.levy_step_completed_r = False
    st.legate.acted_this_call_to_arms = False
    st.veche.acted_this_call_to_arms = False


@pytest.mark.parametrize("has_events", [False, True])
def test_this_levy_events_are_retained_until_both_sides_advance(has_events):
    st = load_scenario("pleskau", seed=1)
    _setup_call_to_arms(st)
    decks = ((st.decks.teutonic, "T16"), (st.decks.russian, "R15"))
    if has_events:
        for deck, card in decks:
            deck.deck.remove(card)
            deck.this_levy_events.append(card)

    for side in ("teutonic", "russian"):
        assert all(m["type"] != "aow_discard_this_levy" for m in legal_moves(st))
        before = st.model_dump_json()
        with pytest.raises(IllegalAction) as error:
            apply_action(st, {"type": "aow_discard_this_levy", "side": side, "args": {}})
        assert error.value.code == "unknown_action"
        assert st.model_dump_json() == before
        for deck, card in decks:
            assert deck.this_levy_events == ([card] if has_events else [])
            assert card not in deck.discard
        apply_action(st, {"type": "advance_step", "side": side, "args": {}})

    assert st.meta.phase == "campaign"
    for deck, card in decks:
        assert deck.this_levy_events == []
        assert deck.discard.count(card) == int(has_events)
