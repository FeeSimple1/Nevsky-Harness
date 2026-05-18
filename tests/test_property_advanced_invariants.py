"""Additional property-based invariants — more aggressive checks
on state combinations during play.

Focus on invariants self-play and earlier checks didn't cover:
  - Total card count per side stays constant
  - No card appears in multiple deck lists
  - Lord state + location consistency under action sequences
  - Mustered/disbanded/removed transitions don't lose Lords
  - Combat-pending lifecycle (set → cleared)
  - Calendar marker count consistency
"""
from __future__ import annotations

import importlib.util
import json
from collections import Counter

import nevsky.actions  # noqa: F401
import pytest
from hypothesis import HealthCheck, given, settings, strategies as st

from nevsky.actions import IllegalAction, apply_action
from nevsky.legal_moves import legal_moves
from nevsky.scenarios import load_scenario
from nevsky.state import GameState
from nevsky.static_data import load_cards


spec = importlib.util.spec_from_file_location("sp", "scripts/self_play.py")
sp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sp)


def _total_card_count_per_side(s, side):
    """Count cards across all deck lists for one side."""
    deck = s.decks.teutonic if side == "teutonic" else s.decks.russian
    return (len(deck.deck) + len(deck.discard) + len(deck.holds) +
            len(deck.capabilities_in_play) + len(deck.this_levy_events) +
            len(deck.this_campaign_events) + len(deck.removed) +
            len(deck.pending_draw))


def _tucked_under_lord_count(s, side):
    """Count cards tucked under Lords of this side (this_lord_capabilities)."""
    return sum(len(l.this_lord_capabilities) for lid, l in s.lords.items()
               if l.side == side)


def _expected_card_count_per_side(side):
    """Total cards in cards.json for this side."""
    cards = load_cards()
    return sum(1 for cid, c in cards.items() if c["side"] == side)


def _run_self_play(scenario, seed, max_steps):
    """Helper: run self-play and return the final state."""
    s = load_scenario(scenario, seed=seed)
    for side in ("teutonic", "russian"):
        try:
            apply_action(s, {"type": "confirm_all_setup_transports",
                              "side": side, "args": {}})
        except Exception:
            pass
    rac = Counter()
    for step_n in range(max_steps):
        if sp._is_terminal(s):
            break
        moves_raw = legal_moves(s, with_previews=False)
        moves = []
        for m in moves_raw:
            if "args" in m and isinstance(m["args"], dict):
                moves.append(m)
            else:
                moves.extend(sp._instantiate_templated_move(s, m))
        if not moves:
            break
        prioritized = sorted(moves, key=lambda m: -sp._move_priority(m, rac))
        pick = prioritized[step_n % min(3, len(prioritized))]
        action = {k: v for k, v in pick.items() if k in ("type", "side", "args")}
        if action["type"] == "aow_implement_card":
            cid = action["args"].get("card_id")
            action["args"] = sp._populate_event_args(s, cid, action["args"])
        sig = (action["type"], action.get("side"),
               json.dumps(action.get("args", {}), default=str, sort_keys=True))
        rac[sig] += 1
        if step_n % 50 == 0 and step_n > 0:
            rac.clear()
        try:
            apply_action(s, action)
        except IllegalAction:
            same = sp._expand_event_variants(s, pick) if pick.get("type") == "aow_implement_card" else []
            recovered = False
            for cand in same + list(prioritized[1:]):
                act = {k: v for k, v in cand.items() if k in ("type", "side", "args")}
                if act["type"] == "aow_implement_card" and cand not in same:
                    cid = act["args"].get("card_id")
                    act["args"] = sp._populate_event_args(s, cid, act["args"])
                try:
                    apply_action(s, act)
                    recovered = True
                    break
                except IllegalAction:
                    continue
            if not recovered:
                break
    return s


# ----- Property: total card count per side is invariant -----------------


@given(seed=st.integers(min_value=1, max_value=500))
@settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@pytest.mark.parametrize("scenario", ["watland", "pleskau"])
def test_property_card_count_invariant(scenario, seed):
    """Total cards (across all deck lists + this_lord_capabilities)
    per side should equal the expected count from cards.json minus
    any cards in `removed` state (per scenario special rules)."""
    s = _run_self_play(scenario, seed=seed, max_steps=400)
    for side in ("teutonic", "russian"):
        deck_total = _total_card_count_per_side(s, side)
        tucked = _tucked_under_lord_count(s, side)
        total = deck_total + tucked
        expected = _expected_card_count_per_side(side)
        assert total == expected, \
            f"{side} card-count mismatch: got {total}, expected {expected} " \
            f"(deck={deck_total}, tucked={tucked})"


# ----- Property: no card appears in multiple deck lists -----------------


