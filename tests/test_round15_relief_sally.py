"""Relief Sally choices belong to the Approaching player (4.4.1)."""

import pytest

from nevsky.llm.tools import apply_action_for_side, legal_actions_for_side
from nevsky.state import GameState
from tests.test_round12_lieutenant_movement import act, plan, plan_position, reject

PAIR = ["yaroslav", "knud_and_abel"]
RELIEF_MARCH = {"to": "pskov", "way_type": "trackway"}


def relief_position(*, paired: bool = True) -> GameState:
    state = plan_position()
    state.locales["pskov"].teutonic_conquered = 1
    for lid, loc in (("yaroslav", "pskov"), ("knud_and_abel", "pskov"),
                     ("hermann", "izborsk"), ("gavrilo", "ostrov")):
        state.lords[lid].location = loc
    if paired:
        act(state, "place_lieutenant", "teutonic", lieutenant=PAIR[0], lower_lord=PAIR[1])
    plan(state, teutonic=["pass", "hermann", "hermann", "hermann", "yaroslav", "yaroslav"])
    for side in ("teutonic", "russian"):
        act(state, "fpd_resolve", side, decline_pay=True)
    act(state, "command_reveal", "russian")
    act(state, "cmd_march", "russian", to="pskov", way_type="waterway", discard_to_unladen=True)
    act(state, "withdraw", "teutonic")
    assert state.locales["pskov"].siege_markers == 1
    assert all(state.lords[lid].in_stronghold for lid in PAIR)
    for _ in range(2):
        act(state, "fpd_resolve", state.meta.active_player, decline_pay=True)
    act(state, "command_reveal", "teutonic")
    return state


@pytest.mark.parametrize(("selection", "code"), [
    (PAIR[:1], "lower_lord_required"),
    (PAIR[1:], "lieutenant_required"),
    (["hermann"], "bad_sally_join"),
    ("yaroslav", "bad_sally_join"),
])
def test_march_rejects_bad_relief_sally_before_approach(selection, code):
    state = relief_position()
    reject(state, code, "cmd_march", "teutonic", **RELIEF_MARCH, sally_join=selection)
    assert state.combat_pending is None
    assert state.meta.active_player == "teutonic"


@pytest.mark.parametrize(("paired", "election", "joiners"), [
    (True, {}, PAIR),
    (True, {"sally_join": PAIR}, PAIR),
    (True, {"sally_join": []}, []),
    (False, {"sally_join": PAIR[:1]}, PAIR[:1]),
])
def test_relief_sally_choices_survive_save_and_control_feed(paired, election, joiners):
    state = relief_position(paired=paired)
    march = next(
        move for move in legal_actions_for_side(state, "teutonic")
        if move["type"] == "cmd_march"
        and all(move["args"].get(k) == v for k, v in RELIEF_MARCH.items())
        and not move["args"].get("concede")
    )
    assert march["sally_join_options"] == PAIR
    assert march["sally_join_pairs"] == ([PAIR] if paired else [])
    assert apply_action_for_side(state, "teutonic", {
        **march, "args": {**march["args"], **election},
    })["approach"]
    restored = GameState.model_validate_json(state.model_dump_json())
    battle = act(state, "stand_battle", concede="defender")["battle"]
    assert act(restored, "stand_battle", concede="defender")["battle"] == battle
    assert battle.get("relief_sally", {}).get("sallying_lords", []) == joiners
    positions = battle["attacker_positions"]
    assert len({positions[lid] for lid in joiners}) == len(joiners)

    feed = act(state, "fpd_resolve", "teutonic", decline_pay=True)["feed"]
    assert act(restored, "fpd_resolve", "teutonic", decline_pay=True)["feed"] == feed
    assert {row["lord_id"] for row in feed} == {"hermann", *joiners}
    assert all(row["consumed"]["provender"] == 1 for row in feed)
    assert state.model_dump_json() == restored.model_dump_json()
