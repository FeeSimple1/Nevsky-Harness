"""PLAY-31 (4.8.1): two-pass surplus-only Feed sharing + choices.

4.8.1 SHARING: "First, all Lords must Feed their own Forces, using
Provender and Loot from their own mats. Then, a Lord must expend
Provender and Loot to Feed the Forces of his side's other Lords in the
same Locale who have expended all of their Provender and Loot ..."

The old single pass let an earlier-iterated Lord raid a co-located Lord's
NON-surplus Provender, sending the WRONG Lord Unfed.
"""

from __future__ import annotations

import pytest

from nevsky.actions import IllegalAction, apply_action
from nevsky.scenarios import load_scenario


def _fpd_ready(s, side="teutonic"):
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.active_player = side
    s.campaign_turn.in_feed_pay_disband = True
    s.campaign_turn.fpd_completed_t = False
    s.campaign_turn.fpd_completed_r = False
    s.campaign_turn.fpd_pay_window_side = None


def _big(s, lid, loc, assets):
    """Make lid a 7-unit (cost-2) Moved/Fought Lord at loc with `assets`."""
    s.lords[lid].state = "mustered"
    s.lords[lid].location = loc
    s.lords[lid].in_stronghold = False
    s.lords[lid].moved_fought = True
    s.lords[lid].forces = {"serfs": 7}
    s.lords[lid].assets = dict(assets)


def _feed(res, lid):
    return next(f for f in res["feed"] if f["lord_id"] == lid)


def test_self_feed_before_sharing_no_wrong_lord_unfed():
    s = load_scenario("watland", seed=1)
    # A (andreas, earlier in dict order) has NO Assets; B (hermann) has
    # exactly his own need (2 Provender, no surplus). Co-located.
    _big(s, "andreas", "riga", {})
    _big(s, "hermann", "riga", {"provender": 2})
    # Make sure no OTHER teutonic Lord is co-located to donate.
    for lid, l in s.lords.items():
        if l.side == "teutonic" and lid not in ("andreas", "hermann"):
            l.moved_fought = False
            if l.location == "riga":
                l.location = None
    _fpd_ready(s)
    res = apply_action(s, {"type": "fpd_resolve", "side": "teutonic", "args": {}})
    # B fed himself first, keeps no surplus -> A (no Assets) is the Unfed one.
    assert _feed(res, "hermann")["unfed"] is False, "B must Feed himself first"
    assert _feed(res, "andreas")["unfed"] is True, "A (no Assets) is the Unfed Lord"


def test_surplus_is_shared_to_cover_shortfall():
    s = load_scenario("watland", seed=1)
    # A has 0; B has 3 Provender (needs 2 -> 1 surplus). B's surplus feeds A.
    _big(s, "andreas", "riga", {})
    _big(s, "hermann", "riga", {"provender": 3})
    for lid, l in s.lords.items():
        if l.side == "teutonic" and lid not in ("andreas", "hermann"):
            l.moved_fought = False
            if l.location == "riga":
                l.location = None
    # A needs only 1 (<=6 units) so B's single surplus fully feeds A.
    s.lords["andreas"].forces = {"serfs": 3}
    _fpd_ready(s)
    res = apply_action(s, {"type": "fpd_resolve", "side": "teutonic", "args": {}})
    assert _feed(res, "hermann")["unfed"] is False
    assert _feed(res, "andreas")["unfed"] is False  # covered by B's surplus
    assert _feed(res, "andreas")["consumed"]["provender"] == 1


def test_feed_loot_first_choice():
    s = load_scenario("watland", seed=1)
    _big(s, "andreas", "riga", {"provender": 2, "loot": 2})
    for lid, l in s.lords.items():
        if l.side == "teutonic" and lid != "andreas":
            l.moved_fought = False
    _fpd_ready(s)
    # Default: Provender spent first.
    import copy
    s_def = s.model_copy(deep=True)
    res_def = apply_action(s_def, {"type": "fpd_resolve", "side": "teutonic", "args": {}})
    assert _feed(res_def, "andreas")["consumed"]["provender"] == 2
    # feed_loot_first: Loot spent first.
    res_loot = apply_action(s, {"type": "fpd_resolve", "side": "teutonic",
                                "args": {"feed_loot_first": True}})
    assert _feed(res_loot, "andreas")["consumed"]["loot"] == 2


def test_hillforts_skip_choice_and_validation():
    s = load_scenario("watland", seed=1)
    s.decks.teutonic.capabilities_in_play = ["T8"]
    # Two eligible Livonia Lords.
    _big(s, "andreas", "riga", {})
    _big(s, "hermann", "riga", {})
    from nevsky.campaign import _hillforts_eligible_lords
    for lid, l in s.lords.items():
        if l.side == "teutonic" and lid not in ("andreas", "hermann"):
            l.moved_fought = False
    _fpd_ready(s)
    elig = _hillforts_eligible_lords(s, "teutonic")
    assert set(elig) >= {"andreas", "hermann"}
    # Choose hermann to skip (not the alphabetical-first default 'andreas').
    res = apply_action(s, {"type": "fpd_resolve", "side": "teutonic",
                           "args": {"hillforts_skip": "hermann"}})
    skipped = [f["lord_id"] for f in res["feed"] if f.get("hillforts_skipped")]
    assert skipped == ["hermann"]


def test_hillforts_skip_invalid_rejected():
    s = load_scenario("watland", seed=1)
    s.decks.teutonic.capabilities_in_play = ["T8"]
    _big(s, "andreas", "riga", {})
    _fpd_ready(s)
    with pytest.raises(IllegalAction) as exc:
        apply_action(s, {"type": "fpd_resolve", "side": "teutonic",
                         "args": {"hillforts_skip": "rudolf"}})  # not eligible
    assert exc.value.code == "bad_hillforts_skip"