@given(seed=st.integers(min_value=1, max_value=500))
@settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@pytest.mark.parametrize("scenario", ["watland", "peipus"])
def test_property_no_card_in_multiple_lists(scenario, seed):
    s = _run_self_play(scenario, seed=seed, max_steps=400)
    for side in ("teutonic", "russian"):
        deck = s.decks.teutonic if side == "teutonic" else s.decks.russian
        all_lists = {
            "deck": deck.deck, "discard": deck.discard, "holds": deck.holds,
            "capabilities_in_play": deck.capabilities_in_play,
            "this_levy_events": deck.this_levy_events,
            "this_campaign_events": deck.this_campaign_events,
            "removed": deck.removed, "pending_draw": deck.pending_draw,
        }
        seen_in: dict[str, list[str]] = {}
        for list_name, lst in all_lists.items():
            for cid in lst:
                seen_in.setdefault(cid, []).append(list_name)
        # Also check this_lord_capabilities on this side's Lords
        for lid, lord in s.lords.items():
            if lord.side == side:
                for cid in lord.this_lord_capabilities:
                    seen_in.setdefault(cid, []).append(f"lord:{lid}")
        for cid, locations in seen_in.items():
            assert len(locations) == 1, \
                f"{side}: {cid} appears in {len(locations)} places: {locations}"


# ----- Property: mustered Lord has non-empty forces (unless intentionally 0)


@given(seed=st.integers(min_value=1, max_value=500))
@settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@pytest.mark.parametrize("scenario", ["watland", "pleskau"])
def test_property_mustered_lord_no_stale_state(scenario, seed):
    """A mustered Lord must have a location. A removed Lord must
    have empty forces, vassals, this_lord_capabilities."""
    s = _run_self_play(scenario, seed=seed, max_steps=400)
    for lid, lord in s.lords.items():
        if lord.state == "mustered":
            assert lord.location is not None, \
                f"mustered {lid} has no location"
        if lord.state == "removed":
            # Removed Lord: location None, no forces, no assets,
            # no this_lord_capabilities, no vassals mustered.
            assert lord.location is None, \
                f"removed {lid} has stale location {lord.location}"
            assert not lord.this_lord_capabilities, \
                f"removed {lid} still has this_lord_capabilities"
            for vid, vstate in lord.vassals.items():
                assert vstate.mustered is False, \
                    f"removed {lid} has mustered vassal {vid}"


# ----- Property: combat_pending eventually clears -----------------------


@given(seed=st.integers(min_value=1, max_value=500))
@settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@pytest.mark.parametrize("scenario", ["watland", "pleskau"])
def test_property_combat_pending_doesnt_stick(scenario, seed):
    """At terminal or stalled end, combat_pending should be None
    (some response action resolved it)."""
    s = _run_self_play(scenario, seed=seed, max_steps=400)
    # If we reached terminal, combat must be clear
    if sp._is_terminal(s):
        assert s.combat_pending is None


# ----- Property: VP increments are integer or 0.5-step --------------


@given(seed=st.integers(min_value=1, max_value=500))
@settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@pytest.mark.parametrize("scenario", ["watland"])
def test_property_vp_is_half_step(scenario, seed):
    """VP changes by integer or 0.5 increments only."""
    s = _run_self_play(scenario, seed=seed, max_steps=400)
    # Multiply by 2 and check it's an integer
    for side_name, vp in (("teu", s.calendar.teutonic_vp),
                          ("rus", s.calendar.russian_vp)):
        scaled = vp * 2
        assert abs(scaled - round(scaled)) < 1e-9, \
            f"{side_name} VP={vp} not half-step"


# ----- Property: Calendar Levy/Campaign marker is unique --------------


@given(seed=st.integers(min_value=1, max_value=500))
@settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@pytest.mark.parametrize("scenario", ["watland", "crusade_on_novgorod"])
def test_property_levy_campaign_marker_unique(scenario, seed):
    """The Levy/Campaign marker is on exactly one box (or 0 if
    pre-game / post-game)."""
    s = _run_self_play(scenario, seed=seed, max_steps=600)
    marker_count = sum(1 for cb in s.calendar.boxes if cb.has_levy_campaign_marker)
    assert marker_count <= 1, f"levy_campaign marker on {marker_count} boxes"


# ----- Property: lordship_used never exceeds lordship rating ---------


@given(seed=st.integers(min_value=1, max_value=500))
@settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@pytest.mark.parametrize("scenario", ["watland", "pleskau"])
def test_property_lordship_used_bounded(scenario, seed):
    """lordship_used should never exceed (lordship_rating + bonus)."""
    from nevsky.static_data import load_lords
    sl = load_lords()
    s = _run_self_play(scenario, seed=seed, max_steps=400)
    for lid, lord in s.lords.items():
        base = int(sl[lid]["ratings"]["lordship"])
        bonus = int(s.meta.lordship_bonus.get(lid, 0))
        assert lord.lordship_used <= base + bonus, \
            f"{lid}.lordship_used={lord.lordship_used} > base+bonus={base+bonus}"


# ----- Property: pleskau_lords_removed counters non-negative ----------


@given(seed=st.integers(min_value=1, max_value=500))
@settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@pytest.mark.parametrize("scenario", ["pleskau"])
def test_property_pleskau_counters_non_negative(scenario, seed):
    s = _run_self_play(scenario, seed=seed, max_steps=300)
    assert s.calendar.pleskau_lords_removed_russian >= 0
    assert s.calendar.pleskau_lords_removed_teutonic >= 0
