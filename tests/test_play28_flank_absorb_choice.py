"""PLAY-28 (4.4.2): Flanking-absorb choice.

Rulebook 4.4.2 APPLY HITS TO LORDS: "A Player with a Flanking Lord where
no enemies are Flanking the target selects either the Flanking or
directly opposed Lord to take Hits." (Also STRIKE: "A Flanking Lord may
absorb Hits from a Lord he Flanks if no enemies Flank the target Lord.")

Geometry used: attacker A at Front center (opposed to defender T at
center); defender F at Front left has no attacker opposite, so F Flanks
A. No attacker Flanks T. The defender may therefore choose whether A's
Hits land on T (directly opposed) or F (the Flanking Lord). Serfs are the
Forces (no Protection roll -> deterministic Rout).
"""

from __future__ import annotations

from nevsky.battle import BattleDecisionContext, resolve_battle, _front_flankers_of
from nevsky.scenarios import load_scenario


def _setup():
    s = load_scenario("watland", seed=1)
    teu = [lid for lid, l in s.lords.items() if l.side == "teutonic"][0]
    rus = [lid for lid, l in s.lords.items() if l.side == "russian"][:2]
    T, F = rus
    for lid in [teu] + rus:
        s.lords[lid].state = "mustered"
        s.lords[lid].location = "pskov"
    s.lords[teu].forces = {"serfs": 2}   # -> 1 Melee Hit
    s.lords[T].forces = {"serfs": 1}
    s.lords[F].forces = {"serfs": 1}
    return s, teu, T, F


def _run(scripted=None):
    s, teu, T, F = _setup()
    ctx = BattleDecisionContext(scripted=scripted or [])
    res = resolve_battle(
        s, attacker_side="teutonic", attacker_lords=[teu], defender_lords=[T, F],
        max_rounds=1, decision_ctx=ctx,
        attacker_positions={teu: "center"},
        defender_positions={T: "center", F: "left"},
    )
    return s, teu, T, F, ctx, res


def test_default_hits_go_to_directly_opposed_lord():
    s, teu, T, F, ctx, res = _run()  # fallback = leftmost = opposed
    # The choice was offered, defaulting to the opposed Lord T.
    fa = [e for e in ctx.log if e["type"] == "flank_absorb"]
    assert fa, "flank_absorb choice should be offered"
    assert fa[0]["chosen"] == T
    assert s.lords[T].routed_units, "opposed Lord T should absorb by default"
    assert not s.lords[F].routed_units, "flank Lord F untouched by default"


def test_defender_can_redirect_hits_onto_flanking_lord():
    s0, teu0, T0, F0, _, _ = _run()  # discover ids
    s, teu, T, F, ctx, res = _run(
        scripted=[{"type": "flank_absorb", "chosen": F0}]
    )
    assert s.lords[F].routed_units, "flank Lord F should absorb the Hits"
    assert not s.lords[T].routed_units, "opposed Lord T should be spared"


def test_no_choice_when_an_enemy_also_flanks_the_target():
    """Precondition: the choice exists only if NO enemy Flanks the target.
    Add an attacker at right (Flanks T) -> no flank_absorb offered."""
    s = load_scenario("watland", seed=1)
    teu = [lid for lid, l in s.lords.items() if l.side == "teutonic"][:2]
    rus = [lid for lid, l in s.lords.items() if l.side == "russian"][:2]
    A, A2 = teu
    T, F = rus
    for lid in teu + rus:
        s.lords[lid].state = "mustered"
        s.lords[lid].location = "pskov"
        s.lords[lid].forces = {"serfs": 2}
    ctx = BattleDecisionContext()
    resolve_battle(
        s, attacker_side="teutonic", attacker_lords=[A, A2], defender_lords=[T, F],
        max_rounds=1, decision_ctx=ctx,
        attacker_positions={A: "center", A2: "right"},
        defender_positions={T: "center", F: "left"},
    )
    assert not [e for e in ctx.log if e["type"] == "flank_absorb"], (
        "no flank_absorb choice when an enemy also Flanks the target"
    )


def test_front_flankers_helper():
    s, teu, T, F = _setup()
    # F (defender left) Flanks the attacker A (center); A does not Flank T.
    assert _front_flankers_of(s, teu, {teu: "center"}, {T: "center", F: "left"}) == [F]
    assert _front_flankers_of(s, T, {T: "center", F: "left"}, {teu: "center"}) == []
