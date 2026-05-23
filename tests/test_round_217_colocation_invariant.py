"""Round 217 — co-location invariant (Inferno cross-project advisory).

Inferno-Harness reported a Retreat that applied the Service penalty but
never relocated the loser, leaving opposing un-besieged Lords stacked in
the battle Locale -- and it hid because (a) the auto-resolver never
Concedes (so "loser survives -> Retreat" is a cold path) and (b) there
was no invariant forbidding the illegal state.

Nevsky was checked: the Battle and Sally Retreat paths DO relocate the
loser (campaign.py: `lord.location = target`) with destination rules
(attacker-loser -> approach Locale; defender-loser -> legal neighbor
excluding the approach Way; no enemy Lord/Stronghold at the destination;
no Sail Way). So the relocation bug is absent. This round adds the
missing invariant the advisory recommends regardless -- it closes the
whole class -- and exercises the cold forced-Concede path explicitly.

Invariant: no two MUSTERED Lords of opposing sides, BOTH outside a
Stronghold (in_stronghold False), may share a Locale. Besieged-inside vs
besiegers-outside is legal and is excluded via the in_stronghold flag.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

from nevsky.actions import apply_action
from nevsky.legal_moves import legal_moves
from nevsky.scenarios import load_scenario
from nevsky.state import CombatPending, GameState


def colocation_violations(state: GameState):
    """Locales with >=2 opposing MUSTERED Lords both OUTSIDE a Stronghold.
    Two exclusions keep this to genuinely-illegal states:
      - in_stronghold=True Lords are besieged-inside (legal vs besiegers).
      - While a combat is pending/resolving (state.combat_pending set), the
        attacker is legally co-located with the defender at cp.to_locale
        for the duration of the Approach/Battle -- that Locale is excluded.
    """
    from collections import defaultdict
    by_loc = defaultdict(set)
    for lid, l in state.lords.items():
        if l.state == "mustered" and l.location is not None and not l.in_stronghold:
            by_loc[l.location].add(l.side)
    bad = [loc for loc, sides in by_loc.items() if len(sides) > 1]
    cp = state.combat_pending
    if cp is not None:
        bad = [loc for loc in bad if loc != cp.to_locale]
    return bad


def test_invariant_holds_on_fresh_scenarios():
    for sc in ("watland", "pleskau", "peipus", "return_of_the_prince",
               "return_of_the_prince_nicolle", "crusade_on_novgorod"):
        s = load_scenario(sc, seed=1)
        assert colocation_violations(s) == [], f"{sc} starts with co-located enemies"


def test_no_colocation_after_forced_concede_battle():
    """The cold path: a defender Concedes in a 1v1 battle, loses but
    survives with units -> must Retreat (relocate), not stay stacked with
    the attacker. Run several seeds to cover dice variation."""
    saw_survivor_retreat = False
    for seed in range(1, 16):
        s = load_scenario("watland", seed=seed)
        s.meta.phase = "campaign"
        s.meta.campaign_step = "command"
        s.meta.active_player = "russian"
        s.lords["andreas"].location = "pskov"
        s.lords["andreas"].forces = {"knights": 2}
        s.lords["andreas"].in_stronghold = False
        s.lords["vladislav"].state = "mustered"
        s.lords["vladislav"].location = "pskov"
        s.lords["vladislav"].forces = {"militia": 10}  # big -> survives the loss
        s.lords["vladislav"].in_stronghold = False
        s.combat_pending = CombatPending(
            attacker_side="teutonic", attacker_group=["andreas"],
            defender_side="russian", defender_lords=["vladislav"],
            from_locale="izborsk", to_locale="pskov", way_type="trackway",
            pending_response_by="russian",
        )
        apply_action(s, {"type": "stand_battle", "side": "russian",
                         "args": {"concede": "defender"}})
        # KEY ASSERTION (advisory #3): no illegal co-location, ever.
        assert colocation_violations(s) == [], f"co-location after concede (seed {seed})"
        v = s.lords["vladislav"]
        if v.state == "mustered":
            # Survived the loss -> must have relocated out of the battle Locale.
            assert v.location != "pskov", f"survivor not relocated (seed {seed})"
            saw_survivor_retreat = True
    assert saw_survivor_retreat, "no seed produced a surviving conceding loser to retreat"


def _concrete(state, side):
    spec = importlib.util.spec_from_file_location(
        "sp_mod", Path(__file__).resolve().parent.parent / "scripts" / "self_play.py")
    sp = importlib.util.module_from_spec(spec); spec.loader.exec_module(sp)
    out = []
    for m in legal_moves(state, with_previews=False):
        if m.get("side") != side:
            continue
        if "args" in m and isinstance(m["args"], dict):
            out.append(m)
        else:
            out.extend(sp._instantiate_templated_move(state, m))
    return out


def test_invariant_holds_across_stepped_selfplay():
    """Step several games and check the invariant after EVERY applied
    action -- the illegal state would appear transiently in aftermath."""
    spec = importlib.util.spec_from_file_location(
        "sp_mod", Path(__file__).resolve().parent.parent / "scripts" / "self_play.py")
    sp = importlib.util.module_from_spec(spec); spec.loader.exec_module(sp)
    for sc, seed in [("watland", 1), ("peipus", 2), ("return_of_the_prince", 3)]:
        s = load_scenario(sc, seed=seed)
        for side in ("teutonic", "russian"):
            try:
                apply_action(s, {"type": "confirm_all_setup_transports",
                                 "side": side, "args": {}})
            except Exception:
                pass
        for step in range(4000):
            if sp._is_terminal(s):
                break
            moves = _concrete(s, s.meta.active_player)
            if not moves:
                break
            try:
                apply_action(s, {k: v for k, v in moves[0].items()
                                 if k in ("type", "side", "args")})
            except Exception:
                # try a fallback move; if none, stop this game
                applied = False
                for m in moves[1:]:
                    try:
                        apply_action(s, {k: v for k, v in m.items()
                                         if k in ("type", "side", "args")})
                        applied = True
                        break
                    except Exception:
                        continue
                if not applied:
                    break
            assert colocation_violations(s) == [], (
                f"{sc} seed={seed} step={step}: co-located enemies "
                f"{colocation_violations(s)}")
