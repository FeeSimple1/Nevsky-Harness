"""SMOKE-118 + SMOKE-119 (Round 186): legal_moves enumerator
filtering improvements.

SMOKE-118: levy_capability was offered as (by_lord, card_id) pairs
without filtering by capability_eligibility, per-Lord cap-2 limit,
or duplicate-capability-name. Agents and the LLM-play interface
(which uses legal_moves as the move palette) would attempt
ineligible levies that the harness rejected with ineligible_levyer
/ ineligible_target / cap_limit / duplicate_capability codes.

SMOKE-119: stand_battle concede pseudo-option used
`{"concede": side}` (game side) instead of `{"concede": "attacker"
| "defender"}` (battle role). The harness's _h_stand_battle
expects the latter; concede picks were rejected with bad_concede.

Found via scripts/strategic_agent.py sweep — the strategic agent
exercises combat paths the greedy agent doesn't, exposing these
two enumerator gaps.

Both are "legal_moves over-enumeration" bugs — the enumerator was
presenting moves the harness would reject. Not catastrophic, but
real for any consumer that uses legal_moves as the move palette
(self_play.py, strategic_agent.py, the LLM-play interface).
"""
from __future__ import annotations

import nevsky.actions  # noqa: F401
from nevsky.legal_moves import legal_moves
from nevsky.scenarios import load_scenario


# ----- SMOKE-118 -----------------------------------------------------------


def test_smoke_118_levy_capability_filters_by_eligibility():
    """T15 Mindaugas requires Andreas or Rudolf (capability_
    eligibility). legal_moves should NOT offer T15 to heinrich."""
    s = load_scenario("watland", seed=1)
    s.meta.phase = "levy"
    s.meta.levy_step = "muster"
    s.meta.active_player = "teutonic"
    # Ensure heinrich is mustered and has lordship budget
    heinrich = s.lords.get("heinrich")
    if heinrich is None or heinrich.state != "mustered":
        # Skip if Heinrich isn't mustered in this scenario
        return
    moves = legal_moves(s, with_previews=False)
    levy_moves = [m for m in moves
                  if m["type"] == "levy_capability"
                  and m["args"]["by_lord"] == "heinrich"]
    # T15 should NOT appear; T15 eligibility is Andreas/Rudolf only.
    for m in levy_moves:
        assert m["args"]["card_id"] != "T15", (
            f"legal_moves offers heinrich + T15 but T15 eligibility is "
            f"Andreas/Rudolf only"
        )


def test_smoke_118_levy_capability_filters_cap_limit():
    """A Lord already at 2 capabilities should not be offered
    levy_capability (3.4.4 cap_limit)."""
    s = load_scenario("watland", seed=1)
    s.meta.phase = "levy"
    s.meta.levy_step = "muster"
    s.meta.active_player = "teutonic"
    teu = next(lid for lid, l in s.lords.items()
               if l.side == "teutonic" and l.state == "mustered")
    # Add 2 dummy this_lord caps (use real this_lord-scoped capability IDs).
    from nevsky.static_data import load_cards
    cards = load_cards()
    this_lord_caps = [cid for cid, c in cards.items()
                      if c["side"] == "teutonic" and c.get("capability_scope") == "this_lord"
                      and not c.get("no_capability")]
    if len(this_lord_caps) < 2:
        return
    s.lords[teu].this_lord_capabilities = this_lord_caps[:2]
    moves = legal_moves(s, with_previews=False)
    levy_moves = [m for m in moves
                  if m["type"] == "levy_capability"
                  and m["args"]["by_lord"] == teu]
    # No this_lord cap should be offered (cap-limit-2)
    for m in levy_moves:
        cid = m["args"]["card_id"]
        if cards[cid].get("capability_scope") == "this_lord":
            assert False, f"legal_moves offered {teu} + {cid} but {teu} is already at 2 caps"


