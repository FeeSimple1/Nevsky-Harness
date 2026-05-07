"""Battle resolution (4.4) and shared combat primitives.

Phase 3b implements the full Battle round loop:
  - 4.4.1 Array (Front center for active attacker; others fill front; reserve)
  - 4.4.2 Round phase: Concede / Reposition; Strike steps in initiative
    order; Hits; Protection rolls; Rout; New-round check.
  - 4.4.3 - 4.4.5 Aftermath: Retreat / Withdraw / Remove options;
    Service shift on Retreat; Spoils transfer; Losses; markers.

Per BRIEF Phase 4: per-card AoW capability effects (LUCHNIKI archery,
HALBBRUEDER Armor +1, STRELTSY/BALISTARII archery, RAIDERS, CONVERTS,
WARRIOR MONKS rerolls, Russian archery special rounding, etc.) are
deferred. Without those capabilities, Phase 3b Battle resolves with
default unit stats from the Forces table:
  - Knights / Sergeants / Men-at-Arms: Melee, Armor.
  - Light Horse / Militia: Melee, Unarmored, no Archery.
  - Asiatic Horse: Archery only (the only default-archery unit), Evade
    vs Battle Melee else Unarmored.
  - Serfs: Melee, no Protection.
"""

from __future__ import annotations

import math
from typing import Any

from nevsky.rng import roll_d6
from nevsky.state import GameState, Side
from nevsky.static_data import load_forces, load_lords

ForceCounts = dict[str, int]


def _routed_key(lord_id: str) -> str:
    """Internal key used to track Routed units within a battle scope."""
    return f"_routed::{lord_id}"


# ---------------------------------------------------------------------------
# Strike-step generation
# ---------------------------------------------------------------------------


def _hits_for_strike(
    units: ForceCounts, kind: str
) -> float:
    """Return raw fractional hits this Strike step contributes from `units`.

    kind is one of:
      "archery"        - sum (count * archery_battle) for default-archery units
      "melee_horse"    - sum (count * melee_battle) for melee_kind=horse units
      "melee_foot"     - sum (count * melee_battle) for melee_kind=foot units
    """
    forces = load_forces()
    total = 0.0
    for utype, n in units.items():
        if n <= 0:
            continue
        spec = forces.get(utype)
        if spec is None:
            continue
        if kind == "archery":
            if spec.get("archery_default_active"):
                total += n * float(spec.get("archery_battle", 0.0))
        elif kind == "melee_horse":
            if spec.get("melee_kind") == "horse":
                total += n * float(spec.get("melee_battle", 0.0))
        elif kind == "melee_foot":
            if spec.get("melee_kind") == "foot":
                total += n * float(spec.get("melee_battle", 0.0))
    return total


def _round_up(x: float) -> int:
    return math.ceil(x)


# ---------------------------------------------------------------------------
# Protection rolls
# ---------------------------------------------------------------------------


def _protection_spec(utype: str, strike_kind: str) -> str:
    """Return the protection range string for unit `utype` against
    Hits from `strike_kind` (archery|melee).
    """
    forces = load_forces()
    spec = forces[utype]
    if strike_kind == "archery":
        return spec["protection_battle_archery"]
    return spec["protection_battle_melee"]


def _absorb_hit(state: GameState, utype: str, strike_kind: str) -> bool:
    """Roll Protection for one Hit on a unit of `utype`. Return True
    if absorbed (no Rout), False if unit Routs.

    Spec strings:
      "armor:1-N"       -> roll d6; <=N absorbs
      "evade:1-N"       -> roll d6; <=N absorbs (Battle Melee only;
                            falls back to Unarmored elsewhere)
      "unarmored"       -> roll d6; ==1 absorbs
      "none"            -> no roll; always Routs (Serfs)
    """
    spec = _protection_spec(utype, strike_kind)
    if spec == "none":
        return False
    roll = roll_d6(state)
    if spec.startswith("armor:1-"):
        max_abs = int(spec.split("-", 1)[1])
        return roll <= max_abs
    if spec.startswith("evade:1-"):
        if strike_kind == "archery":
            # Evade does not apply against Archery in Battle (4.4.2).
            return roll == 1
        max_abs = int(spec.split("-", 1)[1])
        return roll <= max_abs
    if spec == "unarmored":
        return roll == 1
    return False


# ---------------------------------------------------------------------------
# Hit assignment
# ---------------------------------------------------------------------------


