"""SMOKE-101 (Round 131): Ransom-capability gaps in Lord-removal paths.

Per `apply_ransom` docstring (4.4 Aftermath / 4.5.2 Sack): "Called when
an enemy Lord is removed in Battle/Storm or while Besieged."

Pre-Pass-2 the harness called `apply_ransom` in three branches:
  - `_h_stand_battle`  zero-forces removal
  - `_h_cmd_storm`     Sack of besieged Lords
  - `_h_cmd_sally`     successful sally removal — actually NOT called
                       before this round (see below).

Four branches were missing the call:

  1. `_h_stand_battle` — defender has forces but no retreat path
     (all neighbors blocked by enemy Lord/Stronghold/Conquered marker).
     The zero-forces branch above called apply_ransom; this branch did
     not. Mirror gap (same shape as SMOKE-098/099).

  2. `_h_cmd_sally` failed-Sally path — sallying Lord with 0 forces
     swept by SMOKE-007 logic. Killer is the besiegers (the winners
     of the failed Sally).

  3. `_h_cmd_sally` successful-Sally path — besieger with 0 forces
     removed. Killer is the sallying side.

  4. `_h_cmd_sally` successful-Sally path — besieger has forces but
     no retreat path. Same killer.

All four now call apply_ransom before _remove_lord_permanently, with
the appropriate killer_side argument, and append the result onto
`aftermath["ransom"]` if Ransom is in play.

Audit pattern: "Mirror gaps" — one branch of a switch-like structure
handles something correctly; the sibling branches forget. Same family
as SMOKE-098 (Storm winner-restore) and SMOKE-099 (Sally winner-
restore) where Battle did the right thing and Storm/Sally didn't.
"""
from __future__ import annotations

import inspect

import nevsky.actions  # noqa: F401
import nevsky.campaign as camp


# --- Source-text checks: each branch now calls apply_ransom ---


def test_smoke_101_battle_no_retreat_branch_calls_apply_ransom():
    """Fix #1: _h_stand_battle no-retreat-path branch."""
    src = inspect.getsource(camp._h_stand_battle)
    # Find the no-retreat branch (search for "No retreat possible").
    idx = src.find("No retreat possible")
    assert idx > 0, "no-retreat branch not found in _h_stand_battle"
    # Take a slice of the next ~30 lines after the marker.
    branch_slice = src[idx:idx + 1200]
    assert "SMOKE-101" in branch_slice, \
        "SMOKE-101 marker missing from Battle no-retreat branch"
    assert "apply_ransom" in branch_slice, \
        "apply_ransom not called in Battle no-retreat branch"
    # And before _rem (the removal call).
    ransom_pos = branch_slice.find("apply_ransom")
    rem_pos = branch_slice.find("_rem(state, lid")
    assert ransom_pos > 0 and rem_pos > 0
    assert ransom_pos < rem_pos, "apply_ransom must be called BEFORE _rem"


def test_smoke_101_failed_sally_zero_forces_calls_apply_ransom():
    """Fix #2: _h_cmd_sally failed-Sally zero-forces removal."""
    src = inspect.getsource(camp._h_cmd_sally)
    idx = src.find("SMOKE-007 fix: any sallying Lord with 0 forces")
    assert idx > 0, "failed-Sally zero-forces branch not found"
    branch_slice = src[idx:idx + 1500]
    assert "SMOKE-101" in branch_slice
    assert "apply_ransom" in branch_slice
    # killer_side computed for failed sally must be the besiegers.
    assert "killer_side_failed_sally" in branch_slice
    ransom_pos = branch_slice.find("apply_ransom")
    rem_pos = branch_slice.find("_rem(state, lid")
    assert ransom_pos > 0 and rem_pos > 0
    assert ransom_pos < rem_pos


def test_smoke_101_sally_win_zero_forces_calls_apply_ransom():
    """Fix #3: _h_cmd_sally successful-Sally defender zero-forces."""
    src = inspect.getsource(camp._h_cmd_sally)
    # The success branch is after "Sallying side won." marker.
    idx = src.find("Sallying side won. Besieging side Lords lose")
    assert idx > 0, "sally success branch not found"
    branch_slice = src[idx:]
    # Locate the "if not l.forces:" inside this branch.
    zf_idx = branch_slice.find("if not l.forces:")
    assert zf_idx > 0
    zero_forces_block = branch_slice[zf_idx:zf_idx + 800]
    assert "SMOKE-101" in zero_forces_block
    assert "apply_ransom" in zero_forces_block
    ransom_pos = zero_forces_block.find("apply_ransom")
    rem_pos = zero_forces_block.find("_rem(state, lid")
    assert ransom_pos > 0 and rem_pos > 0
    assert ransom_pos < rem_pos


