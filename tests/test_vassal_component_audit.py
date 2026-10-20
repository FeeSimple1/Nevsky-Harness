"""Printed-component regressions from the Nevsky Vassal 2.1 audit.

Expectations are transcribed from the Lord mats / vassal counter, not
derived from the harness's static data. See docs/VASSAL_AUDIT_20261019.md.
"""

from collections import Counter
import importlib.util
from pathlib import Path

import pytest

from nevsky.actions import _place_lord_on_map, apply_action
from nevsky.legal_moves import legal_moves
from nevsky.llm.session import LLMSession
from nevsky.scenarios import load_scenario


TRANSPORT = ("boat", "cart", "sled", "ship")


def transport_choices(state, lord_id):
    return [
        pd for pd in state.pending_decisions
        if pd.kind == "setup_transport_choice" and pd.context["lord_id"] == lord_id
    ]


@pytest.mark.parametrize("scenario,lord_id,count,provender", [
    ("watland", "domash", 4, 4),
    ("peipus", "domash", 4, 4),
    ("pleskau", "gavrilo", 2, 2),
    ("crusade_on_novgorod", "gavrilo", 2, 2),
    ("return_of_the_prince_nicolle", "gavrilo", 2, 2),
])
def test_printed_starting_assets_at_scenario_setup(scenario, lord_id, count, provender):
    """RoP 1.5.2 / 2.1.2: setup uses the printed Lord mat Assets."""
    state = load_scenario(scenario)
    assets = state.lords[lord_id].assets
    assert assets.get("provender") == provender
    assert sum(assets.get(t, 0) for t in TRANSPORT) == count
    choices = transport_choices(state, lord_id)
    assert {pd.context["slot_index"] for pd in choices} == set(range(count))
    assert all(set(pd.context["allowed_values"]) == set(TRANSPORT) for pd in choices)


@pytest.mark.parametrize("lord_id,seat,count,provender", [
    ("domash", "novgorod", 4, 4),
    ("gavrilo", "pskov", 2, 2),
])
def test_later_muster_replenishes_printed_assets(lord_id, seat, count, provender):
    """RoP 3.4.1: Muster restores all printed Assets and Transport choices."""
    state = load_scenario("return_of_the_prince")
    # Both Lords start on the Calendar. Exercise the successful Muster
    # procedure independently of the Fealty roll / actor's Lordship.
    assert state.lords[lord_id].state == "ready"
    _place_lord_on_map(state, lord_id, seat, state.meta.box)
    assets = state.lords[lord_id].assets
    assert assets.get("provender") == provender
    assert sum(assets.get(t, 0) for t in TRANSPORT) == count
    assert len(transport_choices(state, lord_id)) == count


@pytest.mark.parametrize("lord_id,scenario,choices", [
    ("domash", "watland", ("boat", "cart", "sled", "ship")),
    ("domash", "peipus", ("ship", "ship", "ship", "ship")),
    ("gavrilo", "pleskau", ("ship", "boat")),
])
def test_each_transport_slot_is_discoverable_and_independently_selectable(
    lord_id, scenario, choices
):
    """RoP 3.4.1; Q-001/Q-002: each printed Transport is a player choice."""
    state = load_scenario(scenario)
    state.meta.active_player = "russian"
    moves = legal_moves(state, with_previews=False)
    for index in range(len(choices)):
        assert {m["args"]["value"] for m in moves
                if m["type"] == "set_setup_transport"
                and m["args"]["lord_id"] == lord_id
                and m["args"]["slot_index"] == index} == set(TRANSPORT)
    for index, choice in enumerate(choices):
        action = {"type": "set_setup_transport", "side": "russian", "args": {
            "lord_id": lord_id, "slot_index": index, "value": choice,
        }}
        moves = legal_moves(state, with_previews=False)
        assert any(m["type"] == action["type"] and m["args"] == action["args"]
                   for m in moves)
        apply_action(state, action)
    assert not transport_choices(state, lord_id)
    assert {t: state.lords[lord_id].assets.get(t, 0) for t in TRANSPORT} == {
        t: Counter(choices)[t] for t in TRANSPORT
    }


@pytest.mark.parametrize("advanced", [False, True])
def test_mstislavich_partisans_use_printed_one_box_service(advanced):
    """RoP 3.4.2: advanced Vassal Service uses the printed counter rating."""
    state = load_scenario("pleskau", optional_rules={"advanced_vassal_service": advanced})
    state.meta.levy_step = "muster"
    # Extend Yaroslav to box 4 so his vassal's Service, rather than his
    # own impending Disband, determines its advanced-rule placement.
    state.calendar.boxes[1].service_markers.remove("yaroslav")
    state.calendar.boxes[3].service_markers.append("yaroslav")
    vid = "yaroslav_mstislavich_partisans"
    apply_action(state, {"type": "muster_vassal", "side": "teutonic", "args": {
        "by_lord": "yaroslav", "vassal_id": vid,
    }})
    vassal = state.lords["yaroslav"].vassals[vid]
    assert vassal.mustered
    assert state.lords["yaroslav"].forces["militia"] == 2
    assert vassal.on_calendar == advanced
    assert vassal.calendar_box == (2 if advanced else None)
    assert (vid in state.calendar.boxes[1].vassal_service_markers) == advanced
    assert vid not in state.calendar.boxes[2].vassal_service_markers


@pytest.mark.parametrize("backend", ["session", "helper"])
@pytest.mark.parametrize("confirm", [False, True])
def test_interactive_start_preserves_choices_unless_explicitly_accepted(backend, confirm):
    """Q-001/Q-002: starting an interface must preserve the player override."""
    kwargs = {"confirm_transports": True} if confirm else {}
    if backend == "session":
        state = LLMSession.start_new("pleskau", llm_side="russian", **kwargs).state
    else:
        path = Path(__file__).resolve().parents[1] / "scripts/chatgpt_play_helper.py"
        spec = importlib.util.spec_from_file_location("vassal_audit_helper", path)
        helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(helper)
        helper.start("pleskau", **kwargs)
        state = helper._S["state"]
    assert len(transport_choices(state, "gavrilo")) == (0 if confirm else 2)
    # Vladislav is a Q-001 explicit-choice hotspot, preserved as well.
    assert len(transport_choices(state, "vladislav")) == (0 if confirm else 1)
    moves = legal_moves(state, with_previews=False)
    assert all(m["side"] == "teutonic" for m in moves)
    assert bool([m for m in moves if m["type"] == "set_setup_transport"]) != confirm
