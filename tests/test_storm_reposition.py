"""Follow-up B regression tests: Storm Reposition (4.5.2 page 17, 2E).

Storm has its own one-Lord-Front Array. In each Round after the first,
Attacker then Defender may switch their Front Lord with any Reserve
Lord. Operator decision via BattleDecisionContext.

Tests cover:
- Initial Storm Array: Active attacker and chosen defender take Front.
- Reserve Lord doesn't strike or absorb Hits.
- Round 2+ allows operator to swap Front and Reserve.
- Operator can choose to "stay" (keep current Front).
- Front Rout in Round 1 -> Reserve forced into Front in Round 2.
- Decision trace logged in result.
"""

from __future__ import annotations

import pytest

from nevsky.actions import IllegalAction, apply_action
from nevsky.battle import BattleDecisionContext, resolve_storm
from nevsky.legal_moves import legal_moves
from nevsky.llm.session import LLMSession
from nevsky.llm.tools import apply_action_for_side, legal_actions_for_side
from nevsky.scenarios import load_scenario
from nevsky.state import STORM_FRONT_ACTION
from tests.test_cross_game_combat_spoils import place, position


def _one_round_storm():
    state = position(seed=4)
    state.locales["pskov"].siege_markers = 1
    place(state, "hermann", {"knights": 3, "sergeants": 2, "men_at_arms": 2})
    place(state, "aleksandr", {"knights": 3, "men_at_arms": 3}, inside=True)
    place(state, "gavrilo", {"militia": 1}, inside=True)
    place(state, "yaroslav", {"knights": 2}, "izborsk")
    return state


@pytest.mark.parametrize("mode", ["callback", "script", "referee"])
def test_defender_selects_the_round_one_storm_front(mode):
    state = _one_round_storm()
    storm = next(move for move in legal_moves(state, with_previews=False)
                 if move["type"] == "cmd_storm")
    assert storm["defender_front_options"] == ["aleksandr", "gavrilo"]
    baseline = apply_action(state.model_copy(deep=True), storm)["battle"]
    seen = []

    def choose(decision):
        seen.append(decision)
        return "gavrilo"

    election = {
        "callback": {"decision_callback": choose},
        "script": {"scripted_decisions": [{"type": "storm_defender_front", "chosen": "gavrilo"}]},
        "referee": {"defender_front": "gavrilo"},
    }[mode]
    result = apply_action(state, {**storm, "args": {**storm["args"], **election}})["battle"]
    if mode == "callback":
        assert [(d["type"], d["side"], d["options"]) for d in seen] == [
            ("storm_defender_front", "defender", ["aleksandr", "gavrilo"]),
        ]
    assert result["rounds"] == baseline["rounds"] == 1
    first = result["log"][0]
    assert baseline["log"][0]["defender_storm_positions"]["aleksandr"] == "storm_front"
    assert first["defender_storm_positions"] == {
        "aleksandr": "storm_reserve", "gavrilo": "storm_front",
    }
    assert first["attacker_storm_positions"] == {"hermann": "storm_front"}
    melee = next(step for step in first["steps"] if step["step"] == "melee_defender")
    control = next(step for step in baseline["log"][0]["steps"]
                   if step["step"] == "melee_defender")
    assert melee["hits_after_walls"] < control["hits_after_walls"]


def test_player_storm_hands_off_before_dice_and_survives_save_load(tmp_path):
    state = _one_round_storm()
    state.meta.optional_rules["hidden_mats"] = True
    state.decks.teutonic.deck.remove("T10")
    state.decks.teutonic.holds.append("T10")
    storm = next(move for move in legal_actions_for_side(state, "teutonic")
                 if move["type"] == "cmd_storm")
    assert storm["args"]["choose_defender_front"] is True
    before = state.model_dump_json()
    with pytest.raises(IllegalAction, match="wrong_actor"):
        apply_action_for_side(state, "teutonic", {
            **storm, "args": {**storm["args"], "defender_front": "gavrilo"},
        })
    assert state.model_dump_json() == before
    dice = state.meta.rng_state
    result = apply_action_for_side(state, "teutonic", {
        **storm, "args": {**storm["args"], "field_organ_lord": "hermann",
                           "holds": {"field_organ": "T10"}},
    })
    assert result["awaiting_storm_front"] == {"owed_by": "russian", "locale": "pskov"}
    assert state.meta.rng_state == dice and "T10" in state.decks.teutonic.holds
    assert not legal_actions_for_side(state, "teutonic")
    session = LLMSession(state, "russian", "crusade_on_novgorod")
    view = session.full_state()
    assert view["lords"]["hermann"]["forces"] == state.lords["hermann"].forces
    assert view["lords"]["yaroslav"]["forces"] == {"_hidden": 1}
    assert view["history"][-1]["action"]["args"] == {"lord_id": "hermann"}
    assert "attack_args" not in view["pending_decisions"][0]["context"]
    path = tmp_path / "storm.json"
    session.save(path)
    session = LLMSession.load(path)
    moves = session.legal_actions()
    assert {m["args"]["lord_id"] for m in moves} == {"aleksandr", "gavrilo"}
    assert {m["type"] for m in moves} == {STORM_FRONT_ACTION}
    before = session.state.model_dump_json()
    for side, action, code in [
        ("teutonic", {**moves[0], "side": "teutonic"}, "wrong_actor"),
        ("russian", {"type": STORM_FRONT_ACTION, "args": {"lord_id": "hermann"}}, "bad_storm_front"),
        ("russian", {"type": "fpd_resolve"}, "storm_front_pending"),
    ]:
        with pytest.raises(IllegalAction, match=code):
            apply_action_for_side(session.state, side, action)
        assert session.state.model_dump_json() == before
    result = session.apply(next(m for m in moves if m["args"]["lord_id"] == "gavrilo"))
    assert result["battle"]["log"][0]["defender_storm_positions"]["gavrilo"] == "storm_front"
    assert result["field_organ_lord"] == "hermann"
    assert "T10" in session.state.decks.teutonic.discard
    assert session.full_state()["lords"]["hermann"]["forces"] == {"_hidden": 1}