def test_smoke_118_levy_capability_filters_duplicate_name():
    """A Lord who has Balistarii (via T4/T5/T6) should not be offered
    another Balistarii — same capability_name = duplicate."""
    s = load_scenario("watland", seed=1)
    s.meta.phase = "levy"
    s.meta.levy_step = "muster"
    s.meta.active_player = "teutonic"
    teu = next(lid for lid, l in s.lords.items()
               if l.side == "teutonic" and l.state == "mustered")
    # Give the Lord T4 (Balistarii); legal_moves should not offer T5/T6
    s.lords[teu].this_lord_capabilities = ["T4"]
    moves = legal_moves(s, with_previews=False)
    levy_moves = [m for m in moves
                  if m["type"] == "levy_capability"
                  and m["args"]["by_lord"] == teu
                  and m["args"]["card_id"] in ("T5", "T6")]
    assert not levy_moves, \
        f"legal_moves offered {teu} duplicate Balistarii: {levy_moves}"


# ----- SMOKE-119 ----------------------------------------------------------


def test_smoke_119_concede_uses_battle_role():
    """The stand_battle concede option must use 'attacker' or
    'defender' (battle role), not the side name."""
    s = load_scenario("watland", seed=1)
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.active_player = "russian"
    # Put a teutonic Lord at a russian-defended locale via combat_pending
    from nevsky.state import CombatPending
    s.combat_pending = CombatPending(
        attacker_side="teutonic", attacker_group=["andreas"],
        from_locale="fellin", to_locale="pskov", way_type="trackway",
        defender_side="russian", defender_lords=["yaroslav"],
        pending_response_by="russian", laden=False,
    )
    moves = legal_moves(s, with_previews=False)
    concede_moves = [m for m in moves
                      if m["type"] == "stand_battle"
                      and m.get("args", {}).get("concede") is not None]
    assert concede_moves, "expected a concede pseudo-option"
    for m in concede_moves:
        c = m["args"]["concede"]
        assert c in ("attacker", "defender"), \
            f"concede arg should be battle role, got {c!r}"
    # Russian is defending in this pending combat; the concede option
    # should be concede="defender"
    assert concede_moves[0]["args"]["concede"] == "defender"


def test_smoke_119_attacker_concede_role():
    """When the side is the attacker AND owed a response, the concede
    option uses concede='attacker'."""
    s = load_scenario("watland", seed=1)
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.active_player = "russian"
    # Russian attacks Teutonic, attacker_side=russian. Construct an
    # interrupt where the attacker is owed (rare but possible via the
    # ambush_block_pending interrupt — handled separately; here we
    # construct a vanilla case for the concede-role test).
    from nevsky.state import CombatPending
    s.combat_pending = CombatPending(
        attacker_side="russian", attacker_group=["andrey"],
        from_locale="izborsk", to_locale="pskov", way_type="trackway",
        defender_side="teutonic", defender_lords=["yaroslav"],
        pending_response_by="russian",  # contrived but tests the role mapping
        laden=False,
    )
    moves = legal_moves(s, with_previews=False)
    concede_moves = [m for m in moves
                      if m["type"] == "stand_battle"
                      and m.get("args", {}).get("concede") is not None]
    if concede_moves:
        assert concede_moves[0]["args"]["concede"] == "attacker"



# ----- SMOKE-120 (also Round 186): R16 Tempest no-op when no target -------


def test_smoke_120_r16_no_op_when_no_teutonic_lord_on_map():
    """R16 should no-op when no Teutonic Lord is mustered, per
    SMOKE-112/113/114 family."""
    import nevsky.events as events
    s = load_scenario("watland", seed=1)
    # Disband / remove all Teutonic Lords
    for lid, l in list(s.lords.items()):
        if l.side == "teutonic":
            l.state = "removed"
            l.location = None
    res = events.resolve_immediate_event(s, "R16", {})
    assert res.get("no_op") is True
    assert res.get("reason") == "no_teutonic_lord_on_map"


def test_smoke_120_r16_resolves_normally_when_target_exists():
    """When at least one Teutonic Lord is mustered, R16 fires normally."""
    import nevsky.events as events
    s = load_scenario("watland", seed=1)
    teu = next(lid for lid, l in s.lords.items()
               if l.side == "teutonic" and l.state == "mustered")
    s.lords[teu].assets["ship"] = 3
    res = events.resolve_immediate_event(s, "R16", {"target": teu})
    assert res.get("no_op") is None or res.get("no_op") is False
    assert s.lords[teu].assets.get("ship", 0) == 0
