"""N2-01/02/03: public combat aftermath, occupancy and shared Retreat loads."""

from __future__ import annotations

import pytest

from nevsky import battle
from nevsky.actions import IllegalAction, apply_action
from nevsky.campaign import SALLY_FATE_ACTION
from nevsky.legal_moves import legal_moves
from nevsky.llm.tools import apply_action_for_side, legal_actions_for_side
from nevsky.rewards import REWARD_ACTION
from nevsky.scenarios import load_scenario
from nevsky.state import CombatPending, GameState


def position(seed=1, box=1):
    state = load_scenario("crusade_on_novgorod", seed=seed)
    state.meta.box = box
    state.meta.phase = "campaign"
    state.meta.campaign_step = "command"
    state.meta.active_player = "teutonic"
    state.campaign_turn.active_card = state.campaign_turn.active_lord = "hermann"
    state.campaign_turn.actions_remaining = 2
    for lord in state.lords.values():
        lord.in_stronghold = False
        lord.routed_units = {}
        lord.state = "removed"
        lord.location = None
        lord.assets = {}
    state.locales["pskov"].siege_markers = 0
    state.locales["pskov"].teutonic_conquered = 0
    state.locales["pskov"].russian_conquered = 0
    return state


def place(state, lid, forces=None, **assets):
    lord = state.lords[lid]
    lord.state = "mustered"
    lord.location = "pskov"
    lord.forces = forces or {"knights": 1, "men_at_arms": 2}
    lord.assets = dict(assets)
    return lord


def field(seed=1, box=1):
    state = position(seed, box)
    place(state, "hermann", {"knights": 1, "sergeants": 1, "men_at_arms": 1})
    place(state, "gavrilo", provender=2)
    place(state, "domash", {"sergeants": 1, "men_at_arms": 2}, cart=2)
    state.combat_pending = CombatPending(
        attacker_side="teutonic",
        attacker_group=["hermann"],
        defender_side="russian",
        defender_lords=["gavrilo", "domash"],
        from_locale="ostrov",
        to_locale="pskov",
        way_type="waterway",
        pending_response_by="russian",
    )
    state.meta.active_player = "russian"  # The defender owes the Approach response.
    return state


def stand(state, **args):
    return apply_action(
        state, {"type": "stand_battle", "side": "russian", "args": {"concede": "defender", **args}}
    )


def relief(seed):
    state = position(seed)
    state.meta.active_player = "russian"
    state.campaign_turn.active_card = state.campaign_turn.active_lord = "aleksandr"
    place(state, "aleksandr", {"knights": 1, "men_at_arms": 1}, coin=1)
    place(state, "gavrilo", {"knights": 1, "militia": 2}, coin=1, provender=2)
    place(
        state,
        "hermann",
        {"knights": 2, "sergeants": 1, "men_at_arms": 2, "militia": 1},
        coin=1,
        provender=2,
    )
    state.lords["gavrilo"].in_stronghold = True
    state.locales["pskov"].siege_markers = 2
    state.combat_pending = CombatPending(
        attacker_side="russian",
        attacker_group=["aleksandr"],
        defender_side="teutonic",
        defender_lords=["hermann"],
        from_locale="ostrov",
        to_locale="pskov",
        way_type="waterway",
        pending_response_by="teutonic",
    )
    state.meta.active_player = "teutonic"
    return state