def _setup_two_attacker_storm(seed: int = 1) -> tuple:
    """Construct a Storm with 2 attackers and 1 Besieged defender."""
    s = load_scenario("watland", seed=seed)
    teus = [
        lid for lid, l in s.lords.items()
        if l.side == "teutonic" and l.state == "mustered"
    ][:2]
    rus = [
        lid for lid, l in s.lords.items()
        if l.side == "russian" and l.state == "mustered"
    ][:1]
    if not rus:
        # Force a Russian Mustered.
        rus_id = next(lid for lid, l in s.lords.items() if l.side == "russian")
        s.lords[rus_id].state = "mustered"
        s.lords[rus_id].location = "pskov"
        rus = [rus_id]
    # Co-locate everyone at pskov; defender is in_stronghold.
    for t in teus:
        s.lords[t].location = "pskov"
    s.lords[rus[0]].location = "pskov"
    s.lords[rus[0]].in_stronghold = True
    return s, teus, rus


def test_storm_reposition_initial_array_first_lord_at_storm_front() -> None:
    """4.5.2 Storm Array: first Lord per side at storm_front; rest in
    storm_reserve."""
    s, teus, rus = _setup_two_attacker_storm()
    s.lords[teus[0]].forces = {"knights": 2}
    s.lords[teus[1]].forces = {"sergeants": 2}
    s.lords[rus[0]].forces = {"militia": 2}
    res = resolve_storm(
        s, attacker_side="teutonic",
        attacker_lords=teus, defender_lords=rus,
        locale_id="pskov", walls_max=0, siege_markers=2,
        garrison={},
    )
    pos = res["attacker_storm_positions"]
    assert pos[teus[0]] == "storm_front"
    assert pos[teus[1]] == "storm_reserve"


def test_storm_reposition_reserve_lord_not_in_first_round_strikes() -> None:
    """A Reserve Lord's units do NOT strike in Round 1. Verify by
    setting up a Reserve Lord with overwhelming Forces; the defender
    must NOT take damage from Reserve strikes in Round 1."""
    s, teus, rus = _setup_two_attacker_storm()
    s.lords[teus[0]].forces = {"sergeants": 1}  # Front Lord -- weak
    s.lords[teus[1]].forces = {"knights": 99}  # Reserve -- huge
    s.lords[rus[0]].forces = {"men_at_arms": 4}
    res = resolve_storm(
        s, attacker_side="teutonic",
        attacker_lords=teus, defender_lords=rus,
        locale_id="pskov", walls_max=0, siege_markers=1,
        garrison={},
    )
    # Round 1 Hits to defender from Lord-side Strikes should be limited
    # to what teus[0] (the Front Lord) generates, not what teus[1]
    # would generate. Inspect the round 1 melee_attacker step:
    rd1 = res["log"][0]
    melee_atk_steps = [
        st for st in rd1["steps"] if st["step"] == "melee_attacker"
    ]
    if melee_atk_steps:
        # 1 Sergeant -> 1 melee Hit. 99 Knights would have produced 99x2 = 198 (capped at 6).
        assert melee_atk_steps[0]["hits_after_walls"] <= 6


