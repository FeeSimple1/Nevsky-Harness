"""Round 31 — Storm position-tracking invariants.

SMOKE-017: when a defender Front Lord is Routed (no forces) and a
Reserve Lord forced-advances to Front, the previous Front Lord must
be demoted from "storm_front" so we don't end up with two Lords
labeled Front simultaneously.

Combat resolution itself is not affected (strike logic filters by
Lord.forces), but the position state would otherwise be inconsistent
and could break rendering, save/load, or future invariants that
assume "exactly 1 Front per side".
"""
from __future__ import annotations

from nevsky.battle import resolve_storm
from nevsky.scenarios import load_scenario


def _muster(scenario, t_list, r_list, seed=1, box=1):
    s = load_scenario(scenario, seed=seed)
    s.meta.box = box
    teu_ids: list[str] = []
    rus_ids: list[str] = []
    for lid, l in s.lords.items():
        if l.side == "teutonic" and len(teu_ids) < len(t_list):
            l.state = "mustered"; l.location = "novgorod"
            l.in_stronghold = False
            l.forces = dict(t_list[len(teu_ids)])
            teu_ids.append(lid)
        elif l.side == "russian" and len(rus_ids) < len(r_list):
            l.state = "mustered"; l.location = "novgorod"
            l.in_stronghold = True
            l.forces = dict(r_list[len(rus_ids)])
            rus_ids.append(lid)
    return s, teu_ids, rus_ids


def test_storm_reserve_advance_demotes_old_front():
    """Defender [empty Lord, full Lord]: Reserve advances to Front;
    the empty Lord must be demoted from "storm_front" so only one
    Lord ends up labeled Front."""
    s, t_ids, r_ids = _muster(
        "crusade_on_novgorod",
        [{"knights": 3, "men_at_arms": 3}],
        [{}, {"knights": 3, "men_at_arms": 3}],
    )
    res = resolve_storm(
        s, "teutonic", t_ids, r_ids,
        "novgorod", walls_max=3, siege_markers=3,
        garrison={"men_at_arms": 3},
    )
    pos = res["defender_storm_positions"]
    front_count = sum(1 for p in pos.values() if p == "storm_front")
    assert front_count == 1, (
        f"Exactly 1 defender Lord should be at storm_front; got "
        f"{front_count} (positions={pos})"
    )


def test_storm_reserve_advance_preserves_invariant_across_multiple_rounds():
    """Same fixture but with attacker that pummels — verify the
    invariant holds throughout."""
    s, t_ids, r_ids = _muster(
        "crusade_on_novgorod",
        [{"knights": 5, "men_at_arms": 5}],
        [{}, {"knights": 1}],  # tiny reserve so it routs quickly
    )
    res = resolve_storm(
        s, "teutonic", t_ids, r_ids,
        "novgorod", walls_max=1, siege_markers=4,
        garrison={},
    )
    pos = res["defender_storm_positions"]
    front_count = sum(1 for p in pos.values() if p == "storm_front")
    # At end either 1 (the reserve survived as Front) or 0 (everyone
    # routed). NEVER 2.
    assert front_count <= 1, (
        f"More than 1 Lord at storm_front; positions={pos}"
    )


def test_storm_attacker_reserve_advance_invariant():
    """Symmetry: same invariant for attacker side."""
    s, t_ids, r_ids = _muster(
        "crusade_on_novgorod",
        [{}, {"knights": 3, "men_at_arms": 3}],
        [{"knights": 1, "men_at_arms": 1}],
    )
    res = resolve_storm(
        s, "teutonic", t_ids, r_ids,
        "novgorod", walls_max=3, siege_markers=3,
        garrison={"men_at_arms": 1},
    )
    pos = res["attacker_storm_positions"]
    front_count = sum(1 for p in pos.values() if p == "storm_front")
    assert front_count == 1, (
        f"Exactly 1 attacker Lord should be at storm_front; got "
        f"{front_count} (positions={pos})"
    )
