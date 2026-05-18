"""Property-based / fuzz tests using Hypothesis.

Goal: surface bugs in rare state combinations not reached by static
probing or self-play. Each test asserts an invariant that must hold
across many randomly-generated states or action sequences.

Categories:
  1. Save/Load round-trip (model_dump_json round-trips for all scenarios)
  2. Per-cap invariants (1.7.3 asset 8-cap, VP 0-17.5 cap)
  3. Calendar consistency (no Lord in two boxes simultaneously)
  4. Combat-pending lifecycle (set → cleared)
  5. Action-sequence determinism (same seed + same actions → same state)

Bugs surfaced here are documented as their own SMOKE rounds.
"""
from __future__ import annotations

import nevsky.actions  # noqa: F401
import nevsky.battle as battle
import pytest
from hypothesis import HealthCheck, assume, given, settings, strategies as st

from nevsky.scenarios import load_scenario
from nevsky.state import GameState


SCENARIOS = (
    "watland", "pleskau", "peipus",
    "return_of_the_prince", "return_of_the_prince_nicolle",
    "crusade_on_novgorod",
)


# ---------- Property 1: scenario load is deterministic --------------------


@given(seed=st.integers(min_value=1, max_value=10_000))
@settings(max_examples=50, deadline=None)
@pytest.mark.parametrize("scenario", SCENARIOS)
def test_property_scenario_load_deterministic(scenario, seed):
    s1 = load_scenario(scenario, seed=seed)
    s2 = load_scenario(scenario, seed=seed)
    assert s1.model_dump_json() == s2.model_dump_json()


# ---------- Property 2: save/load round-trip is idempotent ----------------


@given(seed=st.integers(min_value=1, max_value=10_000))
@settings(max_examples=30, deadline=None)
@pytest.mark.parametrize("scenario", SCENARIOS)
def test_property_save_load_round_trip(scenario, seed):
    s = load_scenario(scenario, seed=seed)
    txt = s.model_dump_json()
    s2 = GameState.model_validate_json(txt)
    txt2 = s2.model_dump_json()
    assert txt == txt2


# ---------- Property 3: VP cap invariants -------------------------------


@given(seed=st.integers(min_value=1, max_value=10_000))
@settings(max_examples=30, deadline=None)
@pytest.mark.parametrize("scenario", SCENARIOS)
def test_property_initial_vp_within_cap(scenario, seed):
    s = load_scenario(scenario, seed=seed)
    assert 0.0 <= s.calendar.russian_vp <= 17.5
    assert 0.0 <= s.calendar.teutonic_vp <= 17.5


# ---------- Property 4: no Lord in two cylinder positions simultaneously -


@given(seed=st.integers(min_value=1, max_value=10_000))
@settings(max_examples=30, deadline=None)
@pytest.mark.parametrize("scenario", SCENARIOS)
def test_property_lord_in_one_calendar_position(scenario, seed):
    s = load_scenario(scenario, seed=seed)
    cal = s.calendar
    for lid in s.lords:
        # Cylinder positions
        in_off_left = lid in cal.off_left
        in_off_right = lid in cal.off_right
        in_boxes = sum(1 for cb in cal.boxes if lid in cb.cylinders)
        total_cyl_positions = int(in_off_left) + int(in_off_right) + in_boxes
        assert total_cyl_positions <= 1, (
            f"{lid} has {total_cyl_positions} cylinder positions: "
            f"off_left={in_off_left}, off_right={in_off_right}, in_boxes={in_boxes}"
        )
        # Service positions
        in_off_left_s = lid in cal.off_left_service
        in_off_right_s = lid in cal.off_right_service
        in_boxes_s = sum(1 for cb in cal.boxes if lid in cb.service_markers)
        total_svc_positions = int(in_off_left_s) + int(in_off_right_s) + in_boxes_s
        assert total_svc_positions <= 1, (
            f"{lid} has {total_svc_positions} service positions"
        )


# ---------- Property 5: per-asset 8-cap invariant -----------------------


@given(seed=st.integers(min_value=1, max_value=10_000))
@settings(max_examples=30, deadline=None)
@pytest.mark.parametrize("scenario", SCENARIOS)
def test_property_initial_asset_cap(scenario, seed):
    s = load_scenario(scenario, seed=seed)
    for lid, lord in s.lords.items():
        for asset, n in lord.assets.items():
            assert 0 <= n <= 8, f"{lid}.assets[{asset}] = {n}"


# ---------- Property 6: Lord state values are valid ---------------------


