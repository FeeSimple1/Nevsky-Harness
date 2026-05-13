"""Round 67 — SMOKE-059 regression tests.

Per AoW Reference T11 Crusade Tip: "Teutons may Levy the Crusade
Capability card in any Season, but Crusader Forces still would
Muster only in Summer." The harness gated Summer Crusader Vassal
Muster on T11 in capabilities_in_play but didn't enforce the
Summer-season requirement.
"""

import pytest

import nevsky.actions  # noqa
from nevsky.scenarios import load_scenario
from nevsky.actions import apply_action, IllegalAction


def _setup_summer_crusaders(season_box):
    st = load_scenario("watland", seed=1)
    st.meta.box = season_box
    st.decks.teutonic.capabilities_in_play.append("T11")
    andreas = st.lords["andreas"]
    from nevsky.static_data import load_lords
    sl = load_lords()["andreas"]
    sc_vassal = next(v["vassal_id"] for v in sl.get("vassals", [])
                     if v.get("special") == "summer_crusaders")
    andreas.vassals[sc_vassal].ready = True
    andreas.vassals[sc_vassal].mustered = False
    st.meta.phase = "levy"
    st.meta.levy_step = "muster"
    st.meta.active_player = "teutonic"
    for L in st.lords.values():
        L.just_arrived_this_levy = False
    return st, sc_vassal


def test_summer_crusaders_in_early_winter_rejected():
    st, vid = _setup_summer_crusaders(season_box=4)  # early_winter
    with pytest.raises(IllegalAction) as exc:
        apply_action(st, {"type": "muster_vassal", "side": "teutonic",
                          "args": {"by_lord": "andreas", "vassal_id": vid}})
    assert exc.value.code == "vassal_season"


def test_summer_crusaders_in_late_winter_rejected():
    st, vid = _setup_summer_crusaders(season_box=6)  # late_winter
    with pytest.raises(IllegalAction) as exc:
        apply_action(st, {"type": "muster_vassal", "side": "teutonic",
                          "args": {"by_lord": "andreas", "vassal_id": vid}})
    assert exc.value.code == "vassal_season"


def test_summer_crusaders_in_rasputitsa_rejected():
    st, vid = _setup_summer_crusaders(season_box=7)  # rasputitsa
    with pytest.raises(IllegalAction) as exc:
        apply_action(st, {"type": "muster_vassal", "side": "teutonic",
                          "args": {"by_lord": "andreas", "vassal_id": vid}})
    assert exc.value.code == "vassal_season"


def test_summer_crusaders_in_summer_accepted():
    """Box 1-2 or 9-10 is Summer (per scenarios convention)."""
    st, vid = _setup_summer_crusaders(season_box=1)  # summer
    # In watland, andreas might already be Mustered in summer; verify the
    # harness path accepts.
    from nevsky.actions import _season_of_box
    assert _season_of_box(st.meta.box) == "summer"
    res = apply_action(st, {"type": "muster_vassal", "side": "teutonic",
                           "args": {"by_lord": "andreas", "vassal_id": vid}})
    assert res["by_lord"] == "andreas"


def test_summer_crusaders_without_t11_still_rejected():
    """Sanity: T11-not-in-play still produces vassal_gated."""
    st, vid = _setup_summer_crusaders(season_box=1)  # summer
    # Remove T11
    st.decks.teutonic.capabilities_in_play.remove("T11")
    with pytest.raises(IllegalAction) as exc:
        apply_action(st, {"type": "muster_vassal", "side": "teutonic",
                          "args": {"by_lord": "andreas", "vassal_id": vid}})
    assert exc.value.code == "vassal_gated"
