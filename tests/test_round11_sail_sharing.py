"""Public Sail uses Shared Ships and temporary Lodya conversions."""

import pytest

from nevsky.actions import IllegalAction
from nevsky.llm.session import LLMSession
from nevsky.state import GameState
from nevsky.static_data import load_lords
from tests.test_cross_game_relief_retreat import place, position


def _activate(state, lid):
    state.meta.active_player = state.lords[lid].side
    state.campaign_turn.active_lord = state.campaign_turn.active_card = lid
    state.campaign_turn.actions_remaining = load_lords()[lid]["ratings"]["command"]
    return LLMSession(state, state.meta.active_player, "crusade_on_novgorod")


def _sail_moves(session, destination):
    return [m for m in session.legal_actions() if m["type"] == "cmd_sail"
            and m["args"]["destination"] == destination]


def _replay_sail(session, move, donor):
    state = session.state
    mat = state.lords[donor]
    before = dict(mat.assets), mat.location, mat.moved_fought
    restored = LLMSession(GameState.model_validate_json(state.model_dump_json()),
                          session.llm_side, "crusade_on_novgorod")
    assert session.apply(move) == restored.apply(move)
    assert state.model_dump_json() == restored.state.model_dump_json()
    assert (mat.assets, mat.location, mat.moved_fought) == before


@pytest.mark.parametrize("mode", ["local", "remote_cogs", "remote_without_cogs"])
def test_sail_can_leave_ship_owner_behind(mode):
    state = position(seed=1, box=9)
    hermann = place(state, "hermann", {"knights": 1}, provender=1)
    hermann.location = "reval"
    donor = place(state, "knud_and_abel", {"militia": 1}, ship=2 if mode == "local" else 1)
    donor.location = "reval" if mode == "local" else "riga"
    if mode == "remote_cogs":
        state.decks.teutonic.deck.remove("T18")
        state.decks.teutonic.capabilities_in_play.append("T18")
        donor.this_lord_capabilities = ["T18"]
    session = _activate(state, "hermann")
    moves = _sail_moves(session, "narwia")
    if mode == "remote_without_cogs":
        assert not moves
        before = state.model_dump_json()
        with pytest.raises(IllegalAction) as exc:
            session.apply({"type": "cmd_sail", "args": {"destination": "narwia"}})
        assert exc.value.code == "insufficient_ships"
        assert state.model_dump_json() == before
    else:
        move, = moves
        assert move["args"]["group"] == ["hermann"]
        assert "discard_excess_provender" not in move["args"]
        _replay_sail(session, move, donor.lord_id)
        assert hermann.location == "narwia" and hermann.assets["provender"] == 1


def test_sail_menu_can_use_a_co_located_lodya_owners_boats():
    state = position(seed=1, box=9)
    gavrilo = place(state, "gavrilo", {"knights": 1})
    donor = place(state, "domash", {"militia": 1}, boat=2)
    gavrilo.location = donor.location = "neva"
    state.decks.russian.deck.remove("R16")
    state.decks.russian.capabilities_in_play.append("R16")
    donor.this_lord_capabilities = ["R16"]
    session = _activate(state, "gavrilo")
    move, = _sail_moves(session, "luga")
    assert move["args"]["lodya_conversions"] == {"domash": {"boats_as_ships": 2}}
    before = state.model_dump_json()
    invalid = {**move, "args": {**move["args"], "lodya_conversions": {
        "domash": {"boats_as_ships": 3}}}}
    with pytest.raises(IllegalAction) as exc:
        session.apply(invalid)
    assert exc.value.code == "bad_lodya_conversion"
    assert state.model_dump_json() == before
    _replay_sail(session, move, "domash")
    assert gavrilo.location == "luga"
