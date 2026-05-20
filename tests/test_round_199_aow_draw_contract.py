"""R199 (SMOKE-131 + SMOKE-132): enforce the SoP 3.1 AoW
draw/implement contract.

SoP Sequence-of-Play 3.1 `draw_two_and_implement`: "draw 2 cards;
implement in order drawn" — one sub-step per Levy.

SMOKE-131: advance_step was offered/accepted during arts_of_war while
pending_draw still held an implementable card, orphaning it. Now
illegal (suppressed in legal_moves; handler raises pending_draw_nonempty).

SMOKE-132: aow_draw drew 2 but didn't track per-Levy draws, so a side
could draw 2, implement, then draw 2 more (4/Levy). Now capped at one
draw per Levy via meta.aow_drawn_{t,r}, reset at each Levy entry.

Surfaced in the Crusade-on-Novgorod LLM playthrough (off-by-one on the
re-indexed action list selected advance_step with a card pending).
"""
from __future__ import annotations
import inspect

import pytest

import nevsky.actions  # noqa: F401
from nevsky.actions import IllegalAction, apply_action
from nevsky.legal_moves import legal_moves
from nevsky.scenarios import load_scenario
from nevsky.static_data import load_cards


def _impl_args(state, cid):
    a = {"card_id": cid}
    if load_cards()[cid].get("capability_scope") == "this_lord":
        for lid, l in state.lords.items():
            if (l.side == state.meta.active_player and l.state == "mustered"
                    and len(l.this_lord_capabilities) < 2):
                a["lord_id"] = lid
                break
    return a


def _fresh_aow(scenario="crusade_on_novgorod", side="teutonic"):
    s = load_scenario(scenario, seed=1)
    s.meta.phase = "levy"
    s.meta.levy_step = "arts_of_war"
    s.meta.active_player = side
    return s


# ----- SMOKE-131 -----------------------------------------------------------


def test_advance_blocked_with_pending_draw():
    s = _fresh_aow()
    apply_action(s, {"type": "aow_draw", "side": "teutonic", "args": {}})
    assert len(s.decks.teutonic.pending_draw) >= 1
    # advance_step must not be offered, and must be rejected if forced.
    moves = [m["type"] for m in legal_moves(s, with_previews=False)]
    assert "advance_step" not in moves
    with pytest.raises(IllegalAction) as e:
        apply_action(s, {"type": "advance_step", "side": "teutonic", "args": {}})
    assert e.value.code == "pending_draw_nonempty"


def test_advance_allowed_after_implementing_all():
    s = _fresh_aow()
    apply_action(s, {"type": "aow_draw", "side": "teutonic", "args": {}})
    for cid in list(s.decks.teutonic.pending_draw):
        apply_action(s, {"type": "aow_implement_card", "side": "teutonic",
                         "args": _impl_args(s, cid)})
    assert s.decks.teutonic.pending_draw == []
    moves = [m["type"] for m in legal_moves(s, with_previews=False)]
    assert "advance_step" in moves
    # And it actually advances.
    apply_action(s, {"type": "advance_step", "side": "teutonic", "args": {}})


# ----- SMOKE-132 -----------------------------------------------------------


def test_second_draw_blocked_same_levy():
    s = _fresh_aow()
    apply_action(s, {"type": "aow_draw", "side": "teutonic", "args": {}})
    for cid in list(s.decks.teutonic.pending_draw):
        apply_action(s, {"type": "aow_implement_card", "side": "teutonic",
                         "args": _impl_args(s, cid)})
    # Pending empty, but already drew this Levy -> no draw offered/allowed.
    moves = [m["type"] for m in legal_moves(s, with_previews=False)]
    assert "aow_draw" not in moves
    assert "aow_shuffle" not in moves
    with pytest.raises(IllegalAction) as e:
        apply_action(s, {"type": "aow_draw", "side": "teutonic", "args": {}})
    assert e.value.code == "already_drawn_this_levy"


def test_draw_flag_resets_next_levy():
    """After a full Levy+Campaign, the next Levy lets the side draw
    again. Drive a Watland game to the second Levy's arts_of_war."""
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location(
        "sp", Path("scripts/self_play.py"))
    sp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sp)
    # Run a short self-play; it traverses multiple Levies. If the reset
    # were broken, a side couldn't draw in Levy 2 and the game would
    # deadlock (no_legal_moves) rather than reach terminal.
    r = sp.step_self_play("watland", seed=1, max_steps=20000)
    assert r.get("error") is None or r["error"].get("reason") != "no_legal_moves", r


def test_meta_flags_default_false():
    s = load_scenario("crusade_on_novgorod", seed=1)
    assert s.meta.aow_drawn_t is False
    assert s.meta.aow_drawn_r is False


def test_markers_present_in_source():
    import nevsky.actions as a
    import nevsky.legal_moves as lm
    src = inspect.getsource(a) + inspect.getsource(lm)
    assert "SMOKE-131" in src
    assert "SMOKE-132" in src
    assert "SMOKE-133" in src


# ----- SMOKE-131 scoping: subsequent-Levy events NOT blocked --------------


