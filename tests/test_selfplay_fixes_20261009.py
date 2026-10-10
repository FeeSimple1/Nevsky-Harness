"""Regressions from the completed Pleskau self-play, not just crash checks."""
from __future__ import annotations

import importlib.util
import json
from collections import Counter
from pathlib import Path

import pytest

from nevsky.actions import (
    IllegalAction,
    _disband_at_limit,
    _remove_lord_permanently,
    apply_action,
)
from nevsky.legal_moves import legal_moves
from nevsky.scenarios import determine_scenario_winner, load_scenario
from nevsky.state import GameState
from nevsky.static_data import load_lords

ROOT = Path(__file__).resolve().parents[1]


def new_game(scenario="pleskau", seed=20261009):
    state = load_scenario(scenario, seed=seed)
    for side in ("teutonic", "russian"):
        apply_action(state, {"type": "confirm_all_setup_transports", "side": side, "args": {}})
    return state


def menu_has(state, action):
    return any({k: a[k] for k in ("type", "side", "args") if k in a} == action
               for a in legal_moves(state, with_previews=False))


def vp(state, side):
    return getattr(state.calendar, f"{side}_vp")


def removal_count(state, side):
    return getattr(state.calendar, f"pleskau_lords_removed_{side}")


@pytest.mark.parametrize("side,lid", [("teutonic", "hermann"), ("russian", "gavrilo")])
@pytest.mark.parametrize("box,size", [(1, 6), (3, 4), (7, 5)])
def test_plan_menu_offers_second_and_third_but_not_fourth(side, lid, box, size):
    state = new_game()
    state.meta.phase = "campaign"
    state.meta.campaign_step = "plan"
    state.meta.active_player = side
    state.meta.box = box
    deck = getattr(state.decks, side)
    action = {"type": "plan_add_card", "side": side, "args": {"card": lid}}
    for copy_number in (1, 2, 3):
        assert menu_has(state, action), f"Menu hid legal copy {copy_number} for {lid}"
        apply_action(state, action)
        assert deck.plan.count(lid) == copy_number
    assert not menu_has(state, action)
    before = state.model_dump_json()
    with pytest.raises(IllegalAction) as exc:
        apply_action(state, action)
    assert exc.value.code == "card_limit"
    assert state.model_dump_json() == before
    second = "knud_and_abel" if side == "teutonic" else "vladislav"
    for _ in range(size - 3):
        other = {"type": "plan_add_card", "side": side, "args": {"card": second}}
        assert menu_has(state, other)
        apply_action(state, other)
    assert len(deck.plan) == size and "pass" not in deck.plan
    assert not any(a["type"] == "plan_add_card" for a in legal_moves(state, with_previews=False))
    assert menu_has(state, {"type": "finalize_plan", "side": side, "args": {}})


@pytest.mark.parametrize("side,lid", [("teutonic", "hermann"), ("russian", "gavrilo")])
@pytest.mark.parametrize("phase", ["levy", "campaign"])
@pytest.mark.parametrize("permanent", [False, True])
def test_each_disband_entry_point_awards_opposing_vp(side, lid, phase, permanent):
    state = new_game()
    state.meta.active_player = side
    state.meta.phase = phase
    state.meta.levy_step = "disband"
    state.meta.campaign_step = "command"
    state.campaign_turn.in_feed_pay_disband = True
    state.campaign_turn.fpd_pay_window_side = None
    for lord in state.lords.values():
        if lord.side == side:
            lord.assets = {}
            lord.moved_fought = False
    for cb in state.calendar.boxes:
        if lid in cb.service_markers:
            cb.service_markers.remove(lid)
    if permanent:
        state.calendar.off_left_service.append(lid)
    else:
        state.calendar.boxes[0].service_markers.append(lid)
    beneficiary = "russian" if side == "teutonic" else "teutonic"
    before = vp(state, beneficiary)
    own_before = vp(state, side)
    action = {"type": "disband_resolve" if phase == "levy" else "fpd_resolve",
              "side": side, "args": {}}
    apply_action(state, action)
    assert state.lords[lid].state == ("removed" if permanent else "disbanded")
    assert state.lords[lid].location is None
    assert vp(state, beneficiary) == before + 1
    assert vp(state, side) == own_before
    assert removal_count(state, side) == 1
    marked = [cb.box for cb in state.calendar.boxes
              if getattr(cb, f"{beneficiary}_victory_marker")]
    assert marked == [int(before + 1)]
    restored = GameState.model_validate_json(state.model_dump_json())
    assert vp(restored, beneficiary) == before + 1
    assert removal_count(restored, side) == 1


