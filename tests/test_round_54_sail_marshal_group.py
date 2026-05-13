"""Round 54 — SMOKE-042 regression tests.

Sail (4.7.3) group rules mirror March (4.3.1): only Marshals (or
Lieutenant + Lower Lord pair) may take a group. Per Commands.txt:
"Groups move together as per March (4.3.1); Marshals may take group,
Lieutenants take Lower Lords."
"""

import pytest

import nevsky.actions  # noqa
from nevsky.scenarios import load_scenario
from nevsky.actions import apply_action, IllegalAction


def test_nonmarshal_cannot_sail_group():
    st = load_scenario("pleskau", seed=1)
    y = st.lords["yaroslav"]
    k = st.lords["knud_and_abel"]
    y.location = "reval"
    k.location = "reval"
    y.has_lower_lord = None; y.lieutenant_of = None
    k.has_lower_lord = None; k.lieutenant_of = None
    y.in_stronghold = False; k.in_stronghold = False
    st.locales["reval"].siege_markers = 0
    st.meta.box = 8
    st.meta.phase = "campaign"
    st.meta.campaign_step = "command"
    st.campaign_turn.active_lord = "yaroslav"
    st.campaign_turn.active_card = "yaroslav"
    st.campaign_turn.actions_remaining = 5
    with pytest.raises(IllegalAction) as exc:
        apply_action(st, {"type": "cmd_sail", "side": "teutonic",
                          "args": {"lord_id": "yaroslav", "destination": "narwia",
                                   "group": ["yaroslav", "knud_and_abel"]}})
    assert exc.value.code == "non_marshal_group"


def test_solo_nonmarshal_sail_allowed():
    st = load_scenario("pleskau", seed=1)
    y = st.lords["yaroslav"]
    y.location = "reval"
    y.has_lower_lord = None; y.lieutenant_of = None
    y.in_stronghold = False
    st.locales["reval"].siege_markers = 0
    st.meta.box = 8
    st.meta.phase = "campaign"
    st.meta.campaign_step = "command"
    st.campaign_turn.active_lord = "yaroslav"
    st.campaign_turn.active_card = "yaroslav"
    st.campaign_turn.actions_remaining = 5
    res = apply_action(st, {"type": "cmd_sail", "side": "teutonic",
                           "args": {"lord_id": "yaroslav", "destination": "narwia",
                                    "group": ["yaroslav"]}})
    assert res["to"] == "narwia"


def test_lieutenant_must_sail_with_lower_lord():
    st = load_scenario("pleskau", seed=1)
    y = st.lords["yaroslav"]
    h = st.lords["hermann"]
    y.location = "reval"
    h.location = "reval"
    y.has_lower_lord = "hermann"
    h.lieutenant_of = "yaroslav"
    y.lieutenant_of = None; h.has_lower_lord = None
    y.in_stronghold = False; h.in_stronghold = False
    st.locales["reval"].siege_markers = 0
    st.meta.box = 8
    st.meta.phase = "campaign"
    st.meta.campaign_step = "command"
    st.campaign_turn.active_lord = "yaroslav"
    st.campaign_turn.active_card = "yaroslav"
    st.campaign_turn.actions_remaining = 5
    # Solo group [yaroslav] — should fail Lower Lord requirement
    with pytest.raises(IllegalAction) as exc:
        apply_action(st, {"type": "cmd_sail", "side": "teutonic",
                          "args": {"lord_id": "yaroslav", "destination": "narwia",
                                   "group": ["yaroslav"]}})
    assert exc.value.code == "lower_lord_required"
