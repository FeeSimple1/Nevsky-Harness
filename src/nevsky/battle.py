"""Battle resolution (4.4) and shared combat primitives.

Battle round loop:
  - 4.4.1 Array (Q-005 three-front-positions; Q-006 Relief Sally
    Sally / Rearguard rows).
  - 4.4.2 Round phase: Concede; Reposition (Q-005) and Adjust Rows
    (Q-006); Strike steps in initiative order; Hits; Protection rolls;
    Rout; New-round check.
  - 4.4.3 - 4.4.5 Aftermath: Retreat / Withdraw / Remove options;
    Service shift on Retreat; Spoils transfer; Losses; markers.

Per-card Arts of War effects integrated into the strike /
protection / spoils paths:
  - Luchniki (R1/R2): Light Horse + Militia Archery 0.5/unit.
  - Streltsy (R3/R13) / Balistarii (T4/T5/T6): MaA Archery 0.5/unit
    with target Armor -2.
  - Halbbrueder (T9/T10): Sergeants and MaA Armor +1.
  - Warrior Monks (T7/T15): once-per-step reroll of failed Knights
    Armor.
  - Trebuchets (T14) / Stonemasons (T17): handled at Storm/Sally
    invocation and Castle-construction handlers.

Default unit stats from the Forces table apply where no Capability
modifies them.
"""

from __future__ import annotations

import math
from typing import Any

from nevsky.rng import roll_d6
from nevsky.state import GameState, Side
from nevsky.static_data import load_forces, load_lords, load_ways

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


def _hits_for_lord_strike(
    state: "GameState", lord_id: str, kind: str
) -> float:
    """Capability-aware per-Lord Strike contribution.

    Adds Phase 4a archery extensions:
      - Luchniki (R1/R2): Light Horse and Militia gain Archery (0.5/unit).
      - Streltsy (R3/R13) / Balistarii (T4/T5/T6): Men-at-Arms gain
        Archery (0.5/unit). Archery target Armor -2 is applied at hit
        resolution time, not here.
    """
    from nevsky.capabilities import any_capability

    units = state.lords[lord_id].forces
    base = _hits_for_strike(units, kind)
    if kind != "archery":
        return base
    extra = 0.0
    if any_capability(state, lord_id, "Luchniki"):
        extra += 0.5 * units.get("light_horse", 0)
        extra += 0.5 * units.get("militia", 0)
    if any_capability(state, lord_id, "Streltsy") or any_capability(state, lord_id, "Balistarii"):
        extra += 0.5 * units.get("men_at_arms", 0)
    return base + extra


def _round_up(x: float) -> int:
    return math.ceil(x)


# ---------------------------------------------------------------------------
# Protection rolls
# ---------------------------------------------------------------------------


def _protection_spec(utype: str, strike_kind: str, in_storm: bool = False) -> str:
    """Return the protection range string for unit `utype` against
    Hits from `strike_kind` (archery|melee), using Storm protection
    when `in_storm=True` (4.5.2). Most units have identical Battle
    and Storm protection; Asiatic Horse is the exception per the
    Forces Reference ("Evade vs Battle Melee else Unarmored").
    """
    forces = load_forces()
    spec = forces[utype]
    if in_storm:
        return spec.get("protection_storm", spec.get("protection_battle_melee", "none"))
    if strike_kind == "archery":
        return spec["protection_battle_archery"]
    return spec["protection_battle_melee"]


def _absorb_hit(
    state: GameState, utype: str, strike_kind: str,
    lord_id: str | None = None,
    striker_has_armor_minus_2: bool = False,
    step_state: dict | None = None,
    in_storm: bool = False,
) -> bool:
    """Roll Protection for one Hit on a unit of `utype`. Return True
    if absorbed (no Rout), False if unit Routs.

    `in_storm`: when True, use Storm protection per Forces Reference
    ("Evade vs Battle Melee else Unarmored" for Asiatic Horse). Most
    units' Storm protection equals their Battle Melee protection.

    Phase 4a capability mods (when lord_id is provided):
      - Halbbrueder (T9/T10): owner Lord's Sergeants and MaA gain
        Armor +1 for Rout rolls (4.4.2).
      - Warrior Monks (T7/T15): owner Lord may reroll 1 failed
        Knights Armor roll per Strike step (AUDIT-002 fix:
        per-step budget enforced via step_state["wm_reroll_used",
        lord_id, strike_kind]).
      - Striker Crossbowmen / Garrison MaA: target Armor -2.

    Optional rule "no_horseback_archery" (Rules of Play 6.0): when
    enabled, Asiatic Horse Defense rolls succeed only on '1' (Unarmored
    in all situations, including Battle Melee; negates Evade).
    """
    from nevsky.capabilities import any_capability

    spec = _protection_spec(utype, strike_kind, in_storm=in_storm)
    # Optional rule: No Horseback Archery — Asiatic Horse becomes
    # effectively Unarmored (succeed only on roll 1).
    if (utype == "asiatic_horse"
            and state.meta.optional_rules.get("no_horseback_archery", False)):
        spec = "armor:1-1"
    if spec == "none":
        return False
    if (
        lord_id is not None
        and utype in ("sergeants", "men_at_arms")
        and any_capability(state, lord_id, "Halbbrueder")
        and spec.startswith("armor:1-")
    ):
        n = int(spec.split("-", 1)[1])
        spec = f"armor:1-{n + 1}"

    def _roll(spec_: str) -> bool:
        roll = roll_d6(state)
        if spec_.startswith("armor:1-"):
            max_abs = int(spec_.split("-", 1)[1])
            if striker_has_armor_minus_2:
                max_abs -= 2
            return roll <= max(0, max_abs)
        if spec_.startswith("evade:1-"):
            if strike_kind == "archery":
                return roll == 1
            max_abs = int(spec_.split("-", 1)[1])
            return roll <= max_abs
        if spec_ == "unarmored":
            return roll == 1
        return False

    absorbed = _roll(spec)
    if absorbed:
        return True
    # Warrior Monks (T7/T15): once per Knights Armor failure per
    # Strike step (per Lord). Budget tracked via step_state.
    if (
        utype == "knights"
        and lord_id is not None
        and any_capability(state, lord_id, "Warrior Monks")
    ):
        if step_state is not None:
            key = ("wm_reroll_used", lord_id, strike_kind)
            if step_state.get(key):
                return False
            step_state[key] = True
        return _roll(spec)
    return False


# ---------------------------------------------------------------------------
# Hit assignment
# ---------------------------------------------------------------------------


def _assign_hit_owner_pick(
    units: ForceCounts, routed: ForceCounts, policy: str = "weakest_first"
) -> str | None:
    """Pick which unit type to assign the next Hit to.

    `policy`:
      - "weakest_first" (default, Battle / Storm Defender / Sally):
            owner-picks order, preferring least-protected first (serfs
            > unarmored > evade > armor). The owner is "shielding" their
            stronger units behind weaker ones (4.4.2).
      - "armored_first" (Storm Attacker, 4.5.2 2E rule):
            "The Attacking side must absorb Hits with any Armored units
            before doing so with other units." Reverses the order so
            Armored absorb first; otherwise weakest-first within each
            class.

    Returns the unit type or None if the Lord has no eligible units.
    """
    if not units:
        return None
    forces = load_forces()
    # Classify each unit type by Protection family.
    def classify(u: str) -> tuple[int, int]:
        # Returns (class_rank, armor_strength). class_rank:
        #   0 = none (serfs), 1 = unarmored, 2 = evade, 3 = armor.
        # Higher armor_strength inside armor class = stronger.
        spec = forces[u]["protection_battle_melee"]
        if spec == "none":
            return (0, 0)
        if spec == "unarmored":
            return (1, 0)
        if spec.startswith("evade"):
            return (2, 0)
        n = int(spec.split("-", 1)[1])
        return (3, n)
    eligible = [u for u, n in units.items() if n > 0]
    if not eligible:
        return None
    if policy == "armored_first":
        # 4.5.2: Storm Attacker absorbs with ARMORED units first. Sort by
        # class descending (armor before evade before unarmored before
        # none), then by armor_strength descending so the highest-armor
        # type goes first.
        eligible.sort(key=lambda u: (-classify(u)[0], -classify(u)[1]))
    else:
        # Owner-picks: weakest-first.
        eligible.sort(key=classify)
    return eligible[0]


def _capped_unit_subset(units: dict[str, int], cap: int) -> dict[str, int]:
    """Return a subset of `units` whose total count <= `cap`, prioritising
    heaviest hitters first (Knights > Sergeants > MaA > Light Horse >
    Militia > Asiatic Horse > Serfs). Used for Q-008 Bridge cap on the
    front-center Lord's Melee strike list — the capped player benefits
    from selecting their strongest units to actually strike."""
    priority = ("knights", "sergeants", "men_at_arms",
                "light_horse", "militia", "asiatic_horse", "serfs")
    out: dict[str, int] = {}
    remaining = cap
    for utype in priority:
        n = units.get(utype, 0)
        if n <= 0 or remaining <= 0:
            continue
        take = min(n, remaining)
        out[utype] = take
        remaining -= take
    return out


def _striking_unit_count(
    state: GameState, lord_id: str, utype: str, rounds: int,
    bridge_target_lord: str | None,
) -> int:
    """How many units of `utype` actually Strike this round, after Q-008
    modifiers (Bridge cap). Used by Field Organ to apply the +1 Hit
    bonus only to striking units, per Arts of War Reference T10 Tips
    ('only the units Striking cause the added Hits')."""
    units = state.lords[lord_id].forces
    n = units.get(utype, 0)
    if bridge_target_lord == lord_id:
        cap = 2 * rounds
        capped = _capped_unit_subset(units, cap)
        return capped.get(utype, 0)
    return n