@pytest.mark.parametrize("lid", ["hermann", "gavrilo"])
def test_duplicate_cleanup_cannot_award_again(lid):
    state = new_game()
    side = state.lords[lid].side
    beneficiary = "russian" if side == "teutonic" else "teutonic"
    before = vp(state, beneficiary)
    _disband_at_limit(state, lid, 9)
    _disband_at_limit(state, lid, 9)
    _remove_lord_permanently(state, lid, load_lords()[lid])
    _remove_lord_permanently(state, lid, load_lords()[lid])
    assert vp(state, beneficiary) == before + 1
    assert removal_count(state, side) == 1


@pytest.mark.parametrize("lid", ["rudolf", "domash", "andreas", "aleksandr"])
def test_off_map_or_scenario_excluded_lord_is_not_a_scoring_departure(lid):
    state = new_game()
    assert state.lords[lid].location is None
    before = (state.calendar.teutonic_vp, state.calendar.russian_vp)
    _remove_lord_permanently(state, lid, load_lords()[lid])
    assert (state.calendar.teutonic_vp, state.calendar.russian_vp) == before
    assert removal_count(state, "teutonic") == removal_count(state, "russian") == 0


@pytest.mark.parametrize("lid", ["hermann", "gavrilo"])
def test_distinct_departure_after_remustering_is_counted_again(lid):
    state = new_game()
    original_lord = state.lords[lid].model_copy(deep=True)
    side = original_lord.side
    beneficiary = "russian" if side == "teutonic" else "teutonic"
    before = vp(state, beneficiary)
    _disband_at_limit(state, lid, 9)
    # Lifecycle fixture: restore a Mustered on-map Lord, as a new Muster does.
    state.lords[lid] = original_lord
    _disband_at_limit(state, lid, 10)
    assert vp(state, beneficiary) == before + 2
    assert removal_count(state, side) == 2


@pytest.mark.parametrize("permanent", [False, True])
@pytest.mark.parametrize("lid", ["hermann", "gavrilo"])
def test_other_scenarios_do_not_get_pleskau_points(lid, permanent):
    state = new_game("crusade_on_novgorod")
    before = (state.calendar.teutonic_vp, state.calendar.russian_vp)
    if permanent:
        _remove_lord_permanently(state, lid, load_lords()[lid])
    else:
        _disband_at_limit(state, lid, 9)
    assert (state.calendar.teutonic_vp, state.calendar.russian_vp) == before
    assert removal_count(state, "teutonic") == removal_count(state, "russian") == 0


@pytest.mark.parametrize("permanent", [False, True])
def test_departure_bonus_respects_vp_cap(permanent):
    state = new_game()
    state.calendar.russian_vp = 17.0
    if permanent:
        _remove_lord_permanently(state, "hermann", load_lords()["hermann"])
    else:
        _disband_at_limit(state, "hermann", 9)
    assert state.calendar.russian_vp == 17.5
    assert removal_count(state, "teutonic") == 1