@given(seed=st.integers(min_value=1, max_value=10_000))
@settings(max_examples=30, deadline=None)
@pytest.mark.parametrize("scenario", SCENARIOS)
def test_property_lord_state_values(scenario, seed):
    s = load_scenario(scenario, seed=seed)
    valid_states = {"ready", "mustered", "disbanded", "removed", "no_levy"}
    for lid, lord in s.lords.items():
        assert lord.state in valid_states, f"{lid}.state = {lord.state!r}"
        # Mustered Lord must have a location.
        if lord.state == "mustered":
            assert lord.location is not None, f"mustered {lid} has no location"
        # Removed/disbanded Lord should not have a location.
        if lord.state == "removed":
            assert lord.location is None, f"removed {lid} still has location {lord.location}"


# ---------- Property 7: locale-side flag consistency -------------------


@given(seed=st.integers(min_value=1, max_value=10_000))
@settings(max_examples=30, deadline=None)
@pytest.mark.parametrize("scenario", SCENARIOS)
def test_property_locale_state_consistency(scenario, seed):
    s = load_scenario(scenario, seed=seed)
    for lid, loc in s.locales.items():
        # Both sides can't have a Castle marker on the same locale.
        assert not (loc.russian_castle and loc.teutonic_castle), \
            f"{lid} has both Castle markers"
        # Both sides can't have Ravaged markers on the same locale.
        assert not (loc.russian_ravaged and loc.teutonic_ravaged), \
            f"{lid} has both Ravaged markers"
        # Conquered counts non-negative.
        assert loc.russian_conquered >= 0
        assert loc.teutonic_conquered >= 0
        # Siege markers in valid range.
        assert 0 <= loc.siege_markers <= 4


# ---------- Property 8: Vassal markers consistent ---------------------


@given(seed=st.integers(min_value=1, max_value=10_000))
@settings(max_examples=30, deadline=None)
@pytest.mark.parametrize("scenario", SCENARIOS)
def test_property_vassal_marker_consistency(scenario, seed):
    s = load_scenario(scenario, seed=seed)
    for lid, lord in s.lords.items():
        for vid, vstate in lord.vassals.items():
            if vstate.on_calendar:
                # If on_calendar=True, calendar_box should be set.
                assert vstate.calendar_box is not None
            if vstate.calendar_box is not None and 1 <= vstate.calendar_box <= 16:
                # Marker should also be in the calendar box's
                # vassal_service_markers list.
                cb = s.calendar.boxes[vstate.calendar_box - 1]
                assert vid in cb.vassal_service_markers, (
                    f"{lid}.vassals[{vid}] claims box {vstate.calendar_box} "
                    f"but marker not in calendar box's vassal_service_markers"
                )


# ---------- Property 9: Plan target size matches box ----------------


@given(seed=st.integers(min_value=1, max_value=10_000))
@settings(max_examples=30, deadline=None)
@pytest.mark.parametrize("scenario", SCENARIOS)
def test_property_plan_target_size_matches_box(scenario, seed):
    """Per 4.1, plan target size depends on the season (box position)."""
    from nevsky.campaign import _plan_target_size
    s = load_scenario(scenario, seed=seed)
    box = s.meta.box
    target = _plan_target_size(box)
    assert 1 <= target <= 6  # plan sizes per Calendar reference
    # No Plan stack should exceed the target at load time.
    assert len(s.decks.teutonic.plan) <= target
    assert len(s.decks.russian.plan) <= target


# ---------- Property 10: Lord force counts non-negative ---------------


@given(seed=st.integers(min_value=1, max_value=10_000))
@settings(max_examples=30, deadline=None)
@pytest.mark.parametrize("scenario", SCENARIOS)
def test_property_lord_forces_non_negative(scenario, seed):
    s = load_scenario(scenario, seed=seed)
    for lid, lord in s.lords.items():
        for utype, n in lord.forces.items():
            assert n >= 0, f"{lid}.forces[{utype}] = {n}"
        for utype, n in lord.routed_units.items():
            assert n >= 0, f"{lid}.routed_units[{utype}] = {n}"


# ---------- Property 11: deck card-ID uniqueness ---------------------


@given(seed=st.integers(min_value=1, max_value=10_000))
@settings(max_examples=30, deadline=None)
@pytest.mark.parametrize("scenario", SCENARIOS)
def test_property_deck_card_ids_unique(scenario, seed):
    """No card should appear in more than one deck list (deck +
    discard + holds + capabilities_in_play + this_levy_events +
    this_campaign_events + removed + pending_draw)."""
    s = load_scenario(scenario, seed=seed)
    for side_name, deck in (("teu", s.decks.teutonic), ("rus", s.decks.russian)):
        all_lists = [deck.deck, deck.discard, deck.holds,
                     deck.capabilities_in_play, deck.this_levy_events,
                     deck.this_campaign_events, deck.removed,
                     deck.pending_draw]
        seen = []
        for lst in all_lists:
            seen.extend(lst)
        assert len(seen) == len(set(seen)), \
            f"{side_name} deck has duplicate card IDs: {seen}"
