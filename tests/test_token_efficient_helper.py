"""Lossless display, state-bound selection, privacy and resume contracts.

The complete existing generator is the reference, not a handpicked good-move
list. Real Return of the Prince positions span both players, Levy segments,
planning, command, FPD, combat interrupts and Campaign end.
"""
from __future__ import annotations

import contextlib
import gzip
import importlib.util
import io
import json
from collections import Counter
from copy import deepcopy
from functools import cache
from pathlib import Path

import pytest

from nevsky.actions import IllegalAction, apply_action
from nevsky.llm.action_browser import SelectionError
from nevsky.llm.compact import compact_briefing, detail_payload, player_view
from nevsky.llm.tools import legal_actions_for_side
from nevsky.scenarios import load_scenario
from nevsky.state import GameState, PendingDecision

ROOT = Path(__file__).resolve().parents[1]


def helper():
    spec = importlib.util.spec_from_file_location("token_helper", ROOT / "scripts/chatgpt_play_helper.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def start(nv, scenario="crusade_on_novgorod"):
    with contextlib.redirect_stdout(io.StringIO()):
        nv.start(scenario, seed=20261016)
    return nv._S["state"]


def attach(nv, state):
    nv._S.update(state=state, scenario=state.meta.scenario_id, history=[], findings=[], turn=0)


@cache
def positions():
    selected = {}
    for policy in ("logistics", "combined", "maritime"):
        path = ROOT / f"reports/return_prince_20261028/{policy}/positions.jsonl.gz"
        with gzip.open(path, "rt") as source:
            for line in source:
                row = json.loads(line)
                s = row["state"]
                m = s["meta"]
                key = (m["phase"], m["levy_step"] if m["phase"] == "levy" else m["campaign_step"],
                       m["active_player"], bool(s["combat_pending"]),
                       bool(s["campaign_turn"]["in_feed_pay_disband"]))
                selected.setdefault(key, s)
    return list(selected.values())


def all_pages(nv, **kwargs):
    first = nv.actions(**kwargs)
    result = list(first["items"])
    for page in range(2, first["pages"] + 1):
        result.extend(nv.actions(page=page, **kwargs)["items"])
    return result


def plain(entry):
    return {k: v for k, v in entry.items() if k != "_unvalidated_template"}


@pytest.mark.parametrize("index", range(len(positions())))
def test_all_pages_and_category_filters_are_lossless(index, capsys):
    nv = helper()
    state = GameState.model_validate(positions()[index])
    attach(nv, state)
    before = state.model_dump_json()
    side = state.meta.active_player
    legacy = nv._cav(state, side)[0]
    assert nv.show(side) == legacy
    rows = all_pages(nv, side=side, page_size=3)
    assert [r["action"] for r in rows[:len(legacy)]] == legacy
    for original in legal_actions_for_side(state, side):
        if "args_template" in original:
            assert plain(original) in [plain(r["action"]) for r in rows]
    counts = nv._BROWSER.overview(state, side, nv._validated)
    assert counts["total"] == len(rows)
    by_category = []
    for category, summary in counts["categories"].items():
        filtered = all_pages(nv, side=side, category=category, page_size=2)
        assert len(filtered) == summary["entries"]
        by_category.extend(filtered)
    assert Counter(r["id"] for r in by_category) == Counter(r["id"] for r in rows)
    for size in (1, 7, 100):
        assert all_pages(nv, side=side, page_size=size) == rows
    for row in rows:
        assert nv.action(row["id"], side=side) == row
    assert state.model_dump_json() == before
    capsys.readouterr()


@pytest.mark.parametrize("index", range(0, len(positions()), 3))
def test_lord_and_argument_filters_do_not_renumber(index, capsys):
    nv = helper()
    state = GameState.model_validate(positions()[index])
    attach(nv, state)
    rows = all_pages(nv)
    identities = {r["id"]: r for r in rows}
    for lord in state.lords:
        filtered = all_pages(nv, lord=lord, page_size=2)
        for row in filtered:
            assert row == identities[row["id"]]
        for row in rows:
            a = row["action"]
            if a.get("args", {}).get("by_lord") == lord or "args_template" in a:
                assert row in filtered
    for key, value in (("to", "pskov"), ("units", 2), ("mode", "shift")):
        filtered = all_pages(nv, params={key: value})
        assert all(r == identities[r["id"]] for r in filtered)
        assert all(r in filtered for r in rows if "args_template" in r["action"])
    capsys.readouterr()


@pytest.mark.parametrize("method", ["apply", "auto", "external", "replace", "load", "start"])
def test_stale_ids_never_apply_or_fallback(method, tmp_path, monkeypatch):
    nv = helper()
    state = start(nv)
    old = nv.actions()["items"][0]["id"]
    if method == "apply":
        nv.apply(old)
    elif method == "auto":
        nv.auto(max_steps=1)
    elif method == "external":
        state.veche.coin += 1
    elif method == "replace":
        nv._S["state"] = state.model_copy(deep=True)
    elif method == "load":
        nv.save(str(tmp_path / "state.json"))
        nv.load(str(tmp_path / "state.json"))
    else:
        start(nv)
    before = deepcopy(nv._S)
    def fail(*a, **k):
        raise AssertionError("stale selection attempted fallback or engine action")
    monkeypatch.setattr(nv, "safe_fallback_for_side", fail)
    monkeypatch.setattr(nv, "apply_action", fail)
    with pytest.raises(SelectionError, match="stale.*no action applied"):
        nv.apply(old)
    assert nv._S == before


def test_pay_template_survives_expansion_and_executes_two_units():
    nv = helper()
    state = start(nv)
    state.meta.levy_step = "pay"
    state.lords["hermann"].assets["coin"] = 3
    rows = all_pages(nv, category="pay_with_coin", params={"units": 2})
    template = next(r for r in rows if r["action"].get("args_template", {}).get("from") == "lord:<id>")
    original = nv.action(template["id"])["action"]
    assert original["candidates"]["targets_by_payer"]["hermann"] == ["hermann"]
    before = state.model_dump_json()
    with pytest.raises(SelectionError, match="parameterized"):
        nv.apply(template["id"])
    assert state.model_dump_json() == before
    expected = state.model_copy(deep=True)
    args = {"from": "lord:hermann", "target_lord": "hermann", "units": 2}
    apply_action(expected, {"type": "pay_with_coin", "side": "teutonic", "args": args})
    nv.apply(template["id"], args=args)
    assert state.model_dump() == expected.model_dump()


def test_template_bound_arguments_and_invalid_parameters_are_atomic():
    nv = helper()
    state = start(nv)
    state.meta.levy_step = "pay"
    state.meta.active_player = "russian"
    state.veche.coin = 2
    template = next(r for r in all_pages(nv, category="pay_with_coin", templates=True)
                    if r["action"]["args_template"]["from"] == "veche")
    before = deepcopy(nv._S)
    with pytest.raises(SelectionError, match="bound argument"):
        nv.apply(template["id"], args={"from": "lord:gavrilo"})
    assert nv._S == before
    with pytest.raises(IllegalAction):
        nv.apply(template["id"], args={"target_lord": "hermann", "units": 99})
    assert nv._S == before


def test_concrete_id_cannot_be_reinterpreted_through_args():
    nv = helper()
    state = start(nv)
    state.meta.phase = "campaign"
    state.meta.campaign_step = "plan"
    row = next(r for r in all_pages(nv) if r["action"].get("args", {}).get("card") == "hermann")
    before = deepcopy(nv._S)
    with pytest.raises(SelectionError, match="bound argument"):
        nv.apply(row["id"], args={"card": "pass"})
    assert nv._S == before


def test_selected_id_stays_same_after_arbitrary_browsing():
    nv = helper()
    state = start(nv)
    state.meta.phase = "campaign"
    state.meta.campaign_step = "plan"
    rows = all_pages(nv, page_size=2)
    row = next(r for r in rows if r["action"].get("args", {}).get("card") == "hermann")
    nv.actions(query="pass")
    nv.actions(lord="yaroslav")
    nv.actions(side="russian")
    nv.show()
    expected = state.model_copy(deep=True)
    apply_action(expected, row["action"])
    nv.apply(row["id"])
    assert state.model_dump() == expected.model_dump()


def test_catalog_return_values_are_detached_and_notebook_echo_is_compact():
    nv = helper()
    state = start(nv)
    before = state.model_dump_json()
    menu = nv.show()
    original = deepcopy(menu[0])
    menu[0]["type"] = "corrupted"
    page = nv.actions()
    identifier = page["items"][0]["id"]
    page["items"][0]["action"]["type"] = "corrupted"
    assert nv.action(identifier)["action"] == original
    assert state.model_dump_json() == before
    assert isinstance(menu, list)
    assert len(repr(menu)) < 140 and "corrupted" not in repr(menu)
    assert len(repr(page)) < 100 and "corrupted" not in repr(page)


@pytest.mark.parametrize("arguments", [
    {"page": 0}, {"page": -1}, {"page": 10000}, {"page_size": 0},
    {"page_size": 101}, {"page_size": True}, {"params": []}, {"templates": "yes"},
    {"lord": "not_a_lord"}, {"side": "not_a_side"},
])
def test_bad_filters_do_not_mutate_state(arguments):
    nv = helper()
    start(nv)
    before = deepcopy(nv._S)
    with pytest.raises((ValueError, TypeError)):
        nv.actions(**arguments)
    assert nv._S == before


@pytest.mark.parametrize("side", ["teutonic", "russian"])
def test_all_displays_preserve_hidden_information(side):
    nv = helper()
    state = start(nv)
    state.meta.active_player = side
    other = "russian" if side == "teutonic" else "teutonic"
    getattr(state.decks, other).holds = ["OPPONENT_HOLD_CANARY"]
    getattr(state.decks, other).pending_draw = ["OPPONENT_DRAW_CANARY"]
    getattr(state.decks, other).plan = ["OPPONENT_PLAN_CANARY"]
    for deck in (state.decks.teutonic, state.decks.russian):
        deck.deck = ["FUTURE_DRAW_CANARY"]
    state.meta.seed = 739284771
    state.meta.rng_state = 473928478
    state.pending_decisions.append(PendingDecision(kind="fixture", owed_by=other,
                                                   context={"secret": "PENDING_CANARY"}))
    with contextlib.redirect_stdout(io.StringIO()) as capture:
        nv.show(side)
        page = nv.actions(side=side)
        data = nv.full_state(side)
        for topic in ("cards", "pending", "combat", "calendar", "history", "rules"):
            nv.details(topic, side=side)
        nv.result(side=side, full=True)
    text = capture.getvalue() + json.dumps(dict(data)) + json.dumps(dict(page))
    for secret in ("OPPONENT_HOLD_CANARY", "OPPONENT_DRAW_CANARY", "OPPONENT_PLAN_CANARY",
                   "FUTURE_DRAW_CANARY", "PENDING_CANARY", "739284771", "473928478"):
        assert secret not in text
    assert all(r["action"]["side"] == side for r in page["items"])


def test_history_result_is_redacted_after_perspective_switch(capsys):
    nv = helper()
    state = start(nv)
    nv.apply(nv.actions()["items"][0]["id"])
    own = nv.result(side="teutonic", full=True)
    other = nv.result(side="russian", full=True)
    assert own["result"]["drawn"] == state.decks.teutonic.pending_draw
    assert other["result"]["drawn"] == ["<hidden>", "<hidden>"]
    capsys.readouterr()
    nv.show("russian")
    assert "view=russian" in capsys.readouterr().out
    nv.show("teutonic")
    out = capsys.readouterr().out
    assert "view=teutonic" in out and "Service=" in out and "pending_draw=" in out


def test_opposing_hold_ids_require_their_owner():
    nv = helper()
    state = GameState.model_validate_json((ROOT / "tests/data/crusade_20261010/hidden_hold_R3.json").read_text())
    state.meta.active_player = "teutonic"
    attach(nv, state)
    rows = all_pages(nv, side="russian")
    row = next(r for r in rows if r["action"].get("args", {}).get("card_id") == "R3")
    before = state.model_dump_json()
    with pytest.raises(SelectionError, match="different perspective"):
        nv.apply(row["id"])
    assert state.model_dump_json() == before
    nv.apply(row["id"], side="russian")
    assert state.meta.active_player == "teutonic"
    assert nv._S["history"][-1]["side"] == "russian"


def test_hidden_mats_use_existing_fog_of_war_filter():
    state = load_scenario("pleskau", optional_rules={"hidden_mats": True})
    data = player_view(state, "teutonic")
    assert data["lords"]["gavrilo"]["forces"] == {"_hidden": 1}
    assert data["lords"]["gavrilo"]["assets"] == {}
    assert data["lords"]["hermann"]["assets"] == state.lords["hermann"].assets
    assert "mat=<hidden>" in compact_briefing(state, "teutonic")


def test_save_resume_keeps_game_and_legacy_interfaces(tmp_path):
    nv = helper()
    state = start(nv)
    nv.apply(0)
    menu = nv.show()
    next_action = deepcopy(menu[0])
    # The existing raw dictionary path and return-as-list contract are unchanged.
    assert isinstance(nv.apply(next_action), list)
    path = tmp_path / "game.json"
    nv.save(str(path))
    old = deepcopy(nv._S)
    loaded = helper()
    with contextlib.redirect_stdout(io.StringIO()) as out:
        loaded.load(str(path), side="russian")
    assert loaded._S == old
    assert "Fresh position:" in out.getvalue() and "Service=" in out.getvalue()
    before = deepcopy(loaded._S)
    path.write_text('{"broken":true}')
    with pytest.raises((ValueError, KeyError)):
        loaded.load(str(path))
    assert loaded._S == before
    assert state.model_dump() == loaded._S["state"].model_dump()


@pytest.mark.parametrize("metadata", ["candidates", "holds_available", "args_template"])
def test_auto_never_treats_single_parameter_family_as_forced(metadata, monkeypatch):
    nv = helper()
    state = start(nv)
    before = state.model_dump_json()
    menu = [{"type": "aow_draw", "side": "teutonic", "args": {}, metadata: {"choice": [1, 2]}}]
    monkeypatch.setattr(nv, "_validated", lambda *a, **k: menu)
    monkeypatch.setattr(nv, "show", lambda: [])
    nv.auto(max_steps=1)
    assert state.model_dump_json() == before


def test_details_keep_resources_service_capabilities_supply_and_victory():
    state = load_scenario("watland", seed=20261016)
    before = state.model_dump_json()
    info = detail_payload(state, "teutonic", "lord", lord="andreas")
    assert info["state"]["assets"] == state.lords["andreas"].assets
    assert info["state"]["vassals"]
    assert "service" in info["printed"]["ratings"]
    supply = detail_payload(state, "teutonic", "supply", lord="andreas")
    assert "seats" in supply["lords"]["andreas"]
    assert "transport_pool_default" in supply["lords"]["andreas"]
    assert "Famine" in compact_briefing(state, "teutonic")
    assert "7 VP" in detail_payload(state, "teutonic", "victory")["scenario_end"]
    card = detail_payload(state, "teutonic", "card", card_id="T3")
    assert card["event_text"] and card["capability_text"] and card["event_eligibility"]
    assert state.model_dump_json() == before


def test_notebook_default_does_not_print_rows_but_opt_in_does(capsys):
    nv = helper()
    state = start(nv)
    nv.show()
    sole = capsys.readouterr().out
    assert 'aow_draw=1' in sole and '"args":{}' in sole
    state.meta.phase = "campaign"
    state.meta.campaign_step = "plan"
    nv.show()
    default = capsys.readouterr().out
    assert 'plan_add_card=' in default and '"card":"hermann"' not in default
    nv.show(full_menu=True)
    assert '"card":"hermann"' in capsys.readouterr().out


def test_terminal_catalog_empty_and_ids_stale():
    nv = helper()
    state = start(nv)
    identifier = nv.actions()["items"][0]["id"]
    state.meta.game_over = True
    assert nv.actions()["items"] == []
    with pytest.raises(SelectionError, match="stale"):
        nv.apply(identifier)


@pytest.mark.parametrize("side", ["teutonic", "russian"])
def test_template_and_concrete_partitions_cover_every_entry(side):
    nv = helper()
    state = start(nv)
    state.meta.active_player = side
    state.meta.levy_step = "pay"
    for lord in state.lords.values():
        if lord.state == "mustered":
            lord.assets["coin"] = 3
    all_rows = all_pages(nv, side=side)
    parts = all_pages(nv, side=side, templates=True) + all_pages(nv, side=side, templates=False)
    assert Counter(r["id"] for r in parts) == Counter(r["id"] for r in all_rows)
    assert all_pages(nv, side=side, params={"group": ["hermann"]}) is not None


@pytest.mark.parametrize("side", ["teutonic", "russian"])
def test_public_mat_fields_survive_compact_table(side):
    state = load_scenario("crusade_on_novgorod")
    text = compact_briefing(state, side)
    for lid, mat in state.lords.items():
        if mat.location is None:
            assert lid in text and mat.state in text
            continue
        row = next(line for line in text.splitlines() if f" {lid}@" in line)
        for pile in (mat.forces, mat.assets):
            assert all(f"{key}={amount}" in row for key, amount in pile.items())
    assert "Service=position/rating" in text and "Lordship=used/printed+bonus" in text
    assert state.model_dump() == load_scenario("crusade_on_novgorod").model_dump()


def test_losing_browser_session_invalidates_ids_and_keeps_fresh_briefing(capsys):
    nv = helper()
    start(nv)
    identifier = nv.actions()["items"][0]["id"]
    nv._BROWSER.reset()
    with pytest.raises(SelectionError, match="stale"):
        nv.apply(identifier)
    capsys.readouterr()
    nv.show()
    out = capsys.readouterr().out
    assert "VP T=" in out and "Service=position/rating" in out and "Muster order=" in out


def test_lookup_card_returns_full_reference_tip():
    nv = helper()
    start(nv)
    info = nv.details("card", card_id="R3")
    assert "Teutonic Activation" in info["data"]["reference"]


def test_notebook_pretty_methods_do_not_echo_hidden_or_full_menus():
    nv = helper()
    start(nv)
    class Printer:
        def __init__(self):
            self.output = ""
        def text(self, message):
            self.output += message
    for value in (nv.show(), nv.actions(), nv.full_state()):
        printer = Printer()
        value._repr_pretty_(printer, False)
        assert len(printer.output) < 140 and "rng_state" not in printer.output


def test_unknown_id_and_negative_id_do_not_apply():
    nv = helper()
    state = start(nv)
    identifier = nv.actions()["items"][0]["id"]
    before = deepcopy(nv._S)
    for invalid in ("not-an-id", identifier.rsplit(":", 1)[0] + ":-1",
                    identifier.rsplit(":", 1)[0] + ":999", identifier.rsplit(":", 1)[0] + ":00"):
        with pytest.raises(SelectionError):
            nv.apply(invalid)
        assert nv._S == before
    assert state is nv._S["state"]


def test_complete_return_of_prince_via_ids_and_periodic_save_resume(tmp_path):
    """860 recorded actions; both sides, eight turns, templates and interrupts.

    Setup uses the existing start contract. No raw-action escape hatch or
    fallback is used for any subsequent selection. Loaded IDs are discarded.
    """
    from nevsky.llm.action_browser import _literal
    from nevsky.scenarios import determine_scenario_winner
    source = ROOT / "reports/return_prince_20261028/maritime"
    transcript = json.loads((source / "transcript.json").read_text())
    nv = helper()
    with contextlib.redirect_stdout(io.StringIO()):
        nv.start("return_of_the_prince", seed=20261030)
        expected = nv._S["state"].model_copy(deep=True)
        for index, record in enumerate(transcript[2:]):
            intended = record["action"]
            side = intended["side"]
            rows = all_pages(nv, category=intended["type"], side=side, page_size=100)
            def fits(row, intended=intended):
                a = row["action"]
                bound = a.get("args")
                if isinstance(bound, dict):
                    return all(intended["args"].get(k) == v for k, v in bound.items())
                return all(not _literal(v) or intended["args"].get(k) == v
                           for k, v in a.get("args_template", {}).items())
            exact = [r for r in rows if {k: v for k, v in r["action"].items()
                     if k in ("type", "side", "args")} == intended]
            candidates = exact or [r for r in rows if fits(r)]
            assert candidates, (index, intended)
            selected = candidates[0]
            nv.apply(selected["id"], side=side, args=intended["args"])
            apply_action(expected, deepcopy(intended))
            assert nv._S["state"].model_dump() == expected.model_dump()
            if index % 100 == 0:
                path = tmp_path / "resume.json"
                nv.save(str(path))
                nv.load(str(path))
        assert determine_scenario_winner(nv._S["state"]) == json.loads((source / "summary.json").read_text())["winner"]
        assert nv._S["state"].meta.game_over
        assert len(nv._S["history"]) == len(transcript) - 2 == 858