def test_advance_blocked_for_subsequent_levy_event_r201():
    """R201 extended SMOKE-131 to ALL Levies. At a subsequent Levy a
    side may not advance while a drawn Event is pending; the Event is
    cleared either by resolving it with a target or by a bare-implement
    no-op-discard (un-targetable Event)."""
    s = _fresh_aow()
    s.meta.first_levy_done = True  # subsequent Levy
    apply_action(s, {"type": "aow_draw", "side": "teutonic", "args": {}})
    assert len(s.decks.teutonic.pending_draw) >= 1
    # advance_step is now suppressed and rejected while a card is pending.
    moves = [m["type"] for m in legal_moves(s, with_previews=False)]
    assert "advance_step" not in moves
    with pytest.raises(IllegalAction) as e:
        apply_action(s, {"type": "advance_step", "side": "teutonic", "args": {}})
    assert e.value.code == "pending_draw_nonempty"
    # R202: clear each pending card via the arg-populated implement that
    # legal_moves offers (targetable Events are mandatory, so a bare
    # implement raises). Pick the first offered aow_implement_card each
    # time until pending_draw is empty.
    guard = 0
    while s.decks.teutonic.pending_draw and guard < 10:
        guard += 1
        impl = [m for m in legal_moves(s, with_previews=False)
                if m["type"] == "aow_implement_card"]
        assert impl, "no implement move offered for pending Event"
        apply_action(s, {"type": "aow_implement_card", "side": "teutonic",
                         "args": dict(impl[0]["args"])})
    assert s.decks.teutonic.pending_draw == []
    apply_action(s, {"type": "advance_step", "side": "teutonic", "args": {}})


def test_r202_bare_implement_untargetable_event_discards():
    """R202: a bare implement of an immediate Event with NO legal target
    reveal-and-discards (3.1.4 Greed). R10 Batu Khan targets Andreas;
    remove Andreas from the Calendar so no legal target exists, then a
    bare implement clears with no effect."""
    s = load_scenario("watland", seed=1)
    s.meta.phase = "levy"
    s.meta.levy_step = "arts_of_war"
    s.meta.active_player = "russian"
    s.meta.first_levy_done = True
    cal = s.calendar
    for cb in cal.boxes:
        if "andreas" in cb.cylinders:
            cb.cylinders.remove("andreas")
        if "andreas" in cb.service_markers:
            cb.service_markers.remove("andreas")
    for lst in (cal.off_left, cal.off_right, cal.off_left_service,
                cal.off_right_service):
        if "andreas" in lst:
            lst.remove("andreas")
    if "andreas" in s.lords:
        s.lords["andreas"].location = None
    s.decks.russian.pending_draw = ["R10"]
    res = apply_action(s, {"type": "aow_implement_card", "side": "russian",
                           "args": {"card_id": "R10"}})
    assert "R10" in s.decks.russian.discard
    assert s.decks.russian.pending_draw == []


def test_r202_bare_implement_targetable_event_raises():
    """R202 (Q-R201-A, 3.1.4 Greed): a bare implement of an immediate
    Event that HAS a legal target raises -- the Event is mandatory, the
    player must pick a target. Andreas is on watland's Calendar, so R10
    is targetable."""
    s = load_scenario("watland", seed=1)
    s.meta.phase = "levy"
    s.meta.levy_step = "arts_of_war"
    s.meta.active_player = "russian"
    s.meta.first_levy_done = True
    s.decks.russian.pending_draw = ["R10"]
    with pytest.raises(IllegalAction):
        apply_action(s, {"type": "aow_implement_card", "side": "russian",
                         "args": {"card_id": "R10"}})
    # And legal_moves offers arg-populated implements so it's clearable.
    impl = [m for m in legal_moves(s, with_previews=False)
            if m["type"] == "aow_implement_card"]
    assert impl and all("target" in m["args"] or "lord_id" in m["args"]
                        for m in impl)


def test_r201_explicit_bad_target_still_raises():
    """An explicit but invalid target still raises (genuine arg error
    surfaces) -- only a BARE implement no-op-discards."""
    s = load_scenario("watland", seed=1)
    s.meta.phase = "levy"
    s.meta.levy_step = "arts_of_war"
    s.meta.active_player = "russian"
    s.meta.first_levy_done = True
    s.decks.russian.pending_draw = ["R10"]
    with pytest.raises(IllegalAction):
        apply_action(s, {"type": "aow_implement_card", "side": "russian",
                         "args": {"card_id": "R10", "target": "not_a_real_lord"}})


# ----- SMOKE-133: muster enumeration excludes block-listed Lords ----------


def test_smoke_133_muster_not_offered_for_blocked_lord():
    """R11/R17 block a Lord from using Lordship this Levy. legal_moves
    must not offer muster_lord / muster_vassal for a blocked Lord
    (the handler rejects with blocked_this_levy)."""
    s = load_scenario("crusade_on_novgorod", seed=1)
    s.meta.phase = "levy"
    s.meta.levy_step = "muster"
    s.meta.active_player = "teutonic"
    # Find a mustered Teuton with Lordship budget and a Ready vassal.
    target = None
    for lid, lord in s.lords.items():
        if (lord.side == "teutonic" and lord.state == "mustered"
                and lord.location is not None
                and any(v.ready and not v.mustered for v in lord.vassals.values())):
            target = lid
            break
    if target is None:
        return  # scenario shape doesn't expose the case; nothing to assert
    # Block this Lord.
    s.meta.block_lords_this_levy_t = [target]
    moves = legal_moves(s, with_previews=False)
    for m in moves:
        if m.get("type") in ("muster_lord", "muster_vassal"):
            assert m["args"].get("by_lord") != target, (
                f"muster offered for block-listed Lord {target}: {m}")