def _resolve_hits(
    state: GameState, lord_id: str, hits: int, strike_kind: str,
    striker_has_armor_minus_2: bool = False,
    step_state: dict | None = None,
    assignment_policy: str = "weakest_first",
    hit_flags: list[bool] | None = None,
    in_storm: bool = False,
) -> dict[str, Any]:
    """Apply `hits` Hits to `lord_id`'s units, rolling Protection and
    Routing units that fail. Mutates state.lords[lord_id].forces in
    place. Returns a record of what happened.

    `assignment_policy`:
      - "weakest_first" (default): owner-picks, weakest unit absorbs
        each Hit (Battle / Storm Defender / Sally).
      - "armored_first" (4.5.2 2E AUDIT-003): Storm Attacker absorbs
        Hits with any Armored units before non-Armored.

    `hit_flags` (Q-007 round-in-favor-of-Crossbowmen, Arts of War
    Reference R1/R2 Luchniki Tips): if provided, must have len(hits)
    elements, one bool per Hit indicating whether that specific Hit
    carries the -2-Armor reduction. Used by archery steps so the
    "crossbow Hits" come first and apply -2 Armor only to the count
    that should under the rule (round in favor of Crossbowmen). For
    non-archery steps, pass None and `striker_has_armor_minus_2` is
    applied uniformly (typically False outside archery).
    """
    lord = state.lords[lord_id]
    units = lord.forces
    routed_log: list[dict[str, Any]] = []
    absorbed = 0
    if step_state is None:
        step_state = {}
    if hit_flags is not None:
        # Pad/truncate to match `hits` count for safety; exposes a
        # mismatch as a deterministic mode rather than IndexError.
        if len(hit_flags) < hits:
            hit_flags = hit_flags + [striker_has_armor_minus_2] * (hits - len(hit_flags))
        elif len(hit_flags) > hits:
            hit_flags = hit_flags[:hits]
    for hit_index in range(hits):
        utype = _assign_hit_owner_pick(units, {}, policy=assignment_policy)
        if utype is None:
            break
        per_hit_armor_minus_2 = (
            hit_flags[hit_index] if hit_flags is not None
            else striker_has_armor_minus_2
        )
        absorbed_this = _absorb_hit(
            state, utype, strike_kind,
            lord_id=lord_id,
            striker_has_armor_minus_2=per_hit_armor_minus_2,
            step_state=step_state,
            in_storm=in_storm,
        )
        if absorbed_this:
            absorbed += 1
            routed_log.append({"unit": utype, "absorbed": True})
        else:
            # 4.4.4: Routed units move to Lord's routed_units pile, NOT
            # deleted. Losses rolls in Aftermath decide their fate.
            units[utype] = max(0, units.get(utype, 0) - 1)
            if units.get(utype, 0) == 0:
                del units[utype]
            lord.routed_units[utype] = lord.routed_units.get(utype, 0) + 1  # type: ignore[index]
            routed_log.append({"unit": utype, "absorbed": False})
    return {"hits": hits, "absorbed": absorbed, "routed": routed_log}


# ---------------------------------------------------------------------------
# Battle outcome
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Q-005: Battle Array three-front-positions, Flanking, scripted decisions
# ---------------------------------------------------------------------------
#
# The 2E Battle Array (4.4.1 / 4.4.2 page 14-15) puts Lords in three Front
# positions per side -- left, center, right -- plus Reserve. Strikes go from
# each Lord to the directly-opposed enemy Lord, or (if Flanking) to the
# closest enemy Lord in the row. Reposition happens at the start of each
# Round after the first: Reserves advance into empty Front slots; an empty
# center is filled from left or right.
#
# Several of these steps require player choice. The harness exposes a
# DecisionContext that the engine consults whenever an operator-level
# choice is needed. For tests, a `scripted_decisions` list of pre-canned
# answers is consumed in order; for live play, an optional callback is
# invoked. If neither is supplied, the `deterministic_fallback` policy
# ("leftmost") picks the leftmost legal option so unit tests written
# pre-Q-005 still behave deterministically.


# Decision types the engine may ask the operator about.
_DECISION_TYPES = (
    "initial_placement_attacker",   # which non-Active Lord goes to slot
    "initial_placement_defender",   # which Defender Lord goes to slot
    "reserve_advance",              # which Reserve Lord advances to slot
    "center_fill",                  # which left/right Lord slides to center
    "flanker_target",               # ambiguous Flanker target
)


class BattleDecisionContext:
    """Funnel for operator decisions during Battle.

    Usage:
      ctx = BattleDecisionContext(scripted=[...]) for tests, or
      ctx = BattleDecisionContext(callback=fn) for live play, or
      ctx = BattleDecisionContext() for fallback leftmost-legal.

    Engine code calls ctx.decide(decision_type, side, options, info).
    Every call appends a record to ctx.log so the battle log includes
    a trace of all operator choices.
    """

    def __init__(
        self,
        scripted: list[dict[str, Any]] | None = None,
        callback: "Any | None" = None,
        fallback: str = "leftmost",
    ) -> None:
        self.scripted: list[dict[str, Any]] = list(scripted or [])
        self.callback = callback
        self.fallback = fallback
        self.log: list[dict[str, Any]] = []

    def decide(
        self,
        decision_type: str,
        side: str,
        options: list[Any],
        info: dict[str, Any] | None = None,
    ) -> Any:
        if decision_type not in _DECISION_TYPES:
            raise ValueError(f"unknown decision type: {decision_type!r}")
        info = dict(info or {})
        if not options:
            raise ValueError("decide() called with empty options list")
        # 1. Try scripted decisions FIFO.
        if self.scripted:
            d = self.scripted.pop(0)
            if d.get("type") != decision_type:
                raise ValueError(
                    f"scripted decision type mismatch: expected {decision_type!r}, "
                    f"got {d.get('type')!r}"
                )
            chosen = d["chosen"]
            if chosen not in options:
                raise ValueError(
                    f"scripted choice {chosen!r} not in legal options {options!r} "
                    f"(decision={decision_type}, side={side}, info={info})"
                )
            entry = {
                "type": decision_type, "side": side, "options": options,
                "chosen": chosen, "rationale": d.get("rationale", "scripted"),
                "info": info,
            }
            self.log.append(entry)
            return chosen
        # 2. Try callback.
        if self.callback is not None:
            chosen = self.callback({
                "type": decision_type, "side": side, "options": options,
                "info": info,
            })
            if chosen not in options:
                raise ValueError(
                    f"callback chose {chosen!r} not in legal options {options!r}"
                )
            entry = {
                "type": decision_type, "side": side, "options": options,
                "chosen": chosen, "rationale": "callback", "info": info,
            }
            self.log.append(entry)
            return chosen
        # 3. Deterministic fallback.
        if self.fallback == "leftmost":
            chosen = options[0]
        else:
            raise ValueError(f"unknown fallback policy: {self.fallback!r}")
        entry = {
            "type": decision_type, "side": side, "options": options,
            "chosen": chosen, "rationale": f"fallback={self.fallback}",
            "info": info,
        }
        self.log.append(entry)
        return chosen


_SALLY_SLOTS = ("sally_left", "sally_center", "sally_right")
_REARGUARD_SLOTS = ("rearguard_center", "rearguard_left", "rearguard_right")
_FRONT_SLOTS = ("left", "center", "right")


def _array_sally_lords(
    state: GameState,
    sallying_lords: list[str],
    decision_ctx: BattleDecisionContext,
) -> dict[str, str]:
    """Q-006 (4.4.1 2E Relief Sally): place Sallying Lords in a row
    behind the Defenders. The first Sallying Lord goes to sally_center
    (per analogy with Active at Front center), the rest fill
    sally_left/sally_right; remainder to sally_reserve. If multiple
    candidates, operator picks per slot via decision_ctx.
    """
    positions: dict[str, str] = {}
    if not sallying_lords:
        return positions
    # First Sallying Lord -> sally_center.
    if len(sallying_lords) == 1:
        positions[sallying_lords[0]] = "sally_center"
        return positions
    # First Lord defaults to sally_center; if multiple, operator picks.
    if len(sallying_lords) > 1:
        center_choice = decision_ctx.decide(
            "initial_placement_attacker", "sally", list(sallying_lords),
            {"slot": "sally_center", "phase": "relief_sally_array"},
        )
        positions[center_choice] = "sally_center"
    others = [l for l in sallying_lords if l not in positions]
    if len(others) == 1:
        slot = decision_ctx.decide(
            "initial_placement_attacker", "sally", ["sally_left", "sally_right"],
            {"lord": others[0], "phase": "relief_sally_array_one_extra"},
        )
        positions[others[0]] = slot
    elif len(others) >= 2:
        for slot in ("sally_left", "sally_right"):
            available = [l for l in others if l not in positions]
            if not available:
                break
            chosen = decision_ctx.decide(
                "initial_placement_attacker", "sally", available,
                {"slot": slot, "phase": "relief_sally_array"},
            )
            positions[chosen] = slot
        for l in others:
            if l not in positions:
                positions[l] = "sally_reserve"
    return positions


def _shift_defender_reserves_to_rearguard(
    state: GameState,
    defender_positions: dict[str, str],
    decision_ctx: BattleDecisionContext,
) -> None:
    """Q-006 (4.4.1 2E): when Sallying Lords are present, "Any
    Defending Lords in Reserve instead position as above opposite
    Sallying Attackers to fight them as a Rearguard row." This mutates
    `defender_positions` in place: Reserve -> rearguard_left/center/right.
    Operator picks per slot. Lords beyond the third remain in Reserve.
    """
    reserves = [lid for lid, p in defender_positions.items() if p == "reserve"]
    if not reserves:
        return
    # Fill rearguard center first, then left, then right.
    for slot in _REARGUARD_SLOTS:
        available = [
            lid for lid in reserves
            if defender_positions.get(lid) == "reserve"
        ]
        if not available:
            break
        if len(available) == 1:
            chosen = available[0]
        else:
            chosen = decision_ctx.decide(
                "initial_placement_defender", "defender", available,
                {"slot": slot, "phase": "rearguard"},
            )
        defender_positions[chosen] = slot


def _init_battle_array(
    state: GameState,
    attacker_lords: list[str],
    defender_lords: list[str],
    active_attacker: str,
    decision_ctx: BattleDecisionContext,
    sallying_lords: list[str] | None = None,
) -> tuple[dict[str, str], dict[str, str]]:
    """4.4.1 Battle Array (2E):
      - Active Lord at Attacker Front center.
      - Attacker fills Front left/right with up to 2 other Lords; rest
        Reserve. Operator picks which Lord per slot if multiple options.
      - Defender fills center first opposite Attacker center, then left,
        then right, "as able". If multiple Defenders, operator picks
        which one fills each slot. Excess Defenders go to Reserve.
      - Q-006: if `sallying_lords` is non-empty, Relief Sally Array
        applies: Sallying Lords are placed at sally_center / sally_left
        / sally_right / sally_reserve (behind the Defenders) and any
        Defender Reserve Lords are shifted to rearguard_center /
        rearguard_left / rearguard_right (facing Sallying).

    Returns (attacker_positions, defender_positions). Sally positions
    are stored inside attacker_positions; rearguard positions inside
    defender_positions.
    """
    # Attacker side ---------------------------------------------------
    attacker_positions: dict[str, str] = {}
    if active_attacker not in attacker_lords:
        # Defensive: caller should pass an Attacker-side Active Lord.
        attacker_lords = [active_attacker] + [
            l for l in attacker_lords if l != active_attacker
        ]
    attacker_positions[active_attacker] = "center"
    others = [l for l in attacker_lords if l != active_attacker]
    if len(others) == 1:
        slot = decision_ctx.decide(
            "initial_placement_attacker", "attacker", ["left", "right"],
            {"lord": others[0], "phase": "front_left_right_only_one_lord"},
        )
        attacker_positions[others[0]] = slot
    elif len(others) >= 2:
        # Pick left first, then right.
        for slot in ("left", "right"):
            available = [l for l in others if l not in attacker_positions]
            if not available:
                break
            chosen = decision_ctx.decide(
                "initial_placement_attacker", "attacker", available,
                {"slot": slot, "phase": "initial_array"},
            )
            attacker_positions[chosen] = slot
        # Remainder to Reserve.
        for l in others:
            if l not in attacker_positions:
                attacker_positions[l] = "reserve"
    # Defender side --------------------------------------------------
    defender_positions: dict[str, str] = {}
    available = list(defender_lords)
    fill_order: list[str] = []
    for slot in ("center", "left", "right"):
        if slot in attacker_positions.values():
            fill_order.append(slot)
    for slot in fill_order:
        if not available:
            break
        if len(available) == 1:
            chosen = available[0]
        else:
            chosen = decision_ctx.decide(
                "initial_placement_defender", "defender", available,
                {"slot": slot, "phase": "initial_array"},
            )
        defender_positions[chosen] = slot
        available.remove(chosen)
    for l in available:
        defender_positions[l] = "reserve"
    # Q-006 Relief Sally extensions.
    if sallying_lords:
        sally_pos = _array_sally_lords(state, sallying_lords, decision_ctx)
        attacker_positions.update(sally_pos)
        # Shift Defender Reserves into Rearguard slots.
        _shift_defender_reserves_to_rearguard(
            state, defender_positions, decision_ctx,
        )
    return attacker_positions, defender_positions