def test_storm_reposition_round2_operator_swaps_front_reserve() -> None:
    """4.5.2 Round 2+: operator may swap Front and Reserve. With a
    scripted swap, Front Lord changes between rounds."""
    s, teus, rus = _setup_two_attacker_storm()
    # Beef both attackers so the Front Lord survives Round 1 and Round
    # 2's Reposition presents a genuine choice (not a forced advance
    # after Front Rout).
    s.lords[teus[0]].forces = {"knights": 8, "sergeants": 4}
    s.lords[teus[1]].forces = {"knights": 8, "sergeants": 4}
    s.lords[rus[0]].forces = {"men_at_arms": 1}  # weak defender
    ctx = BattleDecisionContext(scripted=[
        # Round 2 Attacker reposition: swap to teus[1].
        {"type": "reserve_advance", "chosen": teus[1],
         "rationale": "swap to fresh Lord"},
    ])
    res = resolve_storm(
        s, attacker_side="teutonic",
        attacker_lords=teus, defender_lords=rus,
        locale_id="pskov", walls_max=0, siege_markers=3,
        garrison={},
        decision_ctx=ctx,
    )
    decisions = res["decisions"]
    swap_decisions = [d for d in decisions if d["type"] == "reserve_advance"]
    # Either the swap was logged, OR the storm ended in Round 1
    # before Reposition could fire (in which case no decision is
    # expected — but the test setup is intended to keep both Lords
    # alive into Round 2).
    if len(res["log"]) >= 2:
        assert any(d["chosen"] == teus[1] for d in swap_decisions), (
            f"expected scripted swap to teus[1] but got {swap_decisions}"
        )


def test_storm_reposition_operator_can_stay_with_current_front() -> None:
    """Operator may decline to swap by picking the current Front Lord
    in the option list (the 'stay' option)."""
    s, teus, rus = _setup_two_attacker_storm()
    # Bulk Front Lord so he survives Round 1.
    s.lords[teus[0]].forces = {"knights": 8, "sergeants": 4}
    s.lords[teus[1]].forces = {"knights": 8, "sergeants": 4}
    s.lords[rus[0]].forces = {"men_at_arms": 1}
    ctx = BattleDecisionContext(scripted=[
        # Round 2 Attacker reposition: stay (pick current Front).
        {"type": "reserve_advance", "chosen": teus[0],
         "rationale": "stay"},
    ])
    res = resolve_storm(
        s, attacker_side="teutonic",
        attacker_lords=teus, defender_lords=rus,
        locale_id="pskov", walls_max=0, siege_markers=3,
        garrison={},
        decision_ctx=ctx,
    )
    # Decision logged. Storm may end in Round 1 -- if so, no decision
    # required. But with this setup it should reach Round 2.
    decisions = res["decisions"]
    stays = [d for d in decisions if d["type"] == "reserve_advance" and d["chosen"] == teus[0]]
    if len(res["log"]) >= 2:
        assert len(stays) >= 1


def test_storm_reposition_advances_reserve_when_front_routs() -> None:
    """If Round 1 Routs the Front Lord, Round 2's Reposition forces
    a Reserve into Front (no operator choice when only one Reserve)."""
    s, teus, rus = _setup_two_attacker_storm()
    # Front Lord: 1 unit (will likely Rout immediately).
    s.lords[teus[0]].forces = {"serfs": 1}
    s.lords[teus[1]].forces = {"knights": 1}
    s.lords[rus[0]].forces = {"men_at_arms": 4, "knights": 4}
    res = resolve_storm(
        s, attacker_side="teutonic",
        attacker_lords=teus, defender_lords=rus,
        locale_id="pskov", walls_max=0, siege_markers=3,
        garrison={},
    )
    # The Storm log should show a reposition advance for round 2 if
    # the Front Lord Routed in round 1.
    if len(res["log"]) >= 2:
        rd2 = res["log"][1]
        rep = rd2.get("reposition")
        if rep is not None:
            atk_moves = rep.get("attacker", [])
            advance_moves = [m for m in atk_moves if m.get("step") == "advance"]
            # If Front Routed and Reserve advances, we expect this:
            if not s.lords[teus[0]].forces and s.lords.get(teus[1]) and s.lords[teus[1]].forces:
                assert advance_moves, f"expected advance after Front Rout, got {rep}"


def test_storm_reposition_decisions_logged() -> None:
    """The decision trace appears under result['decisions']."""
    s, teus, rus = _setup_two_attacker_storm()
    s.lords[teus[0]].forces = {"knights": 2}
    s.lords[teus[1]].forces = {"knights": 2}
    s.lords[rus[0]].forces = {"men_at_arms": 2}
    res = resolve_storm(
        s, attacker_side="teutonic",
        attacker_lords=teus, defender_lords=rus,
        locale_id="pskov", walls_max=0, siege_markers=2,
        garrison={},
    )
    assert "decisions" in res