@pytest.mark.parametrize("seed", [1, 8])
def test_losing_relief_joiner_withdraws_and_resolves_all_routed_losses(seed, monkeypatch):
    state = relief(seed)
    observed = {}
    resolver = battle.resolve_battle

    def observe(*args, **kwargs):
        result = resolver(*args, **kwargs)
        observed["forces"] = dict(state.lords["gavrilo"].forces)
        observed["routed"] = dict(state.lords["gavrilo"].routed_units)
        return result

    monkeypatch.setattr(battle, "resolve_battle", observe)
    result = apply_action(
        state,
        {
            "type": "stand_battle",
            "side": "teutonic",
            "args": {"concede": "attacker", "concede_round": 2},
        },
    )
    assert result["loser"] == "russian" and observed["routed"]
    assert bool(observed["forces"]) == (seed == 8)
    lord = state.lords["gavrilo"]
    assert not lord.routed_units
    losses = next(rec for rec in result["losses"] if rec["lord_id"] == lord.lord_id)
    assert sum(rec["n_routed"] for rec in losses["rolls"]) == sum(observed["routed"].values())
    assert not any(rec["lord"] == "gavrilo" for rec in result["retreats"])
    if lord.state == "mustered":
        assert lord.location == "pskov" and lord.in_stronghold
        assert "gavrilo" in result["sally_withdrew"]
        assert not any(rec["from"] == "gavrilo" for rec in result["spoils"])
    else:
        assert "gavrilo" in result["removed"]
        assert (
            next(rec for rec in result["spoils"] if rec["from"] == "gavrilo")["mode"]
            == "all_except_ships"
        )


def crowded_withdrawal(existing=False):
    state = field()
    for lid in ("aleksandr", "andrey"):
        place(state, lid, provender=1)
    state.combat_pending.defender_lords = ["aleksandr", "gavrilo", "domash", "andrey"]
    if existing:
        for lid in ("gavrilo", "andrey"):
            state.lords[lid].in_stronghold = True
        state.combat_pending.defender_lords = ["aleksandr", "domash"]
    else:
        apply_action(
            state, {"type": "withdraw", "side": "russian", "args": {"lords": ["gavrilo", "andrey"]}}
        )
    return state


@pytest.mark.parametrize("existing", [False, True])
@pytest.mark.parametrize("selection", [True, ["aleksandr", "domash"]])
def test_battle_withdrawal_counts_existing_occupants_and_rejects_atomically(existing, selection):
    state = crowded_withdrawal(existing)
    saved = state.model_dump_json()
    retained_lord = state.lords["aleksandr"]
    with pytest.raises(IllegalAction) as error:
        stand(state, withdraw_losers=selection)
    assert error.value.code == "over_capacity"
    assert state.model_dump_json() == saved and state.lords["aleksandr"] is retained_lord
    retry = GameState.model_validate_json(saved)
    for target in (state, retry):
        stand(target, withdraw_losers=["aleksandr"], retreat_to={"domash": "dubrovno"})
        inside = [
            lid
            for lid, lord in target.lords.items()
            if lord.state == "mustered" and lord.location == "pskov" and lord.in_stronghold
        ]
        assert set(inside) == {"aleksandr", "gavrilo", "andrey"}
        assert target.lords["domash"].location == "dubrovno"
    assert state.model_dump_json() == retry.model_dump_json()


@pytest.mark.parametrize(
    "food,carts,other_food,other_carts,kept,other_kept",
    [
        (2, 0, 0, 2, 2, 0),
        (3, 2, 2, 2, 2, 2),
        (1, 3, 4, 0, 1, 2),
        (3, 0, 1, 2, 1, 1),
        (1, 0, 1, 0, 0, 0),
    ],
)
def test_conceding_co_retreaters_share_spare_carts(
    food, carts, other_food, other_carts, kept, other_kept
):
    state = field()
    state.lords["gavrilo"].assets = {"provender": food, "cart": carts, "loot": 1}
    state.lords["domash"].assets = {"provender": other_food, "cart": other_carts}
    result = stand(state, retreat_to={"gavrilo": "dubrovno", "domash": "dubrovno"})
    assert all(state.lords[lid].state == "mustered" for lid in ("gavrilo", "domash"))
    assert state.lords["gavrilo"].assets.get("provender", 0) == kept
    assert state.lords["domash"].assets.get("provender", 0) == other_kept
    assert state.lords["gavrilo"].assets["cart"] == carts
    assert state.lords["domash"].assets["cart"] == other_carts
    assert (
        state.lords["hermann"].assets.get("provender", 0) == food + other_food - kept - other_kept
    )
    assert state.lords["hermann"].assets["loot"] == 1
    assert all(rec["mode"] == "loot_and_excess" for rec in result["spoils"])