def _remove_routed_from_array(
    state: GameState, positions: dict[str, str]
) -> list[str]:
    """A Lord Routs the moment his last Unrouted unit Routs (4.4.2).
    Routed Lords are removed from the Array. Returns a list of Lord
    ids that newly Routed (had a Front position before, now removed).
    """
    newly_routed: list[str] = []
    for lid in list(positions.keys()):
        if lid not in state.lords:
            # Defensive: Lord removed from state entirely.
            if positions[lid] in ("left", "center", "right", "reserve"):
                if positions[lid] != "routed":
                    newly_routed.append(lid)
                positions[lid] = "routed"
            continue
        lord = state.lords[lid]
        # Routed = no Forces (all units are in routed_units pile).
        if not lord.forces and positions[lid] != "routed":
            newly_routed.append(lid)
            positions[lid] = "routed"
    return newly_routed


def _adjust_rows_for_relief_sally(
    state: GameState,
    attacker_positions: dict[str, str],
    defender_positions: dict[str, str],
) -> list[dict[str, Any]]:
    """4.4.2 page 15 (2E): Adjust Rows. Fires only in Relief Sally
    when an entire row Routs. Implements:

    - Rule 1: "If no Sallying Lords remain, Rearguard becomes Reserve."
      All Defender rearguard_* Lords convert to "reserve" so the
      ordinary Battle Array dynamics resume.

    - Rule 2: "If no Rearguard, Sallying Lords Flank Defenders." This
      is purely a strike-target rule and is already handled by
      _strike_target (when no Rearguard, Sally Lords Flank Front
      Defenders all equally close). No row transition.

    - Rule 3: "If no Front Defenders, Rearguard faces about as Front."
      All Defender Front slots empty -> Rearguard Lords become Front
      (rearguard_left -> left, rearguard_center -> center,
      rearguard_right -> right).

    - Rule 4: "If no Front Attackers, Rearguard becomes Front against
      Sally and original Front Defenders face about as Reserve." Front
      Attacker slots all empty -> Defender Front Lords go to Reserve;
      Defender Rearguard Lords stay where they are (they are now the
      primary engaging row -- _strike_target already routes Sally vs
      Rearguard correctly, so no slot rename is needed).

    Returns a log of row transitions (empty list if Relief Sally is
    not active or no transitions fired).
    """
    transitions: list[dict[str, Any]] = []
    # Detect Relief Sally: presence of any sally_* or rearguard_*
    # positions on this Battle.
    has_sally_or_rearguard = any(
        p.startswith("sally_") for p in attacker_positions.values()
    ) or any(
        p.startswith("rearguard_") for p in defender_positions.values()
    )
    if not has_sally_or_rearguard:
        return transitions
    # SNAPSHOT row-alive flags BEFORE applying any transition. The
    # rules trigger off the START-of-Reposition state; applying Rule 3
    # (rearguard -> front) must NOT cause Rule 4 to retroactively fire
    # because the new "front" was just promoted.
    sally_alive = any(
        p.startswith("sally_") and lid in state.lords and state.lords[lid].forces
        for lid, p in attacker_positions.items()
    )
    front_def_alive = any(
        p in _FRONT_SLOTS and lid in state.lords and state.lords[lid].forces
        for lid, p in defender_positions.items()
    )
    front_atk_alive = any(
        p in _FRONT_SLOTS and lid in state.lords and state.lords[lid].forces
        for lid, p in attacker_positions.items()
    )
    rearguard_alive = any(
        p.startswith("rearguard_") and lid in state.lords and state.lords[lid].forces
        for lid, p in defender_positions.items()
    )

    # Rule 1: "If no Sallying Lords remain, Rearguard becomes Reserve."
    # Ends Relief Sally geometry so regular Battle Array dynamics
    # resume. Supersedes Rules 3 and 4: if Sally is dead, the Battle
    # is back to a normal Front-only engagement.
    if not sally_alive and rearguard_alive:
        for lid, p in list(defender_positions.items()):
            if p.startswith("rearguard_"):
                defender_positions[lid] = "reserve"
                transitions.append({
                    "rule": "no_sally_remain",
                    "lord": lid, "from": p, "to": "reserve",
                })
        return transitions

    # Rule 3 and Rule 4 affect disjoint sets of Lords (rearguard_* vs
    # Front Defenders) and may both fire on the same turn. Use the
    # snapshot to decide independently. Apply Rule 3 first (promote
    # Rearguard) then Rule 4 (demote any remaining Front Defenders).

    # Rule 3: "If no Front Defenders, Rearguard faces about as Front."
    if not front_def_alive and rearguard_alive:
        for lid, p in list(defender_positions.items()):
            if p == "rearguard_left":
                defender_positions[lid] = "left"
                transitions.append({
                    "rule": "no_front_defenders", "lord": lid,
                    "from": "rearguard_left", "to": "left",
                })
            elif p == "rearguard_center":
                defender_positions[lid] = "center"
                transitions.append({
                    "rule": "no_front_defenders", "lord": lid,
                    "from": "rearguard_center", "to": "center",
                })
            elif p == "rearguard_right":
                defender_positions[lid] = "right"
                transitions.append({
                    "rule": "no_front_defenders", "lord": lid,
                    "from": "rearguard_right", "to": "right",
                })

    # Rule 4: "If no Front Attackers, ... original Front Defenders face
    # about as Reserve." Note: Rule 3 may have just promoted Rearguard
    # to Front; Rule 4 should target ONLY the ORIGINAL Front Defenders
    # (those that were at Front in the snapshot AND still alive). We
    # use the snapshot to identify them.
    if not front_atk_alive and sally_alive:
        # Build the snapshot of original Front Defenders (alive).
        # We can't re-detect post-Rule-3 because Rule 3 may have just
        # filled left/center/right with the formerly-rearguard Lords.
        original_front_def = [
            lid for lid, p in defender_positions.items()
            if p in _FRONT_SLOTS
        ]
        # If Rule 3 just promoted Lords here, those Lords have
        # transitions in the log. Filter them out.
        promoted_lords = {t["lord"] for t in transitions
                          if t["rule"] == "no_front_defenders"}
        for lid in original_front_def:
            if lid in promoted_lords:
                continue
            if lid not in state.lords or not state.lords[lid].forces:
                continue
            from_slot = defender_positions[lid]
            defender_positions[lid] = "reserve"
            transitions.append({
                "rule": "no_front_attackers", "lord": lid,
                "from": from_slot, "to": "reserve",
            })
    return transitions


def _reposition(
    state: GameState,
    positions: dict[str, str],
    side_label: str,
    decision_ctx: BattleDecisionContext,
    opposing_positions: dict[str, str] | None = None,
) -> dict[str, Any]:
    """4.4.2 Reposition (Round 2+):
      - Advance Lords: Reserves slide into any empty Front position.
      - Center fill: if center remains empty after advance, slide one
        Lord from left or right to fill center.

    SMOKE-014 (Round 12): when `opposing_positions` is provided AND the
    opposing side's Front is empty AND the opposing side has a Sally
    row alive, this side's Front is empty *by design* under Adjust
    Rows Rule 4 (4.4.2 page 15: "If no Front Attackers, Rearguard
    becomes Front against Sally and original Front Defenders face
    about as Reserve"). In that case Reposition Advance is suppressed
    -- otherwise the just-demoted Lord(s) would Advance right back to
    Front and Rule 4 would re-fire next round, looping forever in the
    log.

    Mutates `positions` in place. Returns a log of advances; on
    suppression the log contains a single `frozen_under_rule_4`
    entry and no moves.
    """
    moves: list[dict[str, Any]] = []
    # SMOKE-014 suppression: if the opposing side's Front is empty AND
    # opposing Sally row is alive, this side's Front is empty by design
    # per Adjust Rows Rule 4. Don't undo that demotion.
    if opposing_positions is not None:
        opp_front_alive = any(
            p in ("left", "center", "right")
            and lid in state.lords and state.lords[lid].forces
            for lid, p in opposing_positions.items()
        )
        opp_sally_alive = any(
            p.startswith("sally_")
            and lid in state.lords and state.lords[lid].forces
            for lid, p in opposing_positions.items()
        )
        if (not opp_front_alive) and opp_sally_alive:
            return {"moves": [], "suppressed": "frozen_under_rule_4"}
    # Step 1: Advance Reserves into empty Front slots.
    occupied_front: set[str] = {
        p for lid, p in positions.items()
        if p in ("left", "center", "right")
        and lid in state.lords and state.lords[lid].forces
    }
    empty_slots = [s for s in ("left", "center", "right") if s not in occupied_front]
    for slot in empty_slots:
        reserves = [
            lid for lid, p in positions.items()
            if p == "reserve"
            and lid in state.lords and state.lords[lid].forces
        ]
        if not reserves:
            break
        if len(reserves) == 1:
            chosen = reserves[0]
        else:
            chosen = decision_ctx.decide(
                "reserve_advance", side_label, reserves,
                {"slot": slot, "phase": "advance_lords"},
            )
        positions[chosen] = slot
        moves.append({"step": "advance", "lord": chosen, "to": slot})
    # Step 2: Center fill from left/right if center still empty.
    occupied_front = {
        p for lid, p in positions.items()
        if p in ("left", "center", "right")
        and lid in state.lords and state.lords[lid].forces
    }
    if "center" not in occupied_front:
        candidates = [
            lid for lid, p in positions.items()
            if p in ("left", "right")
            and lid in state.lords and state.lords[lid].forces
        ]
        if candidates:
            if len(candidates) == 1:
                chosen = candidates[0]
            else:
                chosen = decision_ctx.decide(
                    "center_fill", side_label, candidates,
                    {"phase": "center_fill"},
                )
            old_slot = positions[chosen]
            positions[chosen] = "center"
            moves.append({"step": "center_fill", "lord": chosen, "from": old_slot})
    return {"moves": moves}


def _opposite_slot(slot: str) -> str:
    """Map an Attacker slot to the same-row Defender slot. Battle Array
    is mirrored: Attacker left faces Defender left, etc.
    """
    return slot  # mirrored same-name


def _row_distance(a: str, b: str) -> int:
    """Distance between two Front slots in the row (left=0, center=1,
    right=2). Used for Flanker "closest" target selection.
    """
    pos = {"left": 0, "center": 1, "right": 2}
    return abs(pos[a] - pos[b])


