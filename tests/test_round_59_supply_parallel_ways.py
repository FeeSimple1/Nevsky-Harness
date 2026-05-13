"""Round 59 — SMOKE-047 regression tests.

Supply route validation must accept a transport type whenever ANY of
the parallel Way types between two locales matches its transport-
Way constraint. Previously the harness's way_index stored just one
type per locale pair, with later-loaded ways silently overwriting
earlier ones — so a Supply via Cart along a trackway dorpat→odenpah
failed because the waterway entry overwrote the trackway.
"""

import nevsky.actions  # noqa
from nevsky.scenarios import load_scenario
from nevsky.actions import apply_action


def _setup_supply(st, lord_id, location):
    L = st.lords[lord_id]
    L.state = "mustered"
    L.location = location
    L.in_stronghold = False
    L.assets = {"provender": 0, "cart": 5, "ship": 0, "boat": 0, "sled": 0}
    st.meta.box = 1  # Summer
    st.meta.phase = "campaign"
    st.meta.campaign_step = "command"
    st.campaign_turn.active_lord = lord_id
    st.campaign_turn.active_card = lord_id
    st.campaign_turn.actions_remaining = 5


def test_supply_cart_on_parallel_trackway_waterway_pair():
    """dorpat-odenpah has both trackway and waterway; cart should still
    work via the trackway."""
    st = load_scenario("watland", seed=1)
    _setup_supply(st, "hermann", "odenpah")
    res = apply_action(st, {"type": "cmd_supply", "side": "teutonic",
                           "args": {"lord_id": "hermann",
                                    "sources": [{"locale_id": "dorpat",
                                                 "route": ["dorpat", "odenpah"],
                                                 "transport": "cart"}]}})
    assert res["added"] == 1


def test_supply_boat_on_parallel_trackway_waterway_pair():
    """Same pair: boat should work via the waterway."""
    st = load_scenario("watland", seed=1)
    _setup_supply(st, "hermann", "odenpah")
    st.lords["hermann"].assets["boat"] = 5
    res = apply_action(st, {"type": "cmd_supply", "side": "teutonic",
                           "args": {"lord_id": "hermann",
                                    "sources": [{"locale_id": "dorpat",
                                                 "route": ["dorpat", "odenpah"],
                                                 "transport": "boat"}]}})
    assert res["added"] == 1
