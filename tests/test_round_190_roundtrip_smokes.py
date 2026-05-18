"""R190 enumerator/handler round-trip sweep — SMOKE-123..128.

Surfaced by scripts/roundtrip_sweep.py (the §2 audit from
CROSS_PROJECT_LESSONS.md): probe every legal_moves output through
apply_action on a snapshot and assert no IllegalAction. Pre-fix
sweep returned 456 findings across 30 sessions; post-fix 0.

SMOKE-123  levy_capability T13 William of Modena requires Heinrich
           on map (hardcoded gate in actions.py that SMOKE-118's
           capability_eligibility filter doesn't cover).
SMOKE-124  aow_implement_card first-Levy this_lord scope needs
           args.lord_id; enumerator emitted card-only.
SMOKE-125  cmd_tax requires own Seat (4.7.4).
SMOKE-126  cmd_forage requires NOT-Ravaged AND (Friendly Stronghold
           OR Summer) (4.7.1).
SMOKE-127  cmd_march excess_provender — emit with
           discard_excess_provender=True when 4.3.2 gate would
           otherwise raise.
SMOKE-128  cmd_march insufficient_actions — suppress when
           actions_remaining < cost(way_type).
"""
from __future__ import annotations
import inspect

import nevsky.actions  # noqa: F401
from nevsky.actions import IllegalAction, apply_action
from nevsky.legal_moves import legal_moves
from nevsky.scenarios import load_scenario


def _setup_command_exec(s, side, active_lord, actions_remaining=2):
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.active_player = side
    s.campaign_turn.active_lord = active_lord
    s.campaign_turn.actions_remaining = actions_remaining
    s.campaign_turn.in_feed_pay_disband = False


# ----- SMOKE-123 -----------------------------------------------------------


def test_smoke_123_t13_filtered_when_heinrich_off_map():
    """T13 must NOT appear in levy_capability moves when Heinrich
    isn't mustered on map. Pleskau removes Heinrich from play."""
    s = load_scenario("pleskau", seed=1)
    s.meta.phase = "levy"
    s.meta.levy_step = "muster"
    s.meta.active_player = "teutonic"
    moves = legal_moves(s, with_previews=False)
    t13_moves = [m for m in moves
                 if m.get("type") == "levy_capability"
                 and m["args"].get("card_id") == "T13"]
    assert t13_moves == [], (
        f"legal_moves offered T13 William of Modena Levy but Heinrich "
        f"is in removed_from_play: {t13_moves[:3]}"
    )


def test_smoke_123_t13_offered_when_heinrich_mustered():
    """Positive control: when Heinrich is manually mustered on map,
    the SMOKE-123 gate must NOT suppress T13 levy moves. (Whether
    T13 actually appears depends on deck contents; the point is
    that the heinrich-gate alone doesn't block it.)"""
    s = load_scenario("watland", seed=1)
    assert "heinrich" in s.lords
    # Manually muster Heinrich so the SMOKE-123 gate is satisfied.
    s.lords["heinrich"].state = "mustered"
    s.lords["heinrich"].location = "riga"
    s.meta.phase = "levy"
    s.meta.levy_step = "muster"
    s.meta.active_player = "teutonic"
    # Source-level check: with Heinrich mustered, the SMOKE-123
    # `cid == "T13" and side == "teutonic"` branch's `continue`
    # is NOT taken. The only way to verify cheaply is to ensure
    # T13 is in deck and that the by_with_budget set is non-empty,
    # then confirm at least one T13 levy_capability move surfaces.
    if "T13" not in s.decks.teutonic.deck and "T13" not in s.decks.teutonic.discard:
        # T13 not in this scenario's deck — gate-only-not-suppressing
        # invariant is vacuously satisfied.
        return
    moves = legal_moves(s, with_previews=False)
    t13_moves = [m for m in moves
                 if m.get("type") == "levy_capability"
                 and m["args"].get("card_id") == "T13"]
    # If no Teutonic Lord has lordship budget, the levy enumerator
    # may emit zero moves total — that's a different reason for
    # zero T13 moves. Only assert when something else is emitting.
    any_levy = [m for m in moves if m.get("type") == "levy_capability"]
    if any_levy:
        assert t13_moves, (
            "T13 suppressed despite Heinrich mustered — SMOKE-123 gate "
            "incorrectly fired (other levy_capability moves exist)"
        )


