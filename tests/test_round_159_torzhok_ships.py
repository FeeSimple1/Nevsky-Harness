"""SMOKE-108 (Round 159): T2 Torzhok default `asset_order` excluded
"ship", so a Domash mat with only Ships had ZERO Assets removed under
default invocation despite the rule "remove 3 Assets".

Per AoW Reference T2 card text: "Remove 3 Assets from Domash OR 3
Coin from Veche". "Assets" includes Coin/Loot/Provender and all
Transport types (Boat/Cart/Sled/Ship). The harness's default order
list was `["coin", "loot", "provender", "boat", "cart", "sled"]` —
silently missing Ships even though Domash is ships_authorized.

Fix appends "ship" as the last priority. Custom asset_order still
respected; agents that want Ships removed first can specify their
own order.
"""
from __future__ import annotations

import inspect

import nevsky.actions  # noqa: F401
import nevsky.events as events
from nevsky.events import resolve_immediate_event
from nevsky.scenarios import load_scenario


def test_smoke_108_marker_present():
    src = inspect.getsource(events._ev_torzhok)
    assert "SMOKE-108" in src


def test_smoke_108_default_order_includes_ship():
    src = inspect.getsource(events._ev_torzhok)
    # Find the default order line.
    idx = src.find('asset_order",')
    assert idx > 0
    nearby = src[idx:idx + 200]
    assert '"ship"' in nearby


def test_smoke_108_removes_ships_under_default_when_only_ships_available():
    s = load_scenario("watland", seed=1)
    # Ensure Domash exists
    if "domash" not in s.lords:
        return  # skip if scenario doesn't have Domash
    d = s.lords["domash"]
    # Clear all assets, set only ships.
    d.assets = {"ship": 3}
    res = resolve_immediate_event(s, "T2", {"target": "domash"})
    assert d.assets.get("ship", 0) == 0
    assert res["removed"].get("ship", 0) == 3


def test_smoke_108_default_order_preserves_coin_first_priority():
    s = load_scenario("watland", seed=1)
    if "domash" not in s.lords:
        return
    d = s.lords["domash"]
    d.assets = {"coin": 2, "ship": 2}
    res = resolve_immediate_event(s, "T2", {"target": "domash"})
    # Coin first (2), then sled/cart/boat/etc skipped, then ship (1).
    # Total removed = 3.
    total_removed = sum(res["removed"].values())
    assert total_removed == 3
    assert res["removed"].get("coin", 0) == 2
    assert res["removed"].get("ship", 0) == 1


def test_smoke_108_custom_order_still_respected():
    """If agent passes asset_order with ship FIRST, ships are removed first."""
    s = load_scenario("watland", seed=1)
    if "domash" not in s.lords:
        return
    d = s.lords["domash"]
    d.assets = {"coin": 3, "ship": 3}
    res = resolve_immediate_event(s, "T2", {
        "target": "domash",
        "asset_order": ["ship", "coin"],
    })
    # Ships first: 3 ships removed.
    assert res["removed"].get("ship", 0) == 3
    assert res["removed"].get("coin", 0) == 0
    assert d.assets.get("coin", 0) == 3
    assert d.assets.get("ship", 0) == 0