@pytest.mark.parametrize("withdraw", [False, True])
def test_separate_destination_or_withdrawer_cannot_lend_transport(withdraw):
    state = field()
    args = {"retreat_to": {"gavrilo": "dubrovno", "domash": "zhelcha_river"}}
    if withdraw:
        args = {"withdraw_losers": ["domash"], "retreat_to": {"gavrilo": "dubrovno"}}
    stand(state, **args)
    assert state.lords["gavrilo"].assets.get("provender", 0) == 0
    assert state.lords["hermann"].assets["provender"] == 2
    assert state.lords["domash"].assets["cart"] == 2
    assert state.lords["domash"].in_stronghold == withdraw


@pytest.mark.parametrize("priority", ["gavrilo", "domash"])
def test_player_priority_selects_who_keeps_shared_food_after_save_load(priority):
    state = field()
    place(state, "aleksandr", cart=2)
    state.combat_pending.defender_lords.append("aleksandr")
    for lid in ("gavrilo", "domash"):
        state.lords[lid].forces = {"knights": 3}
        state.lords[lid].assets = {"provender": 2}
    move = next(
        move
        for move in legal_moves(state, with_previews=False)
        if move["type"] == "stand_battle" and not move["args"]
    )
    assert priority in move["retreat_keep_order_options"]
    assert "retreat_keep_order" in move["retreat_keep_order_template"]
    saved = state.model_dump_json()
    retry = GameState.model_validate_json(saved)
    for target in (state, retry):
        stand(
            target,
            retreat_keep_order=[priority],
            retreat_to={lid: "dubrovno" for lid in ("gavrilo", "domash", "aleksandr")},
        )
        assert target.lords[priority].assets["provender"] == 2
        other = "domash" if priority == "gavrilo" else "gavrilo"
        assert not target.lords[other].assets.get("provender")
    assert state.model_dump_json() == retry.model_dump_json()


def test_owner_can_prioritize_allied_food_over_the_transport_holders_food():
    state = field()
    state.lords["domash"].assets = {"provender": 2, "cart": 2}
    control = state.model_copy(deep=True)
    stand(
        control,
        retreat_keep_order=["not_a_lord"],
        retreat_to={"gavrilo": "dubrovno", "domash": "dubrovno"},
    )
    assert not control.lords["gavrilo"].assets.get("provender")
    assert control.lords["domash"].assets["provender"] == 2
    stand(
        state,
        retreat_keep_order=["gavrilo"],
        retreat_to={"gavrilo": "dubrovno", "domash": "dubrovno"},
    )
    assert state.lords["gavrilo"].assets["provender"] == 2
    assert not state.lords["domash"].assets.get("provender")
    assert state.lords["domash"].assets["cart"] == 2
    assert state.lords["hermann"].assets["provender"] == 2


def _march_for_split_retreat():
    state = position()
    place(state, "hermann").location = "izborsk"
    place(state, "gavrilo", provender=2)
    place(state, "domash", cart=2, provender=2)
    apply_action(state, {"type": "cmd_march", "side": "teutonic",
                         "args": {"lord_id": "hermann", "to": "pskov", "way_type": "trackway"}})
    return state


