"""SMOKE-112 (Round 175): T14 and R18 Bountiful Harvest raised
missing_arg when no Ravaged marker existed in the eligible territory.
Per AoW Reference convention, an immediate event with no valid target
discards with no effect.

T14 Tip: "Russians choose any one white Ravaged marker to remove" —
implicitly requires at least one to exist.
R18 Tip: "Russians choose any one white Ravaged marker to remove,
reducing Teutonic victory points by ½VP" — same.

Pre-fix the resolver raised `missing_arg` when args.locale was
omitted. With no Ravaged marker, every locale choice would fail
"not_ravaged" anyway, so the event was effectively unresolvable.

Found via scripts/self_play.py (Crusade on Novgorod seeds 7 and 8):
after several Levies, the AoW deck drew T14/R18 in a state with no
matching Ravaged markers, and the agent's variant-exhaustion fallback
ran out.

Fix: when no eligible Ravaged marker exists in the relevant territory,
return `{"event": cid, "no_op": True, "reason": ...}` instead of
raising. Pre-existing args.locale paths still validate normally.
"""
from __future__ import annotations

import inspect

import nevsky.actions  # noqa: F401
import nevsky.events as events
from nevsky.events import resolve_immediate_event
from nevsky.scenarios import load_scenario


def test_smoke_112_marker_in_t14():
    src = inspect.getsource(events._ev_bountiful_harvest_t)
    assert "SMOKE-112" in src
    assert "no_op" in src


def test_smoke_112_marker_in_r18():
    src = inspect.getsource(events._ev_bountiful_harvest_r)
    assert "SMOKE-112" in src
    assert "no_op" in src


def test_smoke_112_t14_no_op_when_no_russian_ravaged():
    s = load_scenario("watland", seed=1)
    # Clear all russian_ravaged markers
    for loc in s.locales.values():
        loc.russian_ravaged = False
    res = resolve_immediate_event(s, "T14", {})
    assert res.get("no_op") is True
    assert res.get("event") == "T14"


def test_smoke_112_r18_no_op_when_no_teutonic_ravaged():
    s = load_scenario("watland", seed=1)
    for loc in s.locales.values():
        loc.teutonic_ravaged = False
    res = resolve_immediate_event(s, "R18", {})
    assert res.get("no_op") is True
    assert res.get("event") == "R18"


def test_smoke_112_t14_still_works_with_args_when_target_exists():
    s = load_scenario("watland", seed=1)
    # Set a russian_ravaged marker in a Teutonic locale
    from nevsky.static_data import load_locales
    static = load_locales()
    target_locale = None
    for lid, info in static.items():
        if info.get("territory") in ("teutonic", "crusader"):
            s.locales[lid].russian_ravaged = True
            target_locale = lid
            break
    assert target_locale is not None
    pre_vp = s.calendar.russian_vp
    res = resolve_immediate_event(s, "T14", {"locale": target_locale})
    assert res.get("no_op") is None or res.get("no_op") is False
    assert res.get("locale") == target_locale
    assert s.locales[target_locale].russian_ravaged is False
    assert s.calendar.russian_vp == max(0.0, pre_vp - 0.5)


def test_smoke_112_t14_still_raises_missing_arg_when_target_exists():
    """If a valid target exists but args.locale was omitted, the
    harness still raises missing_arg (no auto-pick)."""
    import pytest
    from nevsky.actions import IllegalAction
    s = load_scenario("watland", seed=1)
    from nevsky.static_data import load_locales
    static = load_locales()
    for lid, info in static.items():
        if info.get("territory") in ("teutonic", "crusader"):
            s.locales[lid].russian_ravaged = True
            break
    with pytest.raises(IllegalAction):
        resolve_immediate_event(s, "T14", {})


def test_smoke_112_r18_still_raises_missing_arg_when_target_exists():
    import pytest
    from nevsky.actions import IllegalAction
    s = load_scenario("watland", seed=1)
    from nevsky.static_data import load_locales
    static = load_locales()
    for lid, info in static.items():
        if info.get("territory") == "russian":
            s.locales[lid].teutonic_ravaged = True
            break
    with pytest.raises(IllegalAction):
        resolve_immediate_event(s, "R18", {})