def test_smoke_101_sally_win_no_retreat_calls_apply_ransom():
    """Fix #4: _h_cmd_sally successful-Sally defender no-retreat."""
    src = inspect.getsource(camp._h_cmd_sally)
    idx = src.find("Sallying side won. Besieging side Lords lose")
    assert idx > 0
    branch_slice = src[idx:]
    # The no-retreat sub-branch inside the else: clause has two
    # "if target is None:" markers (one for Sally and one mirroring
    # Battle); locate the one that's followed by "spoils = transfer_spoils"
    # and a _rem call.
    nr_idx = branch_slice.find("if target is None:")
    assert nr_idx > 0
    no_retreat_block = branch_slice[nr_idx:nr_idx + 1200]
    assert "SMOKE-101" in no_retreat_block
    assert "apply_ransom" in no_retreat_block
    ransom_pos = no_retreat_block.find("apply_ransom")
    rem_pos = no_retreat_block.find("_rem(state, lid")
    assert ransom_pos > 0 and rem_pos > 0
    assert ransom_pos < rem_pos


# --- Killer-side correctness ---


def test_smoke_101_failed_sally_killer_is_besiegers():
    """In failed-Sally, the killer is the besiegers — _other(sd) — not sd."""
    src = inspect.getsource(camp._h_cmd_sally)
    idx = src.find("killer_side_failed_sally")
    assert idx > 0
    # The assignment line should compute it from sd as the *other* side.
    assignment_slice = src[idx:idx + 400]
    # Must compute "russian" when sd == "teutonic" (or some equivalent
    # other(sd) expression).
    assert ('sd == "teutonic"' in assignment_slice
            and '"russian"' in assignment_slice
            and '"teutonic"' in assignment_slice)


def test_smoke_101_sally_win_killer_is_sd():
    """In successful Sally, the killer is the sallying side itself (sd)."""
    src = inspect.getsource(camp._h_cmd_sally)
    idx = src.find("Sallying side won. Besieging side Lords lose")
    branch_slice = src[idx:]
    # Both Sally-win ransom calls use sd as killer.
    # Count apply_ransom calls and the sd argument in the slice.
    ransom_calls = [i for i in range(len(branch_slice))
                    if branch_slice[i:i + 12] == "apply_ransom"]
    assert len(ransom_calls) == 2, \
        f"expected 2 apply_ransom calls in Sally-win branch, got {len(ransom_calls)}"
    for pos in ransom_calls:
        call_slice = branch_slice[pos:pos + 80]
        assert "sd, locale_id" in call_slice, \
            f"sally-win apply_ransom must pass sd as killer; got {call_slice!r}"


# --- Functional check: apply_ransom hooks aftermath["ransom"] correctly ---


def test_smoke_101_apply_ransom_no_recipient_when_no_friendly_lord():
    """If killer side has Ransom in play but no friendly Lord is at the
    Locale, apply_ransom still returns {"ransom": True} with the coin
    "lost_no_recipient" — same shape used by existing callers."""
    from nevsky.campaign import apply_ransom
    from nevsky.scenarios import load_scenario

    s = load_scenario("watland", seed=1)
    s.decks.teutonic.capabilities_in_play = ["T16"]  # Teutonic Ransom
    rus = next(lid for lid, l in s.lords.items()
               if l.side == "russian" and l.state == "mustered")
    # No Teutonic Lord at pskov for the test.
    for lid, l in s.lords.items():
        if l.side == "teutonic" and l.location == "pskov":
            l.location = "riga"
    res = apply_ransom(s, rus, "teutonic", "pskov")
    assert res["ransom"] is True
    assert "coin_lost_no_recipient" in res


def test_smoke_101_apply_ransom_no_ransom_capability():
    """If killer side has no Ransom in play, return {"ransom": False}."""
    from nevsky.campaign import apply_ransom
    from nevsky.scenarios import load_scenario

    s = load_scenario("watland", seed=2)
    # No Ransom capability for teutonic.
    s.decks.teutonic.capabilities_in_play = []
    rus = next(lid for lid, l in s.lords.items()
               if l.side == "russian" and l.state == "mustered")
    res = apply_ransom(s, rus, "teutonic", "pskov")
    assert res["ransom"] is False