def _strike_target(
    striker_pos: str,
    enemy_positions: dict[str, str],
    decision_ctx: BattleDecisionContext,
    side_label: str,
    state: GameState,
) -> str | None:
    """4.4.2 + 4.4.1 Relief Sally Strike target rule:

    For Front Attacker / Front Defender Lords (positions left, center,
    right):
      - The Lord directly opposite (same slot on the enemy side), if
        exists AND has Forces.
      - Otherwise Flanking: closest enemy Lord in the row. Ties broken
        by operator decision.

    For Sally row Lords (sally_left/center/right):
      - If there are Rearguard Lords (rearguard_*), those take priority.
        Sally targets the directly-opposed Rearguard slot, or — if
        Flanking — the closest Rearguard Lord in the row.
      - If no Rearguard, Sallying Lords Flank Front Defenders all
        equally closely (Q-006 / 4.4.1): operator picks a Front
        Defender (any slot is "equally closely").

    For Rearguard row Lords (rearguard_*):
      - Target Sally row directly-opposed (sally_center vs
        rearguard_center, etc.) or Flank within the sally row.

    Returns the target Lord id, or None if no enemy on the targeted row.
    """
    # Determine which row the striker is in: Front (left/center/right),
    # Sally (sally_*), or Rearguard (rearguard_*).
    if striker_pos in _FRONT_SLOTS:
        # Front targets opposite Front row.
        opp = striker_pos  # mirrored
        direct = [
            lid for lid, p in enemy_positions.items()
            if p == opp and lid in state.lords and state.lords[lid].forces
        ]
        if direct:
            return direct[0]
        # Flank within Front.
        targets = [
            (lid, p) for lid, p in enemy_positions.items()
            if p in _FRONT_SLOTS
            and lid in state.lords and state.lords[lid].forces
        ]
    elif striker_pos in _SALLY_SLOTS:
        # Sally targets Rearguard row first.
        sally_row = striker_pos.replace("sally_", "")  # left/center/right
        opp = "rearguard_" + sally_row
        direct = [
            lid for lid, p in enemy_positions.items()
            if p == opp and lid in state.lords and state.lords[lid].forces
        ]
        if direct:
            return direct[0]
        # Flank within Rearguard.
        rearguard = [
            (lid, p) for lid, p in enemy_positions.items()
            if p in _REARGUARD_SLOTS
            and lid in state.lords and state.lords[lid].forces
        ]
        if rearguard:
            # Convert rearguard_X to its same-row Front position-equivalent
            # for distance purposes (rearguard_left at distance 0 from
            # sally_left).
            def _rg_dist(p: str) -> int:
                rg = p.replace("rearguard_", "")
                return _row_distance(sally_row, rg)
            by_distance = sorted(rearguard, key=lambda kv: _rg_dist(kv[1]))
            closest_dist = _rg_dist(by_distance[0][1])
            closest = [lid for lid, p in by_distance if _rg_dist(p) == closest_dist]
            if len(closest) == 1:
                return closest[0]
            chosen = decision_ctx.decide(
                "flanker_target", side_label, closest,
                {"striker_slot": striker_pos,
                 "phase": "sally_rearguard_tiebreak"},
            )
            return chosen
        # No Rearguard: Sally Lords Flank Front Defenders "all equally
        # closely" (4.4.1 2E). Operator picks among Front Defenders.
        targets = [
            (lid, p) for lid, p in enemy_positions.items()
            if p in _FRONT_SLOTS
            and lid in state.lords and state.lords[lid].forces
        ]
        if not targets:
            return None
        if len(targets) == 1:
            return targets[0][0]
        chosen = decision_ctx.decide(
            "flanker_target", side_label, [lid for lid, _ in targets],
            {"striker_slot": striker_pos, "phase": "sally_flanks_front_equal"},
        )
        return chosen
    elif striker_pos in _REARGUARD_SLOTS:
        # Rearguard targets Sally row.
        rg_row = striker_pos.replace("rearguard_", "")
        opp = "sally_" + rg_row
        direct = [
            lid for lid, p in enemy_positions.items()
            if p == opp and lid in state.lords and state.lords[lid].forces
        ]
        if direct:
            return direct[0]
        targets = [
            (lid, p) for lid, p in enemy_positions.items()
            if p in _SALLY_SLOTS
            and lid in state.lords and state.lords[lid].forces
        ]
    else:
        return None
    # Generic Flanking among `targets` (list of (lid, p) tuples).
    if not targets:
        return None
    # Distance is computed by stripping any prefix and using row order.
    def _slot_index(p: str) -> int:
        bare = p.split("_")[-1]  # left/center/right
        return {"left": 0, "center": 1, "right": 2}[bare]
    striker_idx = _slot_index(striker_pos)
    by_distance = sorted(targets, key=lambda kv: abs(_slot_index(kv[1]) - striker_idx))
    closest_dist = abs(_slot_index(by_distance[0][1]) - striker_idx)
    closest = [lid for lid, p in by_distance
               if abs(_slot_index(p) - striker_idx) == closest_dist]
    if len(closest) == 1:
        return closest[0]
    chosen = decision_ctx.decide(
        "flanker_target", side_label, closest,
        {"striker_slot": striker_pos, "phase": "flanker_target_tiebreak"},
    )
    return chosen


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
    concede: str | None = None,
    holds: dict[str, Any] | None = None,
    active_attacker: str | None = None,
    decision_ctx: BattleDecisionContext | None = None,
    attacker_positions: dict[str, str] | None = None,
    defender_positions: dict[str, str] | None = None,
    sallying_lords: list[str] | None = None,
    siegeworks_for_sally: int = 0,
    simple_sally: bool = False,
) -> dict[str, Any]:
    """Run Battle rounds until one side loses (4.4.2).

    Q-005 (2E): Lords are arrayed in three Front positions per side
    (left, center, right) plus Reserve. The Active Attacker starts at
    Front center; other Attackers fill left/right; the Defender mirrors.
    Strikes are resolved per position: each striker Lord's Hits target
    the Lord directly opposite, or — if the striker is Flanking (no
    opposed enemy in the same slot) — the closest enemy Lord in the
    row. Reposition runs at the start of each Round after the first:
    Reserves advance into empty Front slots; an empty center is filled
    from left or right. All operator-level decisions (initial slot
    placement, Reserve advancement, center-fill, Flanker tie-break)
    flow through `decision_ctx`.

    Returns a dict with keys: rounds, winner, loser, attacker_lords,
    defender_lords, attacker_positions, defender_positions, log,
    decisions. The `log` is a list of per-round per-step distributions;
    `decisions` is the trace of operator choices.

    Parameters:
      active_attacker: Lord id that started this Battle (placed at
        Front center). Defaults to attacker_lords[0].
      decision_ctx: BattleDecisionContext for operator choices. If
        None, a default leftmost-fallback context is created.
      attacker_positions / defender_positions: pre-built Array maps
        (lord_id -> slot). If None, the Array is initialized via
        _init_battle_array using decision_ctx.
    """
    log: list[dict[str, Any]] = []
    defender_side: Side = "russian" if attacker_side == "teutonic" else "teutonic"
    if decision_ctx is None:
        decision_ctx = BattleDecisionContext()
    if active_attacker is None:
        active_attacker = attacker_lords[0] if attacker_lords else ""
    if attacker_positions is None or defender_positions is None:
        # If sallying_lords provided, the Active Lord is one of the
        # Marching attackers (NOT a Sallying Lord); they go in the
        # Front Array. Sallying go in the sally_* row.
        marching = [l for l in attacker_lords if not (sallying_lords and l in sallying_lords)]
        if not marching:
            marching = list(attacker_lords)
        active = active_attacker if active_attacker in marching else marching[0]
        atk_pos, def_pos = _init_battle_array(
            state, marching, defender_lords, active, decision_ctx,
            sallying_lords=sallying_lords,
        )
    else:
        atk_pos = dict(attacker_positions)
        def_pos = dict(defender_positions)
    rounds = 0
    while rounds < max_rounds:
        rounds += 1
        round_log: dict[str, Any] = {
            "round": rounds, "steps": [],
            "attacker_positions": dict(atk_pos),
            "defender_positions": dict(def_pos),
            "reposition": None,
        }
        # Q-005 Reposition: Round 2+, attacker then defender.
        if rounds >= 2:
            _remove_routed_from_array(state, atk_pos)
            _remove_routed_from_array(state, def_pos)
            # Follow-up C (4.4.2 page 15): Adjust Rows fires before
            # Reposition when Relief Sally is active and an entire row
            # Routed.
            adjust_log = _adjust_rows_for_relief_sally(state, atk_pos, def_pos)
            atk_repo = _reposition(
                state, atk_pos, "attacker", decision_ctx,
                opposing_positions=def_pos,
            )
            def_repo = _reposition(
                state, def_pos, "defender", decision_ctx,
                opposing_positions=atk_pos,
            )
            round_log["reposition"] = {"attacker": atk_repo, "defender": def_repo}
            if adjust_log:
                round_log["adjust_rows"] = adjust_log
            round_log["attacker_positions"] = dict(atk_pos)
            round_log["defender_positions"] = dict(def_pos)

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
        from nevsky.capabilities import any_capability
        defender_side: Side = "russian" if attacker_side == "teutonic" else "teutonic"
        # Tier 2 hold-event modifiers (Phase 4d). The keys map a card
        # to its semantic effect; values are normalized strings:
        #   "marsh":       "attacker"|"defender" (side whose Horse is blocked)
        #   "hill":        "attacker"|"defender" (side whose default Archery is doubled)
        #   "field_organ": lord_id (recipient of Round-1 Knights+Sergeants Melee +1)
        #   "raven_rock":  truthy -> Russian defender Walls 1-2 vs Melee Round 1
        # Card-id strings (e.g., "T5") are accepted and translated.
        H = holds or {}
        def _norm_marsh(v):
            if v in ("attacker", "defender", None):
                return v
            # "T5" was played by Teu defender -> blocks R Horse (attacker).
            # "R2" was played by Rus defender -> blocks T Horse (attacker).
            # Both versions: blocks attacker.
            if v in ("T5", "R2"):
                return "attacker"
            return None
        def _norm_hill(v):
            if v in ("attacker", "defender", None):
                return v
            # T9 = Teu defender doubles Teu archery; R5 = Rus defender doubles Rus archery.
            if v == "T9":
                return "defender" if attacker_side == "russian" else "defender"
            if v == "R5":
                return "defender" if attacker_side == "teutonic" else "defender"
            return None
        marsh_blocks_horse_for = _norm_marsh(H.get("marsh"))
        hill_archery_full_for = _norm_hill(H.get("hill"))
        # SMOKE-081 (Round 85): accept field_organ_lord key when present
        # (agent-facing per docstring), fall back to legacy "field_organ"
        # holding a lord_id directly (test_round_18 path).
        _fo_lord = H.get("field_organ_lord")
        _fo_legacy = H.get("field_organ")
        if _fo_lord is not None:
            field_organ_lord = _fo_lord
        elif _fo_legacy is not None and _fo_legacy in state.lords:
            field_organ_lord = _fo_legacy
        else:
            field_organ_lord = None
        raven_rock_walls = bool(H.get("raven_rock", False))
        # Q-008 Bridge: front-center Lord of the targeted side capped to
        # 2*round_number Melee strike units. holds["bridge"] = lord_id
        # of the targeted Lord (front-center), or None.
        # SMOKE-081 (Round 85): same dual-key pattern as field_organ.
        _br_lord = H.get("bridge_target_lord")
        _br_legacy = H.get("bridge")
        if _br_lord is not None:
            bridge_target_lord = _br_lord
        elif _br_legacy is not None and _br_legacy in state.lords:
            bridge_target_lord = _br_legacy
        else:
            bridge_target_lord = None
        # Winter check: per the card, Bridge applies non-Winter only.
        from nevsky.scenarios import _season_for_box
        if bridge_target_lord and _season_for_box(state.meta.box) in (
                "early_winter", "late_winter"):
            bridge_target_lord = None
        # Q-008 Ambush: Round 1 disables left/right Lords on the
        # targeted side from striking and from being targeted (they're
        # "uninvolved"). holds["ambush"] = "attacker"|"defender" or
        # card-id ("T6"|"R6"). Both are played by the defender, so
        # effective disable target is the attacker.
        ambush_raw = H.get("ambush")
        if ambush_raw in ("attacker", "defender"):
            ambush_disable_for = ambush_raw
        elif ambush_raw in ("T6", "R6"):
            ambush_disable_for = "attacker"
        else:
            ambush_disable_for = None
        # 4.4.2 Pursuit: if the conceder strikes, halve their Hits
        # (round up). conceder is "attacker" or "defender" or None.
        for label, kind, striker_lords, target_lords in steps:
            step_state: dict = {}  # AUDIT-002: Warrior Monks per-step reroll budget
            striker_role = ("attacker" if striker_lords is attacker_lords
                             else "defender")
            # Q-005: per-Lord positions for this step.
            striker_positions = atk_pos if striker_role == "attacker" else def_pos
            enemy_positions = def_pos if striker_role == "attacker" else atk_pos
            side_label = striker_role
            # Marsh: Rounds 1-2, opposite-side Horse units of the side
            # FACING the marsh-player don't Strike.
            block_horse_strike = False
            if marsh_blocks_horse_for is not None and rounds <= 2:
                if striker_role == marsh_blocks_horse_for:
                    block_horse_strike = True

            # Q-005 + Q-007: per-striker raw Hits split into Crossbow
            # (-2-Armor) and Normal contributions; per-target routing
            # via positions. Each striker Lord's Hits target the Lord
            # directly opposite (same slot) or — if Flanking — the
            # closest enemy Lord in the row.
            #
            # Q-007 ('round in favor of Crossbowmen', Arts of War
            # Reference R1/R2 Luchniki Tips): Crossbow Hits (Streltsy/
            # Balistarii MaA archery) are tracked separately so the
            # final Hit count gives Crossbowmen the ceiling-rounded
            # share. For non-archery steps, all contribution is normal.
            per_target_cb_raw: dict[str, float] = {}
            per_target_norm_raw: dict[str, float] = {}
            per_striker_log: list[dict[str, Any]] = []
            forces_table = load_forces()
            for lid in striker_lords:
                if lid not in state.lords:
                    continue
                if not state.lords[lid].forces:
                    continue
                # Reserve / Routed Lords don't strike. Sally and
                # Rearguard rows DO strike (Q-006).
                pos = striker_positions.get(lid)
                if pos in ("reserve", "sally_reserve", "routed", None):
                    continue
                # Q-008 Ambush: Round 1 disables left/right Lords on
                # the targeted side from striking entirely.
                if (ambush_disable_for == striker_role and rounds == 1
                        and pos in ("left", "right")):
                    continue
                this_cb_raw = 0.0
                this_norm_raw = 0.0
                # Q-008 Marsh: side-level Horse-Strike block, both
                # Archery and Melee. All Horse units (Knights, Light
                # Horse, Asiatic Horse) blocked; absorption unaffected.
                horse_blocked = (block_horse_strike and rounds <= 2)
                if horse_blocked and kind == "melee_horse":
                    pass  # all Horse Melee blocked
                elif horse_blocked and kind == "archery":
                    # Compute archery contribution from non-Horse units only.
                    units = state.lords[lid].forces
                    foot_units = {k: v for k, v in units.items()
                                  if k not in ("knights", "light_horse", "asiatic_horse")}
                    base = _hits_for_strike(foot_units, "archery")
                    this_norm_raw += base
                    # Luchniki militia (foot) still strikes; LH is Horse-blocked.
                    if any_capability(state, lid, "Luchniki"):
                        this_norm_raw += 0.5 * foot_units.get("militia", 0)
                    # Streltsy/Balistarii MaA (foot, crossbow).
                    if any_capability(state, lid, "Streltsy") or any_capability(state, lid, "Balistarii"):
                        this_cb_raw += 0.5 * foot_units.get("men_at_arms", 0)
                elif kind == "archery":
                    # Normal archery accumulation: split crossbow vs normal.
                    units = state.lords[lid].forces
                    base_archery = _hits_for_strike(units, "archery")
                    this_norm_raw += base_archery
                    if any_capability(state, lid, "Luchniki"):
                        this_norm_raw += 0.5 * units.get("light_horse", 0)
                        this_norm_raw += 0.5 * units.get("militia", 0)
                    if any_capability(state, lid, "Streltsy") or any_capability(state, lid, "Balistarii"):
                        this_cb_raw += 0.5 * units.get("men_at_arms", 0)
                    # Q-008 Hill: Rounds 1-2, this side's archery x1
                    # (instead of default 0.5/unit). Doubles BOTH
                    # crossbow and normal contributions equally.
                    if (hill_archery_full_for == striker_role and rounds <= 2):
                        this_cb_raw *= 2
                        this_norm_raw *= 2
                else:
                    # Melee step: all hits are "normal" (no -2-Armor effect).
                    # Q-008 ordering: determine the striking-unit subset
                    # FIRST (Bridge cap applies on the Lord identified by
                    # bridge_target_lord), then compute base strike from
                    # that subset, then add Field Organ bonus per striking
                    # Knight (in melee_horse) / Sergeant (in melee_foot).
                    units = state.lords[lid].forces
                    if bridge_target_lord == lid and rounds <= 8:
                        cap = 2 * rounds
                        total_units = sum(units.values())
                        if total_units > cap:
                            striking_units = _capped_unit_subset(units, cap)
                        else:
                            striking_units = dict(units)
                    else:
                        striking_units = dict(units)
                    this_norm_raw += _hits_for_strike(striking_units, kind)
                    # Q-008 Field Organ: +1 Hit per actually-striking
                    # Knight (melee_horse) or Sergeant (melee_foot)
                    # for the targeted Lord, Round 1 only.
                    if field_organ_lord == lid and rounds == 1:
                        if kind == "melee_horse":
                            this_norm_raw += striking_units.get("knights", 0)
                        elif kind == "melee_foot":
                            this_norm_raw += striking_units.get("sergeants", 0)
                if (this_cb_raw + this_norm_raw) <= 0:
                    continue
                # Pursuit: halve conceder Hits this Round (per striker,
                # both buckets equally).
                if concede is not None and rounds == 1 and striker_role == concede:
                    this_cb_raw = this_cb_raw / 2.0
                    this_norm_raw = this_norm_raw / 2.0
                # Find target via positions.
                target_lid = _strike_target(
                    striker_positions[lid], enemy_positions, decision_ctx,
                    side_label, state,
                )
                if target_lid is None:
                    continue
                # Q-008 Ambush: Round 1 disables enemy left/right Lords
                # from being targeted (they're "uninvolved").
                if (ambush_disable_for is not None
                        and ambush_disable_for != striker_role
                        and rounds == 1
                        and enemy_positions.get(target_lid) in ("left", "right")):
                    # Reroute via _strike_target to a non-disabled slot
                    # if any. The simplest correct behavior: skip this
                    # striker's contribution if the only available
                    # target is disabled.
                    continue
                per_target_cb_raw[target_lid] = per_target_cb_raw.get(target_lid, 0.0) + this_cb_raw
                per_target_norm_raw[target_lid] = per_target_norm_raw.get(target_lid, 0.0) + this_norm_raw
                per_striker_log.append({
                    "striker": lid, "striker_slot": striker_positions[lid],
                    "target": target_lid, "target_slot": enemy_positions.get(target_lid),
                    "raw_cb": this_cb_raw, "raw_norm": this_norm_raw,
                    "raw": this_cb_raw + this_norm_raw,
                })
            # Combine cb + norm raws. Q-007 (Arts of War Reference R1/R2
            # Luchniki Tips, "round in favor of Crossbowmen"):
            #   total_hits   = ceil(crossbow_raw + normal_raw)
            #   crossbow_hits = ceil(crossbow_raw)        # round in favor
            #   normal_hits  = total_hits - crossbow_hits
            per_target_hits: dict[str, int] = {}
            per_target_cb_hits: dict[str, int] = {}
            for tlid in set(list(per_target_cb_raw) + list(per_target_norm_raw)):
                cb_raw = per_target_cb_raw.get(tlid, 0.0)
                norm_raw = per_target_norm_raw.get(tlid, 0.0)
                total = _round_up(cb_raw + norm_raw)
                cb_hits = _round_up(cb_raw)
                cb_hits = min(cb_hits, total)
                per_target_hits[tlid] = total
                per_target_cb_hits[tlid] = cb_hits
            if not per_target_hits:
                continue
            strike_kind = "archery" if kind == "archery" else "melee"
            distribution: list[dict[str, Any]] = []
            # Q-006: Track Hits that came from Sally-row strikers per
            # target so Siegeworks-vs-Sally walls can be rolled
            # separately (4.4.1 2E "Siegeworks ... protect against
            # Strikes by Sallying Attackers only (round separately)").
            per_target_sally_hits: dict[str, float] = {}
            for entry in per_striker_log:
                # SMOKE-050 (Round 61): in a simple Sally, the besieged
                # Lords ARE all the attackers — their strikes count as
                # Sallying Attacker strikes for Siegeworks-as-Walls
                # absorption (4.5.3 "Defenders/Besiegers receive
                # Siegeworks as Walls"). Without this, the Walls
                # protection only fires on Relief Sally where the
                # sallying Lords are positioned at sally_* slots.
                is_sally_strike = entry["striker_slot"] in _SALLY_SLOTS or simple_sally
                if is_sally_strike:
                    tlid = entry["target"]
                    per_target_sally_hits[tlid] = (
                        per_target_sally_hits.get(tlid, 0.0) + entry["raw"]
                    )
            for tlid in per_target_hits:
                hits = per_target_hits[tlid]
                cb_hits = per_target_cb_hits[tlid]
                raw = float(hits)  # for Sally walls reduction below
                # Q-006 Siegeworks-vs-Sally walls: if any Hits incoming
                # to this target came from a Sally striker AND
                # siegeworks_for_sally > 0, roll Walls separately on
                # those Hits. Walls range = 1..siegeworks_for_sally.
                sally_raw = per_target_sally_hits.get(tlid, 0.0)
                if sally_raw > 0 and siegeworks_for_sally > 0:
                    sally_hits = _round_up(sally_raw)
                    sally_absorbed = 0
                    for _ in range(sally_hits):
                        r = roll_d6(state)
                        if r <= siegeworks_for_sally:
                            sally_absorbed += 1
                    if sally_absorbed > 0:
                        distribution.append({
                            "lord": tlid,
                            "target": "siegeworks_vs_sally",
                            "absorbed": sally_absorbed,
                        })
                        # Reduce the target's effective Hits by absorbed.
                        raw = max(0.0, raw - sally_absorbed)
                        hits = _round_up(raw)
                # Raven's Rock: Russian defender gets Walls 1-2 vs Melee
                # Round 1 (R4). Per-Hit roll, applied to each Hit
                # incoming to the target.
                walls_absorbed = 0
                if (raven_rock_walls and rounds == 1 and kind != "archery"
                        and striker_role == "attacker"
                        and attacker_side == "teutonic"
                        and tlid in state.lords
                        and state.lords[tlid].side == "russian"):
                    for _ in range(hits):
                        r = roll_d6(state)
                        if r <= 2:
                            walls_absorbed += 1
                    if walls_absorbed > 0:
                        distribution.append({
                            "lord": tlid, "target": "ravens_rock_walls",
                            "absorbed": walls_absorbed,
                        })
                        hits -= walls_absorbed
                if hits <= 0:
                    continue
                if tlid not in state.lords or not state.lords[tlid].forces:
                    continue
                # Q-007: build ordered hit_flags so the first cb_hits
                # carry -2 Armor, the rest don't. Use the post-walls/
                # walls-absorbed-adjusted hits count; if walls absorbed
                # some hits, reduce cb_hits proportionally (crossbow
                # Hits aren't preferentially absorbed, so floor-divide
                # against original total).
                eff_cb_hits = min(cb_hits, hits)
                eff_norm_hits = hits - eff_cb_hits
                hit_flags_list = [True] * eff_cb_hits + [False] * eff_norm_hits
                tres = _resolve_hits(
                    state, tlid, hits, strike_kind,
                    hit_flags=hit_flags_list,
                    step_state=step_state,
                )
                distribution.append({"lord": tlid, **tres})
            if distribution or per_striker_log:
                round_log["steps"].append({
                    "step": label,
                    "per_striker": per_striker_log,
                    "distribution": distribution,
                })
            # Update positions for newly-Routed Lords.
            _remove_routed_from_array(state, atk_pos)
            _remove_routed_from_array(state, def_pos)
            # SMOKE-015 guard: bool() prevents vacuous _all_routed([])
            # from short-circuiting if a future caller passes an empty
            # side. Battle is not currently invoked with empty sides.
            atk_wiped = bool(attacker_lords) and _all_routed(state, attacker_lords)
            def_wiped = bool(defender_lords) and _all_routed(state, defender_lords)
            if atk_wiped or def_wiped:
                break

        log.append(round_log)
        # Common return-shape helper.
        def _ret(winner: Side, loser: Side, **extra: Any) -> dict[str, Any]:
            r = {
                "rounds": rounds, "winner": winner, "loser": loser,
                "attacker_lords": attacker_lords,
                "defender_lords": defender_lords,
                "attacker_positions": dict(atk_pos),
                "defender_positions": dict(def_pos),
                "log": log,
                "decisions": list(decision_ctx.log),
            }
            r.update(extra)
            return r
        if concede is not None and rounds == 1:
            if concede == "attacker":
                return _ret(defender_side, attacker_side, conceded="attacker")
            else:
                return _ret(attacker_side, defender_side, conceded="defender")
        if _all_routed(state, attacker_lords):
            return _ret(defender_side, attacker_side)
        if _all_routed(state, defender_lords):
            return _ret(attacker_side, defender_side)

    # Stalemate after max rounds: defender wins (attacker fails to
    # break through).
    return {
        "rounds": rounds, "winner": defender_side, "loser": attacker_side,
        "attacker_lords": attacker_lords, "defender_lords": defender_lords,
        "attacker_positions": dict(atk_pos),
        "defender_positions": dict(def_pos),
        "log": log, "stalemate": True,
        "decisions": list(decision_ctx.log),
    }


