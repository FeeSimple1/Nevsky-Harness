"""SMOKE-107 (Round 153): Veche Option C "Extra Muster" had the same
unreachable-handler gap as SMOKE-106 (Legate Use 2c).

Per Calendar and Veche reference:
  "ACTION C — Bonus Lordship for one Russian Lord
   Cost: Remove 1x 1VP Conquered marker from the Veche box.
   Effect: One Russian Lord at any Friendly Locale (NOT a Siege
   Locale) immediately performs an EXTRA Muster using his Lordship
   rating (3.4)."

Pre-fix `_h_veche_action` Option C set `target.lordship_used = 0`
but each Muster handler (`_h_muster_lord`, `_h_muster_vassal`,
`_h_levy_transport`, `_h_levy_capability`) hard-required
`levy_step == 'muster'`. The granted EXTRA Muster could not be
performed during call_to_arms — same gap as SMOKE-106 but on the
Russian Veche side.

Fix:
  - Add `Veche.extra_muster_target_lord: str | None`.
  - Veche Option C records the target Lord id there.
  - Helper `_require_muster_or_legate_2c_extra` (added in
    SMOKE-106) extended to accept call_to_arms when EITHER
    `state.legate.extra_muster_target_lord == by_id` OR
    `state.veche.extra_muster_target_lord == by_id`.
  - `_h_advance_step` clears BOTH flags on CtA -> done.
"""
from __future__ import annotations

import inspect

import nevsky.actions as actions
import nevsky.state as state_mod
import pytest


def test_smoke_107_marker_in_veche_c():
    src = inspect.getsource(actions._h_veche_action)
    assert "SMOKE-107" in src
    assert "veche.extra_muster_target_lord" in src


def test_smoke_107_marker_in_state_veche():
    src = inspect.getsource(state_mod.Veche)
    assert "SMOKE-107" in src
    assert "extra_muster_target_lord" in src


def test_smoke_107_helper_extended_to_veche():
    src = inspect.getsource(actions._require_muster_or_legate_2c_extra)
    assert "SMOKE-107" in src
    assert "veche.extra_muster_target_lord" in src


def test_smoke_107_advance_step_clears_veche_flag():
    src = inspect.getsource(actions._h_advance_step)
    idx = src.find("SMOKE-107")
    assert idx > 0
    nearby = src[idx:idx + 400]
    assert "veche.extra_muster_target_lord = None" in nearby


def test_smoke_107_helper_accepts_veche_target_in_cta():
    """In CtA, helper accepts by_lord matching the Veche-C target."""
    from nevsky.scenarios import load_scenario
    s = load_scenario("watland", seed=1)
    s.meta.phase = "levy"
    s.meta.levy_step = "call_to_arms"
    s.veche.extra_muster_target_lord = "domash"
    s.legate.extra_muster_target_lord = None
    actions._require_muster_or_legate_2c_extra(s, "domash")


def test_smoke_107_helper_rejects_other_lord_when_only_veche_set():
    from nevsky.scenarios import load_scenario
    s = load_scenario("watland", seed=1)
    s.meta.phase = "levy"
    s.meta.levy_step = "call_to_arms"
    s.veche.extra_muster_target_lord = "domash"
    s.legate.extra_muster_target_lord = None
    with pytest.raises(actions.IllegalAction):
        actions._require_muster_or_legate_2c_extra(s, "yaroslav")


def test_smoke_107_helper_accepts_either_flag():
    """Either Legate or Veche flag matching enables call_to_arms muster."""
    from nevsky.scenarios import load_scenario
    s = load_scenario("watland", seed=1)
    s.meta.phase = "levy"
    s.meta.levy_step = "call_to_arms"
    # Only legate flag set:
    s.legate.extra_muster_target_lord = "andreas"
    s.veche.extra_muster_target_lord = None
    actions._require_muster_or_legate_2c_extra(s, "andreas")
    # Only veche flag set:
    s.legate.extra_muster_target_lord = None
    s.veche.extra_muster_target_lord = "domash"
    actions._require_muster_or_legate_2c_extra(s, "domash")