def load_script(name):
    spec = importlib.util.spec_from_file_location(f"repair_{name}", ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def helper():
    return load_script("chatgpt_play_helper")


def test_forced_draw_enters_action_history(helper):
    helper.start("pleskau", seed=20261009)
    helper.auto(max_steps=1)
    assert helper._S["turn"] == len(helper._S["history"]) == 1
    assert helper._S["history"][0] == {
        "turn": 0, "side": "teutonic",
        "action": {"type": "aow_draw", "side": "teutonic", "args": {}},
    }


def test_mixed_manual_auto_history_saves_and_replays_exactly(helper, tmp_path):
    helper.start("pleskau", seed=20261009)
    helper.auto(max_steps=1)
    helper.apply(0)
    helper.auto(max_steps=8)
    history = helper._S["history"]
    assert len(history) >= 2
    assert helper._S["turn"] == len(history)
    assert [e["turn"] for e in history] == list(range(len(history)))
    path = tmp_path / "mixed.json"
    helper.save(str(path))
    saved = json.loads(path.read_text())
    replayed = new_game()
    for entry in saved["history"]:
        apply_action(replayed, entry["action"])
    assert replayed.model_dump_json() == saved["state_json"]


def test_failed_auto_action_is_not_recorded_as_completed(helper, monkeypatch):
    helper.start("pleskau", seed=20261009)
    before = helper._S["state"].model_dump_json()

    def fail(*_args):
        raise RuntimeError("diagnostic fixture")

    monkeypatch.setattr(helper, "apply_action", fail)
    helper.auto(max_steps=1)
    assert helper._S["history"] == [] and helper._S["turn"] == 0
    assert helper._S["state"].model_dump_json() == before
    assert helper._S["findings"][-1]["kind"] == "exception"


@pytest.mark.parametrize("diagnostic", [{"code": "fixture_rejection"}, {"exception": "RuntimeError: fixture"}])
def test_filtered_rejections_are_notable_and_visible(helper, capsys, diagnostic):
    finding = {"kind": "over_enum_filtered", "turn": 0, "side": "teutonic",
               "action": {"type": "diagnostic_fixture", "args": {}}, **diagnostic}
    helper._S["findings"] = [finding]
    assert helper.findings_report() == [finding]
    output = capsys.readouterr().out
    assert "1 total, 1 notable" in output
    assert "over_enum_filtered" in output and "diagnostic_fixture" in output
    assert next(iter(diagnostic.values())) in output
    assert "no engine anomalies" not in output


def test_unknown_diagnostic_is_printed_without_false_clean_summary(helper, capsys):
    helper._S["findings"] = [{"kind": "future_diagnostic", "message": "inspect me"}]
    helper.findings_report()
    output = capsys.readouterr().out
    assert "inspect me" in output and "no engine anomalies" not in output


def test_empty_findings_still_report_clean(helper, capsys):
    assert helper.findings_report() == []
    output = capsys.readouterr().out
    assert "0 total, 0 notable" in output and "no engine anomalies" in output


def test_original_179_action_game_now_scores_russian_victory():
    payload = json.loads((ROOT / "tests" / "data" / "pleskau_selfplay_20261009.json").read_text())
    state = load_scenario(payload["scenario"], seed=payload["seed"])
    applied = 0
    departures = []
    for count, typ, side, args in payload["action_runs"]:
        for _ in range(count):
            before = {lid: lord.side for lid, lord in state.lords.items()
                      if lord.state == "mustered" and lord.location is not None}
            before_vp = {sd: vp(state, sd) for sd in ("teutonic", "russian")}
            apply_action(state, {"type": typ, "side": side, "args": args})
            after = {lid for lid, lord in state.lords.items()
                     if lord.state == "mustered" and lord.location is not None}
            for lid in sorted(set(before) - after):
                beneficiary = "russian" if before[lid] == "teutonic" else "teutonic"
                assert vp(state, beneficiary) == before_vp[beneficiary] + 1
                departures.append(lid)
            applied += 1
            if applied % 10 == 0:
                state = GameState.model_validate_json(state.model_dump_json())
    assert applied == 179
    assert departures == ["gavrilo", "yaroslav", "knud_and_abel"]
    assert state.meta.game_over and state.meta.box == 2
    winner = determine_scenario_winner(state)
    assert winner["winner"] == "russian"
    assert (winner["t_vp"], winner["r_vp"]) == (1.0, 3.0)
    print("ORIGINAL_REPLAY_VERIFIED", json.dumps({"actions": applied, "winner": winner}))


def test_fresh_menu_driven_selfplay_completes_with_departure_accounting():
    state = new_game()
    llm = load_script("llm_self_play")
    strategic = load_script("strategic_agent")
    visits = Counter()
    for step in range(1500):
        if state.meta.game_over:
            break
        side = state.meta.active_player or "teutonic"
        menu, rejected = llm.concrete_actions_validated(state, side)
        assert not rejected, (step, rejected)
        concrete = [a for a in menu if isinstance(a.get("args"), dict)]
        assert concrete, (step, state.meta)

        def score(action):
            typ, args = action["type"], action.get("args", {})
            if typ == "plan_add_card":
                return 110 if args.get("card") != "pass" else 20
            value = strategic._action_score(state, action, side)
            if typ == "cmd_march":
                value -= 18 * visits[(side, args.get("lord_id"), args.get("to"))]
            return value

        action = {k: v for k, v in max(concrete, key=score).items()
                  if k in ("type", "side", "args")}
        before = {lid: lord.side for lid, lord in state.lords.items()
                  if lord.state == "mustered" and lord.location is not None}
        old_counts = {sd: removal_count(state, sd) for sd in ("teutonic", "russian")}
        apply_action(state, action)
        after = {lid for lid, lord in state.lords.items()
                 if lord.state == "mustered" and lord.location is not None}
        departed = Counter(before[lid] for lid in set(before) - after)
        for sd in ("teutonic", "russian"):
            assert removal_count(state, sd) == old_counts[sd] + departed[sd]
        if action["type"] == "cmd_march":
            args = action["args"]
            visits[(side, args.get("lord_id"), args.get("to"))] += 1
    assert state.meta.game_over, "Fresh self-play failed to reach a terminal state"
    print("FRESH_SELFPLAY_VERIFIED", json.dumps({"actions": step, "winner": determine_scenario_winner(state)}))