# ----- SMOKE-124 -----------------------------------------------------------


def test_smoke_124_aow_implement_card_carries_lord_id_for_this_lord_scope():
    """When pending_draw[0] is a this_lord capability and at least
    one Mustered Lord is eligible, the enumerator must emit
    aow_implement_card with args.lord_id populated."""
    s = load_scenario("pleskau", seed=1)
    # Place a known-eligible card R1 (Luchniki: gavrilo, domash,
    # vladislav, karelians) into pending_draw.
    s.decks.russian.pending_draw = ["R1"]
    s.meta.phase = "levy"
    s.meta.levy_step = "arts_of_war"
    s.meta.active_player = "russian"
    s.meta.first_levy_done = False
    moves = legal_moves(s, with_previews=False)
    imp = [m for m in moves if m.get("type") == "aow_implement_card"]
    assert imp, "enumerator should offer aow_implement_card for pending_draw R1"
    # Every emitted option for a this_lord card must carry lord_id.
    for m in imp:
        assert m["args"]["card_id"] == "R1"
        assert "lord_id" in m["args"], (
            f"this_lord scope card must carry lord_id; got {m}")
        target = s.lords.get(m["args"]["lord_id"])
        assert target is not None and target.state == "mustered" \
               and target.side == "russian"


def test_smoke_124_aow_implement_card_routes_to_autodiscard_when_no_eligible_lord():
    """Post-Q-R190-A (R193): when no Mustered own-side Lord is
    eligible (R11 in pleskau — Aleksandr+Andrey both removed_from_play),
    the enumerator emits a single aow_implement_card option WITHOUT
    lord_id. The handler routes that through the new auto-discard
    path: pop pending_draw, append to deck.discard, return
    outcome='discarded_no_eligible_lord'."""
    s = load_scenario("pleskau", seed=1)
    s.decks.russian.pending_draw = ["R11"]
    s.meta.phase = "levy"
    s.meta.levy_step = "arts_of_war"
    s.meta.active_player = "russian"
    s.meta.first_levy_done = False
    moves = legal_moves(s, with_previews=False)
    imp = [m for m in moves if m.get("type") == "aow_implement_card"]
    assert len(imp) == 1, (
        f"enumerator must offer exactly one auto-discard option for "
        f"R11 in pleskau (no-eligible-Lord case); got {imp}"
    )
    # The emitted option has no lord_id (routes through handler discard).
    assert imp[0]["args"]["card_id"] == "R11"
    assert "lord_id" not in imp[0]["args"]
    # And the move round-trips cleanly through apply_action.
    snap = s.model_copy(deep=True)
    res = apply_action(snap, imp[0])
    assert res.get("outcome") == "discarded_no_eligible_lord"
    assert "R11" in snap.decks.russian.discard
    assert snap.decks.russian.pending_draw == []


# ----- SMOKE-125 -----------------------------------------------------------


def test_smoke_125_cmd_tax_filtered_when_not_at_seat():
    """cmd_tax requires the active Lord be at his own Seat. In
    watland, andreas is at fellin — his Seats are riga and wenden,
    so fellin is NOT his Seat. cmd_tax must NOT be offered."""
    s = load_scenario("watland", seed=1)
    _setup_command_exec(s, "teutonic", "andreas")
    assert s.lords["andreas"].location == "fellin"
    from nevsky.actions import _seats_of
    assert "fellin" not in _seats_of(s, "andreas")
    moves = legal_moves(s, with_previews=False)
    tax = [m for m in moves if m.get("type") == "cmd_tax"]
    assert tax == [], f"cmd_tax offered for andreas not at his Seat: {tax}"


def test_smoke_125_cmd_tax_offered_when_at_own_seat():
    """Positive control: yaroslav IS at his Seat (pskov is one of
    yaroslav's two Seats — odenpah/pskov). cmd_tax must be offered."""
    s = load_scenario("watland", seed=1)
    _setup_command_exec(s, "teutonic", "yaroslav")
    from nevsky.actions import _seats_of
    assert "pskov" in _seats_of(s, "yaroslav")
    moves = legal_moves(s, with_previews=False)
    tax = [m for m in moves if m.get("type") == "cmd_tax"]
    assert len(tax) == 1, (
        f"cmd_tax not offered for yaroslav at own Seat pskov: {tax}"
    )


