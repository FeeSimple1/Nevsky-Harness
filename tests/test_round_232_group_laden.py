"""4.3.2 SHARED TRANSPORT: Lords moving as a group Share Transport.
'Count all Provender and usable Transport of Lords moving together to
determine Laden status.' Previously the harness used per-Lord Laden
(any member Laden -> whole group Laden) and summed per-member excess,
which over-charged March cost / over-forced discards for groups.
"""
from __future__ import annotations

import nevsky.actions  # noqa: F401
from nevsky.campaign import (
    _group_excess_provender,
    _group_is_laden,
    _is_laden,
)
from nevsky.scenarios import load_scenario


def _two_lords(prov_a, cart_b):
    s = load_scenario("crusade_on_novgorod", seed=1)
    s.meta.box = 1  # Summer -> Carts usable on Trackways
    a = next(lid for lid, l in s.lords.items() if l.side == "teutonic")
    b = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and lid != a)
    s.lords[a].assets = {"provender": prov_a}
    s.lords[b].assets = {"cart": cart_b}
    return s, a, b


def test_group_pools_transport_for_laden():
    # A alone: 3 Provender, 0 Transport -> Laden. B: 3 Carts, 0 Provender.
    s, a, b = _two_lords(prov_a=3, cart_b=3)
    assert _is_laden(s, a, way_type="trackway") is True          # alone, Laden
    # Group: combined 3 Provender vs 3 usable Carts -> NOT Laden.
    assert _group_is_laden(s, [a, b], way_type="trackway") is False


def test_group_pools_transport_for_excess():
    # A alone: 5 Provender, 0 Transport -> excess (5 > 2*0). Group with
    # 3 Carts: combined 5 Provender vs 2*3=6 -> no excess.
    s, a, b = _two_lords(prov_a=5, cart_b=3)
    assert _group_excess_provender(s, [a, b], way_type="trackway") == 0


def test_group_still_laden_when_combined_exceeds():
    # 5 Provender vs 2 Carts combined -> Laden (5 > 2) and excess (5 > 4 = 1).
    s, a, b = _two_lords(prov_a=5, cart_b=2)
    assert _group_is_laden(s, [a, b], way_type="trackway") is True
    assert _group_excess_provender(s, [a, b], way_type="trackway") == 1
