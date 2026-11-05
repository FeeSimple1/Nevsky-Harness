"""Round 3 Nevsky audit. Resolve Spoils against the survivors of combat."""

import pytest

from nevsky.actions import apply_action
from nevsky.scenarios import load_scenario


def position(seed, active="hermann", side="teutonic"):
    state = load_scenario("crusade_on_novgorod", seed=seed)
    state.meta.phase = "campaign"
    state.meta.campaign_step = "command"
    state.meta.active_player = side
    state.campaign_turn.active_card = state.campaign_turn.active_lord = active
    state.campaign_turn.actions_remaining = 2
    for lord in state.lords.values():
        lord.state = "removed"
        lord.location = None
        lord.in_stronghold = False
        lord.forces = {}
        lord.routed_units = {}
        lord.assets = {}
    for locale in ("pskov", "novgorod"):
        state.locales[locale].teutonic_conquered = 0
        state.locales[locale].russian_conquered = 0
        state.locales[locale].siege_markers = 0
    state.decks.russian.holds = []
    state.decks.teutonic.holds = []
    return state


def place(state, lid, forces, locale="pskov", *, inside=False, **assets):
    lord = state.lords[lid]
    lord.state = "mustered"
    lord.location = locale
    lord.in_stronghold = inside
    lord.forces = forces
    lord.assets = assets


@pytest.mark.parametrize("seed, removed", [(1, True), (4, False)])
def test_failed_sally_captures_assets_only_from_a_removed_withdrawer(seed, removed):
    state = position(seed, "gavrilo", "russian")
    state.locales["pskov"].siege_markers = 2
    place(state, "gavrilo", {"militia": 1}, inside=True, coin=3, cart=1, provender=2, ship=1)
    place(state, "hermann", {"knights": 2, "men_at_arms": 3})
    place(state, "aleksandr", {"knights": 1}, "novgorod")

    result = apply_action(state, {
        "type": "cmd_sally", "side": "russian", "args": {"lord_id": "gavrilo"},
    })

    assert result["battle"]["winner"] == "teutonic"
    assert state.locales["pskov"].siege_markers == 1
    assets = {"coin": 3, "cart": 1, "provender": 2}
    if removed:
        assert result["removed_after_sally"] == ["gavrilo"]
        assert result["spoils"][0]["distributed"] == {"hermann": assets}
        assert state.lords["gavrilo"].state == "removed"
        assert state.lords["hermann"].assets == assets
    else:
        assert "spoils" not in result
        assert state.lords["gavrilo"].in_stronghold
        assert state.lords["gavrilo"].assets == {**assets, "ship": 1}
        assert state.lords["hermann"].assets == {}


def test_failed_sally_spoils_skip_a_besieger_removed_by_losses():
    state = position(27, "gavrilo", "russian")
    state.locales["pskov"].siege_markers = 1
    place(state, "gavrilo", {"knights": 2, "men_at_arms": 2}, inside=True, coin=3, ship=1)
    place(state, "hermann", {"militia": 1})
    place(state, "yaroslav", {"knights": 3, "men_at_arms": 4})
    place(state, "aleksandr", {"knights": 1}, "novgorod")

    result = apply_action(state, {
        "type": "cmd_sally", "side": "russian", "args": {"lord_id": "gavrilo"},
    })

    assert result["removed_after_sally"] == ["gavrilo"]
    assert result["winner_removed_by_losses"] == ["hermann"]
    assert result["spoils"][0]["distributed"] == {"yaroslav": {"coin": 3}}
    assert state.lords["yaroslav"].assets == {"coin": 3}


def test_battle_spoils_skip_a_preferred_lord_removed_by_losses():
    state = position(1)
    place(state, "hermann", {"militia": 1}, "izborsk")
    place(state, "yaroslav", {"knights": 2, "men_at_arms": 3}, "izborsk")
    place(state, "gavrilo", {"knights": 2, "men_at_arms": 2}, coin=3, loot=2, cart=1)
    place(state, "aleksandr", {"knights": 1}, "novgorod")
    apply_action(state, {
        "type": "cmd_march", "side": "teutonic",
        "args": {"lord_id": "hermann", "to": "pskov", "group": ["hermann", "yaroslav"]},
    })
    plan = {"hermann": {"loot": 2}}

    result = apply_action(state, {
        "type": "stand_battle", "side": "russian",
        "args": {"concede": "defender", "concede_round": 2,
                 "spoils_recipient": "hermann", "spoils_allocation": plan},
    })

    assert result["winner"] == "teutonic"
    assert result["winner_removed_by_losses"] == ["hermann"]
    assert result["spoils"][0]["distributed"] == {"yaroslav": {"loot": 2}}
    assert state.lords["hermann"].assets == {}
    assert state.lords["yaroslav"].assets == {"loot": 2}
    assert state.lords["gavrilo"].assets == {"coin": 3, "cart": 1}
    assert plan == {"hermann": {"loot": 2}}


def test_successful_sally_spoils_skip_a_sallying_lord_removed_by_losses():
    state = position(1, "domash", "russian")
    state.locales["pskov"].siege_markers = 1
    place(state, "domash", {"militia": 1}, inside=True)
    place(state, "gavrilo", {"knights": 2, "men_at_arms": 3}, inside=True)
    place(state, "hermann", {"knights": 2, "men_at_arms": 2}, loot=2)

    result = apply_action(state, {
        "type": "cmd_sally", "side": "russian",
        "args": {"lord_id": "domash", "concede": "defender", "concede_round": 2},
    })

    assert result["sally_outcome"] == "broken_siege"
    assert result["winner_removed_by_losses"] == ["domash"]
    assert result["spoils"][0]["distributed"] == {"gavrilo": {"loot": 2}}
    assert state.lords["gavrilo"].assets == {"loot": 2}


def test_all_sack_spoils_use_survivors_of_storm_losses():
    state = position(4)
    state.locales["novgorod"].siege_markers = 3
    state.veche.coin = 2
    place(state, "hermann", {"militia": 1}, "novgorod")
    place(state, "yaroslav", {"knights": 8, "men_at_arms": 4}, "novgorod")
    place(state, "gavrilo", {"militia": 1}, "novgorod", inside=True, cart=1, ship=1)
    place(state, "aleksandr", {"knights": 1}, "pskov")

    result = apply_action(state, {
        "type": "cmd_storm", "side": "teutonic",
        "args": {"lord_id": "hermann", "spoils_recipient": "hermann"},
    })

    assert result["battle"]["winner"] == "attacker"
    assert result["winner_removed_by_losses"] == ["hermann"]
    assert result["sack_spoils_distribution"] == [
        {"from_lord": "gavrilo", "split": {"yaroslav": {"cart": 1}}},
    ]
    assert result["stronghold_spoils_distribution"] == {
        "yaroslav": {"coin": 3, "loot": 3, "provender": 3},
    }
    assert result["veche_coin_distribution"] == {"yaroslav": {"coin": 2}}
    assert result["spoils_recipient"] == "yaroslav"
    assert state.veche.coin == 0
    assert state.lords["yaroslav"].assets == {"cart": 1, "coin": 5, "loot": 3, "provender": 3}