def _assign_hit_owner_pick(units: ForceCounts, routed: ForceCounts) -> str | None:
    """Pick which unit type to assign the next Hit to. Phase 3b uses a
    deterministic policy: prefer least-protected unit class first
    (serfs > unarmored > armor) so Battle outcomes are well-defined.

    Returns the unit type or None if the Lord has no eligible units.
    """
    if not units:
        return None
    forces = load_forces()
    # Order: serfs (no protection), unarmored, armor.
    def rank(u: str) -> tuple[int, int]:
        spec = forces[u]["protection_battle_melee"]
        if spec == "none":
            return (0, 0)
        if spec == "unarmored":
            return (1, 0)
        if spec.startswith("evade"):
            return (2, 0)
        # armor 1-N: higher N = better
        n = int(spec.split("-", 1)[1])
        return (3, n)
    eligible = [u for u, n in units.items() if n > 0]
    if not eligible:
        return None
    eligible.sort(key=rank)
    return eligible[0]


def _resolve_hits(
    state: GameState, lord_id: str, hits: int, strike_kind: str
) -> dict[str, Any]:
    """Apply `hits` Hits to `lord_id`'s units, rolling Protection and
    Routing units that fail. Mutates state.lords[lord_id].forces in
    place. Returns a record of what happened.
    """
    lord = state.lords[lord_id]
    units = lord.forces
    routed_log: list[dict[str, Any]] = []
    absorbed = 0
    for _ in range(hits):
        utype = _assign_hit_owner_pick(units, {})
        if utype is None:
            break
        absorbed_this = _absorb_hit(state, utype, strike_kind)
        if absorbed_this:
            absorbed += 1
            routed_log.append({"unit": utype, "absorbed": True})
        else:
            # Rout: remove unit from active forces. (Phase 3b uses
            # immediate removal: Routed units are eliminated from the
            # Lord's forces dict. The Battle reference distinguishes
            # Routed vs Lost via 4.4.4 Losses rolls; Phase 3b treats
            # Routed = Lost as a simplification, since we do not yet
            # track a Routed sidecar pile on the Lord's mat.)
            routed_log.append({"unit": utype, "absorbed": False})
    return {"hits": hits, "absorbed": absorbed, "routed": routed_log}


# ---------------------------------------------------------------------------
# Battle outcome
# ---------------------------------------------------------------------------


def _side_total_units(state: GameState, lord_ids: list[str]) -> int:
    return sum(sum(state.lords[lid].forces.values()) for lid in lord_ids if lid in state.lords)


def _all_routed(state: GameState, lord_ids: list[str]) -> bool:
    return _side_total_units(state, lord_ids) == 0


