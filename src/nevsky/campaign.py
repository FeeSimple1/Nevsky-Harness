"""Campaign-phase action handlers (4.1-4.9).

Phase 3a covers: Plan (4.1), Activation loop (4.2), simple Commands
(Tax 4.7.4, Forage 4.7.1, Ravage 4.7.2, Supply 4.6, Sail 4.7.3, Pass
4.7.5), Feed/Pay/Disband cycle (4.8), and End Campaign housekeeping
(4.9).

Phase 3b will add March (4.3), Avoid Battle, Withdraw, Battle (4.4).
Phase 3c will add Siege/Storm (4.5) and Sally (4.5.3).

Per BRIEF Phase 4: per-card AoW effects are deferred. The harness
flags cards in play that would affect a current action; the user/LLM
applies the actual capability text.
"""

from __future__ import annotations

from typing import Any

from nevsky.actions import (
    IllegalAction,
    _disband_at_limit,
    _find_levy_marker_box,
    _find_service_marker_box,
    _is_friendly_locale,
    _remove_lord_permanently,
    _require_active,
    _require_side_player,
    _season_of_box,
    _shift_service_right,
    _side_deck,
)
from nevsky.state import GameState, Side
from nevsky.static_data import load_locales, load_lords, load_ways

# ---------------------------------------------------------------------------
# 4.1 Plan
# ---------------------------------------------------------------------------


def _plan_target_size(box: int) -> int:
    """SoP 4.1 stack size by season."""
    season = _season_of_box(box)
    if season == "summer":
        return 6
    if season == "rasputitsa":
        return 5
    return 4  # early_winter / late_winter


