"""Ambush blocks Avoid for the current Approach, including saved games."""

import json

import pytest

from nevsky.actions import IllegalAction, apply_action
from nevsky.legal_moves import legal_moves
from nevsky.llm.briefing import briefing_for_side
from nevsky.llm.session import LLMSession
from nevsky.state import GameState
from tests.test_round12_lieutenant_movement import PAIR, act, next_russian_card, plan, plan_position


def _hold_ambush(state, attacker):
    card = "T6" if attacker == "teutonic" else "R6"
    deck = getattr(state.decks, attacker)
    deck.deck.remove(card)
    deck.holds.append(card)
    return card


@pytest.mark.parametrize("attacker", ["teutonic", "russian"])
@pytest.mark.parametrize("legacy_save", [False, True])
def test_played_ambush_rejects_avoid_after_save_and_load(attacker, legacy_save, tmp_path):
    state = plan_position()
    defender = "russian" if attacker == "teutonic" else "teutonic"
    leader, target = ("hermann", "gavrilo") if attacker == "teutonic" else ("gavrilo", "hermann")
    state.lords[leader].location = "odenpah"
    state.lords[target].location = "dorpat"
    card = _hold_ambush(state, attacker)
    if attacker == "teutonic":
        state.locales["dorpat"].siege_markers = 1
        plan(state)
    else:
        plan(state, teutonic=["pass", "hermann", "hermann", "hermann", "yaroslav", "yaroslav"])
        next_russian_card(state)
    act(state, "cmd_march", attacker, to="dorpat", way_type="trackway")
    avoid = {"type": "avoid_battle", "side": defender,
             "args": {"to": "gdov", "way_type": "waterway"}}
    assets = {lid: dict(state.lords[lid].assets) for lid in (leader, target)}
    assert apply_action(state, avoid)["ambush_interrupt"]
    assert act(state, "play_ambush_block", attacker)["card_consumed"] == card
    assert {lid: state.lords[lid].assets for lid in assets} == assets
    assert state.lords[target].location == "dorpat"

    path = tmp_path / "ambush.json"
    LLMSession(state, defender, "pleskau").save(path)
    if legacy_save:
        old = json.loads(path.read_text())
        old_state = json.loads(old["state_json"])
        old_state["combat_pending"].pop("avoid_blocked_by_ambush")
        old["state_json"] = json.dumps(old_state)
        path.write_text(json.dumps(old))
    session = LLMSession.load(path)
    restored = session.state
    assert restored.model_dump_json() == state.model_dump_json()
    before = restored.model_dump_json()
    for menu in (legal_moves(restored, with_previews=False), session.legal_actions()):
        assert not any(move["type"] == "avoid_battle" for move in menu)
        assert any(move["type"] == "stand_battle" for move in menu)
    assert "Ambush blocked Avoid Battle" in briefing_for_side(restored, defender)
    with pytest.raises(IllegalAction, match="ambush_blocked"):
        apply_action(restored, avoid)
    with pytest.raises(IllegalAction, match="ambush_blocked"):
        session.apply(avoid)
    assert restored.model_dump_json() == before
    assert not session.history

    # Both legal continuations occur through the fixed-player API.
    if attacker == "teutonic":
        assert session.apply({"type": "stand_battle", "args": {"concede": "defender"}})["battle"]
    else:
        assert session.apply({"type": "withdraw"})["withdrew_lords"] == [target]
    assert restored.combat_pending is None


def test_ambush_block_survives_partial_withdrawal_by_a_linked_pair():
    state = plan_position()
    state.lords["hermann"].location = "sablia"
    third = "domash"
    state.lords[third].state = "mustered"
    for lid in (*PAIR, third):
        state.lords[lid].location = "novgorod"
    act(state, "place_lieutenant", lieutenant=PAIR[0], lower_lord=PAIR[1])
    _hold_ambush(state, "teutonic")
    plan(state)
    act(state, "cmd_march", "teutonic", to="novgorod", way_type="trackway")
    assert act(state, "avoid_battle", lords=PAIR, to="tesovo")["ambush_interrupt"]
    act(state, "play_ambush_block", "teutonic")
    assert act(state, "withdraw", lords=PAIR)["withdrew_lords"] == PAIR

    restored = GameState.model_validate_json(state.model_dump_json())
    assert restored.combat_pending.defender_lords == [third]
    assert not any(move["type"] == "avoid_battle"
                   for move in legal_moves(restored, with_previews=False))
    before = restored.model_dump_json()
    with pytest.raises(IllegalAction, match="ambush_blocked"):
        act(restored, "avoid_battle", lords=[third], to="tesovo")
    assert restored.model_dump_json() == before
    assert act(restored, "withdraw", lords=[third])["withdrew_lords"] == [third]
    assert restored.combat_pending is None
    assert all(restored.lords[lid].in_stronghold for lid in (*PAIR, third))