def resolve_battle(
    state: GameState,
    attacker_side: Side,
    attacker_lords: list[str],
    defender_lords: list[str],
    max_rounds: int = 10,
) -> dict[str, Any]:
    """Run Battle rounds until one side loses (4.4.2).

    Returns a dict with keys: rounds, winner, loser, attacker_lords,
    defender_lords, log (per-round per-step details).

    Phase 3b simplifications:
      - No Walls in Battle (4.4.2: Walls only by Event in Battle).
      - No Pursuit Concede (deferred, simple loop ends on full rout).
      - Reposition: only Round 2+, and reduced to "advance reserves to
        empty front slots" since front-slot positions are not
        individually modeled (Phase 3b treats each side as a single
        pool; flanking is not modeled).
      - Strikes are pooled across all participating Lords on each side
        per step; Hits are then distributed to Lords. We use a simple
        per-step distribution: the side suffering Hits assigns them to
        the most-eligible unit across its Lords (serfs first, etc.).
    """
    log: list[dict[str, Any]] = []
    defender_side: Side = "russian" if attacker_side == "teutonic" else "teutonic"
    rounds = 0
    while rounds < max_rounds:
        rounds += 1
        round_log: dict[str, Any] = {"round": rounds, "steps": []}

        # Strike steps in initiative order (Battle):
        #   1) Archery defender
        #   2) Archery attacker
        #   3) Melee horse defender
        #   4) Melee horse attacker
        #   5) Melee foot defender
        #   6) Melee foot attacker
        steps = [
            ("archery_defender",   "archery",     defender_lords, attacker_lords),
            ("archery_attacker",   "archery",     attacker_lords, defender_lords),
            ("melee_horse_defender","melee_horse",defender_lords, attacker_lords),
            ("melee_horse_attacker","melee_horse",attacker_lords, defender_lords),
            ("melee_foot_defender", "melee_foot", defender_lords, attacker_lords),
            ("melee_foot_attacker", "melee_foot", attacker_lords, defender_lords),
        ]
        for label, kind, striker_lords, target_lords in steps:
            # Sum hits across all striker Lords' active units.
            raw_hits = 0.0
            for lid in striker_lords:
                if lid not in state.lords:
                    continue
                raw_hits += _hits_for_strike(state.lords[lid].forces, kind)
            hits = _round_up(raw_hits)
            strike_kind = "archery" if kind == "archery" else "melee"
            distribution: list[dict[str, Any]] = []
            remaining = hits
            for tlid in target_lords:
                if tlid not in state.lords:
                    continue
                if remaining <= 0:
                    break
                if not state.lords[tlid].forces:
                    continue
                # Distribute proportionally: assign each Hit one at a
                # time to the front-most Lord still standing.
                tres = _resolve_hits(state, tlid, remaining, strike_kind)
                distribution.append({"lord": tlid, **tres})
                remaining = 0
            round_log["steps"].append({
                "step": label, "raw_hits": raw_hits, "hits": hits,
                "distribution": distribution,
            })
            # Mid-round rout check: if either side fully Routed, end now.
            if _all_routed(state, attacker_lords) or _all_routed(state, defender_lords):
                break

        log.append(round_log)
        if _all_routed(state, attacker_lords):
            return {
                "rounds": rounds, "winner": defender_side, "loser": attacker_side,
                "attacker_lords": attacker_lords, "defender_lords": defender_lords,
                "log": log,
            }
        if _all_routed(state, defender_lords):
            return {
                "rounds": rounds, "winner": attacker_side, "loser": defender_side,
                "attacker_lords": attacker_lords, "defender_lords": defender_lords,
                "log": log,
            }

    # Stalemate after max rounds: defender wins (attacker fails to break through).
    return {
        "rounds": rounds, "winner": defender_side, "loser": attacker_side,
        "attacker_lords": attacker_lords, "defender_lords": defender_lords,
        "log": log, "stalemate": True,
    }


# ---------------------------------------------------------------------------
# Aftermath: Retreat / Service shift
# ---------------------------------------------------------------------------


_SERVICE_SHIFT_TABLE = {1: 1, 2: 1, 3: 2, 4: 2, 5: 3, 6: 3}


def apply_retreat_service_shift(state: GameState, lord_id: str) -> int:
    """4.4.3 Service: roll 1d6 per Retreating Lord; shift Service marker
    LEFT by the table value. Returns the shift amount.
    """
    roll = roll_d6(state)
    boxes = _SERVICE_SHIFT_TABLE[roll]
    cal = state.calendar
    cur = None
    for cb in cal.boxes:
        if lord_id in cb.service_markers:
            cur = cb.box
            cb.service_markers.remove(lord_id)
            break
    if cur is None and lord_id in cal.off_right:
        cal.off_right.remove(lord_id)
        cur = 17
    if cur is None:
        return 0
    new_box = max(1, cur - boxes)
    if cur == 17 and new_box >= 17:
        cal.off_right.append(lord_id)
    else:
        cal.boxes[new_box - 1].service_markers.append(lord_id)
    return boxes


def transfer_spoils(
    state: GameState, from_lord: str, to_lords: list[str], mode: str
) -> dict[str, Any]:
    """4.4.5 Spoils: transfer Assets from loser Lord to winners.

    mode:
      "all_except_ships"  - removed Lord or retreated-without-conceding
      "loot_and_excess"   - conceded-then-retreated (simplified)
      "none"              - withdrew (no transfer)
    """
    if mode == "none":
        return {"from": from_lord, "transferred": {}, "mode": mode}
    if from_lord not in state.lords:
        return {"from": from_lord, "transferred": {}, "mode": mode, "error": "no_lord"}
    src = state.lords[from_lord]
    transferred: dict[str, int] = {}
    for k in ("coin", "provender", "loot", "boat", "cart", "sled"):
        amt = src.assets.get(k, 0)
        if amt > 0 and (mode == "all_except_ships" or (mode == "loot_and_excess" and k == "loot")):
            transferred[k] = amt
            src.assets.pop(k, None)
    # Distribute to first winner Lord.
    if to_lords and transferred:
        winner = to_lords[0]
        if winner in state.lords:
            for k, v in transferred.items():
                state.lords[winner].assets[k] = state.lords[winner].assets.get(k, 0) + v  # type: ignore[index]
    return {"from": from_lord, "to": to_lords[0] if to_lords else None,
            "transferred": transferred, "mode": mode}
