"""Round 58 — SMOKE-046 regression tests.

4.7.3 Sail requires Ships per Sailing group's load:
  - 1 Ship per Teutonic horse unit
  - 2 Ships per Russian horse unit
  - 1 Ship per Provender
  - 2 Ships per Loot
Ships pool across the group; T18 Cogs doubles each Ship's capacity.
"""

import pytest

import nevsky.actions  # noqa
from nevsky.scenarios import load_scenario
from nevsky.actions import apply_action, IllegalAction


def _setup_sail(st, lid, src="reval"):
    L = st.lords[lid]
    L.location = src
    L.in_stronghold = False
    L.assets["provender"] = 0
    L.assets["loot"] = 0
    st.locales[src].siege_markers = 0
    st.meta.box = 8  # summer
    st.meta.phase = "campaign"
    st.meta.campaign_step = "command"
    st.campaign_turn.active_lord = lid
    st.campaign_turn.active_card = lid
    st.campaign_turn.actions_remaining = 5


def test_sail_with_no_ships_rejected_for_horse_units():
    """Teutonic Lord with horse units but 0 Ships cannot Sail."""
    st = load_scenario("pleskau", seed=1)
    h = st.lords["hermann"]
    h.forces = {"knights": 1, "sergeants": 1}  # 2 horse units
    _setup_sail(st, "hermann")
    h.assets["ship"] = 0
    with pytest.raises(IllegalAction) as exc:
        apply_action(st, {"type": "cmd_sail", "side": "teutonic",
                          "args": {"lord_id": "hermann", "destination": "narwia",
                                   "group": ["hermann"]}})
    assert exc.value.code == "insufficient_ships"


def test_sail_teutonic_horse_one_ship_per_unit():
    """Teutonic: 1 Ship per horse unit suffices."""
    st = load_scenario("pleskau", seed=1)
    h = st.lords["hermann"]
    h.forces = {"knights": 2, "sergeants": 1}  # 3 horse units
    _setup_sail(st, "hermann")
    h.assets["ship"] = 3  # exactly enough
    res = apply_action(st, {"type": "cmd_sail", "side": "teutonic",
                           "args": {"lord_id": "hermann", "destination": "narwia",
                                    "group": ["hermann"]}})
    assert res["to"] == "narwia"


def test_sail_russian_horse_two_ships_per_unit():
    """Russian: 2 Ships per horse unit required."""
    st = load_scenario("pleskau", seed=1)
    # Use gavrilo (Russian) — actually pleskau scenario uses gavrilo
    g = st.lords["gavrilo"]
    g.forces = {"knights": 1}  # 1 horse unit, needs 2 ships for Russian
    # Russian Lords aren't ships-authorized by default; force allow for probe
    # (test bypasses static authorization for clarity).
    g.location = "neva"  # seaport
    g.in_stronghold = False
    g.assets["provender"] = 0
    g.assets["loot"] = 0
    g.assets["ship"] = 1  # only 1 ship -> insufficient (needs 2)
    st.locales["neva"].siege_markers = 0
    st.meta.box = 8
    st.meta.phase = "campaign"
    st.meta.campaign_step = "command"
    st.campaign_turn.active_lord = "gavrilo"
    st.campaign_turn.active_card = "gavrilo"
    st.campaign_turn.actions_remaining = 5
    with pytest.raises(IllegalAction) as exc:
        apply_action(st, {"type": "cmd_sail", "side": "russian",
                          "args": {"lord_id": "gavrilo", "destination": "luga",
                                   "group": ["gavrilo"]}})
    assert exc.value.code == "insufficient_ships"


def test_sail_provender_one_ship_each():
    """Each Provender on board needs 1 Ship."""
    st = load_scenario("pleskau", seed=1)
    h = st.lords["hermann"]
    h.forces = {}  # no horse units
    _setup_sail(st, "hermann")
    h.assets["provender"] = 3
    h.assets["ship"] = 2  # need 3, have 2
    with pytest.raises(IllegalAction) as exc:
        apply_action(st, {"type": "cmd_sail", "side": "teutonic",
                          "args": {"lord_id": "hermann", "destination": "narwia",
                                   "group": ["hermann"]}})
    assert exc.value.code == "insufficient_ships"


def test_sail_loot_two_ships_each():
    """Each Loot on board needs 2 Ships."""
    st = load_scenario("pleskau", seed=1)
    h = st.lords["hermann"]
    h.forces = {}
    _setup_sail(st, "hermann")
    h.assets["loot"] = 2
    h.assets["ship"] = 3  # need 4 (2*2), have 3
    with pytest.raises(IllegalAction) as exc:
        apply_action(st, {"type": "cmd_sail", "side": "teutonic",
                          "args": {"lord_id": "hermann", "destination": "narwia",
                                   "group": ["hermann"]}})
    assert exc.value.code == "insufficient_ships"


def test_sail_ships_pool_across_group():
    """Ships across the group pool together for the Sail capacity check."""
    st = load_scenario("pleskau", seed=1)
    h = st.lords["hermann"]
    k = st.lords["knud_and_abel"]
    h.forces = {"knights": 2}
    k.forces = {"sergeants": 2}
    _setup_sail(st, "hermann")
    k.location = h.location
    k.in_stronghold = False
    k.assets["provender"] = 0
    k.assets["loot"] = 0
    # Hermann is secondary Marshal but Andreas is removed in pleskau -> active marshal
    h.has_lower_lord = None; h.lieutenant_of = None
    k.has_lower_lord = None; k.lieutenant_of = None
    # Need 4 ships (2 + 2) total. Split: h has 2, k has 2 -> pool = 4. OK.
    h.assets["ship"] = 2
    k.assets["ship"] = 2
    res = apply_action(st, {"type": "cmd_sail", "side": "teutonic",
                           "args": {"lord_id": "hermann", "destination": "narwia",
                                    "group": ["hermann", "knud_and_abel"]}})
    assert res["to"] == "narwia"
