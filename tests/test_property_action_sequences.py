"""Property tests: run action sequences with invariant checks at each step."""
from __future__ import annotations

import importlib.util
import nevsky.actions  # noqa: F401
import pytest
from collections import Counter
from hypothesis import HealthCheck, given, settings, strategies as st

from nevsky.actions import IllegalAction, apply_action
from nevsky.legal_moves import legal_moves
from nevsky.scenarios import load_scenario
from nevsky.state import GameState


spec = importlib.util.spec_from_file_location("sp", "scripts/self_play.py")
sp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sp)


def _check_invariants(s, ctx_msg=""):
    cal = s.calendar
    assert 0.0 <= s.calendar.russian_vp <= 17.5, f"{ctx_msg} R_vp={s.calendar.russian_vp}"
    assert 0.0 <= s.calendar.teutonic_vp <= 17.5, f"{ctx_msg} T_vp={s.calendar.teutonic_vp}"

    for lid in s.lords:
        in_off_l = lid in cal.off_left
        in_off_r = lid in cal.off_right
        in_boxes = sum(1 for cb in cal.boxes if lid in cb.cylinders)
        total = int(in_off_l) + int(in_off_r) + in_boxes
        assert total <= 1, f"{ctx_msg}: {lid} in {total} cyl positions"
        in_off_l_s = lid in cal.off_left_service
        in_off_r_s = lid in cal.off_right_service
        in_boxes_s = sum(1 for cb in cal.boxes if lid in cb.service_markers)
        total_s = int(in_off_l_s) + int(in_off_r_s) + in_boxes_s
        assert total_s <= 1, f"{ctx_msg}: {lid} in {total_s} svc positions"

    for lid, lord in s.lords.items():
        for a, n in lord.assets.items():
            assert 0 <= n <= 8, f"{ctx_msg}: {lid}.assets[{a}]={n}"
        for u, n in lord.forces.items():
            assert n >= 0, f"{ctx_msg}: {lid}.forces[{u}]={n}"
        for u, n in lord.routed_units.items():
            assert n >= 0, f"{ctx_msg}: {lid}.routed_units[{u}]={n}"

    for lid, lord in s.lords.items():
        assert lord.state in ("ready", "mustered", "disbanded", "removed",
                              "no_levy"), f"{ctx_msg}: {lid}.state={lord.state}"
        if lord.state == "removed":
            assert lord.location is None, \
                f"{ctx_msg}: removed {lid} has location {lord.location}"

    for lid, loc in s.locales.items():
        assert not (loc.russian_castle and loc.teutonic_castle), \
            f"{ctx_msg}: {lid} both Castle"
        assert not (loc.russian_ravaged and loc.teutonic_ravaged), \
            f"{ctx_msg}: {lid} both Ravaged"
        assert 0 <= loc.siege_markers <= 4

    for side_name, deck in (("teu", s.decks.teutonic), ("rus", s.decks.russian)):
        all_lists = [deck.deck, deck.discard, deck.holds,
                     deck.capabilities_in_play, deck.this_levy_events,
                     deck.this_campaign_events, deck.removed,
                     deck.pending_draw]
        seen = []
        for lst in all_lists:
            seen.extend(lst)
        assert len(seen) == len(set(seen)), \
            f"{ctx_msg}: {side_name} duplicates"


def _step_with_invariants(scenario, seed, max_steps, every_n_check=10):
    """Run self-play directly, checking invariants every N steps."""
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
        import json
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
        if step_n % every_n_check == 0:
            _check_invariants(s, ctx_msg=f"step {step_n}")
    _check_invariants(s, ctx_msg="final")
    return s


@given(seed=st.integers(min_value=1, max_value=100))
@settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@pytest.mark.parametrize("scenario", ["watland", "pleskau"])
def test_property_invariants_hold_through_self_play(scenario, seed):
    _step_with_invariants(scenario, seed, max_steps=400, every_n_check=20)


@given(seed=st.integers(min_value=1, max_value=200))
@settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_property_invariants_pleskau_exhaustive(seed):
    _step_with_invariants("pleskau", seed, max_steps=300, every_n_check=10)


@given(seed=st.integers(min_value=1, max_value=300))
@settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@pytest.mark.parametrize("scenario", ["watland", "peipus"])
def test_property_no_lord_two_states(scenario, seed):
    _step_with_invariants(scenario, seed, max_steps=400, every_n_check=20)


@given(seed=st.integers(min_value=1, max_value=200))
@settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_property_long_scenario_invariants(seed):
    _step_with_invariants("crusade_on_novgorod", seed, max_steps=1500, every_n_check=50)


@given(seed=st.integers(min_value=1, max_value=300))
@settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_property_save_load_round_trip_during_play(seed):
    s = _step_with_invariants("watland", seed, max_steps=200, every_n_check=200)
    txt = s.model_dump_json()
    s2 = GameState.model_validate_json(txt)
    assert s.model_dump_json() == s2.model_dump_json()
