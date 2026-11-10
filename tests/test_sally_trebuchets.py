"""N6-02. A friendly Trebuchets bearer can support a Sally until Rout."""

from nevsky.actions import apply_action
from nevsky.state import GameState
from tests.test_cross_game_relief_retreat import place, position, stand
from tests.test_cross_game_sally import sally, sally_state


def _relief_battle(bearer=None, *, bearer_locale="pskov", doomed=False):
    state = position(seed=1, box=9)
    state.campaign_turn.active_lord = state.campaign_turn.active_card = "andreas"
    andreas = place(state, "andreas", {"militia": 1} if doomed else {
        "knights": 2, "men_at_arms": 2,
    })
    andreas.location = "ostrov"
    place(state, "rudolf", {"knights": 1, "men_at_arms": 2}).in_stronghold = True
    if doomed:
        place(state, "gavrilo", {"knights": 1, "men_at_arms": 2})
    else:
        hermann = place(state, "hermann", {"men_at_arms": 2})
        hermann.location = bearer_locale
        hermann.in_stronghold = bearer_locale == "pskov"
        place(state, "aleksandr", {"knights": 2, "men_at_arms": 4})
    state.locales["pskov"].teutonic_conquered = 2
    state.locales["pskov"].siege_markers = 1
    if bearer:
        deck = state.decks.teutonic
        for pile in (deck.deck, deck.holds, deck.discard, deck.removed):
            pile[:] = [card for card in pile if card != "T14"]
        state.lords[bearer].this_lord_capabilities.append("T14")

    apply_action(state, {"type": "cmd_march", "side": "teutonic", "args": {
        "lord_id": "andreas", "to": "pskov", "way_type": "waterway", "sally_join": ["rudolf"],
    }})
    state = GameState.model_validate_json(state.model_dump_json())
    return stand(state, concede_round=2)["battle"]


def _siegeworks_absorptions(battle):
    return [(entry["round"], step["step"], hit["absorbed"])
            for entry in battle["log"] for step in entry.get("steps", [])
            for hit in step["distribution"] if hit.get("target") == "siegeworks_vs_sally"]


def test_relief_sally_gets_trebuchets_from_a_nonjoining_lord_at_the_locale():
    control = _relief_battle()
    elsewhere = _relief_battle("hermann", bearer_locale="dorpat")
    supporting = _relief_battle("hermann")
    assert elsewhere == control
    assert "hermann" not in supporting["attacker_lords"]
    assert supporting["relief_sally"]["sallying_lords"] == ["rudolf"]
    assert _siegeworks_absorptions(control) == [(2, "melee_horse_attacker", 1)]
    assert _siegeworks_absorptions(supporting) == []


def test_relief_sally_loses_trebuchets_as_soon_as_the_bearer_routs():
    control = _relief_battle(doomed=True)
    with_trebuchets = _relief_battle("andreas", doomed=True)
    defending_horse = next(step for step in with_trebuchets["log"][0]["steps"]
                           if step["step"] == "melee_horse_defender")
    assert defending_horse["distribution"][0]["routed"] == [
        {"unit": "militia", "absorbed": False},
    ]
    assert _siegeworks_absorptions(with_trebuchets)[0] == (1, "melee_horse_attacker", 1)
    assert with_trebuchets == control


def test_simple_sally_reserves_siegeworks_for_the_besiegers():
    battle = sally(sally_state(seed=1), concede="attacker")["battle"]
    defending_horse = next(step for step in battle["log"][0]["steps"]
                           if step["step"] == "melee_horse_defender")
    assert all(hit.get("target") != "siegeworks_vs_sally"
               for hit in defending_horse["distribution"])
    assert defending_horse["distribution"][0]["hits"] == 2
