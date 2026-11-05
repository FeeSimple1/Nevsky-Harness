"""Cross-game N1–N3: Sally uses normal Battle Events, array and Losses."""
from __future__ import annotations

import pytest

from nevsky.actions import IllegalAction, apply_action
from nevsky.legal_moves import legal_moves
from nevsky.scenarios import load_scenario


def sally_state(seed=4):
    state = load_scenario("crusade_on_novgorod", seed=seed)
    state.meta.phase = "campaign"
    state.meta.campaign_step = "command"
    state.meta.active_player = "russian"
    state.campaign_turn.active_card = "gavrilo"
    state.campaign_turn.active_lord = "gavrilo"
    state.campaign_turn.actions_remaining = 2
    for lid in ("gavrilo", "hermann"):
        state.lords[lid].location = "pskov"
        state.lords[lid].routed_units = {}
    state.lords["gavrilo"].in_stronghold = True
    state.lords["gavrilo"].forces = {"knights": 2, "men_at_arms": 3}
    state.lords["hermann"].in_stronghold = False
    state.lords["hermann"].forces = {"knights": 1}
    state.locales["pskov"].teutonic_conquered = 0
    state.locales["pskov"].russian_conquered = 0
    state.locales["pskov"].siege_markers = 1
    return state


def add_hold(state, card):
    deck = state.decks.teutonic if card.startswith("T") else state.decks.russian
    for zone in ("deck", "discard", "holds", "pending_draw", "capabilities_in_play"):
        cards = getattr(deck, zone)
        while card in cards:
            cards.remove(card)
    deck.holds.append(card)


def sally(state, **args):
    return apply_action(state, {"type": "cmd_sally", "side": "russian",
                                "args": {"lord_id": "gavrilo", **args}})


def test_fully_routed_besieger_gets_losses_roll_and_survives():
    state = sally_state(seed=4)
    result = sally(state, retreat_to={"hermann": "dubrovno"})
    assert result["battle"]["loser"] == "teutonic"
    losses = next(x for x in result["losses"] if x["lord_id"] == "hermann")
    assert losses["rolls"][0]["n_routed"] == 1
    assert losses["rolls"][0]["kept"] == 1
    lord = state.lords["hermann"]
    assert lord.state == "mustered" and lord.location == "dubrovno"
    assert lord.forces == {"knights": 1} and not lord.routed_units
    assert "hermann" not in result.get("removed", [])
    assert result["siege_lifted"] is True


def test_field_organ_from_menu_is_consumed_and_changes_real_combat():
    state = sally_state()
    add_hold(state, "T10")
    control = state.model_copy(deep=True)
    move = next(m for m in legal_moves(state, with_previews=False)
                if m["type"] == "cmd_sally")
    event = next(h for h in move["holds_available"] if h["card"] == "T10")
    assert event["requires"]["field_organ_lord"] == ["hermann"]
    result = sally(state, holds={event["key"]: event["card"],
                                 "field_organ_lord": "hermann"})
    baseline = sally(control)
    assert result["battle"]["holds_consumed"] == [{"card": "T10", "key": "field_organ"}]
    assert "T10" not in state.decks.teutonic.holds
    assert "T10" in state.decks.teutonic.discard
    assert result["battle"]["log"] != baseline["battle"]["log"]
    assert "T10" in control.decks.teutonic.holds  # Declining remains legal.


def test_active_sally_lord_takes_center_and_other_array_choice_is_honored():
    state = sally_state(seed=3)
    lord = state.lords["aleksandr"]  # Earlier in the state dict than Gavrilo.
    lord.state = "mustered"
    lord.location = "pskov"
    lord.in_stronghold = True
    lord.forces = {"knights": 1, "men_at_arms": 1}
    lord.assets = {"provender": 1}
    choices = []
    def choose(decision):
        choices.append(decision)
        if decision["type"] == "initial_placement_attacker":
            return "right"
        return decision["options"][0]
    result = sally(state, decision_callback=choose)
    assert result["battle"]["attacker_positions"]["gavrilo"] == "center"
    assert result["battle"]["attacker_positions"]["aleksandr"] == "right"
    assert any(d["type"] == "initial_placement_attacker" for d in choices)


@pytest.mark.parametrize("card,key,target,error", [
    ("R2", "marsh", None, "role_blocked"),
    ("T10", "field_organ", "gavrilo", "bad_target"),
    ("T10", "field_organ", "yaroslav", "bad_target"),
    ("R4", "raven_rock", None, "season_blocked"),
])
def test_illegal_sally_hold_is_rejected_without_mutation(card, key, target, error):
    state = sally_state()
    add_hold(state, card)
    holds = {key: card}
    if target:
        holds["field_organ_lord"] = target
    before = state.model_dump_json()
    with pytest.raises(IllegalAction) as exc:
        sally(state, holds=holds)
    assert exc.value.code == error
    assert state.model_dump_json() == before
    move = next(m for m in legal_moves(state, with_previews=False)
                if m["type"] == "cmd_sally")
    offered = {h["card"] for h in move.get("holds_available", [])}
    if card != "T10":
        assert card not in offered


def test_conceding_besieger_who_dies_in_losses_yields_spoils_and_ransom():
    state = sally_state(seed=1)
    state.lords["hermann"].forces = {"knights": 1, "militia": 1}
    state.lords["hermann"].assets = {"coin": 1, "cart": 1, "ship": 1}
    state.lords["gavrilo"].assets = {"provender": 2}
    add_hold(state, "R7")
    state.decks.russian.holds.remove("R7")
    state.decks.russian.capabilities_in_play.append("R7")
    result = sally(state, concede="defender", concede_round=2)
    assert result["battle"]["conceded"] == "defender"
    assert state.lords["hermann"].state == "removed"
    assert result["removed"] == ["hermann"]
    assert result["spoils"][0]["mode"] == "all_except_ships"
    assert result["spoils"][0]["transferred"] == {"coin": 1, "cart": 1}
    assert result["ransom"] == [{"ransom": True, "removed": "hermann",
                                "recipient": "gavrilo", "coin": 4}]
    assert state.lords["gavrilo"].assets["coin"] == 5


def test_fully_routed_besieger_without_retreat_is_still_removed():
    from nevsky.campaign import _legal_retreat_dests
    state = sally_state(seed=4)  # Would recover on a Losses roll if Retreat were possible.
    destinations = {dest for dest, _ in _legal_retreat_dests(state, "pskov", "teutonic")}
    blockers = [lord for lid, lord in state.lords.items()
                if lord.side == "russian" and lid != "gavrilo"]
    assert len(blockers) >= len(destinations)
    for destination, lord in zip(sorted(destinations), blockers):
        lord.state = "mustered"
        lord.location = destination
        lord.in_stronghold = False
        lord.forces = {"militia": 1}
    assert _legal_retreat_dests(state, "pskov", "teutonic") == []
    result = sally(state)
    assert state.lords["hermann"].state == "removed"
    assert "hermann" in result["removed"]
    assert not result.get("retreats")


def test_surviving_conceding_besieger_retains_non_spoils_assets():
    state = sally_state(seed=8)
    state.lords["hermann"].forces = {"knights": 1, "militia": 1}
    state.lords["hermann"].assets = {"coin": 1, "cart": 1, "ship": 1}
    result = sally(state, concede="defender", concede_round=2)
    assert result["battle"]["conceded"] == "defender"
    assert state.lords["hermann"].state == "mustered"
    assert result["spoils"][0]["mode"] == "loot_and_excess"
    assert state.lords["hermann"].assets == {"coin": 1, "cart": 1, "ship": 1}