@pytest.mark.parametrize("staged", [False, True])
def test_conceding_owners_can_split_shared_transport_after_a_real_march(staged):
    state = _march_for_split_retreat()
    split = {"gavrilo": 1, "domash": 1}
    retreats = {"gavrilo": "dubrovno", "domash": "dubrovno"}
    if staged:
        result = apply_action_for_side(state, "russian", {
            "type": "stand_battle", "args": {"concede": "defender", "retreat_to": retreats},
        })
        assert result["awaiting_aftermath_reward"] == {
            "owed_by": "russian", "reward": "retreat_provender",
        }
        assert not state.lords["hermann"].assets.get("provender")
        state = GameState.model_validate_json(state.model_dump_json())
        [move] = legal_actions_for_side(state, "russian")
        assert move["type"] == REWARD_ACTION
        assert move["reward"]["groups"] == [{
            "destination": "dubrovno", "way_type": "trackway",
            "on_mats": {"gavrilo": 2, "domash": 2},
            "total_to_keep": 2, "default": {"gavrilo": 0, "domash": 2},
        }]
        before = state.model_dump_json()
        for side, args, code in [
            ("teutonic", {"retreat_keep": split}, "wrong_actor"),
            ("russian", {"retreat_keep": {"gavrilo": 1}}, "bad_retreat_keep"),
            ("russian", {"retreat_keep": {"gavrilo": True, "domash": 1}}, "bad_retreat_keep"),
        ]:
            with pytest.raises(IllegalAction, match=code):
                apply_action_for_side(state, side, {"type": REWARD_ACTION, "args": args})
            assert state.model_dump_json() == before
        result = apply_action_for_side(state, "russian", {
            "type": REWARD_ACTION, "args": {"retreat_keep": split},
        })
        assert state.meta.active_player == "teutonic"
    else:
        move = next(m for m in legal_moves(state, with_previews=False)
                    if m["type"] == "stand_battle")
        assert "retreat_keep" in move["retreat_keep_template"]
        result = stand(state, retreat_to=retreats, retreat_keep=split)
    assert all(state.lords[lid].assets["provender"] == 1 for lid in split)
    assert state.lords["domash"].assets["cart"] == 2
    assert state.lords["hermann"].assets["provender"] == 2
    assert [row["transferred"] for row in result["spoils"]] == [
        {"provender": 1}, {"provender": 1},
    ]


def test_retreat_keep_cannot_shift_capacity_between_destinations():
    state = _march_for_split_retreat()
    before = state.model_dump_json()
    with pytest.raises(IllegalAction, match="bad_retreat_keep"):
        stand(state, retreat_to={"gavrilo": "zhelcha_river", "domash": "dubrovno"},
              retreat_keep={"gavrilo": 1, "domash": 1})
    assert state.model_dump_json() == before


@pytest.mark.parametrize("order", ["gavrilo", ["gavrilo", "gavrilo"], [1]])
def test_malformed_keep_order_rejects_after_combat_without_state_or_rng_mutation(order):
    state = field()
    before = state.model_dump_json()
    with pytest.raises(IllegalAction) as error:
        stand(state, retreat_keep_order=order)
    assert error.value.code == "bad_retreat_keep_order"
    assert state.model_dump_json() == before


def test_relief_joiner_lost_in_withdrawal_yields_spoils_and_ransom():
    state = relief(27)
    state.decks.teutonic.deck.remove("T16")
    state.decks.teutonic.capabilities_in_play.append("T16")
    result = apply_action(
        state,
        {
            "type": "stand_battle",
            "side": "teutonic",
            "args": {"concede": "attacker", "concede_round": 2},
        },
    )
    assert result["removed"] == ["gavrilo"]
    assert state.lords["gavrilo"].state == "removed"
    assert not state.lords["gavrilo"].routed_units
    assert result["ransom"] == [
        {"ransom": True, "removed": "gavrilo", "recipient": "hermann", "coin": 4}
    ]
    spoil = next(rec for rec in result["spoils"] if rec["from"] == "gavrilo")
    assert spoil["mode"] == "all_except_ships"
    assert spoil["transferred"] == {"coin": 1, "provender": 2}
    assert not any(rec["lord"] == "gavrilo" for rec in result["retreats"])