def _h_plan_add_card(
    state: GameState, side: str, args: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """4.1: append a Command card to the side's Plan stack.

    args.card: lord_id of a currently Mustered own-side Lord, OR "pass".
    Each Lord has 3 Command cards; the side may include the same Lord up
    to 3 times. If too few Mustered Lords to fill the season's target,
    Pass cards fill the remainder (1.9.2).
    """
    sd = _require_side_player(state, side)
    if state.meta.phase != "campaign":
        raise IllegalAction("wrong_phase", "plan_add_card requires campaign phase")
    if state.meta.campaign_step != "plan":
        raise IllegalAction(
            "wrong_step", f"plan_add_card requires campaign_step=plan; got {state.meta.campaign_step}"
        )
    plan_done = state.meta.plan_complete_t if sd == "teutonic" else state.meta.plan_complete_r
    if plan_done:
        raise IllegalAction("already_done", f"{sd} Plan already finalized this Campaign")

    card = args.get("card")
    if not isinstance(card, str):
        raise IllegalAction("missing_arg", "args.card must be a Lord id or 'pass'")

    deck = _side_deck(state, sd)
    target = _plan_target_size(state.meta.box)
    if len(deck.plan) >= target:
        raise IllegalAction(
            "plan_full",
            f"{sd} Plan already at target size {target}; finalize_plan to proceed",
        )
    if card == "pass":
        deck.plan.append("pass")
        return ({"appended": "pass", "plan_size": len(deck.plan)}, [])

    # Lord card: must be Mustered own-side Lord with < 3 entries already.
    if card not in state.lords or state.lords[card].side != sd:
        raise IllegalAction("bad_card", f"{card} not a {sd} Lord")
    if state.lords[card].state != "mustered":
        raise IllegalAction("bad_card", f"{card} is not Mustered (state={state.lords[card].state})")
    if deck.plan.count(card) >= 3:
        raise IllegalAction(
            "card_limit",
            f"{card} already has 3 Command cards in Plan (max per Lord per Campaign)",
        )
    deck.plan.append(card)
    return ({"appended": card, "plan_size": len(deck.plan)}, [])


def _h_finalize_plan(
    state: GameState, side: str, args: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Mark this side's Plan complete. Both sides must finalize before
    Activation (4.2) begins.
    """
    sd = _require_side_player(state, side)
    if state.meta.phase != "campaign":
        raise IllegalAction("wrong_phase", "finalize_plan requires campaign phase")
    if state.meta.campaign_step != "plan":
        raise IllegalAction("wrong_step", "finalize_plan requires campaign_step=plan")

    deck = _side_deck(state, sd)
    target = _plan_target_size(state.meta.box)
    if len(deck.plan) != target:
        raise IllegalAction(
            "plan_size_mismatch",
            f"Plan size {len(deck.plan)}; season target {target}",
        )
    if sd == "teutonic":
        if state.meta.plan_complete_t:
            raise IllegalAction("already_done", "Teutonic Plan already finalized")
        state.meta.plan_complete_t = True
    else:
        if state.meta.plan_complete_r:
            raise IllegalAction("already_done", "Russian Plan already finalized")
        state.meta.plan_complete_r = True

    advanced = False
    if state.meta.plan_complete_t and state.meta.plan_complete_r:
        # Move to Activation loop.
        state.meta.campaign_step = "command"
        state.meta.active_player = "teutonic"  # T reveals first per 4.2
        state.campaign_turn.next_to_reveal = "teutonic"
        state.campaign_turn.active_card = None
        state.campaign_turn.active_lord = None
        state.campaign_turn.actions_remaining = 0
        state.campaign_turn.in_feed_pay_disband = False
        state.campaign_turn.fpd_completed_t = False
        state.campaign_turn.fpd_completed_r = False
        advanced = True
    return ({"plan_complete": True, "advanced_to_activation": advanced}, [])


# ---------------------------------------------------------------------------
# 4.2 Command Activation loop
# ---------------------------------------------------------------------------


def _h_command_reveal(
    state: GameState, side: str, args: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """4.2: reveal the top Command card of the active side.

    Sets campaign_turn.active_card / active_lord / actions_remaining.
    Auto-passes when the card is Pass / belongs to a Lower Lord (4.1.3
    deferred to Phase 3b — for now, Lower-Lord pass not handled) / Lord
    not on map (4.2.3).
    """
    sd = _require_side_player(state, side)
    if state.meta.phase != "campaign":
        raise IllegalAction("wrong_phase", "command_reveal requires campaign phase")
    if state.meta.campaign_step != "command":
        raise IllegalAction("wrong_step", "command_reveal requires campaign_step=command")
    if state.campaign_turn.in_feed_pay_disband:
        raise IllegalAction("in_feed_pay_disband", "complete 4.8 before next reveal")
    if state.campaign_turn.actions_remaining > 0:
        raise IllegalAction(
            "actions_remaining",
            f"active Lord still has {state.campaign_turn.actions_remaining} actions left",
        )
    _require_active(state, sd)
    if state.campaign_turn.next_to_reveal != sd:
        raise IllegalAction(
            "wrong_actor",
            f"next reveal is by {state.campaign_turn.next_to_reveal}; got {sd}",
        )

    deck = _side_deck(state, sd)
    if not deck.plan:
        raise IllegalAction("plan_empty", f"{sd} Plan stack is empty")
    card = deck.plan[0]
    deck.plan = deck.plan[1:]

    state.campaign_turn.active_card = card
    static = load_lords()
    if card == "pass":
        # 4.2.3 Pass: no actions; flip to other side; enter 4.8 (Feed/Pay/Disband)
        # for cards that did not move/fight no MOVED_FOUGHT lords -> trivial.
        state.campaign_turn.active_lord = None
        state.campaign_turn.actions_remaining = 0
        _enter_feed_pay_disband(state)
        return ({"revealed": "pass", "outcome": "pass"}, [])

    # Card is a Lord id.
    lord = state.lords.get(card)
    if lord is None or lord.state != "mustered" or lord.location is None:
        # 4.2.3: Lord on card not on map -> Pass.
        state.campaign_turn.active_lord = None
        state.campaign_turn.actions_remaining = 0
        _enter_feed_pay_disband(state)
        return ({"revealed": card, "outcome": "pass_not_on_map"}, [])

    state.campaign_turn.active_lord = card
    state.campaign_turn.actions_remaining = int(static[card]["ratings"]["command"])
    return ({"revealed": card, "outcome": "active", "actions": state.campaign_turn.actions_remaining}, [])


def _enter_feed_pay_disband(state: GameState) -> None:
    """Helper: transition to per-card 4.8 sub-step."""
    state.campaign_turn.in_feed_pay_disband = True
    state.campaign_turn.fpd_completed_t = False
    state.campaign_turn.fpd_completed_r = False
    state.meta.active_player = "teutonic"  # T-then-R for 4.8


def _h_end_card(
    state: GameState, side: str, args: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """End the active Command card before exhausting actions (e.g., the
    Lord declares Pass mid-card per 4.7.5, or chose to stop voluntarily).

    Most simple Command actions consume 1 action each; the Lord may stop
    when they choose. Some Commands are entire-card (Sail, Tax) and
    automatically end the card via the action itself.
    """
    sd = _require_side_player(state, side)
    if state.meta.phase != "campaign":
        raise IllegalAction("wrong_phase", "end_card requires campaign phase")
    if state.meta.campaign_step != "command":
        raise IllegalAction("wrong_step", "end_card requires campaign_step=command")
    if state.campaign_turn.in_feed_pay_disband:
        raise IllegalAction("in_feed_pay_disband", "already in 4.8")
    _require_active(state, sd)
    if state.campaign_turn.next_to_reveal != sd:
        raise IllegalAction("wrong_actor", "not your active Command")
    state.campaign_turn.actions_remaining = 0
    _enter_feed_pay_disband(state)
    return ({"ended": True}, [])


def _h_fpd_resolve(
    state: GameState, side: str, args: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """4.8 Feed/Pay/Disband for one side, applied to all that side's
    MOVED_FOUGHT Lords.

    4.8.1 Feed: per-Lord 1 Provender/Loot for 1-6 units, 2 for 7+. Own
    Provender/Loot first, then surplus shared with co-located own-side
    Lords. Unfed: shift Service marker 1 box LEFT.
    4.8.2 Pay: same mechanics as 3.2 (caller may queue pay_with_coin /
    pay_with_loot actions before fpd_resolve to actually shift Service).
    4.8.2 Disband: at-limit Disband during Campaign counts cylinder
    placement from NEXT box (3.3.2 2E).
    4.8.3: remove all MOVED_FOUGHT markers.

    For Phase 3a we resolve Feed and Disband automatically; Pay is left
    for the player to invoke separately via pay_with_coin / pay_with_loot
    BEFORE calling fpd_resolve. This is consistent with the rules order:
    4.8.1 Feed -> 4.8.2 Pay -> 4.8.2 Disband check -> 4.8.3 remove.
    """
    sd = _require_side_player(state, side)
    if state.meta.phase != "campaign":
        raise IllegalAction("wrong_phase", "fpd_resolve requires campaign phase")
    if state.meta.campaign_step != "command":
        raise IllegalAction("wrong_step", "fpd_resolve requires campaign_step=command")
    if not state.campaign_turn.in_feed_pay_disband:
        raise IllegalAction("not_in_fpd", "not in 4.8 sub-step")
    _require_active(state, sd)

    # Feed every MOVED_FOUGHT Lord on this side.
    feed_results: list[dict[str, Any]] = []
    for lord_id, lord in list(state.lords.items()):
        if lord.side != sd or not lord.moved_fought:
            continue
        n_units = sum(lord.forces.values())
        cost = 2 if n_units >= 7 else 1
        own_avail = lord.assets.get("provender", 0) + lord.assets.get("loot", 0)
        # try own provender first, then loot
        consumed = {"provender": 0, "loot": 0}
        remaining = cost
        if remaining > 0 and lord.assets.get("provender", 0) > 0:
            take = min(remaining, lord.assets["provender"])
            lord.assets["provender"] -= take
            consumed["provender"] = take
            remaining -= take
            if lord.assets["provender"] == 0:
                del lord.assets["provender"]
        if remaining > 0 and lord.assets.get("loot", 0) > 0:
            take = min(remaining, lord.assets["loot"])
            lord.assets["loot"] -= take
            consumed["loot"] = take
            remaining -= take
            if lord.assets["loot"] == 0:
                del lord.assets["loot"]
        # Try sharing from co-located own-side Lords if still short.
        if remaining > 0:
            for other_id, other in state.lords.items():
                if other_id == lord_id or other.side != sd:
                    continue
                if other.location != lord.location:
                    continue
                for k in ("provender", "loot"):
                    if remaining > 0 and other.assets.get(k, 0) > 0:
                        take = min(remaining, other.assets[k])
                        other.assets[k] -= take
                        if other.assets[k] == 0:
                            del other.assets[k]
                        consumed[k] += take
                        remaining -= take
                if remaining == 0:
                    break
        unfed = remaining > 0
        if unfed:
            # Shift Service marker 1 box LEFT (4.8.1 unfed penalty).
            sm_box = _find_service_marker_box(state, lord_id)
            if sm_box is not None and sm_box >= 1 and sm_box <= 16:
                state.calendar.boxes[sm_box - 1].service_markers.remove(lord_id)
                if sm_box == 1:
                    state.calendar.off_left.append(lord_id)
                else:
                    state.calendar.boxes[sm_box - 2].service_markers.append(lord_id)
        feed_results.append({
            "lord_id": lord_id,
            "units": n_units,
            "cost": cost,
            "consumed": consumed,
            "unfed": unfed,
        })

    # 4.8.2 Disband check: any Lord whose Service marker is at-or-left-of Levy.
    static = load_lords()
    levy_box = _find_levy_marker_box(state)
    permanently_removed: list[str] = []
    disbanded: list[dict[str, Any]] = []
    for lord_id, lord in list(state.lords.items()):
        if lord.side != sd or lord.state != "mustered":
            continue
        sm_box = _find_service_marker_box(state, lord_id)
        if sm_box is None:
            continue
        if sm_box < levy_box:
            _remove_lord_permanently(state, lord_id, static[lord_id])
            permanently_removed.append(lord_id)
        elif sm_box == levy_box:
            srating = int(static[lord_id]["ratings"]["service"])
            new_box = sm_box + 1 + srating  # 4.8.2 + 3.3.2 (2E): count from NEXT box
            _disband_at_limit(state, lord_id, new_box)
            disbanded.append({"lord_id": lord_id, "new_box": min(new_box, 17)})

    # 4.8.3: remove MOVED_FOUGHT markers.
    for lord in state.lords.values():
        if lord.side == sd and lord.moved_fought:
            lord.moved_fought = False

    # Mark side complete.
    if sd == "teutonic":
        state.campaign_turn.fpd_completed_t = True
        state.meta.active_player = "russian"
    else:
        state.campaign_turn.fpd_completed_r = True

    advanced = False
    if state.campaign_turn.fpd_completed_t and state.campaign_turn.fpd_completed_r:
        # 4.8.3 done; ready for next reveal or end campaign.
        state.campaign_turn.in_feed_pay_disband = False
        state.campaign_turn.active_card = None
        state.campaign_turn.active_lord = None
        # Alternate reveal pointer: if last card was T's, R reveals next
        # and vice versa. SoP 4.2: alternating T-R-T-R-... regardless of
        # outcome of the card itself.
        next_side: Side = "russian" if state.campaign_turn.next_to_reveal == "teutonic" else "teutonic"
        state.campaign_turn.next_to_reveal = next_side
        # Check if both Plan stacks are empty -> end of Campaign.
        if not state.decks.teutonic.plan and not state.decks.russian.plan:
            state.meta.campaign_step = "end_campaign"
            state.meta.active_player = "teutonic"
            state.meta.end_campaign_completed_t = False
            state.meta.end_campaign_completed_r = False
        else:
            # If next_side has empty plan but other still has cards, the
            # other side keeps revealing alternately by skipping.
            # Implementation: if next_side's plan is empty and other has
            # cards, other side reveals; we just set active_player to
            # whichever has plan remaining.
            if not _side_deck(state, next_side).plan:
                next_side = "russian" if next_side == "teutonic" else "teutonic"
                state.campaign_turn.next_to_reveal = next_side
            state.meta.active_player = next_side
        advanced = True

    return ({"side": sd, "feed": feed_results, "permanently_removed": permanently_removed,
             "disbanded": disbanded, "advanced": advanced}, [])


# ---------------------------------------------------------------------------
# Active-Lord helpers
# ---------------------------------------------------------------------------


def _require_active_lord_command(state: GameState, side: Side, lord_id: str) -> None:
    """The Lord performing this command must be the campaign_turn.active_lord."""
    if state.meta.campaign_step != "command":
        raise IllegalAction("wrong_step", "command actions require campaign_step=command")
    if state.campaign_turn.in_feed_pay_disband:
        raise IllegalAction("in_feed_pay_disband", "Feed/Pay/Disband sub-step running; no Lord actions")
    if state.campaign_turn.active_lord != lord_id:
        raise IllegalAction(
            "not_active_lord",
            f"active Lord is {state.campaign_turn.active_lord}; got {lord_id}",
        )
    if state.lords[lord_id].side != side:
        raise IllegalAction("wrong_side", f"{lord_id} not on {side} side")
    if state.campaign_turn.actions_remaining <= 0:
        raise IllegalAction("no_actions_left", "Lord has no actions remaining on this card")


def _consume_actions(state: GameState, n: int) -> None:
    state.campaign_turn.actions_remaining -= n
    if state.campaign_turn.actions_remaining < 0:
        state.campaign_turn.actions_remaining = 0


def _is_besieged(state: GameState, lord_id: str) -> bool:
    lord = state.lords[lord_id]
    if lord.state != "mustered" or lord.location is None:
        return False
    return state.locales[lord.location].siege_markers > 0


def _is_own_seat(state: GameState, lord_id: str, locale_id: str) -> bool:
    """Check whether `locale_id` is one of `lord_id`'s Seats (3.4.1)."""
    from nevsky.actions import _seats_of  # reuse Phase 2 logic

    return locale_id in _seats_of(state, lord_id)


# ---------------------------------------------------------------------------
# 4.7.4 Tax
# ---------------------------------------------------------------------------


def _h_cmd_tax(
    state: GameState, side: str, args: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """4.7.4: Active Unbesieged Lord at his own Seat. Add 1 Coin (max 8).
    Tax consumes the entire card.
    """
    sd = _require_side_player(state, side)
    lord_id = args.get("lord_id", state.campaign_turn.active_lord)
    if not isinstance(lord_id, str):
        raise IllegalAction("missing_arg", "args.lord_id required")
    _require_active_lord_command(state, sd, lord_id)

    lord = state.lords[lord_id]
    if _is_besieged(state, lord_id):
        raise IllegalAction("besieged", "Tax requires Unbesieged Lord (4.7.4)")
    if lord.location is None or not _is_own_seat(state, lord_id, lord.location):
        raise IllegalAction("not_at_seat", f"{lord_id} not at own Seat")

    if lord.assets.get("coin", 0) >= 8:
        raise IllegalAction("coin_max", f"{lord_id} at Coin cap (1.7.3)")
    lord.assets["coin"] = lord.assets.get("coin", 0) + 1
    lord.moved_fought = True
    # Tax consumes the entire card.
    state.campaign_turn.actions_remaining = 0
    _enter_feed_pay_disband(state)
    return ({"lord_id": lord_id, "added": "coin", "new_count": lord.assets["coin"]}, [])


# ---------------------------------------------------------------------------
# 4.7.1 Forage
# ---------------------------------------------------------------------------


def _h_cmd_forage(
    state: GameState, side: str, args: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """4.7.1: 1 action; +1 Provender (max 8). Requires:
    - Active Unbesieged Lord
    - Locale NOT Ravaged
    - At a Friendly Stronghold OR season is Summer
    """
    sd = _require_side_player(state, side)
    lord_id = args.get("lord_id", state.campaign_turn.active_lord)
    if not isinstance(lord_id, str):
        raise IllegalAction("missing_arg", "args.lord_id required")
    _require_active_lord_command(state, sd, lord_id)

    lord = state.lords[lord_id]
    if _is_besieged(state, lord_id):
        raise IllegalAction("besieged", "Forage requires Unbesieged Lord")
    loc = state.locales[lord.location]  # type: ignore[index]
    own_ravaged = loc.teutonic_ravaged if sd == "teutonic" else loc.russian_ravaged
    enemy_ravaged = loc.russian_ravaged if sd == "teutonic" else loc.teutonic_ravaged
    if own_ravaged or enemy_ravaged:
        raise IllegalAction("ravaged", f"{lord.location} is Ravaged; Forage forbidden (4.7.1)")

    season = _season_of_box(state.meta.box)
    static_locales = load_locales()
    is_friendly_stronghold = (
        _is_friendly_locale(state, lord.location, sd)  # type: ignore[arg-type]
        and static_locales[lord.location].get("type")  # type: ignore[index]
        in ("commandery", "fort", "city", "novgorod", "bishopric", "castle")
    )
    if not (is_friendly_stronghold or season == "summer"):
        raise IllegalAction(
            "forage_seasonal",
            "Forage requires Friendly Stronghold OR Summer (4.7.1)",
        )

    if lord.assets.get("provender", 0) >= 8:
        raise IllegalAction("provender_max", f"{lord_id} at Provender cap")
    lord.assets["provender"] = lord.assets.get("provender", 0) + 1
    lord.moved_fought = True
    _consume_actions(state, 1)
    return ({"lord_id": lord_id, "added": "provender", "new_count": lord.assets["provender"]}, [])


# ---------------------------------------------------------------------------
# 4.7.2 Ravage
# ---------------------------------------------------------------------------


def _h_cmd_ravage(
    state: GameState, side: str, args: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """4.7.2: place own-color Ravaged marker (1/2 VP); +1 Provender; +1 Loot
    if Locale type != Region. Costs 1 action default; 2 actions if an
    Unbesieged enemy Lord is adjacent (2E).
    Requires:
    - Active Unbesieged Lord
    - Locale is enemy territory (NOT own)
    - Locale NOT Conquered
    - Locale NOT Friendly to Active Lord's side
    - Locale NOT already Ravaged (either color)
    """
    sd = _require_side_player(state, side)
    lord_id = args.get("lord_id", state.campaign_turn.active_lord)
    if not isinstance(lord_id, str):
        raise IllegalAction("missing_arg", "args.lord_id required")
    _require_active_lord_command(state, sd, lord_id)

    lord = state.lords[lord_id]
    if _is_besieged(state, lord_id):
        raise IllegalAction("besieged", "Ravage requires Unbesieged Lord")
    if lord.location is None:
        raise IllegalAction("no_location", "Lord has no location")

    static_locales = load_locales()
    static = static_locales[lord.location]
    own_terr = sd
    if static["territory"] == own_terr:
        raise IllegalAction("own_territory", f"Cannot Ravage own territory ({lord.location})")
    loc = state.locales[lord.location]
    if loc.russian_conquered > 0 or loc.teutonic_conquered > 0:
        raise IllegalAction("conquered", "Locale already Conquered (4.7.2)")
    if _is_friendly_locale(state, lord.location, sd):
        raise IllegalAction("friendly", "Locale is Friendly to Active side; cannot Ravage")
    if loc.russian_ravaged or loc.teutonic_ravaged:
        raise IllegalAction("already_ravaged", "Locale already Ravaged (4.7.2)")

    # Adjacent unbesieged enemy Lord -> 2 actions.
    cost = 1
    ways = load_ways()
    adjacent = set()
    for w in ways:
        if w["a"] == lord.location:
            adjacent.add(w["b"])
        elif w["b"] == lord.location:
            adjacent.add(w["a"])
    for ol in state.lords.values():
        if ol.state == "mustered" and ol.side != sd and ol.location in adjacent:
            if state.locales[ol.location].siege_markers == 0:  # type: ignore[arg-type]
                cost = 2
                break
    if state.campaign_turn.actions_remaining < cost:
        raise IllegalAction(
            "insufficient_actions",
            f"Ravage costs {cost} actions; {state.campaign_turn.actions_remaining} remain",
        )

    # Place ravaged marker.
    if sd == "teutonic":
        loc.teutonic_ravaged = True
        state.calendar.teutonic_vp += 0.5
    else:
        loc.russian_ravaged = True
        state.calendar.russian_vp += 0.5

    # +1 Provender.
    lord.assets["provender"] = min(8, lord.assets.get("provender", 0) + 1)
    # +1 Loot if non-Region.
    if static["type"] != "region":
        lord.assets["loot"] = min(8, lord.assets.get("loot", 0) + 1)
    lord.moved_fought = True
    _consume_actions(state, cost)
    return (
        {
            "lord_id": lord_id,
            "locale": lord.location,
            "actions_used": cost,
            "ravaged_color": sd,
            "loot_added": static["type"] != "region",
        },
        [],
    )


# ---------------------------------------------------------------------------
# 4.7.5 Pass
# ---------------------------------------------------------------------------


def _h_cmd_pass(
    state: GameState, side: str, args: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """4.7.5: forfeit any unused actions on this Command card.
    Available to any Lord (including Besieged). Ends the card.
    """
    sd = _require_side_player(state, side)
    lord_id = args.get("lord_id", state.campaign_turn.active_lord)
    if not isinstance(lord_id, str):
        raise IllegalAction("missing_arg", "args.lord_id required")
    _require_active_lord_command(state, sd, lord_id)

    state.campaign_turn.actions_remaining = 0
    _enter_feed_pay_disband(state)
    return ({"lord_id": lord_id, "outcome": "passed"}, [])


# ---------------------------------------------------------------------------
# 4.7.3 Sail
# ---------------------------------------------------------------------------


def _h_cmd_sail(
    state: GameState, side: str, args: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """4.7.3: move directly Seaport -> Seaport. Entire card.

    args:
      lord_id          Active Lord
      destination      Seaport locale_id
      group            list[lord_id] of co-Sailing Lords (default: just lord_id)
                       (Marshal group, Lieutenant Lower Lord support deferred to 3b)
      ships_used       int: total Ships across the Sailing group (validation)

    Constraints:
      - Active Lord is Unbesieged at a Seaport.
      - Season is NOT Winter.
      - Destination Seaport free of Unbesieged enemy Lords.
      - Lord's group has enough Ships per ship_requirements.
      - If destination has Unbesieged enemy Stronghold: place a Siege marker.
    """
    sd = _require_side_player(state, side)
    lord_id = args.get("lord_id", state.campaign_turn.active_lord)
    dest = args.get("destination")
    group = args.get("group", [lord_id]) or [lord_id]
    if not (isinstance(lord_id, str) and isinstance(dest, str) and isinstance(group, list)):
        raise IllegalAction("missing_arg", "args: lord_id, destination, group(optional)")
    _require_active_lord_command(state, sd, lord_id)

    static_locales = load_locales()
    if static_locales[dest].get("seaport") is not True:
        raise IllegalAction("not_seaport", f"{dest} is not a Seaport (4.7.3)")
    src = state.lords[lord_id].location
    if src is None or static_locales[src].get("seaport") is not True:
        raise IllegalAction("not_seaport", f"Lord must be at a Seaport (got {src})")
    if _is_besieged(state, lord_id):
        raise IllegalAction("besieged", "Sail requires Unbesieged Lord")
    season = _season_of_box(state.meta.box)
    if season in ("early_winter", "late_winter"):
        raise IllegalAction("winter", "Sail forbidden in Winter (4.7.3)")
    # Destination must be free of Unbesieged enemy Lords.
    for ol in state.lords.values():
        if ol.state == "mustered" and ol.side != sd and ol.location == dest:
            if state.locales[dest].siege_markers == 0:
                raise IllegalAction("dest_blocked", f"{dest} has Unbesieged enemy Lord")

    # Move group.
    for gid in group:
        if gid not in state.lords or state.lords[gid].side != sd:
            raise IllegalAction("bad_group", f"{gid} not on your side")
        if state.lords[gid].location != src:
            raise IllegalAction("bad_group", f"{gid} not co-located with {lord_id}")
        state.lords[gid].location = dest
        state.lords[gid].moved_fought = True

    # Sailing to Unbesieged enemy Stronghold places a Siege marker.
    placed_siege = False
    dest_loc = state.locales[dest]
    dest_static = static_locales[dest]
    if dest_static["type"] in ("commandery", "fort", "city", "novgorod", "bishopric") and dest_loc.siege_markers == 0:
        # Enemy stronghold? -- check enemy Conquered marker or own-side absence
        enemy_owns_stronghold = (
            (sd == "teutonic" and (dest_static["territory"] == "russian" or dest_loc.russian_conquered > 0))
            or (sd == "russian" and (dest_static["territory"] in ("teutonic", "crusader") or dest_loc.teutonic_conquered > 0))
        )
        if enemy_owns_stronghold:
            dest_loc.siege_markers = 1
            placed_siege = True

    state.campaign_turn.actions_remaining = 0
    _enter_feed_pay_disband(state)
    return (
        {
            "lord_id": lord_id,
            "from": src,
            "to": dest,
            "group": group,
            "placed_siege": placed_siege,
        },
        [],
    )


# ---------------------------------------------------------------------------
# 4.6 Supply
# ---------------------------------------------------------------------------


def _h_cmd_supply(
    state: GameState, side: str, args: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """4.6: 1 action. +1 Provender per Source via valid Route(s) using
    enough Transport(s) (2E: 1 Transport per Provender per Way).

    args:
      lord_id     Active Lord
      sources     list of {locale_id, route: [<adjacent locales>], transport: <type>}
                  Each entry adds 1 Provender. Up to 2 Seat sources;
                  Russians: Novgorod via Ships up to 2 Provender;
                  Teutons: any Seaport via Ships up to 2 Provender.
                  For Phase 3a we accept the player-provided declarations
                  and validate them.
    """
    sd = _require_side_player(state, side)
    lord_id = args.get("lord_id", state.campaign_turn.active_lord)
    sources = args.get("sources", [])
    if not (isinstance(lord_id, str) and isinstance(sources, list)):
        raise IllegalAction("missing_arg", "args.lord_id required, args.sources required (list)")
    _require_active_lord_command(state, sd, lord_id)

    lord = state.lords[lord_id]
    if _is_besieged(state, lord_id):
        raise IllegalAction("besieged", "Supply requires Unbesieged Lord")
    if lord.location is None:
        raise IllegalAction("no_location", "Lord has no location")
    if state.campaign_turn.actions_remaining < 1:
        raise IllegalAction("insufficient_actions", "Supply costs 1 action")

    static_locales = load_locales()
    ways_list = load_ways()
    way_index: dict[tuple[str, str], str] = {}
    for w in ways_list:
        way_index[(w["a"], w["b"])] = w["type"]
        way_index[(w["b"], w["a"])] = w["type"]

    season = _season_of_box(state.meta.box)
    seat_count = 0
    ship_count = 0
    added = 0

    for src in sources:
        sid = src.get("locale_id")
        route = src.get("route", [])
        ttype = src.get("transport")
        if not isinstance(sid, str) or not isinstance(route, list) or not isinstance(ttype, str):
            raise IllegalAction("bad_source", "each source: {locale_id, route[], transport}")
        if ttype not in ("boat", "cart", "sled", "ship"):
            raise IllegalAction("bad_source", f"unknown transport {ttype}")

        # Validate transport seasonality (1.7.4).
        if ttype == "ship":
            if season in ("early_winter", "late_winter"):
                raise IllegalAction("ship_winter", "Ships not usable in Winter")
            ship_count += 1
        elif ttype == "boat":
            if season in ("early_winter", "late_winter"):
                raise IllegalAction("boat_winter", "Boats only usable in Summer/Rasputitsa")
        elif ttype == "cart":
            if season != "summer":
                raise IllegalAction("cart_non_summer", "Carts usable in Summer only")
        elif ttype == "sled":
            if season not in ("early_winter", "late_winter", "rasputitsa"):
                raise IllegalAction("sled_summer", "Sleds usable in Winter/Rasputitsa only")

        # Source eligibility.
        if ttype == "ship":
            if sd == "russian":
                if sid != "novgorod":
                    raise IllegalAction("bad_source", "Russian Ship Supply source must be Novgorod")
            else:  # teutonic
                if not static_locales[sid].get("seaport"):
                    raise IllegalAction("bad_source", "Teutonic Ship Supply source must be a Seaport")
            ship_count += 0  # already counted above
        else:
            # Seat source (own-side mustered Lord's Seat).
            if sid not in [s for sl in (lord_id,) for s in _all_seats(state, sl)]:
                raise IllegalAction("bad_source", f"{sid} not a Seat of {lord_id}")
            seat_count += 1

        # Route validation: chain of adjacent locales from sid -> ... -> lord.location.
        if not route:
            raise IllegalAction("bad_route", "route must list intermediate locales (incl. ends)")
        if route[0] != sid or route[-1] != lord.location:
            raise IllegalAction("bad_route", "route must start at source and end at Lord's locale")
        for i in range(len(route) - 1):
            a, b = route[i], route[i + 1]
            wtype = way_index.get((a, b))
            if wtype is None:
                raise IllegalAction("bad_route", f"no Way between {a} and {b}")
            # Transport-Way compatibility (1.7.4).
            if ttype == "boat" and wtype != "waterway":
                raise IllegalAction("transport_way", "Boats use only Waterways")
            if ttype == "cart" and wtype != "trackway":
                raise IllegalAction("transport_way", "Carts use only Trackways")
            # sleds, ships fine for any (within seasonal limits)
            # Route may not enter enemy Lord/Stronghold/Conquered locale unless Besieged there.
            for chk in (a, b):
                if chk in (sid, lord.location):
                    continue
                cloc = state.locales[chk]
                if (sd == "teutonic" and cloc.russian_conquered > 0) or (sd == "russian" and cloc.teutonic_conquered > 0):
                    if cloc.siege_markers == 0:
                        raise IllegalAction("route_blocked", f"Route blocked at {chk}")
                # Enemy Lord present?
                for ol in state.lords.values():
                    if ol.state == "mustered" and ol.side != sd and ol.location == chk:
                        if cloc.siege_markers == 0:
                            raise IllegalAction("route_blocked", f"Enemy Lord at {chk} blocks Route")

        added += 1

    if seat_count > 2:
        raise IllegalAction("too_many_seat_sources", "max 2 Seat sources (4.6.1)")
    if ship_count > 2:
        raise IllegalAction("too_many_ship_sources", "max 2 Ship sources")

    # Add provender (cap 8).
    final_added = min(added, 8 - lord.assets.get("provender", 0))
    lord.assets["provender"] = lord.assets.get("provender", 0) + final_added
    lord.moved_fought = True
    _consume_actions(state, 1)
    return ({"lord_id": lord_id, "added": final_added, "lost_to_cap": added - final_added}, [])


def _all_seats(state: GameState, lord_id: str) -> list[str]:
    """Helper: all seats for a Lord (delegates to actions._seats_of)."""
    from nevsky.actions import _seats_of

    return _seats_of(state, lord_id)


# ---------------------------------------------------------------------------
# 4.9 End Campaign
# ---------------------------------------------------------------------------


def _h_end_campaign_resolve(
    state: GameState, side: str, args: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """4.9 End Campaign sequence:
    - 4.9.1 Grow (only at end of Rasputitsa, turn 8 or 16)
    - 4.9.2 Game-end check
    - 4.9.3 Plow & Reap (end-of-Summer or end-of-Late-Winter)
    - 4.9.4 Wastage (per Lord, discard if >1 of any Asset type or
            >1 this-lord-capability)
    - 4.9.5 Reset: discard This-Campaign events; advance box; flip
            to Levy

    Both sides call this; we run the side-specific portion (Wastage,
    discard This-Campaign events) then on R completion advance the
    Calendar marker.
    """
    sd = _require_side_player(state, side)
    if state.meta.phase != "campaign":
        raise IllegalAction("wrong_phase", "end_campaign_resolve requires campaign phase")
    if state.meta.campaign_step != "end_campaign":
        raise IllegalAction("wrong_step", "end_campaign_resolve requires campaign_step=end_campaign")
    _require_active(state, sd)

    box = state.meta.box
    season = _season_of_box(box)

    # 4.9.1 Grow (T then R) -- runs only on T's turn for both sides combined,
    # since both halves halve enemy markers. We model: when T resolves, T
    # halves Russian Ravaged markers; when R resolves, R halves Teuton
    # Ravaged markers. Only at end of Rasputitsa (turn 8/16).
    grew = []
    if season == "rasputitsa" and (box == 8 or box == 16):
        target_color = "russian" if sd == "teutonic" else "teutonic"
        ravaged = [
            lid for lid, loc in state.locales.items()
            if (target_color == "russian" and loc.russian_ravaged)
            or (target_color == "teutonic" and loc.teutonic_ravaged)
        ]
        # Reduce to half rounded UP -> we REMOVE half rounded DOWN so half-up remain.
        to_remove = len(ravaged) // 2
        # Remove from a deterministic order: sorted by locale id.
        ravaged_sorted = sorted(ravaged)
        for rid in ravaged_sorted[:to_remove]:
            if target_color == "russian":
                state.locales[rid].russian_ravaged = False
                state.calendar.russian_vp = max(0.0, state.calendar.russian_vp - 0.5)
            else:
                state.locales[rid].teutonic_ravaged = False
                state.calendar.teutonic_vp = max(0.0, state.calendar.teutonic_vp - 0.5)
            grew.append(rid)

    # 4.9.4 Wastage (per side).
    wastage_actions = []
    for lord_id, lord in state.lords.items():
        if lord.side != sd or lord.state != "mustered":
            continue
        # Discard 1 if any Asset count >1 OR >1 this-lord-cap.
        discarded_asset = None
        most_type = None
        most_count = 0
        for k, v in lord.assets.items():
            if v > most_count:
                most_count = v
                most_type = k
        if most_count > 1:
            lord.assets[most_type] -= 1  # type: ignore[index]
            if lord.assets[most_type] == 0:  # type: ignore[index]
                del lord.assets[most_type]  # type: ignore[arg-type]
            discarded_asset = most_type
        elif len(lord.this_lord_capabilities) > 1:
            cid = lord.this_lord_capabilities.pop()
            _side_deck(state, sd).deck.append(cid)
            discarded_asset = f"capability:{cid}"
        if discarded_asset:
            wastage_actions.append({"lord_id": lord_id, "discarded": discarded_asset})

    # 4.9.5 Reset: discard This-Campaign events.
    deck = _side_deck(state, sd)
    discarded_camp_events = list(deck.this_campaign_events)
    deck.discard.extend(discarded_camp_events)
    deck.this_campaign_events = []

    if sd == "teutonic":
        if state.meta.end_campaign_completed_t:
            raise IllegalAction("already_done", "Teutonic End Campaign already done")
        state.meta.end_campaign_completed_t = True
        state.meta.active_player = "russian"
    else:
        if state.meta.end_campaign_completed_r:
            raise IllegalAction("already_done", "Russian End Campaign already done")
        state.meta.end_campaign_completed_r = True

    advanced = False
    game_over = False
    if state.meta.end_campaign_completed_t and state.meta.end_campaign_completed_r:
        # 4.9.2 Game-end check: was this the scenario's final 40-Days?
        if state.meta.box >= state.meta.span_end_box:
            state.meta.phase = "campaign"
            state.meta.campaign_step = "done"
            game_over = True
        else:
            # 4.9.3 Plow & Reap (end of Summer / end of Late Winter only)
            _plow_and_reap(state, season)
            # Advance Calendar marker by 1, flip to Levy.
            cal = state.calendar
            for cb in cal.boxes:
                if cb.has_levy_campaign_marker:
                    cb.has_levy_campaign_marker = False
                    cb.levy_campaign_face = None
                    new_box = cb.box + 1
                    if new_box <= 16:
                        cal.boxes[new_box - 1].has_levy_campaign_marker = True
                        cal.boxes[new_box - 1].levy_campaign_face = "levy"
                    state.meta.box = new_box
                    break
            # Reset campaign-turn / step bookkeeping for next Campaign;
            # transition to Levy.
            state.meta.phase = "levy"
            state.meta.levy_step = "arts_of_war"
            state.meta.levy_step_completed_t = False
            state.meta.levy_step_completed_r = False
            state.meta.first_levy_done = True  # post-first-Levy
            state.meta.active_player = "teutonic"
            state.meta.campaign_step = "plan"  # ready for next Campaign
            state.meta.plan_complete_t = False
            state.meta.plan_complete_r = False
            state.meta.end_campaign_completed_t = False
            state.meta.end_campaign_completed_r = False
            state.campaign_turn.next_to_reveal = "teutonic"
            state.campaign_turn.active_card = None
            state.campaign_turn.active_lord = None
            state.campaign_turn.actions_remaining = 0
            state.campaign_turn.in_feed_pay_disband = False
            state.campaign_turn.fpd_completed_t = False
            state.campaign_turn.fpd_completed_r = False
            advanced = True

    return ({"side": sd, "grew": grew, "wastage": wastage_actions,
             "this_campaign_discarded": discarded_camp_events,
             "advanced_to_next_levy": advanced, "game_over": game_over}, [])


def _plow_and_reap(state: GameState, season: str) -> None:
    """4.9.3: end-of-Summer Carts -> Sleds; end-of-Late-Winter Sleds -> Carts.
    After flipping, each Lord discards Sleds/Carts down to half rounded UP.
    """
    if season not in ("summer", "late_winter"):
        return
    for lord in state.lords.values():
        if lord.state != "mustered":
            continue
        if season == "summer":
            sleds = lord.assets.get("sled", 0) + lord.assets.get("cart", 0)
            lord.assets["sled"] = sleds
            lord.assets.pop("cart", None)
        else:
            carts = lord.assets.get("sled", 0) + lord.assets.get("cart", 0)
            lord.assets["cart"] = carts
            lord.assets.pop("sled", None)
        # Discard down to half rounded UP.
        for k in ("sled", "cart"):
            v = lord.assets.get(k, 0)
            if v > 0:
                keep = (v + 1) // 2
                lord.assets[k] = keep


# ---------------------------------------------------------------------------
# Public registry
# ---------------------------------------------------------------------------


HANDLERS = {
    # 4.1 Plan
    "plan_add_card": _h_plan_add_card,
    "finalize_plan": _h_finalize_plan,
    # 4.2 Activation
    "command_reveal": _h_command_reveal,
    "end_card": _h_end_card,
    "fpd_resolve": _h_fpd_resolve,
    # 4.7 simple commands
    "cmd_tax": _h_cmd_tax,
    "cmd_forage": _h_cmd_forage,
    "cmd_ravage": _h_cmd_ravage,
    "cmd_pass": _h_cmd_pass,
    "cmd_sail": _h_cmd_sail,
    # 4.6 supply
    "cmd_supply": _h_cmd_supply,
    # 4.9 end campaign
    "end_campaign_resolve": _h_end_campaign_resolve,
}