# ---------------------------------------------------------------------------
# Aftermath: Retreat / Service shift
# ---------------------------------------------------------------------------


_SERVICE_SHIFT_TABLE = {1: 1, 2: 1, 3: 2, 4: 2, 5: 3, 6: 3}


def apply_retreat_service_shift(state: GameState, lord_id: str) -> int:
    """4.4.3 Service: roll 1d6 per Retreating Lord; shift Service marker
    LEFT by the table value. Returns the shift amount.

    SMOKE-070 (Round 74): when the shift would carry the marker past
    box 1, the marker lands on off_left_service (one box off the
    Calendar), matching SMOKE-062's _shift_service semantics. Off-left
    Service markers trigger 3.3.1 permanent removal at the next
    Disband. Previously the function clamped at box 1, silently
    denying the legal off-Calendar landing.
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
    # SMOKE-057 (Round 65): Service markers off the right edge live in
    # `off_right_service`, NOT `off_right` (which is the cylinder list).
    # Previously this branch consulted the wrong list, so a Lord with
    # Service marker past box 16 silently skipped the shift.
    if cur is None and lord_id in cal.off_right_service:
        cal.off_right_service.remove(lord_id)
        cur = 17
    # SMOKE-070 (Round 74): also handle marker already at off_left_service.
    if cur is None and lord_id in cal.off_left_service:
        cal.off_left_service.remove(lord_id)
        cur = 0
    if cur is None:
        return 0
    new_box = cur - boxes
    if new_box < 1:
        # Land on off_left_service (one box off Calendar; further
        # shifts are absorbed there).
        cal.off_left_service.append(lord_id)
    elif cur == 17 and new_box >= 17:
        cal.off_right_service.append(lord_id)
    else:
        cal.boxes[new_box - 1].service_markers.append(lord_id)

    # SMOKE-103 (Round 139): Advanced Vassal Service rule (3.4.2)
    # — per Battle and Storm reference service_shift_on_retreat:
    # "shift each Vassal's marker the same number, ONLY under
    # advanced Vassal Service rule." The Pay-step shift
    # (`_shift_service_right` in actions.py) already had this
    # cascade; Retreat-shift was missing it. Same audit pattern as
    # SMOKE-098/099/101 (mirror-gap between sibling shift paths).
    if state.meta.optional_rules.get("advanced_vassal_service", False):
        if lord_id in state.lords:
            for vid, vstate in state.lords[lord_id].vassals.items():
                if not vstate.on_calendar or vstate.calendar_box is None:
                    continue
                old_v_box = vstate.calendar_box
                if 1 <= old_v_box <= 16:
                    vcb = cal.boxes[old_v_box - 1]
                    if vid in vcb.vassal_service_markers:
                        vcb.vassal_service_markers.remove(vid)
                target_v = old_v_box - boxes
                if target_v < 1:
                    # Sentinel for off-left vassal position (matches
                    # actions._shift_service_right convention).
                    vstate.calendar_box = 0
                elif target_v > 16:
                    vstate.calendar_box = 17
                else:
                    cal.boxes[target_v - 1].vassal_service_markers.append(vid)
                    vstate.calendar_box = target_v
    return boxes


def _usable_transport_count_for_way(
    state: GameState, lord_id: str, way_type: str
) -> int:
    """Count Transport on a Lord's mat that is "Usable" (1.7.4) along
    a given Way type in the current Season:
      - Boats: Rasputitsa/Summer; Waterways only.
      - Carts: Summer only; Trackways only.
      - Sleds: Winter (early/late) only; any Way.
      - Ships: not used for overland Way movement; never counted here.

    way_type is "trackway" or "waterway".
    """
    from nevsky.actions import _season_of_box
    if lord_id not in state.lords:
        return 0
    lord = state.lords[lord_id]
    season = _season_of_box(state.meta.box)
    n = 0
    if way_type == "waterway":
        if season in ("summer", "rasputitsa"):
            n += int(lord.assets.get("boat", 0))
        if season in ("early_winter", "late_winter"):
            n += int(lord.assets.get("sled", 0))
    elif way_type == "trackway":
        if season == "summer":
            n += int(lord.assets.get("cart", 0))
        if season in ("early_winter", "late_winter"):
            n += int(lord.assets.get("sled", 0))
    # Rasputitsa on a Trackway: nothing usable except by special-case
    # rules — no Transport type fits the standard table.
    return n


def _way_type_between(from_locale: str, to_locale: str) -> str | None:
    """Return "trackway" or "waterway" if a Way connects the two
    Locales, else None.
    """
    for w in load_ways():
        if (w["a"] == from_locale and w["b"] == to_locale) or (
            w["a"] == to_locale and w["b"] == from_locale
        ):
            return w["type"]
    return None


def _award_assets_capped(state: "GameState", lord_id: str,
                          assets: dict[str, int]) -> dict[str, Any]:
    """SMOKE-032: Per-type 8-cap aware asset award (rule 1.7.3 Wastage
    Per Lord: "AT MOST 8 of each Asset type. Any excess gained beyond 8
    is lost immediately.").

    Adds ``assets`` (a dict of asset_type -> count) to the target Lord's
    mat, capping each type at 8. Returns ``{added: dict, lost_to_cap:
    dict}`` so callers can surface what was actually transferred vs.
    what overflowed.

    Used by every Spoils path (Avoid Battle, Battle Aftermath via
    transfer_spoils, Storm Sack inter-Lord transfer).
    """
    added: dict[str, int] = {}
    lost: dict[str, int] = {}
    if lord_id not in state.lords:
        return {"added": added, "lost_to_cap": lost}
    lord = state.lords[lord_id]
    for k, v in assets.items():
        give = int(v)
        if give <= 0:
            continue
        current = int(lord.assets.get(k, 0))
        room = max(0, 8 - current)
        accepted = min(give, room)
        if accepted > 0:
            lord.assets[k] = current + accepted  # type: ignore[index]
            added[k] = accepted
        excess = give - accepted
        if excess > 0:
            lost[k] = excess
    return {"added": added, "lost_to_cap": lost}


def transfer_spoils(
    state: GameState, from_lord: str, to_lords: list[str], mode: str,
    retreat_way_type: str | None = None,
) -> dict[str, Any]:
    """4.4.5 Spoils: transfer Assets from loser Lord to winners.

    mode:
      "all_except_ships"  - Removed (Sack / unable to Retreat or
                            Withdraw) OR Retreated WITHOUT having
                            Conceded the Field. Transfer all Coin,
                            Provender, Loot, and overland Transport;
                            keep Ships only.
      "loot_and_excess"   - Conceded the Field AND Retreated (4.4.3 2E):
                            "transfer all Loot and any Provender beyond
                            that which they could take along the
                            Retreat Way without being Laden". Lose no
                            other Assets. Provider must pass
                            `retreat_way_type` ("trackway" or
                            "waterway") so the Unladen Transport count
                            can be computed. If retreat_way_type is
                            None (e.g., legacy callers), fall back to
                            "all Loot" only (the original simplified
                            behavior).
      "none"              - Withdrew (4.4.3): no transfer.

    AUDIT-004 (Round 9): the "loot_and_excess" branch now actually
    computes the excess-Provender amount along the retreat Way per the
    2E rule, instead of transferring zero Provender.
    """
    if mode == "none":
        return {"from": from_lord, "transferred": {}, "mode": mode}
    if from_lord not in state.lords:
        return {"from": from_lord, "transferred": {}, "mode": mode, "error": "no_lord"}
    src = state.lords[from_lord]
    transferred: dict[str, int] = {}
    if mode == "all_except_ships":
        for k in ("coin", "provender", "loot", "boat", "cart", "sled"):
            amt = src.assets.get(k, 0)
            if amt > 0:
                transferred[k] = amt
                src.assets.pop(k, None)
    elif mode == "loot_and_excess":
        # Conceded + Retreated: transfer all Loot.
        loot = int(src.assets.get("loot", 0))
        if loot > 0:
            transferred["loot"] = loot
            src.assets.pop("loot", None)
        # Provender beyond Unladen along the Retreat Way: usable
        # Transport count on that Way determines how much Provender the
        # Lord can carry without being Laden (4.3.2).
        if retreat_way_type in ("trackway", "waterway"):
            usable = _usable_transport_count_for_way(state, from_lord, retreat_way_type)
            prov = int(src.assets.get("provender", 0))
            excess = max(0, prov - usable)
            if excess > 0:
                transferred["provender"] = excess
                src.assets["provender"] = prov - excess  # type: ignore[index]
                if src.assets["provender"] == 0:
                    src.assets.pop("provender", None)
    # Distribute to first winner Lord.
    if to_lords and transferred:
        winner = to_lords[0]
        if winner in state.lords:
            award = _award_assets_capped(state, winner, transferred)
            # If the cap dropped any (1.7.3), reflect that in the
            # returned transferred dict — the loser already had assets
            # removed, but the winner kept only `award["added"]`. The
            # "lost_to_cap" portion vanishes (per rule: "any excess
            # gained beyond 8 is lost immediately").
            transferred = dict(award["added"])
            lost_to_cap = award["lost_to_cap"]
    return {"from": from_lord, "to": to_lords[0] if to_lords else None,
            "transferred": transferred,
            "lost_to_cap": locals().get("lost_to_cap", {}),
            "mode": mode,
            "retreat_way_type": retreat_way_type}


# ---------------------------------------------------------------------------
# 4.5.2 Storm helpers (Phase 3c)
# ---------------------------------------------------------------------------


def _storm_hits_for_units(units: ForceCounts, kind: str, in_storm: bool = True) -> float:
    """Variant of _hits_for_strike for Storm:
    - Garrison Men-at-Arms have Archery with target Armor -2 (encoded as
      'archery_garrison' kind here).
    - Garrison Knights have Melee only.
    The caller passes Garrison units separately; for normal Lord units in
    a Storm, melee uses melee_storm value.
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
        elif kind == "archery_garrison_maa":
            # Garrison MaA: Archery 0.5/unit per Forces table.
            if utype == "men_at_arms":
                total += n * 0.5
        elif kind == "melee":
            v = float(spec.get("melee_storm" if in_storm else "melee_battle", 0.0))
            total += n * v
    return total


def _walls_absorb(state: GameState, hits: int, walls_max: int) -> int:
    """Roll one d6 per Hit; <= walls_max absorbs. Returns Hits remaining."""
    if walls_max <= 0:
        return hits
    remaining = hits
    absorbed = 0
    for _ in range(hits):
        roll = roll_d6(state)
        if roll <= walls_max:
            absorbed += 1
            remaining -= 1
    return remaining


def resolve_storm(
    state: GameState,
    attacker_side: Side,
    attacker_lords: list[str],
    defender_lords: list[str],
    locale_id: str,
    walls_max: int,
    siege_markers: int,
    garrison: dict[str, int],
    decision_ctx: BattleDecisionContext | None = None,
) -> dict[str, Any]:
    """Resolve a Storm at `locale_id` (4.5.2 2E).

    Storm Array (4.5.2 page 17): each side's Front row holds at most
    one Lord. The Attacker's Active Lord starts at Front; other Lords
    start in Reserve. The Defender's first Lord (defender_lords[0])
    starts at Front; others start in Reserve.

    Storm Reposition (4.5.2 page 17, 2E follow-up B): in each Round
    after the first, Attacker then Defender MAY switch positions
    between their Front and any Reserve Lord. Operator decision via
    decision_ctx; the engine offers options that include "stay" plus
    each Reserve Lord; the operator picks who occupies Front this
    Round.

    Other 2E rules already enforced:
      - Garrison units sit with the defending Front Lord; defender
        Hits absorbed by Garrison first (4.5.2).
      - Walls roll for defender per Hit (1..walls_max).
      - Siegeworks (siege_markers as Walls 1..siege_markers) for
        attacker.
      - Per-Lord Melee Hits cap of 6 (AUDIT-001).
      - Storm Attacker absorbs Hits with Armored units first (AUDIT-003).
      - Storm ends on full Rout, on attacker Concede, or when
        rounds_completed >= siege_markers (attacker loses).

    Returns a dict with keys: rounds, winner, loser, log,
    garrison_remaining, attacker_storm_positions,
    defender_storm_positions, decisions.
    """
    log: list[dict[str, Any]] = []
    rounds = 0
    # Local mutable garrison units (separate from Lord forces).
    g_units: dict[str, int] = dict(garrison)
    if decision_ctx is None:
        decision_ctx = BattleDecisionContext()
    # Storm Array: first Lord = Front, rest = Reserve.
    atk_storm_pos: dict[str, str] = {}
    if attacker_lords:
        atk_storm_pos[attacker_lords[0]] = "storm_front"
        for lid in attacker_lords[1:]:
            atk_storm_pos[lid] = "storm_reserve"
    def_storm_pos: dict[str, str] = {}
    if defender_lords:
        def_storm_pos[defender_lords[0]] = "storm_front"
        for lid in defender_lords[1:]:
            def_storm_pos[lid] = "storm_reserve"
    while rounds < max(1, siege_markers + 1):
        rounds += 1
        round_log: dict[str, Any] = {
            "round": rounds, "steps": [],
            "attacker_storm_positions": dict(atk_storm_pos),
            "defender_storm_positions": dict(def_storm_pos),
            "reposition": None,
        }
        # Storm Reposition (4.5.2 page 17): Round 2+, Attacker then
        # Defender may swap their Front Lord with any Reserve Lord.
        if rounds >= 2:
            repo_log: dict[str, Any] = {}
            for side_label, positions, side_lords in (
                ("attacker", atk_storm_pos, attacker_lords),
                ("defender", def_storm_pos, defender_lords),
            ):
                # Find current Front and Reserves with Forces.
                current_front = next(
                    (lid for lid, p in positions.items()
                     if p == "storm_front"
                     and lid in state.lords and state.lords[lid].forces),
                    None,
                )
                reserves = [
                    lid for lid, p in positions.items()
                    if p == "storm_reserve"
                    and lid in state.lords and state.lords[lid].forces
                ]
                # If Front is Routed but a Reserve exists, the Reserve
                # must take Front (forced advance, not really a choice).
                if current_front is None and reserves:
                    chosen = (
                        reserves[0] if len(reserves) == 1 else
                        decision_ctx.decide(
                            "reserve_advance", side_label, reserves,
                            {"phase": "storm_advance_after_front_rout"},
                        )
                    )
                    # SMOKE-017 (Round 31): demote any prior Lord still
                    # labeled "storm_front" but Routed (no forces) to
                    # "storm_reserve" so we don't end up with two Lords
                    # at Front simultaneously. Strike logic already
                    # filters by Lord.forces, so this is a state-
                    # consistency fix, not a combat-result fix.
                    for lid_, p_ in list(positions.items()):
                        if p_ == "storm_front" and lid_ != chosen:
                            positions[lid_] = "storm_reserve"
                    positions[chosen] = "storm_front"
                    repo_log.setdefault(side_label, []).append({
                        "step": "advance", "lord": chosen,
                    })
                    continue
                if not reserves or current_front is None:
                    continue
                # Operator may switch: options = [current_front] (stay)
                # + each reserve Lord (swap into Front).
                options = [current_front] + reserves
                chosen = decision_ctx.decide(
                    "reserve_advance", side_label, options,
                    {"phase": "storm_reposition", "current_front": current_front},
                )
                if chosen != current_front:
                    positions[current_front] = "storm_reserve"
                    positions[chosen] = "storm_front"
                    repo_log.setdefault(side_label, []).append({
                        "step": "swap", "from": current_front, "to": chosen,
                    })
            if repo_log:
                round_log["reposition"] = repo_log
                round_log["attacker_storm_positions"] = dict(atk_storm_pos)
                round_log["defender_storm_positions"] = dict(def_storm_pos)

        # Storm initiative (4.5.2):
        #   1) archery defender (Garrison MaA + Lord-default archery)
        #   2) archery attacker
        #   3) melee defenders (Garrison + Front Lord)
        #   4) melee attackers (Front Lord)
        # Hits cap on melee: 6 per Lord per side per Round.
        # Storm Front Lord per side; Reserve Lords do not Strike.
        from nevsky.capabilities import any_capability
        atk_front_lords = [
            lid for lid, p in atk_storm_pos.items()
            if p == "storm_front" and lid in state.lords
            and state.lords[lid].forces
        ]
        def_front_lords = [
            lid for lid, p in def_storm_pos.items()
            if p == "storm_front" and lid in state.lords
            and state.lords[lid].forces
        ]
        # Q-007 split: track Crossbow (-2-Armor) vs Normal archery raws
        # on each side. Garrison MaA archery is always Crossbow (per
        # Forces Reference: Storm Garrison MaA archery imposes -2 Armor).
        def_arch_cb_raw = _storm_hits_for_units(g_units, "archery_garrison_maa")
        def_arch_norm_raw = 0.0
        for lid in def_front_lords:
            units = state.lords[lid].forces
            base = _hits_for_strike(units, "archery")
            def_arch_norm_raw += base  # default archery from Asiatic Horse, etc.
            if any_capability(state, lid, "Luchniki"):
                def_arch_norm_raw += 0.5 * units.get("light_horse", 0)
                def_arch_norm_raw += 0.5 * units.get("militia", 0)
            if any_capability(state, lid, "Streltsy") or any_capability(state, lid, "Balistarii"):
                def_arch_cb_raw += 0.5 * units.get("men_at_arms", 0)
        atk_arch_cb_raw = 0.0
        atk_arch_norm_raw = 0.0
        for lid in atk_front_lords:
            units = state.lords[lid].forces
            base = _hits_for_strike(units, "archery")
            atk_arch_norm_raw += base
            if any_capability(state, lid, "Luchniki"):
                atk_arch_norm_raw += 0.5 * units.get("light_horse", 0)
                atk_arch_norm_raw += 0.5 * units.get("militia", 0)
            if any_capability(state, lid, "Streltsy") or any_capability(state, lid, "Balistarii"):
                atk_arch_cb_raw += 0.5 * units.get("men_at_arms", 0)
        def_arch = def_arch_cb_raw + def_arch_norm_raw
        atk_arch = atk_arch_cb_raw + atk_arch_norm_raw
        # AUDIT-001 fix (4.5.2 2E rule): "Maximum 6 Melee Hits per Lord
        # per Round". Apply cap PER LORD before summing, not on the
        # per-side total. Garrison units share the defending Front
        # Lord's cap (rules: "strikes_combine_with: Defending Front
        # Lord (round up combined totals)").
        def_melee = 0.0
        if def_front_lords:
            for lid in def_front_lords:
                lord_melee = _storm_hits_for_units(state.lords[lid].forces, "melee")
                # Defender Front Lord absorbs Garrison melee under the same cap.
                lord_melee += _storm_hits_for_units(g_units, "melee")
                def_melee += min(6.0, lord_melee)
        else:
            # SMOKE-015b: garrison-only defense still strikes in melee.
            # No Lord to combine with; cap applies to garrison alone.
            def_melee = min(6.0, _storm_hits_for_units(g_units, "melee"))
        atk_melee = 0.0
        for lid in atk_front_lords:
            atk_melee += min(6.0, _storm_hits_for_units(state.lords[lid].forces, "melee"))
        # Q-007: per-side Crossbow Hit count derived from raws via
        # 'round in favor of Crossbowmen'. Total stays = ceil(sum).
        def_arch_total = _round_up(def_arch)
        def_arch_cb = min(_round_up(def_arch_cb_raw), def_arch_total)
        atk_arch_total = _round_up(atk_arch)
        atk_arch_cb = min(_round_up(atk_arch_cb_raw), atk_arch_total)
        # Phase 4a: Trebuchets reduce Walls and Siegeworks by 1 if any
        # Unrouted Lord on the storming side has it (4.5.2).
        atk_has_trebuchets = any(
            any_capability(state, lid, "Trebuchets") and state.lords[lid].forces
            for lid in attacker_lords if lid in state.lords
        )
        # AUDIT-001 fix: melee cap applied per-Lord in the sum loop above.

        # Resolve defender archery -> attacker units (Walls do NOT protect
        # attacker; Siegeworks do not protect attacker against own
        # archery either -- only walls protect defender).
        # Trebuchets (T14): reduce Walls/Siegeworks by 1 (min 0) when
        # the storming side has at least one Unrouted Lord with Trebuchets.
        eff_walls_max = max(0, walls_max - 1) if atk_has_trebuchets else walls_max
        eff_siegeworks = siege_markers  # Trebuchets reduce defender Walls;
                                         # the defender side does not get its
                                         # own Trebuchets bonus against the
                                         # attacker\'s Siegeworks (rule scope).

        # AUDIT-003 (4.5.2 2E): Storm Attacker MUST absorb Hits with any
        # Armored units before non-Armored. Encode per-step assignment
        # policy alongside other step parameters.
        # Storm Hit absorption: Reserve Lords do NOT absorb Hits.
        # Defender side: Garrison absorbs first, then Defender Front
        # Lord. Attacker side: Attacker Front Lord.
        # Each tuple: (label, kind, hits, target_lords, target_is_defender,
        # cb_hits, assignment_policy). cb_hits is the count of Hits in
        # this step that carry -2 Armor reduction (Q-007). Melee steps
        # have cb_hits=0 (Crossbowmen rule applies to Archery only).
        steps_data = [
            ("archery_defender", "archery", def_arch_total, atk_front_lords, False, def_arch_cb, "armored_first"),
            ("archery_attacker", "archery", atk_arch_total, def_front_lords, True,  atk_arch_cb, "weakest_first"),
            ("melee_defender",   "melee",   _round_up(def_melee), atk_front_lords, False, 0, "armored_first"),
            ("melee_attacker",   "melee",   _round_up(atk_melee), def_front_lords, True,  0, "weakest_first"),
        ]
        for label, kind, hits, target_lords, target_is_defender, cb_hits, assignment_policy in steps_data:
            step_state: dict = {}  # AUDIT-002: per-step Warrior Monks reroll budget
            if target_is_defender:
                hits = _walls_absorb(state, hits, eff_walls_max)
            else:
                hits = _walls_absorb(state, hits, eff_siegeworks)
            distribution: list[dict[str, Any]] = []
            remaining = hits
            if target_is_defender and g_units:
                # Hits to Garrison first (4.5.2 hit_assignment_defender).
                for utype in ("men_at_arms", "knights"):
                    while remaining > 0 and g_units.get(utype, 0) > 0:
                        # Garrison units have armor:1-3 (MaA) or armor:1-4 (Knights).
                        from nevsky.static_data import load_forces
                        spec = load_forces()[utype]["protection_storm"]
                        if spec.startswith("armor:1-"):
                            roll = roll_d6(state)
                            max_abs = int(spec.split("-", 1)[1])
                            if roll <= max_abs:
                                remaining -= 1
                                distribution.append({"target": "garrison", "unit": utype, "absorbed": True})
                                continue
                        # Failed -> remove garrison unit.
                        g_units[utype] -= 1
                        remaining -= 1
                        distribution.append({"target": "garrison", "unit": utype, "absorbed": False})
            # Then Lord units.
            for tlid in target_lords:
                if remaining <= 0:
                    break
                if tlid not in state.lords:
                    continue
                if not state.lords[tlid].forces:
                    continue
                strike_kind = "archery" if kind == "archery" else "melee"
                # Q-007: build ordered hit_flags so cb_hits carry -2 Armor.
                # If walls/garrison have absorbed some hits already, the
                # remaining hits get the same crossbow share (cb_hits
                # reduced by absorbed-from-original ratio).
                eff_cb = min(cb_hits, remaining)
                eff_norm = remaining - eff_cb
                hit_flags_list = [True] * eff_cb + [False] * eff_norm
                tres = _resolve_hits(
                    state, tlid, remaining, strike_kind,
                    hit_flags=hit_flags_list,
                    step_state=step_state,
                    assignment_policy=assignment_policy,
                    in_storm=True,
                )
                distribution.append({"target": "lord", "lord": tlid, **tres})
                remaining = 0
            if hits > 0 or distribution:
                round_log["steps"].append({
                    "step": label, "hits_after_walls": hits,
                    "distribution": distribution,
                })
            # SMOKE-015 (Round 13): mid-round break if either side is
            # wiped. _all_routed([]) returns True for an empty list
            # (vacuous truth); for Storm a garrison-only defense
            # (defender_lords=[]) is NOT "wiped" until the garrison
            # is also gone. Guard accordingly.
            atk_wiped = bool(attacker_lords) and _all_routed(state, attacker_lords)
            def_wiped = (
                (not defender_lords or _all_routed(state, defender_lords))
                and sum(g_units.values()) == 0
            )
            if atk_wiped or def_wiped:
                break

        log.append(round_log)
        atk_routed = _all_routed(state, attacker_lords)
        def_routed = (
            (not defender_lords or _all_routed(state, defender_lords))
            and sum(g_units.values()) == 0
        )
        common = {
            "log": log, "garrison_remaining": g_units,
            "attacker_storm_positions": dict(atk_storm_pos),
            "defender_storm_positions": dict(def_storm_pos),
            "decisions": list(decision_ctx.log),
        }
        if atk_routed:
            return {"rounds": rounds, "winner": "defender", "loser": "attacker", **common}
        if def_routed:
            return {"rounds": rounds, "winner": "attacker", "loser": "defender", **common}

    # Time out: attacker loses (rounds_completed >= siege_markers).
    return {
        "rounds": rounds, "winner": "defender", "loser": "attacker",
        "stalemate": True,
        "log": log, "garrison_remaining": g_units,
        "attacker_storm_positions": dict(atk_storm_pos),
        "defender_storm_positions": dict(def_storm_pos),
        "decisions": list(decision_ctx.log),
    }


def apply_losses_rolls(
    state: GameState,
    lord_id: str,
    loser_state: str,
) -> dict:
    """4.4.4 Losses: for each Routed unit, roll 1d6.

    Threshold by loser_state:
      - "retreated_no_concede": needs roll == 1 to keep
      - "storm_attacker":       needs roll == 1 to keep
      - "withdrew" or "conceded_then_retreated":
            needs roll within unmodified Protection range
      - "removed":              all routed units lost (Lord was wiped)

    Asiatic Horse always uses Evade range.

    Successful rolls: unit returns to lord.forces.
    Failed rolls: unit permanently lost (removed from routed_units).
    """
    from nevsky.rng import roll_d6

    lord = state.lords[lord_id]
    if not lord.routed_units:
        return {"lord_id": lord_id, "rolls": []}
    rolls = []
    forces_table = load_forces()
    routed = dict(lord.routed_units)
    for utype, n in routed.items():
        spec = forces_table[utype]
        # Determine threshold.
        if loser_state == "removed":
            keep = 0  # all lost
        elif loser_state in ("retreated_no_concede", "storm_attacker"):
            keep = 1  # only roll == 1 keeps
        elif loser_state in ("withdrew", "conceded_then_retreated"):
            # Unmodified Protection range. For armor: 1-N. For evade: 1-N.
            # For unarmored / serfs / asiatic_horse-archery: 1.
            prot = spec["protection_battle_melee"]
            if utype == "asiatic_horse":
                # Asiatic Horse always uses Evade range.
                prot = "evade:1-3"
            if prot == "none":
                keep = 0
            elif prot == "unarmored":
                keep = 1
            elif prot.startswith("armor:1-"):
                keep = int(prot.split("-", 1)[1])
            elif prot.startswith("evade:1-"):
                keep = int(prot.split("-", 1)[1])
            else:
                keep = 0
        else:
            keep = 1
        rolls_for_type = []
        kept = 0
        lost = 0
        for _ in range(n):
            r = roll_d6(state)
            if r <= keep:
                kept += 1
                rolls_for_type.append({"roll": r, "outcome": "kept"})
            else:
                lost += 1
                rolls_for_type.append({"roll": r, "outcome": "lost"})
        # Move kept back to forces; lost just removed.
        if kept > 0:
            lord.forces[utype] = lord.forces.get(utype, 0) + kept  # type: ignore[index]
        # Clear routed pile entry.
        del lord.routed_units[utype]
        rolls.append({
            "unit": utype, "n_routed": n, "keep_threshold": keep,
            "kept": kept, "lost": lost, "rolls": rolls_for_type,
        })
    return {"lord_id": lord_id, "rolls": rolls}


def clear_routed_pile(state: GameState, lord_id: str) -> int:
    """Discard all routed_units for a Lord without rolling. Returns
    count discarded. Used for permanent-removal cases where the Lord
    is leaving the game anyway."""
    if lord_id not in state.lords:
        return 0
    lord = state.lords[lord_id]
    n = sum(lord.routed_units.values())
    lord.routed_units = {}
    return n
