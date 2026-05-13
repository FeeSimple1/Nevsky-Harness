"""Round 53 — SMOKE-041 regression tests.

Per Commands.txt 4.3.1: "Marshal may take a group March." A non-
Marshal Lord cannot bring co-located own-side Lords along in a
March. A Lieutenant (Lord with has_lower_lord set) may bring their
Lower Lord (4.1.3) but no one else.
"""

import pytest

import nevsky.actions  # ensure handlers registered
from nevsky.scenarios import load_scenario
from nevsky.actions import apply_action, IllegalAction
from nevsky.static_data import load_ways


def _adj(src):
    for w in load_ways():
        if w["a"] == src:
            return w["b"]
        if w["b"] == src:
            return w["a"]
    return None


def _setup_march(st, active):
    st.meta.phase = "campaign"
    st.meta.campaign_step = "command"
    st.campaign_turn.active_lord = active
    st.campaign_turn.active_card = active
    st.campaign_turn.actions_remaining = 5


def test_nonmarshal_lord_cannot_take_group():
    st = load_scenario("pleskau", seed=1)
    y = st.lords["yaroslav"]   # marshal_role: None
    k = st.lords["knud_and_abel"]  # marshal_role: None
    k.location = y.location
    k.assets["provender"] = 0
    y.assets["provender"] = 0
    _setup_march(st, "yaroslav")
    with pytest.raises(IllegalAction) as exc:
        apply_action(st, {"type": "cmd_march", "side": "teutonic",
                          "args": {"lord_id": "yaroslav", "to": _adj(y.location),
                                   "group": ["yaroslav", "knud_and_abel"]}})
    assert exc.value.code == "non_marshal_group"


def test_marshal_can_take_group():
    """Andreas (permanent Marshal) can take a co-located own-side Lord."""
    st = load_scenario("pleskau", seed=1)
    # Andreas isn't in pleskau; use watland
    st = load_scenario("watland", seed=1)
    andreas = st.lords.get("andreas")
    if andreas is None or andreas.state != "mustered":
        return  # scenario doesn't have andreas mustered; skip
    # Find a co-located own-side Lord (or place one)
    same_side = [
        lid for lid, L in st.lords.items()
        if L.side == andreas.side and L.state == "mustered" and lid != "andreas"
    ]
    if not same_side:
        return
    other = same_side[0]
    st.lords[other].location = andreas.location
    st.lords[other].assets["provender"] = 0
    andreas.assets["provender"] = 0
    _setup_march(st, "andreas")
    dest = _adj(andreas.location)
    res = apply_action(st, {"type": "cmd_march", "side": andreas.side,
                           "args": {"lord_id": "andreas", "to": dest,
                                    "group": ["andreas", other]}})
    assert res["to"] == dest


def test_lieutenant_can_take_only_lower_lord():
    """Active Lieutenant with Lower Lord can March together but not with
    additional same-side Lords (unless that Lieutenant is also a Marshal,
    which is forbidden by 4.1.3 anyway)."""
    st = load_scenario("pleskau", seed=1)
    y = st.lords["yaroslav"]
    h = st.lords["hermann"]
    k = st.lords["knud_and_abel"]
    h.location = y.location
    k.location = y.location
    # yaroslav = Lieutenant, hermann = Lower Lord
    y.has_lower_lord = "hermann"
    h.lieutenant_of = "yaroslav"
    # Hermann's Marshal-secondary role might activate; force not by setting
    # andreas-equivalent on the map. For pleskau there's no andreas. Use
    # plain non-Marshal yaroslav as Lieutenant.
    h.has_lower_lord = None
    y.lieutenant_of = None
    k.has_lower_lord = None
    k.lieutenant_of = None
    for L in (y, h, k):
        L.assets["provender"] = 0
    _setup_march(st, "yaroslav")
    # Group with Lieutenant + Lower Lord only — should succeed
    res = apply_action(st, {"type": "cmd_march", "side": "teutonic",
                           "args": {"lord_id": "yaroslav", "to": _adj(y.location),
                                    "group": ["yaroslav", "hermann"]}})
    assert res["to"] is not None
    # Reset locations
    st = load_scenario("pleskau", seed=1)
    y = st.lords["yaroslav"]
    h = st.lords["hermann"]
    k = st.lords["knud_and_abel"]
    h.location = y.location
    k.location = y.location
    y.has_lower_lord = "hermann"
    h.lieutenant_of = "yaroslav"
    h.has_lower_lord = None
    y.lieutenant_of = None
    k.has_lower_lord = None
    k.lieutenant_of = None
    for L in (y, h, k):
        L.assets["provender"] = 0
    _setup_march(st, "yaroslav")
    # Group with Lieutenant + Lower Lord + Third Lord — should fail
    with pytest.raises(IllegalAction) as exc:
        apply_action(st, {"type": "cmd_march", "side": "teutonic",
                          "args": {"lord_id": "yaroslav", "to": _adj(y.location),
                                   "group": ["yaroslav", "hermann", "knud_and_abel"]}})
    assert exc.value.code == "non_marshal_group"


def test_solo_nonmarshal_march_allowed():
    """A non-Marshal Lord may March alone (group=[self])."""
    st = load_scenario("pleskau", seed=1)
    y = st.lords["yaroslav"]
    y.assets["provender"] = 0
    _setup_march(st, "yaroslav")
    res = apply_action(st, {"type": "cmd_march", "side": "teutonic",
                           "args": {"lord_id": "yaroslav", "to": _adj(y.location),
                                    "group": ["yaroslav"]}})
    assert res["to"] is not None
