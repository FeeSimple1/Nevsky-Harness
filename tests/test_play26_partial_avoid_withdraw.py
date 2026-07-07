"""PLAY-26 (4.3.4): partial per-Lord Avoid Battle / Withdraw.

4.3.4: "some or all Inactive Lords may move to one or more adjacent
Locales" (Avoid), and the side "may Withdraw some or all Lords into its
Stronghold there, a number of Lords up to Siege Capacity"; any Lords who
do neither fight the Battle. avoid_battle / withdraw take an optional
`lords` subset and stay non-terminal while outside defenders remain.
"""

from __future__ import annotations

import pytest

from nevsky.actions import IllegalAction, apply_action
from nevsky.legal_moves import legal_moves
from nevsky.scenarios import load_scenario
from nevsky.state import CombatPending


def _combat_two_defenders(to_loc="pskov", from_loc="izborsk",
                          way_type="trackway",
                          d1="domash", d2="gavrilo", attacker="hermann"):
    s = load_scenario("pleskau", seed=1)
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.active_player = "russian"  # defender responds
    s.lords[attacker].state = "mustered"
    s.lords[attacker].location = to_loc
    for d in (d1, d2):
        s.lords[d].state = "mustered"
        s.lords[d].location = to_loc
        s.lords[d].in_stronghold = False
        s.lords[d].assets = {}
    s.combat_pending = CombatPending(
        attacker_side="teutonic", attacker_group=[attacker],
        from_locale=from_loc, to_locale=to_loc, way_type=way_type,
        defender_side="russian", defender_lords=[d1, d2],
        pending_response_by="russian", laden=False,
    )
    return s


def _avoid_opts(s, lords=None):
    out = []
    for m in legal_moves(s, with_previews=False):
        if m["type"] != "avoid_battle" or m.get("side") != "russian":
            continue
        if lords is None or m["args"].get("lords") == lords:
            out.append(m)
    return out


def test_partial_avoid_keeps_window_open_and_reduces_defenders():
    s = _combat_two_defenders()
    opt = next(o for o in _avoid_opts(s, lords=["domash"]))
    res = apply_action(s, opt)
    assert res.get("awaiting_response") is True
    # combat is still pending; only domash left.
    assert s.combat_pending is not None
    assert s.combat_pending.defender_lords == ["gavrilo"]
    assert s.lords["domash"].location != "pskov"
    assert s.lords["domash"].moved_fought is True
    # response is still owed by the defender.
    assert s.combat_pending.pending_response_by == "russian"
    assert s.meta.active_player == "russian"
    # stand_battle is still offered for the remaining defender.
    types = {m["type"] for m in legal_moves(s, with_previews=False)
             if m.get("side") == "russian"}
    assert "stand_battle" in types


def test_all_avoid_via_bare_to_is_still_terminal():
    """Backward-compat: avoid_battle{to} (no lords) moves ALL defenders
    and resolves the Approach (no battle, combat cleared)."""
    s = _combat_two_defenders()
    opt = next(o for o in _avoid_opts(s) if "lords" not in o["args"])
    res = apply_action(s, opt)
    assert res.get("awaiting_response") is None
    assert s.combat_pending is None
    dest = opt["args"]["to"]
    assert s.lords["domash"].location == dest
    assert s.lords["gavrilo"].location == dest


def test_capacity1_fort_split_one_withdraws_one_avoids():
    """Canonical case: 2 Lords at a Capacity-1 Fort (izborsk) can split
    1-in / 1-avoid, which all-or-nothing Withdraw made impossible."""
    s = _combat_two_defenders(to_loc="izborsk", from_loc="pskov")
    # Withdraw only domash into the Fort.
    res = apply_action(s, {"type": "withdraw", "side": "russian",
                           "args": {"lords": ["domash"]}})
    assert res.get("awaiting_response") is True
    assert s.lords["domash"].in_stronghold is True
    assert s.combat_pending.withdrawn_lords == ["domash"]
    assert s.combat_pending.defender_lords == ["gavrilo"]
    assert s.locales["izborsk"].siege_markers >= 1
    # A second Withdraw would exceed Capacity 1 (cumulative).
    with pytest.raises(IllegalAction) as exc:
        apply_action(s, {"type": "withdraw", "side": "russian",
                         "args": {"lords": ["gavrilo"]}})
    assert exc.value.code == "over_capacity"
    # gavrilo (the sole remaining defender) Avoids -> Approach resolved,
    # no battle. With one defender left the bare avoid_battle{to} form
    # moves him.
    opt = next(o for o in _avoid_opts(s) if "lords" not in o["args"])
    apply_action(s, opt)
    assert s.combat_pending is None
    assert s.lords["gavrilo"].location == opt["args"]["to"]
    assert s.lords["domash"].in_stronghold is True


def test_enumerator_offers_per_lord_avoid_and_withdraw():
    s = _combat_two_defenders()
    ms = [m for m in legal_moves(s, with_previews=False)
          if m.get("side") == "russian"]
    per_lord_avoid = [m for m in ms if m["type"] == "avoid_battle"
                      and m["args"].get("lords") == ["domash"]]
    per_lord_wd = [m for m in ms if m["type"] == "withdraw"
                   and m["args"].get("lords") == ["domash"]]
    assert per_lord_avoid, "expected a per-Lord Avoid option"
    assert per_lord_wd, "expected a per-Lord Withdraw option"


def test_partial_withdraw_bad_lord_rejected():
    s = _combat_two_defenders()
    with pytest.raises(IllegalAction) as exc:
        apply_action(s, {"type": "withdraw", "side": "russian",
                         "args": {"lords": ["aleksandr"]}})  # not a defender
    assert exc.value.code == "bad_lords"
