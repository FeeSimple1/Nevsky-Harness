"""Round 222 — validated action palette (P0, Inferno/GPT-5.5 advisory) +
the parallel-ways march fix it surfaced (SMOKE-159).

- concrete_actions_validated() probes each concrete candidate against a
  deep copy and filters any the handler rejects, returning them as
  structured `rejected` diagnostics (RNG-safe: seed+rng_state are in-state).
- SMOKE-159: cmd_march to a destination reachable by PARALLEL Ways
  (trackway + waterway, e.g. odenpah<->dorpat) must pin `way_type` so the
  handler resolves the same Way the enumerator costed -- else a
  no-discard waterway entry could be applied as the trackway and rejected
  with excess_provender.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from nevsky.actions import IllegalAction, apply_action
import nevsky.campaign as camp
from nevsky.legal_moves import legal_moves
from nevsky.scenarios import load_scenario
from nevsky.static_data import load_ways

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _llm_mod():
    if "src" not in sys.path:
        sys.path.insert(0, "src")
    spec = importlib.util.spec_from_file_location("llm_sp", _SCRIPTS / "llm_self_play.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# --- validation mechanism --------------------------------------------------

def test_validation_filters_and_reports_illegal_candidate(monkeypatch):
    llm = _llm_mod()
    s = load_scenario("watland", seed=1)
    legal = {"type": "advance_step", "side": "teutonic", "args": {}}
    illegal = {"type": "cmd_tax", "side": "teutonic",
               "args": {"lord_id": "andreas"}}  # tax outside command phase -> rejected
    monkeypatch.setattr(llm, "_concrete_actions", lambda state, side: [legal, illegal])
    validated, rejected = llm.concrete_actions_validated(s, "teutonic")
    vtypes = [a["type"] for a in validated]
    assert "advance_step" in vtypes
    assert "cmd_tax" not in vtypes
    assert any(r["action"]["type"] == "cmd_tax" for r in rejected)


def test_validation_preserves_real_rng_state(monkeypatch):
    llm = _llm_mod()
    s = load_scenario("watland", seed=1)
    before = s.meta.rng_state
    # an action that rolls dice if applied (muster) -- probing must use a copy
    cand = {"type": "advance_step", "side": "teutonic", "args": {}}
    monkeypatch.setattr(llm, "_concrete_actions", lambda state, side: [cand])
    llm.concrete_actions_validated(s, "teutonic")
    assert s.meta.rng_state == before  # real game's RNG untouched by probing


# --- SMOKE-159 parallel-ways march -----------------------------------------

def _has_parallel_ways(a, b):
    ts = {w["type"] for w in load_ways() if {w["a"], w["b"]} == {a, b}}
    return ts == {"trackway", "waterway"}


def test_parallel_ways_march_pins_way_type_and_applies():
    assert _has_parallel_ways("odenpah", "dorpat"), "fixture assumes odenpah<->dorpat parallel"
    s = load_scenario("peipus", seed=1)  # winter -> trackway/waterway costs differ
    h = "hermann"
    s.lords[h].location = "odenpah"
    s.lords[h].in_stronghold = False
    s.lords[h].assets = {"provender": 1, "boat": 2, "cart": 1}
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.active_player = "teutonic"
    s.campaign_turn.active_lord = h
    s.campaign_turn.next_to_reveal = "teutonic"
    s.campaign_turn.in_feed_pay_disband = False
    s.campaign_turn.actions_remaining = camp._effective_command_rating(s, h)
    marches = [m for m in legal_moves(s, with_previews=False)
               if m.get("type") == "cmd_march" and m["args"].get("to") == "dorpat"]
    assert marches, "expected march(es) to dorpat"
    for m in marches:
        assert "way_type" in m["args"], "parallel-ways march must pin way_type"
        # every enumerated march must apply cleanly (no excess_provender)
        probe = s.model_copy(deep=True)
        apply_action(probe, {k: v for k, v in m.items() if k in ("type", "side", "args")})
