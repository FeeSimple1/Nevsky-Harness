"""IF-3 regressions for session, compact and notebook Hidden Mats views."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from nevsky.llm.briefing import briefing_for_side
from nevsky.llm.compact import detail_payload, player_view
from nevsky.llm.session import LLMSession
from nevsky.llm.tools import apply_action_for_side, legal_actions_for_side
from nevsky.llm.view import view_for_side
from nevsky.render import state_view_for_side
from nevsky.scenarios import load_scenario


@pytest.mark.parametrize("side", ["teutonic", "russian"])
@pytest.mark.parametrize("hidden", [False, True])
@pytest.mark.parametrize("advanced", [False, True])
def test_session_and_compact_views_apply_the_same_mat_rule_without_mutation(side, hidden, advanced):
    state = load_scenario(
        "pleskau", optional_rules={"hidden_mats": hidden, "advanced_vassal_service": advanced}
    )
    enemy_id = "yaroslav" if side == "russian" else "gavrilo"
    own_id = "gavrilo" if side == "russian" else "hermann"
    enemy = state.lords[enemy_id]
    enemy.this_lord_capabilities = ["T6" if side == "russian" else "R6"]
    enemy.assets = {"provender": 3, "cart": 2}
    vid, vassal = next(iter(enemy.vassals.items()))
    vassal.mustered = True
    vassal.ready = False
    vassal.on_calendar = advanced
    vassal.calendar_box = 7 if advanced else None
    if advanced:
        state.calendar.boxes[6].vassal_service_markers.append(vid)
    before = state.model_dump_json()
    session = LLMSession(state, side, "pleskau")
    views = [
        session.full_state(),
        view_for_side(state, side),
        player_view(state, side),
        detail_payload(state, side, "state"),
    ]
    expected = enemy.model_dump()
    if hidden:
        expected.update(
            forces={"_hidden": 1}, assets={}, routed_units={}, this_lord_capabilities=[], vassals={}
        )
    for view in views:
        assert view["lords"][enemy_id] == expected
        assert view["lords"][own_id] == state.lords[own_id].model_dump()
        assert view["calendar"] == state.calendar.model_dump()
        assert "seed" not in view["meta"] and "rng_state" not in view["meta"]
    assert detail_payload(state, side, "lord", lord=enemy_id)["state"] == expected
    assert session.briefing() == briefing_for_side(state, side)
    opponent = session.briefing().split("## Opponent Lords", 1)[1].split("## Your AoW deck", 1)[0]
    if hidden:
        assert "mat contents hidden" in opponent
        assert "forces:" not in opponent and enemy.this_lord_capabilities[0] not in opponent
    else:
        assert enemy.this_lord_capabilities[0] in opponent and "forces:" in opponent
    assert state.model_dump_json() == before


@pytest.mark.parametrize("advanced", [False, True])
@pytest.mark.parametrize("hidden", [False, True])
def test_vassal_and_transport_history_respects_mat_screening(advanced, hidden, tmp_path):
    state = load_scenario(
        "pleskau", optional_rules={"hidden_mats": hidden, "advanced_vassal_service": advanced}
    )
    for side in ("teutonic", "russian"):
        apply_action_for_side(state, side, {"type": "confirm_all_setup_transports"})
    state.meta.levy_step = "muster"
    state.calendar.boxes[1].service_markers.remove("yaroslav")
    state.calendar.boxes[3].service_markers.append("yaroslav")
    vid = "yaroslav_mstislavich_partisans"
    for kind, args in (
        ("muster_vassal", {"by_lord": "yaroslav", "vassal_id": vid}),
        ("levy_transport", {"by_lord": "hermann", "transport_type": "boat"}),
    ):
        move = next(m for m in legal_actions_for_side(state, "teutonic")
                    if m["type"] == kind and m["args"] == args)
        apply_action_for_side(state, "teutonic", move)

    before = state.model_dump_json()
    original = [entry.model_dump() for entry in state.history[-2:]]
    owner = LLMSession(state, "teutonic", "pleskau").full_state()
    assert owner["lords"]["yaroslav"]["forces"]["militia"] == 2
    assert owner["lords"]["yaroslav"]["vassals"][vid]["mustered"]
    assert owner["history"][-2:] == original
    assert original[0]["result"]["added_forces"] == {"militia": 2}
    assert original[1]["result"]["new_count"] == owner["lords"]["hermann"]["assets"]["boat"]

    opponent = LLMSession(state, "russian", "pleskau")
    view = opponent.full_state()
    vassal, transport = view["history"][-2:]
    if hidden:
        assert view["lords"]["yaroslav"]["forces"] == {"_hidden": 1}
        assert view["lords"]["yaroslav"]["vassals"] == {}
        assert view["lords"]["hermann"]["assets"] == {}
        assert vassal["action"]["type"] == "muster_vassal"
        assert vassal["action"]["args"] == vassal["result"] == {
            "by_lord": "yaroslav", "vassal_id": "<hidden>",
        }
        assert transport["action"]["type"] == "levy_transport"
        assert transport["action"]["args"] == transport["result"] == {
            "by_lord": "hermann", "transport_type": "<hidden>",
        }
    else:
        assert view["history"][-2:] == original
    assert (vid in view["calendar"]["boxes"][1]["vassal_service_markers"]) == advanced
    assert detail_payload(state, "russian", "history")[-2:] == [vassal, transport]

    path = tmp_path / "levy-session.json"
    opponent.save(path)
    restored = LLMSession.load(path)
    assert restored.full_state() == view
    assert restored.state.model_dump_json() == state.model_dump_json() == before


@pytest.mark.parametrize("side", ["teutonic", "russian"])
def test_session_save_load_preserves_authoritative_mats_and_applies_visibility_after_load(
    side, tmp_path
):
    state = load_scenario("pleskau", optional_rules={"hidden_mats": True})
    session = LLMSession(state, side, "pleskau")
    path = tmp_path / "session.json"
    session.save(path)
    loaded = LLMSession.load(path)
    assert loaded.state.model_dump_json() == state.model_dump_json()
    assert loaded.full_state() == session.full_state()
    assert loaded.briefing() == session.briefing()
    enemy = "yaroslav" if side == "russian" else "gavrilo"
    assert loaded.full_state()["lords"][enemy]["vassals"] == {}


@pytest.mark.parametrize("step, action_type, result_key", [
    ("muster", "levy_capability", "card_id"),
    ("arts_of_war", "aow_implement_card", "card"),
])
@pytest.mark.parametrize("card, hidden", [("T14", True), ("T14", False), ("T12", True)])
def test_capability_history_respects_mat_screening(step, action_type, result_key, card, hidden,
                                                  tmp_path):
    state = load_scenario("pleskau", optional_rules={"hidden_mats": hidden})
    state.meta.levy_step = step
    if step == "arts_of_war":
        state.decks.teutonic.deck.remove(card)
        state.decks.teutonic.pending_draw = [card]
    move = next(m for m in legal_actions_for_side(state, "teutonic")
                if m["type"] == action_type and m["args"].get("card_id") == card
                and m["args"].get("by_lord", m["args"].get("lord_id", "hermann")) == "hermann")
    apply_action_for_side(state, "teutonic", move)
    before = state.model_dump_json()
    original = state.history[-1].model_dump()

    owner = LLMSession(state, "teutonic", "pleskau").full_state()
    assert owner["history"][-1] == original
    opponent = LLMSession(state, "russian", "pleskau")
    public = opponent.full_state()
    entry = public["history"][-1]
    if hidden and card == "T14":
        assert public["lords"]["hermann"]["this_lord_capabilities"] == []
        assert entry["action"]["args"]["card_id"] == "<hidden>"
        assert entry["result"][result_key] == "<hidden>"
        assert card not in json.dumps(entry)
    else:
        assert entry == original
        if card == "T14":
            assert card in public["lords"]["hermann"]["this_lord_capabilities"]
        else:
            assert card in public["decks"]["teutonic"]["capabilities_in_play"]
    assert detail_payload(state, "russian", "history")[-1] == entry

    path = tmp_path / "capability-session.json"
    opponent.save(path)
    restored = LLMSession.load(path)
    assert restored.full_state()["history"][-1] == entry
    assert restored.state.model_dump_json() == state.model_dump_json() == before


def test_mask_is_stable_for_different_hidden_armies_and_repeated_filtering():
    state = load_scenario("pleskau", optional_rules={"hidden_mats": True})
    first = state_view_for_side(state, "russian")
    other = state.model_copy(deep=True)
    lord = other.lords["yaroslav"]
    lord.forces = {}
    lord.routed_units = {"militia": 3}
    lord.assets = {"coin": 7}
    for vassal in lord.vassals.values():
        vassal.ready = not vassal.ready
        vassal.mustered = not vassal.mustered
    second = state_view_for_side(other, "russian")
    assert first.lords["yaroslav"].model_dump() == second.lords["yaroslav"].model_dump()
    assert state_view_for_side(first, "russian").model_dump() == first.model_dump()


@pytest.mark.parametrize("side", ["teutonic", "russian"])
@pytest.mark.parametrize("topic", ["state", "lord"])
def test_notebook_focused_details_use_the_shared_filter(side, topic, capsys):
    path = Path(__file__).resolve().parents[1] / "scripts/chatgpt_play_helper.py"
    spec = importlib.util.spec_from_file_location("hidden_mats_helper", path)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    state = load_scenario("pleskau", optional_rules={"hidden_mats": True})
    helper._S["state"] = state
    enemy = "yaroslav" if side == "russian" else "gavrilo"
    result = helper.details(topic, side=side, lord=enemy)
    mat = result["data"]["lords"][enemy] if topic == "state" else result["data"]["state"]
    assert mat["forces"] == {"_hidden": 1} and mat["vassals"] == {}
    assert helper.full_state(side)["lords"][enemy] == mat
    capsys.readouterr()


@pytest.mark.parametrize("mode", ["battle", "sally", "storm"])
@pytest.mark.parametrize("interrupt", [False, True])
def test_live_combat_reveals_participating_mats_and_rehides_them_on_return_or_error(
    mode, interrupt, monkeypatch
):
    from nevsky import battle

    state = load_scenario("pleskau", optional_rules={"hidden_mats": True})
    for lid in ["hermann", "yaroslav", "gavrilo"]:
        lord = state.lords[lid]
        lord.state = "mustered"
        lord.location = "pskov"
        lord.forces = {"infantry": 1 if lid == "gavrilo" else 4}
    spectator = state.lords["domash"]
    spectator.state = "mustered"
    spectator.location = "novgorod"
    spectator.forces = {"militia": 2}
    session = LLMSession(state, "teutonic", "pleskau")
    assert session.full_state()["lords"]["gavrilo"]["forces"] == {"_hidden": 1}
    seen = []

    def inspect_and_choose(payload):
        views = [
            session.full_state(),
            player_view(state, "teutonic"),
            detail_payload(state, "teutonic", "state"),
        ]
        for view in views:
            assert view["lords"]["gavrilo"] == state.lords["gavrilo"].model_dump()
            assert view["lords"]["domash"]["forces"] == {"_hidden": 1}
            assert view["lords"]["domash"]["vassals"] == {}
        assert "infantry×1" in session.briefing()
        seen.append(payload["type"])
        if interrupt:
            raise RuntimeError("stop after inspection")
        return payload["options"][0]

    context = battle.BattleDecisionContext(callback=inspect_and_choose)
    # Walls 6 retain the single defender until Storm Reposition's live choice.
    monkeypatch.setattr(battle, "roll_d6", lambda *args, **kwargs: 6)

    def resolve():
        if mode == "storm":
            return battle.resolve_storm(
                state,
                "teutonic",
                ["hermann", "yaroslav"],
                ["gavrilo"],
                "pskov",
                6,
                4,
                {},
                decision_ctx=context,
            )
        return battle.resolve_battle(
            state,
            "teutonic",
            ["hermann", "yaroslav"],
            ["gavrilo"],
            max_rounds=1,
            decision_ctx=context,
            simple_sally=mode == "sally",
        )

    if interrupt:
        with pytest.raises(RuntimeError, match="stop after inspection"):
            resolve()
    else:
        resolve()
    assert seen
    assert session.full_state()["lords"]["gavrilo"]["forces"] == {"_hidden": 1}
    assert session.full_state()["lords"]["gavrilo"]["vassals"] == {}