@pytest.mark.parametrize(
    "box,transport,destination,kept",
    [
        (1, "boat", "uzmen", 2),
        (3, "sled", "dubrovno", 2),
        (7, "cart", "dubrovno", 0),
    ],
)
def test_shared_retreat_uses_only_transport_usable_in_the_season(box, transport, destination, kept):
    state = field(box=box)
    state.lords["domash"].assets = {transport: 2}
    stand(state, retreat_to={"gavrilo": destination, "domash": destination})
    assert state.lords["gavrilo"].assets.get("provender", 0) == kept
    assert state.lords["domash"].assets[transport] == 2
    assert state.lords["hermann"].assets.get("provender", 0) == 2 - kept


def test_lord_removed_by_losses_cannot_lend_carts_to_a_surviving_co_retreater():
    state = field()
    state.lords["hermann"].forces = {"knights": 4, "men_at_arms": 4}
    state.lords["domash"].forces = {"militia": 1}
    state.combat_pending.defender_positions = {"domash": "center", "gavrilo": "left"}
    result = stand(state, concede_round=2, retreat_to={"gavrilo": "dubrovno", "domash": "dubrovno"})
    assert state.lords["gavrilo"].state == "mustered"
    assert state.lords["domash"].state == "removed"
    assert not state.lords["gavrilo"].assets.get("provender")
    assert state.lords["hermann"].assets["provender"] == 2
    assert state.lords["hermann"].assets["cart"] == 2
    assert (
        next(rec for rec in result["spoils"] if rec["from"] == "domash")["mode"]
        == "all_except_ships"
    )


@pytest.mark.parametrize("staged", [False, True])
def test_simple_sally_winners_use_same_shared_retreat_capacity_for_losing_besiegers(staged):
    state = field()
    state.lords["gavrilo"].forces = {"knights": 8, "men_at_arms": 8}
    state.lords["gavrilo"].in_stronghold = True
    state.locales["pskov"].siege_markers = 1
    state.campaign_turn.active_card = state.campaign_turn.active_lord = "gavrilo"
    state.meta.active_player = "russian"
    state.lords["domash"].state = "removed"
    state.lords["domash"].location = None
    place(state, "yaroslav", {"men_at_arms": 3}, cart=2)
    state.lords["hermann"].assets = {"provender": 2}
    state.lords["hermann"].forces = {"knights": 3}
    state.combat_pending = None
    move = next(
        move for move in legal_moves(state, with_previews=False) if move["type"] == "cmd_sally"
    )
    assert set(move["retreat_keep_order_options"]) == {"hermann", "yaroslav"}
    retreats = {"hermann": "dubrovno", "yaroslav": "dubrovno"}
    if staged:
        state.lords["yaroslav"].assets["provender"] = 2
    result = apply_action(
        state,
        {
            "type": "cmd_sally",
            "side": "russian",
            "args": {
                "lord_id": "gavrilo",
                "concede": "defender",
                **({"choose_loser_fate": True} if staged else {"retreat_to": retreats}),
            },
        },
    )
    assert result["battle"]["loser"] == "teutonic"
    if staged:
        before_food = state.lords["gavrilo"].assets["provender"]
        result = apply_action_for_side(state, "teutonic", {
            "type": SALLY_FATE_ACTION, "args": {"retreat_to": retreats},
        })
        assert result["awaiting_aftermath_reward"] == {
            "owed_by": "teutonic", "reward": "retreat_provender",
        }
        result = apply_action_for_side(state, "teutonic", {"type": REWARD_ACTION, "args": {
            "retreat_keep": {"hermann": 1, "yaroslav": 1},
        }})
        assert state.lords["hermann"].assets["provender"] == 1
        assert state.lords["yaroslav"].assets["provender"] == 1
        assert state.lords["gavrilo"].assets["provender"] == before_food + 2
    else:
        assert state.lords["hermann"].assets["provender"] == 2
        assert all(not rec["transferred"] for rec in result["spoils"])
    assert state.lords["yaroslav"].assets["cart"] == 2
