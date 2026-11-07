"""SMOKE-071 (Round 75): Sally aftermath retreat captures way_type and
honors result['conceded'] flag for 4.4.3 Spoils accounting.

The Sally aftermath defender-loss branch (besiegers lose the Sally
Battle) previously:
  - Always used transfer_spoils mode 'all_except_ships' regardless of
    whether the besieger Conceded the Field.
  - Did not capture the retreat Way's type, so the loot_and_excess
    path would have no way to compute Unladen Transport along the
    Retreat Way.

The R75 fix mirrors SMOKE-069's pattern in the regular Battle
aftermath: capture retreat_way_type_actual from the for-loop, and
check result['conceded']. If conceded_side == 'defender' (besieger
loser), use loot_and_excess + retreat_way_type. Otherwise keep
all_except_ships.

The first two checks retain the original source assertions. The Spoils and
Way-type cases execute real seeded Sally actions.
"""

import inspect

import nevsky.actions  # noqa: F401 — register handlers
from nevsky.campaign import _finish_successful_sally, _h_cmd_sally
from tests.test_cross_game_sally import sally, sally_state


def test_sally_aftermath_captures_retreat_way_type() -> None:
    src = inspect.getsource(_finish_successful_sally)
    # The fix introduces retreat_way_type_actual.
    assert "retreat_way_type_actual" in src, (
        "Sally aftermath should capture retreat_way_type_actual from the "
        "for-w-in-load_ways loop so loot_and_excess can compute Unladen Transport"
    )


def test_sally_aftermath_checks_conceded_flag() -> None:
    src = inspect.getsource(_h_cmd_sally)
    # The fix consults result["conceded"] to decide between
    # loot_and_excess and all_except_ships.
    assert 'result.get("conceded")' in src or "result['conceded']" in src, (
        "Sally aftermath should consult result['conceded'] to decide spoils mode"
    )


def test_sally_aftermath_uses_loot_and_excess_for_conceded() -> None:
    state = sally_state(seed=8)
    lord = state.lords["hermann"]
    lord.forces = {"knights": 1, "militia": 1}
    lord.assets = {"coin": 1, "cart": 1, "ship": 1, "provender": 2, "loot": 1}
    result = sally(state, concede="defender", concede_round=2,
                   retreat_to={"hermann": "dubrovno"})
    assert result["spoils"][0]["mode"] == "loot_and_excess"
    assert result["spoils"][0]["transferred"] == {"loot": 1, "provender": 1}
    assert lord.state == "mustered" and lord.location == "dubrovno"
    assert lord.assets == {"coin": 1, "cart": 1, "ship": 1, "provender": 1}


def test_sally_aftermath_passes_retreat_way_type_to_transfer_spoils() -> None:
    state = sally_state(seed=8)
    lord = state.lords["hermann"]
    lord.forces = {"knights": 1, "militia": 1}
    lord.assets = {"coin": 1, "cart": 4, "boat": 1, "ship": 1, "provender": 2, "loot": 1}
    result = sally(state, concede="defender", concede_round=2,
                   retreat_to={"hermann": "uzmen"})
    spoil = result["spoils"][0]
    assert spoil["retreat_way_type"] == "waterway"
    assert spoil["transferred"] == {"loot": 1, "provender": 1}
    assert lord.state == "mustered" and lord.location == "uzmen"
    assert lord.assets == {"coin": 1, "cart": 4, "boat": 1, "ship": 1, "provender": 1}
