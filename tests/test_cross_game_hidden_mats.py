"""IF-3 regressions for session, compact and notebook Hidden Mats views."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from nevsky.actions import apply_action
from nevsky.llm.briefing import briefing_for_side
from nevsky.llm.compact import detail_payload, player_view
from nevsky.llm.session import LLMSession
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
def test_real_partisans_muster_stays_private_while_public_calendar_markers_survive(advanced):
    state = load_scenario(
        "pleskau", optional_rules={"hidden_mats": True, "advanced_vassal_service": advanced}
    )
    state.meta.levy_step = "muster"
    state.calendar.boxes[1].service_markers.remove("yaroslav")
    state.calendar.boxes[3].service_markers.append("yaroslav")
    vid = "yaroslav_mstislavich_partisans"
    apply_action(
        state,
        {
            "type": "muster_vassal",
            "side": "teutonic",
            "args": {"by_lord": "yaroslav", "vassal_id": vid},
        },
    )
    owner = LLMSession(state, "teutonic", "pleskau").full_state()
    assert owner["lords"]["yaroslav"]["forces"]["militia"] == 2
    assert owner["lords"]["yaroslav"]["vassals"][vid]["mustered"]
    opponent = LLMSession(state, "russian", "pleskau").full_state()
    assert opponent["lords"]["yaroslav"]["forces"] == {"_hidden": 1}
    assert opponent["lords"]["yaroslav"]["vassals"] == {}
    assert (vid in opponent["calendar"]["boxes"][1]["vassal_service_markers"]) == advanced


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