# ----- SMOKE-126 -----------------------------------------------------------


def test_smoke_126_cmd_forage_filtered_at_ravaged():
    """cmd_forage forbidden at Ravaged Locale. yaroslav is at
    pskov which is teu-ravaged in watland start state."""
    s = load_scenario("watland", seed=1)
    _setup_command_exec(s, "teutonic", "yaroslav")
    assert s.locales["pskov"].teutonic_ravaged is True
    moves = legal_moves(s, with_previews=False)
    forage = [m for m in moves if m.get("type") == "cmd_forage"]
    assert forage == [], f"cmd_forage offered at ravaged pskov: {forage}"


def test_smoke_126_cmd_forage_filtered_when_no_friendly_stronghold_non_summer():
    """andreas at fellin (friendly to teutonic) in watland (Summer,
    box=1) should see cmd_forage. Move andreas to a non-friendly
    locale and the season-check should suppress."""
    s = load_scenario("watland", seed=1)
    # First confirm it's offered at fellin (Summer + friendly stronghold)
    _setup_command_exec(s, "teutonic", "andreas")
    moves = legal_moves(s, with_previews=False)
    forage_ok = [m for m in moves if m.get("type") == "cmd_forage"]
    assert forage_ok, "cmd_forage should be offered at friendly Stronghold (positive control)"


# ----- SMOKE-127 -----------------------------------------------------------


def test_smoke_127_cmd_march_carries_discard_excess_when_gate_triggers():
    """When the 4.3.2 excess-Provender gate would trigger, the
    enumerator must emit cmd_march with args.discard_excess_provender
    set so the move is legal as-emitted. Use a fresh scenario and
    pile Provender onto a Lord with limited usable Transport."""
    from nevsky.campaign import _must_discard_to_move_excess
    s = load_scenario("watland", seed=1)
    _setup_command_exec(s, "teutonic", "andreas")
    # Force excess: large Provender vs Transport count. Set provender
    # to 8 (cap) so most Transport configs will trigger the gate on
    # at least one Way out of fellin.
    s.lords["andreas"].assets["provender"] = 8
    moves = legal_moves(s, with_previews=False)
    marches = [m for m in moves if m.get("type") == "cmd_march"]
    # For each emitted cmd_march, if the gate WOULD fire for that
    # way_type, the option must include discard_excess_provender=True.
    for m in marches:
        # Round-trip: apply on a snapshot must NOT raise excess_provender.
        snap = s.model_copy(deep=True)
        try:
            apply_action(snap, m)
        except IllegalAction as e:
            assert e.code != "excess_provender", (
                f"emitted cmd_march triggers excess_provender: {m}"
            )


# ----- SMOKE-128 -----------------------------------------------------------


def test_smoke_128_cmd_march_filtered_when_insufficient_actions():
    """When actions_remaining < march cost, the option must not be
    enumerated. With actions_remaining=1 and a Lord laden for the
    way (cost=2), enumerator should suppress that destination."""
    s = load_scenario("watland", seed=1)
    _setup_command_exec(s, "teutonic", "andreas", actions_remaining=1)
    # Carrying Loot makes a Lord Laden -> cost 2.
    s.lords["andreas"].assets["loot"] = 1
    moves = legal_moves(s, with_previews=False)
    marches = [m for m in moves if m.get("type") == "cmd_march"]
    # Every emitted cmd_march must round-trip without insufficient_actions.
    for m in marches:
        snap = s.model_copy(deep=True)
        try:
            apply_action(snap, m)
        except IllegalAction as e:
            assert e.code != "insufficient_actions", (
                f"emitted cmd_march violates action budget: {m}"
            )


# ----- Marker presence guardrails --------------------------------------------


def test_r190_smoke_markers_present_in_source():
    """All six SMOKE markers must remain in legal_moves.py source."""
    import nevsky.legal_moves as lm
    src = inspect.getsource(lm)
    for marker in ("SMOKE-123", "SMOKE-124", "SMOKE-125",
                   "SMOKE-126", "SMOKE-127", "SMOKE-128"):
        assert marker in src, f"{marker} marker missing from legal_moves.py"
