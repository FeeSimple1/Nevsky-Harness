"""PLAY-36 regression tests: Avoid Provender cap counts SHARED Transport.

Rule 4.3.4 AVOID BATTLE: Lords "may take no Loot and take only
Provender equal to their OWN OR SHARED Transport that is usable on the
Way across which they are moving."

Before PLAY-36 each Avoiding Lord was capped at his OWN usable
Transport, so a co-Avoiding ally's spare Carts could not carry his
Provender and it was discarded to the attacker as Spoils. Now the Lords
Avoiding together in one call pool their usable Transport (1.5.2
Sharing): own Transport covers own Provender first, spare group
capacity covers co-avoiders' excess (markers stay on their owners'
mats), and only Provender beyond the GROUP total is discarded.
`args.avoid_keep_order` sets who benefits from spare capacity first.
"""
from __future__ import annotations

import nevsky.actions  # noqa: F401
from nevsky.actions import apply_action
from nevsky.scenarios import load_scenario
from nevsky.state import CombatPending


def _avoid_setup(s, defenders, attacker="heinrich"):
    s.lords[attacker].state = "mustered"
    s.lords[attacker].location = "izborsk"
    s.lords[attacker].forces = {"knights": 2}
    s.lords[attacker].assets = {}
    for lid in defenders:
        s.lords[lid].state = "mustered"
        s.lords[lid].location = "pskov"
        s.lords[lid].forces = {"militia": 2}
    s.combat_pending = CombatPending(
        attacker_side="teutonic", attacker_group=[attacker],
        from_locale="izborsk", to_locale="pskov", way_type="trackway",
        defender_side="russian", defender_lords=list(defenders),
        pending_response_by="russian", laden=False,
    )
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.campaign_turn.active_card = attacker
    s.campaign_turn.active_lord = attacker
    s.campaign_turn.actions_remaining = 2
    s.meta.active_player = "russian"


def test_ally_spare_carts_carry_provender():
    """gavrilo (3 provender, 1 cart) avoids WITH domash (0 provender,
    2 carts): group capacity 3 covers all -- nothing discarded. The old
    own-only cap discarded 2 to the attacker."""
    s = load_scenario("crusade_on_novgorod", seed=42)
    _avoid_setup(s, ["gavrilo", "domash"])
    s.lords["gavrilo"].assets = {"provender": 3, "cart": 1}
    s.lords["domash"].assets = {"cart": 2}
    r = apply_action(s, {"type": "avoid_battle", "side": "russian",
                         "args": {"to": "dubrovno"}})
    assert s.lords["gavrilo"].assets.get("provender", 0) == 3
    assert r["spoils_to_attacker"]["provender"] == 0
    assert all(d["excess_provender"] == 0 for d in r["discards_per_lord"])


def test_group_total_still_caps():
    """4 provender vs group capacity 3: exactly 1 discarded."""
    s = load_scenario("crusade_on_novgorod", seed=42)
    _avoid_setup(s, ["gavrilo", "domash"])
    s.lords["gavrilo"].assets = {"provender": 4, "cart": 1}
    s.lords["domash"].assets = {"cart": 2}
    s.lords["heinrich"].assets = {}
    r = apply_action(s, {"type": "avoid_battle", "side": "russian",
                         "args": {"to": "dubrovno"}})
    assert s.lords["gavrilo"].assets.get("provender", 0) == 3
    assert s.lords["heinrich"].assets.get("provender", 0) == 1  # spoils


def test_avoid_keep_order_directs_spare_capacity():
    """Two Lords over their own capacity compete for 2 spare Carts:
    avoid_keep_order decides whose Provender survives."""
    s = load_scenario("crusade_on_novgorod", seed=42)
    _avoid_setup(s, ["gavrilo", "vladislav", "domash"])
    s.lords["gavrilo"].assets = {"provender": 2}      # no own transport
    s.lords["vladislav"].assets = {"provender": 2}    # no own transport
    s.lords["domash"].assets = {"cart": 2}            # 2 spare
    r = apply_action(s, {"type": "avoid_battle", "side": "russian",
                         "args": {"to": "dubrovno",
                                  "avoid_keep_order": ["vladislav"]}})
    assert s.lords["vladislav"].assets.get("provender", 0) == 2
    assert s.lords["gavrilo"].assets.get("provender", 0) == 0
    assert r["spoils_to_attacker"]["provender"] == 2


def test_partial_avoid_shares_only_within_moving_subset():
    """PLAY-26 subset Avoid: a STAYING Lord's Carts do not carry the
    avoiders' Provender (his Transport is not moving with them)."""
    s = load_scenario("crusade_on_novgorod", seed=42)
    _avoid_setup(s, ["gavrilo", "domash"])
    s.lords["gavrilo"].assets = {"provender": 3}
    s.lords["domash"].assets = {"cart": 3}   # stays behind
    r = apply_action(s, {"type": "avoid_battle", "side": "russian",
                         "args": {"to": "dubrovno", "lords": ["gavrilo"]}})
    assert s.lords["gavrilo"].assets.get("provender", 0) == 0
    assert r["spoils_to_attacker"]["provender"] == 3


def test_own_transport_unchanged_single_avoider():
    """Single avoider: identical to pre-PLAY-36 behavior."""
    s = load_scenario("crusade_on_novgorod", seed=42)
    _avoid_setup(s, ["gavrilo"])
    s.lords["gavrilo"].assets = {"provender": 3, "cart": 1}
    r = apply_action(s, {"type": "avoid_battle", "side": "russian",
                         "args": {"to": "dubrovno"}})
    assert s.lords["gavrilo"].assets.get("provender", 0) == 1
    assert r["spoils_to_attacker"]["provender"] == 2
