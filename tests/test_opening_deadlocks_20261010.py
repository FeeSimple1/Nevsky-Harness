"""Actual duplicate-capability opening deadlocks, not edited draw orders."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from nevsky.actions import IllegalAction, apply_action
from nevsky.legal_moves import legal_moves
from nevsky.state import GameState

DATA = Path(__file__).parent / "data" / "convergence_20261010"
CASES = [
    ("crusade_on_novgorod_32_priority", "russian", "R6", "gavrilo", "R5"),
    ("watland_48_priority", "teutonic", "T15", "andreas", "T7"),
]


def position(name):
    return GameState.model_validate_json((DATA / (name + ".json")).read_text())


def implement(side, card, **args):
    return {"type": "aow_implement_card", "side": side, "args": {"card_id": card, **args}}


@pytest.mark.parametrize("name,side,card,lord,existing", CASES)
def test_unassignable_duplicate_discards_and_preserves_the_existing_capability(
    name, side, card, lord, existing
):
    state = position(name)
    menu = legal_moves(state, with_previews=False)
    assert len(menu) == 1
    assert menu[0]["args"] == {"card_id": card}
    before = state.model_dump_json()
    reloaded = GameState.model_validate_json(before)
    result = apply_action(reloaded, implement(side, card))
    assert result["outcome"] == "discarded_no_assignable_lord"
    deck = getattr(reloaded.decks, side)
    assert card not in deck.pending_draw and deck.discard.count(card) == 1
    assert card not in deck.removed
    assert reloaded.lords[lord].this_lord_capabilities == [existing]
    assert reloaded.meta.rng_state == state.meta.rng_state
    assert any(m["type"] == "advance_step" for m in legal_moves(reloaded, with_previews=False))


@pytest.mark.parametrize("name,side,card,lord,existing", CASES)
def test_an_explicit_duplicate_target_is_still_rejected_atomically(
    name, side, card, lord, existing
):
    state = position(name)
    before = state.model_dump_json()
    with pytest.raises(IllegalAction, match="duplicate_capability"):
        apply_action(state, implement(side, card, lord_id=lord))
    assert state.model_dump_json() == before


@pytest.mark.parametrize("name,side,card,lord,existing", CASES)
def test_a_valid_alternative_target_prevents_discard(name, side, card, lord, existing):
    state = position(name)
    target = "andrey" if side == "russian" else "rudolf"
    state.lords[target].state = "mustered"
    state.lords[target].location = "novgorod" if side == "russian" else "wenden"
    menu = legal_moves(state, with_previews=False)
    assert any(m.get("args", {}).get("lord_id") == target for m in menu)
    before = state.model_dump_json()
    with pytest.raises(IllegalAction, match="missing_arg"):
        apply_action(state, implement(side, card))
    assert before == state.model_dump_json()
    assert (
        apply_action(state, implement(side, card, lord_id=target))["outcome"] == "tucked_under_lord"
    )


def test_full_mats_without_duplicate_names_are_also_unassignable():
    state = position("crusade_on_novgorod_32_priority")
    state.lords["gavrilo"].this_lord_capabilities = ["R1", "R3"]
    result = apply_action(state, implement("russian", "R6"))
    assert result["outcome"] == "discarded_no_assignable_lord"
    assert state.lords["gavrilo"].this_lord_capabilities == ["R1", "R3"]


@pytest.mark.parametrize("scenario,seed", [("crusade_on_novgorod", 32), ("watland", 48)])
@pytest.mark.parametrize("policy", ["priority", "random"])
def test_original_fuzzer_stalls_now_reach_actual_game_end(scenario, seed, policy):
    spec = importlib.util.spec_from_file_location(
        "opening_fuzzer", Path(__file__).resolve().parents[1] / "scripts" / "fuzz_invariants.py"
    )
    fuzz = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fuzz)
    detail = {}
    assert fuzz.run_game(scenario, seed, policy, details=detail) is None
    assert detail["completed"], detail
    assert detail["stop_reason"] == "completed"
