"""Campaign-phase action handlers (4.1-4.9).

Coverage:
  - 4.1 Plan, including 4.1.3 Lieutenants (Q-003).
  - 4.2 Activation loop.
  - 4.3 March / Avoid Battle / Withdraw.
  - 4.4 Battle invocation (resolve_battle in battle.py).
  - 4.5 Siege / Storm / Sally / Relief Sally (Q-005, Q-006).
  - 4.6 Supply.
  - 4.7 simple Commands (Tax, Forage, Ravage, Sail, Pass).
  - 4.8 Feed / Pay / Disband cycle.
  - 4.9 End Campaign housekeeping.

Per-card AoW capability effects are wired into the appropriate
strike / muster / movement code paths. Where a capability requires
operator choice (e.g., Trebuchets, Stonemasons), the relevant action
handler exposes it; otherwise it is automatically applied. Tier 1
immediate events and Tier 2 Battle Holds resolve via events.py.
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
    _side_deck,
)
from nevsky.state import (
    GameState,
    Side,
    detach_vassal_marker,
    move_vassal_marker,
    vassal_marker_box,
)
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
        # SMOKE-109 (Round 170): when only one side has finalized the
        # Plan, switch active_player to the other side so legal_moves
        # enumerates that side's Plan options. Without this swap,
        # `side = state.meta.active_player` in legal_moves stays on
        # the side that just finalized; the other side's plan moves
        # are unreachable.
        if not state.meta.plan_complete_r:
            state.meta.active_player = "russian"
    else:
        if state.meta.plan_complete_r:
            raise IllegalAction("already_done", "Russian Plan already finalized")
        state.meta.plan_complete_r = True
        # SMOKE-109 (Round 170): mirror swap on Russian-first finalize.
        if not state.meta.plan_complete_t:
            state.meta.active_player = "teutonic"

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




_PERMANENT_MARSHAL_BY_SIDE = {
    "teutonic": "andreas",
    "russian": "aleksandr",
}


def _is_currently_marshal(state: GameState, lord_id: str) -> bool:
    """Return True if `lord_id` is currently filling a Marshal role
    (4.1.3 / 1.5.1).

    Per Q-003 adjudication (RULES_DECISIONS.md):
      - `marshal_role: "permanent"` (Andreas, Aleksandr): ALWAYS a
        Marshal whenever the Lord is on the map.
      - `marshal_role: "secondary"` (Hermann, Andrey): Marshal ONLY
        when actively filling the role.
      - `marshal_role: null` (everyone else): never a Marshal.

    Q-003 + Q-005 integration (Round 10b follow-up): a secondary
    Marshal is "actively filling the role" iff:
      1. They are on the map (Mustered, location not None), AND
      2. Their permanent counterpart (Andreas for Teutonic side,
         Aleksandr for Russian) is NOT on the map (off-Calendar
         entirely OR on-Calendar/Ready), AND
      3. They are at Front Center in an active Battle Array — i.e.,
         state.combat_pending exists AND they appear at "center" in
         the same-side positions dict.

    Outside an active Battle (no `combat_pending`), a secondary
    Marshal can still be "actively filling" the side's Marshal role
    in the broader Campaign sense: the harness treats them as the
    Marshal whenever their permanent counterpart is off the map.
    This matches the rules text "the Marshal" (1.5.1) which is
    determined for Group March (4.3.1) regardless of Battle Array
    state.
    """
    if lord_id not in state.lords:
        return False
    lord = state.lords[lord_id]
    if lord.state != "mustered" or lord.location is None:
        return False
    from nevsky.static_data import load_lords as _ll
    static = _ll().get(lord_id, {})
    role = static.get("marshal_role")
    if role == "permanent":
        return True
    if role == "secondary":
        # Permanent counterpart on map?
        permanent_lid = _PERMANENT_MARSHAL_BY_SIDE.get(lord.side)
        if permanent_lid is None:
            return False
        permanent = state.lords.get(permanent_lid)
        if permanent and permanent.state == "mustered" and permanent.location is not None:
            # Permanent Marshal is on map -> secondary is inactive.
            return False
        # Permanent off map. Secondary is currently a Marshal whenever
        # they are at Front Center in the active Battle, AND for the
        # broader Campaign Marshal role (Group March, etc.) whenever
        # their counterpart is absent. The Campaign-wide reading is
        # what the Lieutenant rule (4.1.3) hinges on, so we return
        # True if the permanent is off-map. The Front-Center clause
        # is honoured implicitly because Lieutenants can only be
        # placed during Plan, BEFORE a Battle starts, and Plan is the
        # only time _is_currently_marshal is consulted.
        return True
    return False


def _h_place_lieutenant(
    state: GameState, side: str, args: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """4.1.3 Lieutenants. Plan-time only.

    args:
      lieutenant: Lord id of the lord acting as Lieutenant (Marshal/upper).
      lower_lord: Lord id of the Lower Lord stacked on top.

    Constraints:
      - Both must be at the SAME Locale.
      - Both must be on the side's side.
      - Lieutenant has at most 1 Lower Lord at a time.
      - Lower Lord cannot also be a Lieutenant (no chains).
      - Neither may currently be a Marshal (4.1.3, 1.5.1). Per Q-003
        (RULES_DECISIONS.md), "currently a Marshal" is interpreted
        permissively: permanent-role Lords (Andreas, Aleksandr) are
        always barred; secondary-role Lords (Hermann, Andrey) are
        barred only when actively filling the Marshal role (which
        needs Q-005's Battle Array; see _is_currently_marshal).
      - Neither may be Besieged (4.5.1 / 4.1.3).

    Effect: lower_lord.lieutenant_of = lieutenant; lieutenant.has_lower_lord
    = lower_lord. Revealing the Lower Lord's Command card resolves as
    Pass (4.2.3) -- handled in _h_command_reveal.
    """
    sd = _require_side_player(state, side)
    if state.meta.phase != "campaign":
        raise IllegalAction("wrong_phase", "place_lieutenant requires campaign phase")
    if state.meta.campaign_step != "plan":
        raise IllegalAction("wrong_step", "place_lieutenant only during Plan (4.1.3)")
    lt = args.get("lieutenant")
    ll = args.get("lower_lord")
    if not (isinstance(lt, str) and isinstance(ll, str)):
        raise IllegalAction("missing_arg", "args: lieutenant, lower_lord")
    if lt == ll:
        raise IllegalAction("self_target", "lieutenant and lower_lord must differ")
    if lt not in state.lords or ll not in state.lords:
        raise IllegalAction("bad_target", f"unknown lord {lt!r} or {ll!r}")
    L = state.lords[lt]
    LL = state.lords[ll]
    if L.side != sd or LL.side != sd:
        raise IllegalAction("wrong_side", "both Lords must be your side")
    if L.state != "mustered" or LL.state != "mustered":
        raise IllegalAction("not_mustered", "both Lords must be Mustered")
    if L.location != LL.location or L.location is None:
        raise IllegalAction("not_co_located", "both Lords must be at the same Locale")
    if _is_besieged(state, lt) or _is_besieged(state, ll):
        raise IllegalAction("besieged", "Lieutenant pairing requires Unbesieged Lords")
    # 4.1.3: "Neither may currently be a Marshal." Q-003 adjudication.
    if _is_currently_marshal(state, lt):
        raise IllegalAction(
            "marshal_lieutenant",
            f"{lt} is currently a Marshal and cannot be a Lieutenant (4.1.3)",
        )
    if _is_currently_marshal(state, ll):
        raise IllegalAction(
            "marshal_lower_lord",
            f"{ll} is currently a Marshal and cannot be a Lower Lord (4.1.3)",
        )
    if L.has_lower_lord:
        raise IllegalAction("lt_full", f"{lt} already has Lower Lord {L.has_lower_lord}")
    if LL.lieutenant_of:
        raise IllegalAction("ll_already", f"{ll} is already a Lower Lord under {LL.lieutenant_of}")
    if LL.has_lower_lord:
        raise IllegalAction("no_chains", f"{ll} is itself a Lieutenant; cannot become Lower Lord")
    if L.lieutenant_of:
        raise IllegalAction("no_chains", f"{lt} is itself a Lower Lord; cannot become Lieutenant")
    L.has_lower_lord = ll
    LL.lieutenant_of = lt
    return ({"lieutenant": lt, "lower_lord": ll, "locale": L.location}, [])


def _h_command_reveal(
    state: GameState, side: str, args: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """4.2: reveal the top Command card of the active side.

    Sets campaign_turn.active_card / active_lord / actions_remaining.
    Auto-passes when the card is Pass / belongs to a Lower Lord (4.1.3:
    Lower-Lord card resolves as `pass_lower_lord`) / Lord
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
    if card == "pass":
        # 4.2.3 Pass: no actions; flip to other side; enter 4.8 (Feed/Pay/Disband)
        # for cards that did not move/fight no MOVED_FOUGHT lords -> trivial.
        state.campaign_turn.active_lord = None
        state.campaign_turn.actions_remaining = 0
        state.campaign_turn.seat_supply_this_card = 0
        _enter_feed_pay_disband(state)
        return ({"revealed": "pass", "outcome": "pass"}, [])

    # Card is a Lord id.
    lord = state.lords.get(card)
    if lord is None or lord.state != "mustered" or lord.location is None:
        # 4.2.3: Lord on card not on map -> Pass.
        state.campaign_turn.active_lord = None
        state.campaign_turn.actions_remaining = 0
        state.campaign_turn.seat_supply_this_card = 0
        _enter_feed_pay_disband(state)
        return ({"revealed": card, "outcome": "pass_not_on_map"}, [])
    # 4.1.3: Lower Lord card resolves as Pass (the Lieutenant carries
    # the group, but the Lower Lord cannot independently activate).
    if lord.lieutenant_of is not None:
        state.campaign_turn.active_lord = None
        state.campaign_turn.actions_remaining = 0
        state.campaign_turn.seat_supply_this_card = 0
        _enter_feed_pay_disband(state)
        return ({"revealed": card, "outcome": "pass_lower_lord",
                 "lieutenant_of": lord.lieutenant_of}, [])

    state.campaign_turn.active_lord = card
    state.campaign_turn.actions_remaining = _effective_command_rating(state, card)
    # SMOKE-030: reset Famine seat-Supply counter at each new card reveal.
    state.campaign_turn.seat_supply_this_card = 0
    # Reset per-card capability flags (Phase 4b).
    state.lords[card].first_march_used_this_card = False
    state.lords[card].raiders_used_this_card = False
    # SMOKE-143 (R206): reset per-card Legate-bonus tracking on each reveal.
    # The +1 bonus is available only if the Lord STARTS his Activation (this
    # reveal) co-located with the on-map Legate (4.2); qualification is
    # fixed here so marching away later does not revoke it.
    state.campaign_turn.legate_bonus_elected = False
    state.campaign_turn.legate_bonus_base = 0
    state.campaign_turn.actions_used_this_card = 0
    state.campaign_turn.legate_bonus_available = (
        state.lords[card].side == "teutonic"
        and state.legate.william_of_modena_in_play
        and state.legate.location == "locale"
        and state.legate.locale_id == state.lords[card].location
    )
    return ({"revealed": card, "outcome": "active", "actions": state.campaign_turn.actions_remaining}, [])


def _effective_command_rating(state: GameState, lord_id: str) -> int:
    """Compute Command rating for `lord_id` with Phase 4a capability mods.

    Modifiers (cumulative; each adds at most +1 by name):
      - Druzhina (R5/R6): this Lord with Knights -> +1
      - House of Suzdal (R11): this Lord -> +1 while Aleksandr AND Andrey on map
      - Treaty of Stensby (T1, side-wide): Heinrich and Knud&Abel -> +1
      - Ordensburgen (T12, side-wide): Teutonic Lord starts at a
        Commandery -> +1 for that card. Commanderies are the four
        Order-symbol Strongholds (Wenden, Fellin, Adsel, Leal), all
        flagged `commandery: true` in locales.json (Q-004). The +1
        applies ONLY at those Locales, never at a non-Commandery home
        Seat (R214 fix).
      - Archbishopric (R15, side-wide): Russian Lord starts at
        Novgorod -> +1.

    Note: the Legate Command +1 (4.2) is NOT applied here. It is an
    optional, player-elected in-card action grant (handler
    _h_legate_command_bonus, SMOKE-143), not a passive rating modifier:
    the player elects it during the card and the pawn returns to William
    of Modena only if the extra action is used. This function returns the
    Lord's intrinsic Command rating plus passive capability modifiers only.
    """
    from nevsky.capabilities import any_capability, has_side_capability
    from nevsky.static_data import load_lords as _load

    lord = state.lords[lord_id]
    sl = _load()[lord_id]
    base = int(sl["ratings"]["command"])
    bonus = 0

    # Druzhina: Knights present.
    if any_capability(state, lord_id, "Druzhina") and lord.forces.get("knights", 0) > 0:
        bonus += 1
    # House of Suzdal: Aleksandr AND Andrey both on map.
    if any_capability(state, lord_id, "House of Suzdal"):
        ak = state.lords.get("aleksandr")
        an = state.lords.get("andrey")
        if (ak and ak.state == "mustered" and ak.location is not None
                and an and an.state == "mustered" and an.location is not None):
            bonus += 1
    # Treaty of Stensby: Heinrich and Knud&Abel.
    if (
        lord.side == "teutonic"
        and lord_id in ("heinrich", "knud_and_abel")
        and has_side_capability(state, "teutonic", "Treaty of Stensby")
    ):
        bonus += 1
    # Ordensburgen (T12): Teutonic Lord starts a Command card at a
    # Commandery -> +1 (Playbook page 36; AoW T12 tips; Map 226-236).
    # Commanderies are exactly the four Order-symbol Strongholds
    # (Wenden, Fellin, Adsel, Leal), all flagged `commandery: true`
    # (Q-004). R214: gate purely on that flag — Wenden (Andreas/Rudolf)
    # and Leal (Heinrich) are covered as Commanderies; non-Commandery
    # home Seats (Dorpat, Odenpah, Reval, Riga) correctly get NO +1.
    from nevsky.static_data import load_locales as _load_locales
    if (
        lord.side == "teutonic"
        and has_side_capability(state, "teutonic", "Ordensburgen")
        and lord.location is not None
    ):
        loc_static = _load_locales().get(lord.location, {})
        # R214 fix: Ordensburgen +1 applies ONLY at a Commandery
        # (Order-symbol Stronghold: Wenden, Fellin, Adsel, Leal — all
        # flagged `commandery: true`). The prior `or lord.location in
        # primary_seats` clause over-granted +1 at non-Commandery home
        # Seats (Dorpat, Odenpah, Reval, Riga), contradicting AoW T12
        # tips, Map ref 226-236, and Q-004 (RULES_DECISIONS.md).
        if loc_static.get("commandery"):
            bonus += 1
    # Archbishopric: Russian Lord starts at Novgorod.
    if (
        lord.side == "russian"
        and has_side_capability(state, "russian", "Archbishopric of Novgorod")
        and lord.location == "novgorod"
    ):
        bonus += 1
    return base + bonus


def _require_full_command_card(state: GameState, lord_id: str, label: str) -> None:
    """Guard for entire-card Commands (4.2): the action requires the Lord's
    full, untouched Command card. A Lord who has already Marched or taken
    any other Action on this card may take no entire-card Command with it.

    Reused by every entire-card handler: Siege (4.5.1), Tax (4.7.4), Sail
    (4.7.3), plus the AoW capability actions Stone Kremlin R18 and
    Stonemasons T17, whose card text reads
    "expends his entire Command card to do nothing except ..."). At card
    reveal ``actions_remaining == _effective_command_rating(lord)``, so
    ``actions_remaining < full_command`` means the Lord has already acted.

    Adjudication: RULES_DECISIONS D-R203, narrowed by D-Q010 (Storm/Sally
    dropped -- they cost one Command action, not the entire card).
    """
    full_command = _effective_command_rating(state, lord_id)
    if state.campaign_turn.actions_remaining < full_command:
        raise IllegalAction(
            "must_be_full_card",
            f"{label} requires full Command card; "
            f"{state.campaign_turn.actions_remaining}/{full_command} actions remain",
        )


def _resolve_legate_command_bonus(state: GameState) -> None:
    """SMOKE-143 (R206): at the end of a Command card, if the Teutonic
    player elected the Legate +1 bonus, return the Legate pawn to the
    William of Modena card IF the extra action was actually used (the Lord
    consumed more actions than his base Command rating). If the bonus was
    elected but the extra action went unused, the pawn stays on the map
    (4.2: "remove ... if and when the Lord uses the extra action").
    """
    ct = state.campaign_turn
    if ct.legate_bonus_elected:
        if ct.actions_used_this_card > ct.legate_bonus_base:
            state.legate.location = "card"
            state.legate.locale_id = None
        ct.legate_bonus_elected = False
        ct.legate_bonus_base = 0


def _enter_feed_pay_disband(state: GameState) -> None:
    """Helper: transition to per-card 4.8 sub-step."""
    # If a 5.2 Campaign Victory fired during this card's combat aftermath the
    # game is already terminal (game_over) and the shared helper froze the
    # turn (in_feed_pay_disband=False, actions_remaining=0). The command
    # handler still runs to completion and calls us last; do NOT re-open the
    # Feed/Pay/Disband sub-step or reassign the active player -- that would
    # leave campaign_turn internally inconsistent ("in FPD" while the game is
    # over). Once terminal, the turn stays frozen.
    if state.meta.game_over:
        return
    _resolve_legate_command_bonus(state)
    state.campaign_turn.in_feed_pay_disband = True
    state.campaign_turn.fpd_completed_t = False
    state.campaign_turn.fpd_completed_r = False
    state.meta.active_player = "teutonic"  # T-then-R for 4.8


def _h_legate_command_bonus(
    state: GameState, side: str, args: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """SMOKE-143 (R206): Legate Command bonus (4.2 LEGATE).

    A Teutonic Lord who STARTS his Activation (his card was revealed)
    co-located with the on-map Legate pawn may add +1 Command action for
    the current card. Per the rule, the pawn returns to the William of
    Modena Capability card only "if and when the Lord uses the extra
    action" -- so removal is deferred to card end (_resolve_legate_command_
    bonus), and a wasted election leaves the pawn on the map. Only once per
    appearance: once removed the Legate is off-map until the next Call to
    Arms re-places it (3.5.1).
    """
    sd = _require_side_player(state, side)
    if sd != "teutonic":
        raise IllegalAction("wrong_side", "Legate Command bonus is Teutonic (4.2)")
    if state.meta.phase != "campaign" or state.meta.campaign_step != "command":
        raise IllegalAction("wrong_step", "Legate bonus only during Command (4.2)")
    if state.campaign_turn.in_feed_pay_disband:
        raise IllegalAction("in_feed_pay_disband", "card is concluding")
    lord_id = args.get("lord_id", state.campaign_turn.active_lord)
    if not isinstance(lord_id, str):
        raise IllegalAction("missing_arg", "args.lord_id required")
    _require_active_lord_command(state, sd, lord_id)
    if not state.campaign_turn.legate_bonus_available:
        raise IllegalAction(
            "legate_unavailable",
            "active Lord did not start his card co-located with the on-map Legate (4.2)",
        )
    if state.campaign_turn.legate_bonus_elected:
        raise IllegalAction("already_elected", "Legate +1 already taken this card")
    state.campaign_turn.legate_bonus_base = _effective_command_rating(state, lord_id)
    state.campaign_turn.actions_remaining += 1
    state.campaign_turn.legate_bonus_elected = True
    return ({"legate_bonus": True, "lord_id": lord_id,
             "actions_remaining": state.campaign_turn.actions_remaining}, [])


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


def _fpd_pending_disband(state: GameState, sd: str) -> bool:
    """True if any Lord on side sd is at-or-left-of the Levy box after
    Feed -- i.e. a Disband (3.3) would fire."""
    levy_box = _find_levy_marker_box(state)
    for lord_id, lord in state.lords.items():
        if lord.side != sd or lord.state != "mustered":
            continue
        sm_box = _find_service_marker_box(state, lord_id)
        if sm_box is not None and sm_box <= levy_box:
            return True
    return False


def _fpd_can_pay(state: GameState, sd: str) -> bool:
    """True if side sd has any payable resource to shift Service right
    (3.2 mechanics): Coin on a Mustered Lord, Loot on a Mustered Lord at a
    Friendly Locale, or (Russian) Veche Coin. Mirrors legal_moves._pay_moves
    so the Pay window only opens when a Pay option will actually be offered."""
    for lord in state.lords.values():
        if lord.side != sd or lord.state != "mustered":
            continue
        if lord.assets.get("coin", 0) > 0:
            return True
        if (lord.assets.get("loot", 0) > 0 and lord.location is not None
                and _is_friendly_locale(state, lord.location, sd)):
            return True
    if sd == "russian" and state.veche.coin > 0:
        return True
    return False


def _fpd_finalize(
    state: GameState, sd: str, feed_results: list[dict[str, Any]]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """4.8.2 Disband check + 4.8.3 marker removal + side-complete/advance.
    Runs after Feed (and after any Pay step). Clears this side's Pay window.
    """
    state.campaign_turn.fpd_pay_window_side = None
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

    # 3.4.2 Advanced Vassal Service: Vassal markers at/over their Service
    # limit are removed/downgraded in this Campaign Disband too (parity
    # with the Levy Disband). No-op unless the optional rule is enabled.
    if state.meta.optional_rules.get("advanced_vassal_service", False):
        from nevsky.actions import _advanced_vassal_disband_step
        _advanced_vassal_disband_step(state, sd)

    # 4.8.3: remove MOVED_FOUGHT markers.
    for lord in state.lords.values():
        if lord.side == sd and lord.moved_fought:
            lord.moved_fought = False

    # Rule 5.2 Campaign Victory: if the Disband check above left either
    # side with zero Mustered Lords, _disband_at_limit /
    # _remove_lord_permanently have already marked the campaign terminal
    # (campaign_step == "done"). Stop here so we do NOT mark the side
    # complete, advance the reveal pointer, transition to end_campaign, or
    # advance the calendar past a game that should already be over.
    if state.meta.campaign_step == "done":
        return ({"side": sd, "feed": feed_results,
                 "permanently_removed": permanently_removed,
                 "disbanded": disbanded, "advanced": False,
                 "game_over": True}, [])

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

    # BUG-4 (R203): second call for this side -- Feed already applied and
    # the Pay window has been offered; complete the Disband check now.
    if state.campaign_turn.fpd_pay_window_side == sd:
        return _fpd_finalize(state, sd, [])

    # Feed every MOVED_FOUGHT Lord on this side. Hillforts (T8) skips
    # one eligible Teutonic Lord in Livonia per Feed.
    # Smoke-test fix: skip Lords whose state != "mustered" (they were
    # permanently removed in Battle/Storm Aftermath but moved_fought=True
    # was set before removal). Also clear their stale moved_fought flag.
    # PLAY-31 (4.8.1): T8 Hillforts skip-Lord is a player CHOICE among the
    # eligible Teutonic Lords; default = first eligible (deterministic).
    hillforts_skip = args.get("hillforts_skip") or _hillforts_skip_lord(state, sd)
    if args.get("hillforts_skip") is not None:
        _elig = _hillforts_eligible_lords(state, sd)
        if hillforts_skip not in _elig:
            raise IllegalAction(
                "bad_hillforts_skip",
                f"{hillforts_skip} not eligible for Hillforts skip; eligible: {_elig}")
    # feed_loot_first: prefer spending own Loot before Provender (4.8.1 lets
    # the player choose; default Provender-first -- Provender only Feeds,
    # while Loot can also Pay at Friendly Locales). bool = all Lords, or a
    # list of lord_ids.
    _lf = args.get("feed_loot_first")
    if _lf is True:
        _loot_first = None  # sentinel: all
    elif isinstance(_lf, list):
        _loot_first = set(_lf)
    else:
        _loot_first = set()

    def _asset_order(lid: str) -> tuple[str, str]:
        if _loot_first is None or lid in _loot_first:
            return ("loot", "provender")
        return ("provender", "loot")

    def _spend(lord, order, remaining, consumed):
        for asset in order:
            if remaining <= 0:
                break
            have = lord.assets.get(asset, 0)
            if have > 0:
                take = min(remaining, have)
                lord.assets[asset] = have - take
                if lord.assets[asset] == 0:
                    del lord.assets[asset]
                consumed[asset] += take
                remaining -= take
        return remaining

    # Identify the feeders (Moved/Fought mustered Lords on this side),
    # clearing stale flags and short-circuiting skips / zero-cost.
    feed_results: list[dict[str, Any]] = []
    feeders: list[tuple[str, Any, int, int]] = []
    for lord_id, lord in list(state.lords.items()):
        if lord.side != sd or not lord.moved_fought:
            continue
        if lord.state != "mustered":
            # Lord was removed/disbanded mid-card; skip Feed.
            lord.moved_fought = False
            continue
        if lord_id == hillforts_skip:
            feed_results.append({"lord_id": lord_id, "hillforts_skipped": True})
            continue
        n_units = sum(lord.forces.values())
        # 4.8.1: 1 Provender/Loot for 1-6 units; 2 for 7+. A 0-unit Lord
        # consumes 0 (defensive; should already be removed per 1.5.1).
        cost = 0 if n_units == 0 else (2 if n_units >= 7 else 1)
        feeders.append((lord_id, lord, n_units, cost))

    # PASS 1 (4.8.1 SHARING): "First, all Lords must Feed their own Forces,
    # using Provender and Loot from their OWN mats." Every feeder self-feeds
    # BEFORE any sharing, so no Lord is raided of Assets it needs itself.
    _fstate: dict[str, dict[str, Any]] = {}
    for lord_id, lord, n_units, cost in feeders:
        consumed = {"provender": 0, "loot": 0}
        remaining = _spend(lord, _asset_order(lord_id), cost, consumed)
        _fstate[lord_id] = {"consumed": consumed, "remaining": remaining,
                             "n_units": n_units, "cost": cost}

    # PASS 2 (4.8.1 SHARING): "Then, a Lord must expend Provender and Loot to
    # Feed the Forces of his side's OTHER Lords in the same Locale who have
    # expended ALL of their Provender and Loot but did not have enough."
    # Only SURPLUS remains in donor mats after Pass 1, so this can no longer
    # take a co-located Lord's own-Feed Provender. Donor order is stable
    # (state order); args.feed_donor_order may prioritise specific donors.
    _donor_pref = args.get("feed_donor_order") or []
    for lord_id, lord, n_units, cost in feeders:
        st = _fstate[lord_id]
        if st["remaining"] <= 0:
            continue  # self-fed in full
        # Donors: co-located same-side Lords with surplus Assets.
        donor_ids = [d for d in _donor_pref
                     if d in state.lords and d != lord_id
                     and state.lords[d].side == sd
                     and state.lords[d].location == lord.location]
        donor_ids += [d for d, dl in state.lords.items()
                      if d != lord_id and d not in donor_ids
                      and dl.side == sd and dl.location == lord.location]
        for donor_id in donor_ids:
            if st["remaining"] <= 0:
                break
            donor = state.lords[donor_id]
            st["remaining"] = _spend(
                donor, ("provender", "loot"), st["remaining"], st["consumed"])

    # UNFED penalty + feed_results, now that all Feeding/sharing is done.
    for lord_id, lord, n_units, cost in feeders:
        st = _fstate[lord_id]
        consumed = st["consumed"]
        if cost == 0:
            feed_results.append({"lord_id": lord_id, "units": 0, "cost": 0,
                                  "consumed": consumed, "unfed": False})
            continue
        remaining = st["remaining"]
        unfed = remaining > 0
        if unfed:
            # Shift Service marker 1 box LEFT (4.8.1 unfed penalty).
            # If at box 1, the marker goes off_left_service. Note: a
            # service marker in off_left_service triggers 3.3.1 permanent
            # removal in the next Disband check.
            sm_box = _find_service_marker_box(state, lord_id)
            if sm_box is not None and sm_box >= 1 and sm_box <= 16:
                state.calendar.boxes[sm_box - 1].service_markers.remove(lord_id)
                if sm_box == 1:
                    state.calendar.off_left_service.append(lord_id)
                else:
                    state.calendar.boxes[sm_box - 2].service_markers.append(lord_id)
                # SMOKE-144 (R206): 3.4.2 advanced rule -- any shift of a
                # Lord's Service cascades to his on-Calendar Vassal markers
                # (same direction, same boxes). _shift_service_right does
                # this for rightward Pay shifts; the Unfed leftward shift
                # (4.8.1) omitted it. Only active when advanced_vassal_service
                # is enabled (off by default).
                if state.meta.optional_rules.get("advanced_vassal_service", False):
                    for vid, vstate in state.lords[lord_id].vassals.items():
                        cur = vassal_marker_box(state.calendar, vid, vstate)
                        if cur is None:
                            continue
                        move_vassal_marker(state.calendar, vid, vstate, cur - 1)
        feed_results.append({
            "lord_id": lord_id,
            "units": n_units,
            "cost": cost,
            "consumed": consumed,
            "unfed": unfed,
        })

    # 4.8.2 Pay window (BUG-4, R203): the per-card cycle is
    # Feed -> Pay -> Disband (SoP 4.8.2 `pay: same_as levy.pay`). If Feed
    # left a pending Disband on this side and the side can Pay, pause here
    # so the player may shift Service right (avert a mid-campaign Disband)
    # before the Disband check. The second fpd_resolve for this side (with
    # the window open) runs _fpd_finalize via the early branch above.
    if (state.campaign_turn.fpd_pay_window_side != sd
            and _fpd_pending_disband(state, sd)
            and _fpd_can_pay(state, sd)):
        state.campaign_turn.fpd_pay_window_side = sd
        return ({"side": sd, "feed": feed_results, "pay_window": True}, [])
    return _fpd_finalize(state, sd, feed_results)


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
    # SMOKE-143 (R206): track actions actually consumed this card so the
    # Legate Command bonus can tell whether its extra action was used.
    state.campaign_turn.actions_used_this_card += n
    # SMOKE-110 (Round 172): per rule 4.8, Feed/Pay/Disband fires after
    # every Command card. Pre-fix the harness only fired FPD when an
    # action explicitly called _enter_feed_pay_disband (Pass, entire-
    # card commands like Tax/Sail/Storm/Sally/Siege, March-into-siege).
    # Non-entire-card commands that exhaust actions naturally
    # (Forage/Ravage/Supply/March/Raiders Ravage) left actions=0
    # without running FPD; the next command_reveal then popped a
    # fresh card and FPD was skipped silently. Found via self-play.
    # Auto-fire FPD when actions hit 0 in normal command flow.
    # Skip when combat_pending is set (the response handler will
    # call _enter_feed_pay_disband after combat resolves).
    if (state.campaign_turn.actions_remaining == 0
            and state.meta.phase == "campaign"
            and state.meta.campaign_step == "command"
            and not state.campaign_turn.in_feed_pay_disband
            and state.combat_pending is None
            and state.campaign_turn.active_lord is not None):
        _enter_feed_pay_disband(state)


def _is_besieged(state: GameState, lord_id: str) -> bool:
    """A Lord is Besieged when he is INSIDE a Stronghold (in_stronghold=True)
    at a Locale with siege_markers > 0 (4.3.5)."""
    lord = state.lords[lord_id]
    if lord.state != "mustered" or lord.location is None:
        return False
    if not lord.in_stronghold:
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
    _require_full_command_card(state, lord_id, "Tax (4.7.4)")  # entire_card (R203)

    lord = state.lords[lord_id]
    if _is_besieged(state, lord_id):
        raise IllegalAction("besieged", "Tax requires Unbesieged Lord (4.7.4)")
    if lord.location is None or not _is_own_seat(state, lord_id, lord.location):
        raise IllegalAction("not_at_seat", f"{lord_id} not at own Seat")

    if lord.assets.get("coin", 0) >= 8:
        raise IllegalAction("coin_max", f"{lord_id} at Coin cap (1.7.3)")
    lord.assets["coin"] = lord.assets.get("coin", 0) + 1
    # R216 (Q-009): stationary Command -- does NOT set Moved/Fought,
    # so it does not trigger Feed (4.8.1). Moved/Fought is only
    # March/Avoid/Battle/Siege/Storm/Sail (SoP glossary; Misc Rules L451).
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
    # SMOKE-066 (Round 71): use _effective_stronghold so Castle marker
    # overlays on Town locales (Stonemasons-built) count as Strongholds
    # for the "Forage at Friendly Stronghold or Summer" check. The
    # prior static-type list excluded "town", so Forage at a friendly
    # Castle-on-Town in non-Summer was wrongly rejected.
    eff_sh = _effective_stronghold(state, lord.location)  # type: ignore[arg-type]
    is_friendly_stronghold = (
        eff_sh is not None
        and not eff_sh.get("no_storm")
        and _is_friendly_locale(state, lord.location, sd)  # type: ignore[arg-type]
    )
    if not (is_friendly_stronghold or season == "summer"):
        raise IllegalAction(
            "forage_seasonal",
            "Forage requires Friendly Stronghold OR Summer (4.7.1)",
        )

    if lord.assets.get("provender", 0) >= 8:
        raise IllegalAction("provender_max", f"{lord_id} at Provender cap")
    # SMOKE-030: Famine event ("T16" against Russian / "R7" against
    # Teutonic) makes Forage add NO Provender this Campaign. The action
    # still resolves and consumes 1 action; the Lord just gets nothing.
    famine_against_us = (
        ("T16" in state.decks.teutonic.this_campaign_events) if sd == "russian"
        else ("R7" in state.decks.russian.this_campaign_events)
    )
    delta = 0 if famine_against_us else 1
    lord.assets["provender"] = lord.assets.get("provender", 0) + delta
    # R216 (Q-009): stationary Command -- does NOT set Moved/Fought,
    # so it does not trigger Feed (4.8.1). Moved/Fought is only
    # March/Avoid/Battle/Siege/Storm/Sail (SoP glossary; Misc Rules L451).
    _consume_actions(state, 1)
    return ({"lord_id": lord_id, "added": "provender",
             "new_count": lord.assets["provender"], "delta": delta,
             "famine_active": famine_against_us}, [])


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
    for ol_id, ol in state.lords.items():
        if ol.state == "mustered" and ol.side != sd and ol.location in adjacent:
            # SMOKE-019 (Round 33): "Unbesieged enemy Lord" must use the
            # Lord-level _is_besieged check, not locale.siege_markers.
            # An enemy at a sieged Locale who is OUTSIDE the Stronghold
            # (e.g., a besieger) is Unbesieged and triggers +1 action.
            if not _is_besieged(state, ol_id):
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
    _refresh_vp_markers(state)

    # +1 Provender.
    lord.assets["provender"] = min(8, lord.assets.get("provender", 0) + 1)
    # +1 Loot if non-Region.
    if static["type"] != "region":
        lord.assets["loot"] = min(8, lord.assets.get("loot", 0) + 1)
    # R216 (Q-009): stationary Command -- does NOT set Moved/Fought,
    # so it does not trigger Feed (4.8.1). Moved/Fought is only
    # March/Avoid/Battle/Siege/Storm/Sail (SoP glossary; Misc Rules L451).
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
      group            list[lord_id] of co-Sailing Lords (default: just lord_id).
                       Each member must be co-located with `lord_id` and on
                       the same side (Marshal group). Lieutenant pairing is
                       a Plan-phase mechanic (Q-003) and does not constrain
                       Sail group membership beyond co-location.
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
    _require_full_command_card(state, lord_id, "Sail (4.7.3)")  # entire_card (R203)

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
    # SMOKE-034 (Round 53/54): Lieutenant + Lower Lord pair must Sail
    # together (4.1.3 "March, Retreat, etc." extended to Sail per
    # 4.7.3's "Groups move together as per March"). Reject Sail that
    # omits the Lower Lord.
    lord_obj = state.lords[lord_id]
    if lord_obj.has_lower_lord is not None and lord_obj.has_lower_lord not in group:
        raise IllegalAction(
            "lower_lord_required",
            f"Active Lieutenant {lord_id} must Sail with Lower Lord "
            f"{lord_obj.has_lower_lord} (4.1.3 / 4.7.3)",
        )
    # SMOKE-042 (Round 54): 4.7.3 Sail group rules mirror 4.3.1 March:
    # only Marshals (or Lieutenant + Lower Lord pair) can take a
    # group. Solo Sails (group=[self]) remain unrestricted.
    if len(group) > 1:
        is_marshal = _is_currently_marshal(state, lord_id)
        is_lieutenant_with_only_pair = (
            lord_obj.has_lower_lord is not None
            and set(group) == {lord_id, lord_obj.has_lower_lord}
        )
        if not (is_marshal or is_lieutenant_with_only_pair):
            raise IllegalAction(
                "non_marshal_group",
                f"{lord_id} is not a Marshal; only the Lieutenant + Lower Lord pair "
                f"or a Marshal-led group may Sail together (4.7.3 / 4.3.1 / 4.1.3)",
            )
    # PLAY-22 (Fable audit): mirror of the March-group check -- a
    # non-active Lieutenant Sailing in a Marshal group must bring the
    # Lower Lord (4.1.3 "March, Retreat, etc." extended to Sail).
    for _gid in group:
        _gl = state.lords.get(_gid)
        if (_gl is not None and _gl.has_lower_lord is not None
                and _gl.has_lower_lord not in group):
            raise IllegalAction(
                "lower_lord_required",
                f"Lieutenant {_gid} in the Sail group must move with "
                f"Lower Lord {_gl.has_lower_lord} (4.1.3 / 4.7.3)",
            )
    # Destination must be free of Unbesieged enemy Lords.
    # SMOKE-019 (Round 33): use _is_besieged on the specific Lord,
    # not locale-level siege markers. A besieger Lord outside the
    # Stronghold at a sieged Locale IS Unbesieged and DOES block.
    for ol_id, ol in state.lords.items():
        if ol.state == "mustered" and ol.side != sd and ol.location == dest:
            if not _is_besieged(state, ol_id):
                raise IllegalAction("dest_blocked", f"{dest} has Unbesieged enemy Lord")

    # First sweep: validate group membership (location + side) before
    # the Ship requirements check (which iterates the same group).
    for gid in group:
        if gid not in state.lords or state.lords[gid].side != sd:
            raise IllegalAction("bad_group", f"{gid} not on your side")
        if state.lords[gid].location != src:
            raise IllegalAction("bad_group", f"{gid} not co-located with {lord_id}")

    # SMOKE-046 (Round 58): 4.7.3 Sail Ship requirements:
    # 1 Ship / Teutonic horse unit, 2 Ships / Russian horse unit,
    # 1 Ship / Provender, 2 Ships / Loot. Compute group totals and
    # compare to group's effective Ship count (T18 Cogs doubles each
    # Ship). Sleds, Carts, Boats are not Ship-loadable for Sail.
    horse_unit_types = ("knights", "sergeants", "light_horse", "asiatic_horse")
    horse_units = sum(
        int(state.lords[gid].forces.get(u, 0))
        for gid in group for u in horse_unit_types
    )
    # SMOKE-100 (Round 120): per rule 1.7.2 Greed, Lords MAY discard
    # Loot and Provender when Sailing (4.7.3 listed alongside March/
    # Avoid Battle/Retreat). The harness previously rejected with
    # insufficient_ships even when voluntary discard could fit the
    # group within budget. Accept optional discard flags:
    #   args.discard_excess_provender=True/<int>
    #   args.discard_excess_loot=True/<int>
    # True discards EVERYTHING; integer N discards up to N.
    horse_ship_factor = 1 if sd == "teutonic" else 2
    ships_available = sum(effective_ship_count(state, gid) for gid in group)
    horse_ship_need = horse_units * horse_ship_factor
    discard_prov_req = args.get("discard_excess_provender")
    discard_loot_req = args.get("discard_excess_loot")
    discarded_prov = 0
    discarded_loot = 0
    if discard_prov_req or discard_loot_req:
        # Greedily discard to fit budget — Loot first (2 Ships saved
        # per discard), then Provender. Honor explicit per-arg caps
        # when given as int; True means up to all available.
        # Distribute discards across group members (Lord may discard
        # from each own mat). The 1.7.2 rule is per-Lord; we apply
        # discard greedily across the group, recording per-Lord delta.
        if discard_loot_req:
            cap_loot = (sum(int(state.lords[gid].assets.get("loot", 0)) for gid in group)
                        if discard_loot_req is True else int(discard_loot_req))
            for gid in group:
                if cap_loot <= 0:
                    break
                have = int(state.lords[gid].assets.get("loot", 0))
                take = min(have, cap_loot)
                if take > 0:
                    state.lords[gid].assets["loot"] = have - take
                    if state.lords[gid].assets["loot"] == 0:
                        del state.lords[gid].assets["loot"]
                    discarded_loot += take
                    cap_loot -= take
        if discard_prov_req:
            cap_prov = (sum(int(state.lords[gid].assets.get("provender", 0)) for gid in group)
                        if discard_prov_req is True else int(discard_prov_req))
            for gid in group:
                if cap_prov <= 0:
                    break
                have = int(state.lords[gid].assets.get("provender", 0))
                take = min(have, cap_prov)
                if take > 0:
                    state.lords[gid].assets["provender"] = have - take
                    if state.lords[gid].assets["provender"] == 0:
                        del state.lords[gid].assets["provender"]
                    discarded_prov += take
                    cap_prov -= take
    provender_total = sum(int(state.lords[gid].assets.get("provender", 0)) for gid in group)
    loot_total = sum(int(state.lords[gid].assets.get("loot", 0)) for gid in group)
    ships_needed = horse_ship_need + provender_total + loot_total * 2
    if ships_needed > ships_available:
        raise IllegalAction(
            "insufficient_ships",
            f"Sail needs {ships_needed} Ships (horse={horse_units}x{horse_ship_factor}, "
            f"prov={provender_total}, loot={loot_total}x2); group has "
            f"{ships_available} effective Ships (4.7.3). Pass "
            f"args.discard_excess_provender / args.discard_excess_loot "
            f"to drop assets first per 1.7.2.",
        )

    # Move group (location + moved_fought already validated above).
    for gid in group:
        state.lords[gid].location = dest
        state.lords[gid].moved_fought = True
        # SMOKE-036 (Round 47): clear in_stronghold on any movement to a
        # new Locale. The flag tracks "inside a Stronghold at the
        # current Locale" and would otherwise leak across moves, causing
        # legal_moves and Battle Array checks to mistake a Lord in the
        # open at the new Locale for one inside a Stronghold.
        state.lords[gid].in_stronghold = False

    # SMOKE-020 (Round 34): trade-route auto-flip on uncontested entry.
    trade_flip = _flip_trade_route_if_uncontested(state, dest, sd)

    # PLAY-3 (Fable playtest): if the Sailing group were the last
    # besiegers at the origin Seaport Locale, their departure ends that
    # Siege (4.3.5) -- same R215 sweep cmd_march already performs.
    from nevsky.actions import _lift_siege_if_no_besiegers
    _lift_siege_if_no_besiegers(state, src)

    # SMOKE-064 (Round 69): Sailing to Unbesieged enemy Stronghold
    # places a Siege marker. Previously the inline type list omitted
    # "castle" (so Sail to wesenberg / Russian-castle overlay missed
    # the siege placement) and "town" (Castle marker overlaid on a
    # Town via T17 Stonemasons did not register). Use the canonical
    # _has_enemy_stronghold_at helper (now Castle-overlay aware).
    placed_siege = False
    dest_loc = state.locales[dest]
    if _has_enemy_stronghold_at(state, dest, sd) and dest_loc.siege_markers == 0:
        dest_loc.siege_markers = 1
        placed_siege = True

    state.campaign_turn.actions_remaining = 0
    _enter_feed_pay_disband(state)
    # SMOKE-043 (Round 55): Teutonic Lord may bring the Legate
    # along on Sail (4.1.1). args.take_legate=True opts in.
    legate_carried = _take_legate_along(
        state, sd, src, dest, bool(args.get("take_legate", False)),
    )
    result = {
        "lord_id": lord_id,
        "from": src,
        "to": dest,
        "group": group,
        "placed_siege": placed_siege,
    }
    if trade_flip is not None:
        result["trade_route_flip"] = trade_flip
    if legate_carried:
        result["legate_carried"] = legate_carried
    return (result, [])


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
    # SMOKE-047 (Round 59): collect ALL Way types between two locales,
    # not just the last one inserted. Parallel Ways (e.g., dorpat-
    # odenpah has both trackway and waterway) need each type tracked
    # so the route's transport_type compatibility check can find a
    # match instead of being blocked by the arbitrary last-loaded type.
    way_index: dict[tuple[str, str], set[str]] = {}
    for w in ways_list:
        way_index.setdefault((w["a"], w["b"]), set()).add(w["type"])
        way_index.setdefault((w["b"], w["a"]), set()).add(w["type"])

    season = _season_of_box(state.meta.box)
    seat_count = 0
    ship_count = 0
    added = 0
    # SMOKE-089 (Round 94): per rule 4.6 each Source contributes 1
    # Provender per Supply action. Listing the same locale twice
    # double-counts the Source against the printed "1 Provender per
    # Source" rule. Track unique sources to reject duplicates. For
    # Russian Ship sources, Novgorod can provide up to 2 Provender
    # in a single action (per the play note), so it counts as a
    # special exception — Novgorod-Ship can appear up to 2 times.
    _smoke089_seen_sources: set[tuple[str, str]] = set()
    _ship_source_count: dict[str, int] = {}

    for src in sources:
        sid = src.get("locale_id")
        route = src.get("route", [])
        ttype = src.get("transport")
        if not isinstance(sid, str) or not isinstance(route, list) or not isinstance(ttype, str):
            raise IllegalAction("bad_source", "each source: {locale_id, route[], transport}")
        if ttype not in ("boat", "cart", "sled", "ship"):
            raise IllegalAction("bad_source", f"unknown transport {ttype}")

        # SMOKE-089 (Round 94): dedupe Source against printed rule.
        _smoke089_key = (sid, "ship" if ttype == "ship" else "seat")
        # 2E Supply: a Ship Source may be listed up to 2x -- 1 Provender
        # per Ship, up to 2 Ships -- for Russians from Novgorod OR Teutons
        # from any Seaport. All other duplicate Sources are illegal.
        _two_ship_source = ttype == "ship" and (
            (sd == "russian" and sid == "novgorod")
            or (sd == "teutonic" and static_locales.get(sid, {}).get("seaport") is True)
        )
        if _smoke089_key in _smoke089_seen_sources:
            if _two_ship_source and _ship_source_count.get(sid, 1) < 2:
                _ship_source_count[sid] = _ship_source_count.get(sid, 1) + 1
            else:
                raise IllegalAction(
                    "duplicate_source",
                    f"Source {sid} (transport={ttype}) already listed; each Source "
                    f"contributes 1 Provender per Supply action (4.6)",
                )
        else:
            _smoke089_seen_sources.add(_smoke089_key)
            if _two_ship_source:
                _ship_source_count[sid] = 1

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
            # SMOKE-078 (Round 80): per rulebook 1.7.4 / Calendar
            # reference, "Sleds: Early Winter, Late Winter (any Way)."
            # Rasputitsa is NOT a Sled season — the rule says "Only
            # Sleds are usable in Winter, and Sleds are usable only in
            # Winter." The harness previously accepted sleds in
            # Rasputitsa for Supply, contradicting the rule.
            if season not in ("early_winter", "late_winter"):
                raise IllegalAction("sled_non_winter", "Sleds usable in Winter only (1.7.4)")

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
            wtypes = way_index.get((a, b))
            if not wtypes:
                raise IllegalAction("bad_route", f"no Way between {a} and {b}")
            # SMOKE-047: Transport-Way compatibility (1.7.4). Accept the
            # route segment if ANY available Way type matches the
            # transport's constraints.
            if ttype == "boat" and "waterway" not in wtypes:
                raise IllegalAction("transport_way", "Boats use only Waterways")
            if ttype == "cart" and "trackway" not in wtypes:
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
                # SMOKE-019 (Round 33): use _is_besieged on the specific
                # Lord, not locale-level siege_markers.
                for ol_id, ol in state.lords.items():
                    if ol.state == "mustered" and ol.side != sd and ol.location == chk:
                        if not _is_besieged(state, ol_id):
                            raise IllegalAction("route_blocked", f"Enemy Lord at {chk} blocks Route")

        added += 1

    if seat_count > 2:
        raise IllegalAction("too_many_seat_sources", "max 2 Seat sources (4.6.1)")
    if ship_count > 2:
        raise IllegalAction("too_many_ship_sources", "max 2 Ship sources")

    # SMOKE-048 (Round 60): 4.6 Transport count validation per 2E:
    # "1 usable Transport required per Provender per Way of each Route.
    # Transports cannot do double duty across multiple Sources or
    # multiple Provender." Pool counts from the active Lord and co-
    # located own-side Lords (1.5.2 sharing). Ships always count for
    # ship-sourced supply; non-ship sources use the matching
    # ground/water transport.
    transport_needed: dict[str, int] = {}
    for src in sources:
        ttype = src["transport"]
        route_len = max(0, len(src["route"]) - 1)
        if ttype == "ship":
            # Ship sources: 1 ship per source (Sea route is direct).
            transport_needed["ship"] = transport_needed.get("ship", 0) + 1
        else:
            transport_needed[ttype] = transport_needed.get(ttype, 0) + route_len
    if transport_needed:
        # Pool from active Lord + co-located own-side Lords.
        pool: dict[str, int] = {}
        for _ol_id, ol in state.lords.items():
            if ol.state != "mustered" or ol.side != sd:
                continue
            if ol.location != lord.location:
                continue
            for k in ("boat", "cart", "sled", "ship"):
                pool[k] = pool.get(k, 0) + int(ol.assets.get(k, 0))
        for k, need in transport_needed.items():
            avail = pool.get(k, 0)
            if avail < need:
                raise IllegalAction(
                    "insufficient_transport",
                    f"Supply needs {need} {k}(s); shared pool has {avail} (4.6 2E)",
                )

    # SMOKE-030: T16 Famine (against Russian) / R7 Famine (against
    # Teutonic) cap Seat-sourced Provender at 1 per Command card.
    # Ship-sourced Provender is NOT affected (Tip: "does not affect
    # Provender via Supply from Ships, Ravage, or Spoils").
    famine_against_us = (
        ("T16" in state.decks.teutonic.this_campaign_events) if sd == "russian"
        else ("R7" in state.decks.russian.this_campaign_events)
    )
    famine_seats_dropped = 0
    if famine_against_us and seat_count > 0:
        already_used = state.campaign_turn.seat_supply_this_card
        allowed = max(0, 1 - already_used)
        if seat_count > allowed:
            famine_seats_dropped = seat_count - allowed
            added -= famine_seats_dropped
        state.campaign_turn.seat_supply_this_card = already_used + min(seat_count, allowed)

    # Add provender (cap 8).
    final_added = min(added, 8 - lord.assets.get("provender", 0))
    lord.assets["provender"] = lord.assets.get("provender", 0) + final_added
    # R216 (Q-009): stationary Command -- does NOT set Moved/Fought,
    # so it does not trigger Feed (4.8.1). Moved/Fought is only
    # March/Avoid/Battle/Siege/Storm/Sail (SoP glossary; Misc Rules L451).
    _consume_actions(state, 1)
    return ({"lord_id": lord_id, "added": final_added,
             "lost_to_cap": added + famine_seats_dropped - final_added,
             "famine_seats_dropped": famine_seats_dropped,
             "famine_active": famine_against_us}, [])


def _all_seats(state: GameState, lord_id: str) -> list[str]:
    """Helper: all seats for a Lord (delegates to actions._seats_of)."""
    from nevsky.actions import _seats_of

    return _seats_of(state, lord_id)


# ---------------------------------------------------------------------------
# 4.9 End Campaign
# ---------------------------------------------------------------------------


def _disband_special_vassals(state: GameState, side: str, special_kind: str
                              ) -> list[dict[str, Any]]:
    """SMOKE-031: Disband all Special Vassals of ``special_kind`` from
    every ``side`` Lord. Returns Forces from the parent Lord's mat,
    flips mustered=False and ready=False, clears any Advanced Vassal
    Service Calendar marker. Returns a list of {lord_id, vassal_id,
    was_mustered, was_ready, forces_returned}.

    Used when the gating Capability is discarded (per AoW Reference
    T11 Crusade Tips: 'Summer Crusaders ... also Disband immediately
    if the Crusade card is discarded'; R10 Steppe Warriors Tips:
    'Special Vassal Forces ... also Disband immediately ... upon
    discard of the Steppe Warriors card').
    """
    from nevsky.static_data import load_lords as _load_sl
    _slords = _load_sl()
    cal = state.calendar
    disbanded: list[dict[str, Any]] = []
    for lord_id, lord in state.lords.items():
        if lord.side != side:
            continue
        sl = _slords.get(lord_id, {})
        for vid, vstate in list(lord.vassals.items()):
            vdata = next((v for v in sl.get("vassals", [])
                           if v["vassal_id"] == vid), None)
            if vdata is None or vdata.get("special") != special_kind:
                continue
            v_forces = vdata.get("forces", {}) or {}
            returned: dict[str, int] = {}
            if vstate.mustered:
                for k, v in v_forces.items():
                    avail = lord.forces.get(k, 0)
                    take = min(int(v), avail)
                    if take > 0:
                        lord.forces[k] = avail - take
                        if lord.forces[k] == 0:
                            del lord.forces[k]
                        returned[k] = take
            was_mustered = vstate.mustered
            was_ready = vstate.ready
            vstate.mustered = False
            vstate.ready = False
            if vstate.on_calendar:
                detach_vassal_marker(cal, vid, vstate)
                vstate.on_calendar = False
                vstate.calendar_box = None
            disbanded.append({
                "lord_id": lord_id, "vassal_id": vid,
                "was_mustered": was_mustered, "was_ready": was_ready,
                "forces_returned": returned,
            })
    return disbanded


def _discard_side_capability(state: GameState, side: str, cid: str
                              ) -> dict[str, Any]:
    """SMOKE-031: discard a side-wide capability with per-card cleanup.

    Removes ``cid`` from the side's ``capabilities_in_play`` (if
    present) and appends to ``discard``. Then runs cascading cleanup
    per AoW Reference Tips:

      - T11 Crusade discarded -> Disband Summer Crusaders (Teutonic).
      - R10 Steppe Warriors discarded -> Disband Mongols / Kipchaqs
        Asiatic Horse Special Vassals (Russian).
      - T13 William of Modena discarded -> Legate leaves map (return
        pawn to William of Modena card).

    Returns ``{"card": cid, "disbanded_vassals": [...],
              "legate_removed": bool}``.
    """
    deck = state.decks.teutonic if side == "teutonic" else state.decks.russian
    was_in_play = cid in deck.capabilities_in_play
    if was_in_play:
        deck.capabilities_in_play.remove(cid)
        if cid not in deck.discard:
            deck.discard.append(cid)
    # Per-card cleanup runs regardless of where the card came from. The
    # caller is expected to invoke this helper when the rule says
    # "Disband [cascade-vassals]" — passing the same card_id twice is
    # idempotent (Disband-already-disbanded sets the same fields).
    disbanded: list[dict[str, Any]] = []
    legate_removed = False
    if cid == "T11" and side == "teutonic":
        disbanded = _disband_special_vassals(state, "teutonic", "summer_crusaders")
    elif cid == "R10" and side == "russian":
        disbanded = _disband_special_vassals(state, "russian", "steppe_warriors")
    elif cid == "T13" and side == "teutonic":
        if state.legate.william_of_modena_in_play:
            state.legate.william_of_modena_in_play = False
            state.legate.location = "card"
            state.legate.locale_id = None
            legate_removed = True
    return {"card": cid, "disbanded_vassals": disbanded,
            "legate_removed": legate_removed, "was_in_play": was_in_play}


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
        # 4.9.1: the removing side SELECTS which Enemy Ravaged markers to
        # reduce. args.grow_remove may name exactly `to_remove` of them;
        # otherwise fall back to a deterministic sort (which Locales stay
        # Ravaged is VP-neutral but affects future Forage legality).
        ravaged_set = set(ravaged)
        chosen = args.get("grow_remove")
        if chosen is not None:
            if not isinstance(chosen, list) or any(c not in ravaged_set for c in chosen):
                raise IllegalAction(
                    "bad_grow_remove",
                    f"grow_remove must list Enemy ({target_color}) Ravaged Locales")
            if len(set(chosen)) != to_remove:
                raise IllegalAction(
                    "bad_grow_remove",
                    f"grow_remove must name exactly {to_remove} Locale(s) to reduce to half")
            ravaged_sorted = list(dict.fromkeys(chosen))
        else:
            ravaged_sorted = sorted(ravaged)
        for rid in ravaged_sorted[:to_remove]:
            if target_color == "russian":
                state.locales[rid].russian_ravaged = False
                state.calendar.russian_vp = max(0.0, state.calendar.russian_vp - 0.5)
            else:
                state.locales[rid].teutonic_ravaged = False
                state.calendar.teutonic_vp = max(0.0, state.calendar.teutonic_vp - 0.5)
            grew.append(rid)

    # PLAY-21 (Fable audit): 4.9.5 RESET -- "Each side may discard any
    # Arts of War cards back to its deck (Teutons then Russians)."
    # args.reset_discard = [card_ids] returns held cards (holds zone)
    # to the owning side's deck. Previously this printed option had no
    # engine path: a dead situational Hold (e.g. an Ambush the side
    # will never use) was stuck forever.
    reset_discarded: list[str] = []
    _rd = args.get("reset_discard")
    if _rd is not None:
        if not isinstance(_rd, list):
            raise IllegalAction("bad_reset_discard",
                                "reset_discard must be a list of card ids")
        _deck = _side_deck(state, sd)
        for cid in _rd:
            if cid not in _deck.holds:
                raise IllegalAction(
                    "bad_reset_discard",
                    f"{cid} not in {sd} holds (4.9.5 returns held cards)")
            _deck.holds.remove(cid)
            _deck.deck.append(cid)
            reset_discarded.append(cid)

    # PLAY-17 (Fable audit): 4.9 order is GROW (4.9.1) -> GAME END
    # (4.9.2) -> PLOW AND REAP (4.9.3) -> WASTAGE (4.9.4) -> RESET
    # (4.9.5). The engine ran Wastage per side BEFORE the global Plow &
    # Reap, so Wastage qualification/discard used pre-flip, pre-halving
    # Transport counts (e.g. 4 Sleds at box 6: rules flip->4 Carts,
    # halve->2, Wastage->1 Cart; engine discarded a Sled first ->2
    # Carts). Transport flips only touch the owning side's mats, so the
    # flip is run per side here, before that side's Wastage; the global
    # call in the both-sides-done block is gone. Skipped when this box
    # is the scenario's final 40 Days (4.9.2 GAME END precedes 4.9.3).
    if state.meta.box < state.meta.span_end_box:
        _plow_and_reap(state, state.meta.box, side=sd)

    # 4.9.4 Wastage (per side). A Lord qualifies when he has more than
    # one of any single Asset type OR more than one This Lord
    # Capability card; the OWNING PLAYER then selects ANY one Asset or
    # This Lord Capability from that Lord to discard (rule example: a
    # Lord with two Boats, one Provender, and one card may discard a
    # Boat, the Provender, OR the card).
    # PLAY-6 (Fable playtest): pre-fix the engine auto-discarded one of
    # the most-numerous Asset type with no player choice, and could
    # never discard a card (or a singleton Asset) from a Lord who
    # qualified via a doubled Asset. Mirror the 4.9.1 grow_remove
    # pattern: args.wastage = {lord_id: "<asset_type>" |
    # "capability:<card_id>"} selects per-Lord; unspecified Lords fall
    # back to the deterministic most-numerous-Asset discard.
    wastage_actions = []
    wastage_choices = args.get("wastage") or {}
    if not isinstance(wastage_choices, dict):
        raise IllegalAction(
            "bad_wastage",
            'wastage must be {lord_id: "<asset_type>" | "capability:<card_id>"}')
    for lord_id, lord in state.lords.items():
        if lord.side != sd or lord.state != "mustered":
            continue
        qualifies = (any(v > 1 for v in lord.assets.values())
                     or len(lord.this_lord_capabilities) > 1)
        chosen = wastage_choices.get(lord_id)
        if chosen is not None and not qualifies:
            raise IllegalAction(
                "bad_wastage",
                f"{lord_id} owes no Wastage (no Asset type >1 and <2 "
                "This Lord Capabilities, 4.9.4)")
        if not qualifies:
            continue
        discarded_asset = None
        if chosen is not None:
            if isinstance(chosen, str) and chosen.startswith("capability:"):
                cid = chosen.split(":", 1)[1]
                if cid not in lord.this_lord_capabilities:
                    raise IllegalAction(
                        "bad_wastage",
                        f"{lord_id} has no This Lord Capability {cid!r}")
                lord.this_lord_capabilities.remove(cid)
                _side_deck(state, sd).deck.append(cid)
                discarded_asset = f"capability:{cid}"
            else:
                if not isinstance(chosen, str) or lord.assets.get(chosen, 0) < 1:
                    raise IllegalAction(
                        "bad_wastage",
                        f"{lord_id} has no Asset of type {chosen!r}")
                lord.assets[chosen] -= 1  # type: ignore[index]
                if lord.assets[chosen] == 0:  # type: ignore[index]
                    del lord.assets[chosen]  # type: ignore[arg-type]
                discarded_asset = chosen
        else:
            # Deterministic fallback (legacy behavior): discard one of
            # the most-numerous Asset type, else pop a This Lord card.
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
            else:
                cid = lord.this_lord_capabilities.pop()
                _side_deck(state, sd).deck.append(cid)
                discarded_asset = f"capability:{cid}"
        if discarded_asset:
            wastage_actions.append({"lord_id": lord_id, "discarded": discarded_asset})

    # 4.9.5 Reset: unstack Lieutenants / Lower Lords (4.1.3) and
    # discard This-Campaign events.
    for lord in state.lords.values():
        if lord.side == sd:
            lord.lieutenant_of = None
            lord.has_lower_lord = None
    deck = _side_deck(state, sd)
    discarded_camp_events = list(deck.this_campaign_events)
    deck.discard.extend(discarded_camp_events)
    deck.this_campaign_events = []

    # 4.9.5 Reset (SMOKE-028a): Remove all Serfs from Russian Lord mats
    # (even if Besieged) back to the Smerdi (R4) Capability card / pool.
    # Reference: Nevsky Calender and Veche Reference.txt lines 175-176:
    # "Remove all Serfs from Russian mats (even if Besieged) to the
    #  Smerdi Capability card."
    serfs_returned: list[dict[str, Any]] = []
    if sd == "russian":
        for lord_id, lord in state.lords.items():
            if lord.side == "russian":
                count = lord.forces.get("serfs", 0)
                if count > 0:
                    lord.forces.pop("serfs", None)
                    serfs_returned.append({"lord_id": lord_id, "count": count})

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
            # 5.3 End of Scenario: record the terminal outcome on the single
            # game_over flag so apply_action rejects any later action and
            # session/winner reporting has a recorded result. (A 5.2 Campaign
            # Victory would already have ended the game earlier via
            # _apply_immediate_campaign_victory; this branch is the VP path.)
            if not state.meta.game_over:
                from nevsky.scenarios import determine_scenario_winner
                _res = determine_scenario_winner(state)
                state.meta.winner = _res["winner"]
                state.meta.victory_reason = _res["reason"]
                state.meta.game_over = True
        else:
            # 4.9.3 Plow & Reap ran per side (PLAY-17), before each
            # side's Wastage.
            # Advance Calendar marker by 1, flip to Levy.
            cal = state.calendar
            new_box_after_advance: int | None = None
            for cb in cal.boxes:
                if cb.has_levy_campaign_marker:
                    cb.has_levy_campaign_marker = False
                    cb.levy_campaign_face = None
                    new_box = cb.box + 1
                    if new_box <= 16:
                        cal.boxes[new_box - 1].has_levy_campaign_marker = True
                        cal.boxes[new_box - 1].levy_campaign_face = "levy"
                    state.meta.box = new_box
                    new_box_after_advance = new_box
                    break
            # 4.9.5 Reset (SMOKE-028b/c, refactored R44/SMOKE-031): If the
            # new 40 Days is the year's first Late Winter (box 5 or 13),
            # discard the Crusade Capability (T11) if in play; the unified
            # _discard_side_capability helper cascades the Summer
            # Crusaders Disband per AoW Reference T11 Tip.
            crusade_auto_discarded = False
            summer_crusaders_disbanded: list[dict[str, Any]] = []
            if new_box_after_advance in (5, 13):
                # Disband Summer Crusaders unconditionally per rule 4.9.5
                # (the rule pairs Crusade-discard with Summer-Crusaders-
                # Disband; the latter must fire even when T11 was never
                # in capabilities_in_play, e.g., state was edited or the
                # Vassal was force-set by a test fixture). Then if T11 is
                # in play, discard it through the helper (which would do
                # an idempotent re-disband — no double effect).
                summer_crusaders_disbanded = _disband_special_vassals(
                    state, "teutonic", "summer_crusaders")
                if "T11" in state.decks.teutonic.capabilities_in_play:
                    _discard_side_capability(state, "teutonic", "T11")
                    crusade_auto_discarded = True
            # Reset campaign-turn / step bookkeeping for next Campaign;
            # transition to Levy.
            state.meta.phase = "levy"
            state.meta.levy_step = "arts_of_war"
            state.meta.levy_step_completed_t = False
            state.meta.levy_step_completed_r = False
            # R199 (SMOKE-132): new Levy -> each side may draw again.
            state.meta.aow_drawn_t = False
            state.meta.aow_drawn_r = False
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
            # SMOKE-035 (Round 47): reset per-Levy Lord flags when
            # transitioning Campaign -> next Levy. just_arrived_this_levy
            # marks a Lord that Mustered in the current Levy (3.4 blocks
            # them from Lordship-spending in the same Muster step). The
            # previous Levy is done; the new Levy has not yet Mustered
            # anyone, so the flag must clear for all Lords. Without this
            # reset, a Lord who Mustered in Levy N still counts as
            # "just arrived" in Levy N+1's Muster step and is wrongly
            # blocked from acting as a Lordship source.
            for lord in state.lords.values():
                lord.just_arrived_this_levy = False
            advanced = True

    return ({"side": sd, "grew": grew, "wastage": wastage_actions, "reset_discard": reset_discarded,
             "this_campaign_discarded": discarded_camp_events,
             "serfs_returned": serfs_returned,
             "crusade_auto_discarded": (
                 crusade_auto_discarded if advanced else False),
             "summer_crusaders_disbanded": (
                 summer_crusaders_disbanded if advanced else []),
             "advanced_to_next_levy": advanced, "game_over": game_over}, [])


_END_OF_SUMMER_BOXES = (2, 10)       # Last Summer box per year.
_END_OF_LATE_WINTER_BOXES = (6, 14)  # Last Late-Winter box per year.


def _plow_and_reap(state: GameState, box: int, side: "Side | None" = None) -> None:
    """4.9.3: end-of-Summer Carts -> Sleds; end-of-Late-Winter Sleds ->
    Carts. After flipping, each Lord discards Sleds/Carts down to half
    rounded UP. (PAC text "last 40 Days of Summer or Late Winter"
    corrected per 2E to NOT include Early Winter.)

    PLAY-17: `side` filters to one side's Lords so the flip can run
    inside each side's end_campaign_resolve, BEFORE that side's Wastage
    (4.9.3 precedes 4.9.4). Transport flips never touch the other
    side's mats, so per-side execution is order-equivalent.
    """
    end_of_summer = box in _END_OF_SUMMER_BOXES
    end_of_late_winter = box in _END_OF_LATE_WINTER_BOXES
    if not (end_of_summer or end_of_late_winter):
        return
    for lord in state.lords.values():
        if lord.state != "mustered":
            continue
        if side is not None and lord.side != side:
            continue
        if end_of_summer:
            # Carts -> Sleds (rule).
            sleds = lord.assets.get("sled", 0) + lord.assets.get("cart", 0)
            lord.assets["sled"] = sleds
            lord.assets.pop("cart", None)
        else:
            # Sleds -> Carts.
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
    "place_lieutenant": _h_place_lieutenant,
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
    "legate_command_bonus": _h_legate_command_bonus,
    # 4.6 supply
    "cmd_supply": _h_cmd_supply,
    # 4.9 end campaign
    "end_campaign_resolve": _h_end_campaign_resolve,
}

# ---------------------------------------------------------------------------
# 4.3 March + 4.3.4 Approach + 4.4 Battle handlers
# ---------------------------------------------------------------------------


def _is_laden(state: GameState, lord_id: str, way_type: str | None = None) -> bool:
    """4.3.2: a Lord is Laden if (a) carrying any Loot, OR (b) carrying
    more Provender than usable Transport (any amount over). The
    "more than twice as much Provender as Transport" case (4.3.2
    bullet 1) is a separate "may not move unless they discard the
    excess" gate; that gate is not a Laden condition per se. See
    `_must_discard_to_move_excess` for the gate.

    SMOKE-012 fix (Round 11): pre-fix this function checked
    `prov > 2 * usable` which was the can't-move threshold, NOT the
    Laden threshold. Lords with prov in (usable, 2*usable] were
    incorrectly reported Unladen.

    SMOKE-026 fix (Round 38): the "usable Transport" calculation must
    respect the WAY TYPE being marched -- Boats only work on Waterways,
    Carts only on Trackways, Sleds on either (in Winter). Pre-fix the
    function ignored the Way and counted any season-valid Transport,
    so a Lord with Boats + Provender could march a Trackway with no
    discard required. When `way_type` is None (e.g., for general
    Laden-status queries not tied to a specific march), the legacy
    season-only behavior applies.
    """
    lord = state.lords[lord_id]
    if lord.assets.get("loot", 0) > 0:
        return True
    usable = _usable_transport_count_for_lord(state, lord_id, way_type)
    prov = lord.assets.get("provender", 0)
    return prov > usable


def _must_discard_to_move_excess(
    state: GameState, lord_id: str, way_type: str | None = None,
) -> int:
    """4.3.2 bullet 1: a Lord with more than twice as much Provender
    as usable Transport may NOT move unless he discards the excess.
    Returns the number of Provender that must be discarded (max(0,
    prov - 2*usable)). Loot is unrelated to this gate.

    SMOKE-026 (Round 38): the "usable Transport" count is Way-aware
    when `way_type` is provided. Without that, a Lord with Boats could
    March a Trackway as if the Boats counted (they don't).
    """
    lord = state.lords[lord_id]
    usable = _usable_transport_count_for_lord(state, lord_id, way_type)
    prov = lord.assets.get("provender", 0)
    return max(0, prov - 2 * usable)


def _group_usable_transport(state: GameState, group: list[str], way_type: "str | None" = None) -> int:
    return sum(_usable_transport_count_for_lord(state, g, way_type)
               for g in group if g in state.lords)


def _group_provender(state: GameState, group: list[str]) -> int:
    return sum(int(state.lords[g].assets.get("provender", 0))
               for g in group if g in state.lords)


def _group_is_laden(state: GameState, group: list[str], way_type: "str | None" = None) -> bool:
    """4.3.2 SHARED TRANSPORT: Lords moving as a group Share Transport.
    Count all Provender and usable Transport of Lords moving together to
    determine Laden status (any Loot in the group is also Laden)."""
    if any(int(state.lords[g].assets.get("loot", 0)) > 0
           for g in group if g in state.lords):
        return True
    return _group_provender(state, group) > _group_usable_transport(state, group, way_type)


def _group_excess_provender(state: GameState, group: list[str], way_type: "str | None" = None) -> int:
    """4.3.2: the group may not move with combined Provender exceeding 2x
    its combined usable Transport unless it discards the excess."""
    return max(0, _group_provender(state, group)
               - 2 * _group_usable_transport(state, group, way_type))


def _usable_transport_count_for_lord(
    state: GameState, lord_id: str, way_type: str | None = None,
) -> int:
    """SMOKE-026 (Round 38) helper: count usable Transport on a Lord's
    mat. If `way_type` is given (trackway / waterway / sea), only
    Transport compatible with that Way type is counted (per 1.7.4):
      - Boats: Waterways only (Summer/Rasputitsa).
      - Carts: Trackways only (Summer).
      - Sleds: either Way type (Winter).
      - Ships: Sea Ways only (Summer/Rasputitsa).
    If `way_type` is None, falls back to "all season-valid Transport"
    regardless of Way -- the legacy behavior pre-Round-38, used when
    the caller doesn't have a specific Way in mind (e.g., a general
    Laden-status query for display).
    """
    lord = state.lords[lord_id]
    season = _season_of_box(state.meta.box)
    if way_type is None:
        n = 0
        for t in ("boat", "cart", "sled", "ship"):
            count = int(lord.assets.get(t, 0))
            if t == "boat" and season in ("summer", "rasputitsa"):
                n += count
            elif t == "cart" and season == "summer":
                n += count
            elif t == "sled" and season in ("early_winter", "late_winter"):
                # SMOKE-078 (Round 80): sleds usable only in Winter per
                # 1.7.4. Rasputitsa was incorrectly included in the
                # general Laden-status query branch.
                n += count
            elif t == "ship" and season in ("summer", "rasputitsa"):
                n += count
        return n
    # Way-aware path.
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
    elif way_type == "sea":
        if season in ("summer", "rasputitsa"):
            n += int(lord.assets.get("ship", 0))
    return n


def _enemies_at(state: GameState, locale_id: str, side: Side) -> list[str]:
    return [
        lid for lid, l in state.lords.items()
        if l.state == "mustered" and l.location == locale_id and l.side != side
    ]


def _unbesieged_enemy_lord_at(state: GameState, locale_id: str, side: Side) -> bool:
    """4.4.3 Retreat gate: is there an UNBESIEGED enemy Lord at locale_id?
    A Besieged enemy Lord (inside a Stronghold this side besieges) does
    NOT block Retreat there (mirrors the March/Sail `_is_besieged`
    convention, SMOKE-019)."""
    return any(
        l.state == "mustered" and l.location == locale_id and l.side != side
        and not _is_besieged(state, lid)
        for lid, l in state.lords.items()
    )


def _legal_retreat_dests(
    state: GameState, from_locale: str, side: Side,
    *, exclude: "tuple[str, str] | None" = None,
) -> list[tuple[str, str]]:
    """4.4.3: adjacent Locales a losing `side` Lord may Retreat to -- those
    with "no Unbesieged enemy Lords or Strongholds". A Besieged enemy Lord
    or a Besieged enemy Stronghold (siege_markers > 0) does NOT block.
    There is NO enemy-Conquered-marker block in 4.4.3 (an enemy-Conquered
    Stronghold blocks only while Unbesieged, via the Stronghold test).
    `exclude` = (neighbor, way_type) the Attackers approached along, which
    Defenders may not Retreat back across. Returns [(dest, way_type)].
    """
    out: list[tuple[str, str]] = []
    for w in load_ways():
        if w["a"] == from_locale:
            cand = w["b"]
        elif w["b"] == from_locale:
            cand = w["a"]
        else:
            continue
        if exclude is not None and cand == exclude[0] and w["type"] == exclude[1]:
            continue
        if _unbesieged_enemy_lord_at(state, cand, side):
            continue
        if (_has_enemy_stronghold_at(state, cand, side)
                and state.locales[cand].siege_markers == 0):
            continue
        out.append((cand, w["type"]))
    return out


def _flip_trade_route_if_uncontested(
    state: GameState, locale_id: str, entering_side: Side,
) -> dict[str, Any] | None:
    """SMOKE-020 (Round 34): Trade-Route conquest flip per Strongholds
    reference: "Trade Routes ... flip simply by an enemy Lord's presence
    with no friendly Lord contesting -- no Storm involved, hence no
    Spoils."

    Called from cmd_march (and any future code path that moves a Lord
    onto a Locale). If the destination is a Trade Route and no own-side
    Lord contests it (the Locale's native side has no Lord present),
    the Conquered marker flips and VP shifts.

    For Russian-territory Trade Routes (the only kind on the Nevsky map):
      - Teutonic enters with no Russian Lord present:
          teutonic_conquered 0 -> 1; calendar.teutonic_vp += 1.
      - Russian enters when teutonic_conquered == 1, with no Teutonic
        Lord present: teutonic_conquered -> 0; calendar.teutonic_vp -= 1.

    Returns a result dict describing the flip, or None if no flip.
    """
    static = load_locales()[locale_id]
    if static.get("type") != "trade_route":
        return None
    native_side = static.get("territory")  # currently always "russian"
    enemy_side: Side = "teutonic" if native_side == "russian" else "russian"
    # The entering side conquers only if it's the non-native side.
    loc = state.locales[locale_id]
    vp = int(static.get("vp", 1))
    if entering_side == enemy_side:
        # Conquest check: no native-side Lord present at the locale.
        contesting = [
            lid for lid, l in state.lords.items()
            if l.state == "mustered" and l.side == native_side
            and l.location == locale_id
        ]
        if contesting:
            return None
        # Flip.
        if entering_side == "teutonic":
            if loc.teutonic_conquered == 0:
                loc.teutonic_conquered = vp
                state.calendar.teutonic_vp += float(vp)
                _refresh_vp_markers(state)
                return {"locale": locale_id, "flip_to": "teutonic", "vp": vp}
        else:
            if loc.russian_conquered == 0:
                loc.russian_conquered = vp
                state.calendar.russian_vp += float(vp)
                _refresh_vp_markers(state)
                return {"locale": locale_id, "flip_to": "russian", "vp": vp}
    else:
        # Native side re-entering: clear any enemy Conquered marker.
        if entering_side == "russian" and loc.teutonic_conquered > 0:
            # Check no Teutonic Lord present.
            contesting = [
                lid for lid, l in state.lords.items()
                if l.state == "mustered" and l.side == "teutonic"
                and l.location == locale_id
            ]
            if not contesting:
                prev = loc.teutonic_conquered
                loc.teutonic_conquered = 0
                state.calendar.teutonic_vp -= float(prev)
                _refresh_vp_markers(state)
                return {"locale": locale_id, "flip_to": "neutral",
                        "cleared_marker": "teutonic", "vp": prev}
        elif entering_side == "teutonic" and loc.russian_conquered > 0:
            contesting = [
                lid for lid, l in state.lords.items()
                if l.state == "mustered" and l.side == "russian"
                and l.location == locale_id
            ]
            if not contesting:
                prev = loc.russian_conquered
                loc.russian_conquered = 0
                state.calendar.russian_vp -= float(prev)
                _refresh_vp_markers(state)
                return {"locale": locale_id, "flip_to": "neutral",
                        "cleared_marker": "russian", "vp": prev}
    return None


def _has_enemy_stronghold_at(state: GameState, locale_id: str, side: Side) -> bool:
    """Enemy Stronghold present if locale is enemy-territory stronghold
    not Conquered by us, OR own-territory stronghold Conquered by enemy,
    OR a Castle marker overlays the locale (T17 Stonemasons — Castle
    replaces Fort/Town) and the overlay color is the enemy side.

    Trade Routes are NOT Strongholds (SMOKE-020, Round 34): they have no
    Walls, Capacity, or Garrison per Strongholds reference, so they
    cannot be Sieged or Stormed. Trade-Route flip on enemy presence is
    handled by `_flip_trade_route_if_uncontested`, NOT by this function.

    SMOKE-064 (Round 69): Castle markers can be overlaid on Town locales
    via T17 Stonemasons. A Castle-on-Town must be treated as a Stronghold
    even though the base type is "town" (not in the stronghold-types
    list). Likewise a Russian Castle marker on a Teutonic Castle (after
    flip on Conquest) means Russian ownership regardless of base type.
    """
    static = load_locales()[locale_id]
    loc = state.locales[locale_id]
    # Castle overlay short-circuit: marker color determines owner.
    if loc.teutonic_castle:
        return side == "russian"
    if loc.russian_castle:
        return side == "teutonic"
    if static["type"] not in ("commandery", "fort", "city", "novgorod", "bishopric", "castle"):
        return False
    if side == "teutonic":
        # Russian-territory stronghold not Conquered by us OR our stronghold Conquered by Russians.
        if static["territory"] == "russian" and loc.teutonic_conquered == 0:
            return True
        if static["territory"] in ("teutonic", "crusader") and loc.russian_conquered > 0:
            return True
    else:  # russian
        if static["territory"] in ("teutonic", "crusader") and loc.russian_conquered == 0:
            return True
        if static["territory"] == "russian" and loc.teutonic_conquered > 0:
            return True
    return False


def _take_legate_along(
    state: GameState, side: str, src: str, dest: str,
    take_flag: bool,
) -> dict[str, Any] | None:
    """4.1.1: Teutonic Lord may bring the Legate along on March / Sail
    if the Lord is co-located with the Legate. Returns a summary dict
    when the Legate is taken, None otherwise. Validates side, the
    Legate's in-play state, and co-location at src; teleports Legate
    pawn to dest. The Lord does not consume Transport for the Legate.
    """
    if not take_flag:
        return None
    if side != "teutonic":
        raise IllegalAction("not_teutonic", "Only Teutonic Lords may take the Legate (4.1.1)")
    if not state.legate.william_of_modena_in_play:
        raise IllegalAction("legate_not_in_play",
                            "Legate not in play; nothing to take")
    if state.legate.location != "locale" or state.legate.locale_id != src:
        raise IllegalAction(
            "legate_not_co_located",
            f"Legate is at {state.legate.locale_id}, not at march source {src} (4.1.1)",
        )
    state.legate.locale_id = dest
    return {"from": src, "to": dest, "took_legate": True}


_VALID_UNIT_TYPES = {
    "knights", "sergeants", "men_at_arms", "serfs",
    "militia", "light_horse", "asiatic_horse",
}


def _validate_absorption_policy(value: Any) -> "str | list[str]":
    """R198: validate an owner-supplied casualty-absorption policy.

    Accepts "weakest_first" (default), "armored_first", or a custom
    priority list of valid unit-type strings (highest sacrifice
    priority first). Raises IllegalAction on anything else.
    """
    if value is None:
        return "weakest_first"
    if isinstance(value, str):
        if value not in ("weakest_first", "armored_first"):
            raise IllegalAction(
                "bad_absorption_policy",
                "absorption_policy must be 'weakest_first', 'armored_first', "
                "or a list of unit types",
            )
        return value
    if isinstance(value, (list, tuple)):
        bad = [u for u in value if u not in _VALID_UNIT_TYPES]
        if bad:
            raise IllegalAction(
                "bad_absorption_policy",
                f"custom absorption_policy has unknown unit types: {bad}; "
                f"valid: {sorted(_VALID_UNIT_TYPES)}",
            )
        return list(value)
    raise IllegalAction(
        "bad_absorption_policy",
        "absorption_policy must be a string or a list of unit types",
    )


def _h_cmd_march(
    state: GameState, side: str, args: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """4.3 March one Locale via a Way. 1 action Unladen, 2 Laden.

    args:
      lord_id    Active Lord
      to         Destination locale_id (must be adjacent via a Way)
      group      Optional list[lord_id] of co-Marching Lords
                 (basic group March via Marshal -- 4.3.1)

    On Approach: if destination contains enemy Lord(s), set
    combat_pending and pause; defender must respond with avoid_battle /
    withdraw / stand_battle. If no enemy Lord but enemy Stronghold,
    place a Siege marker (4.3.5). If neither, just move.
    """
    sd = _require_side_player(state, side)
    lord_id = args.get("lord_id", state.campaign_turn.active_lord)
    dest = args.get("to")
    group = args.get("group", [lord_id]) or [lord_id]
    if not (isinstance(lord_id, str) and isinstance(dest, str) and isinstance(group, list)):
        raise IllegalAction("missing_arg", "args: lord_id, to, group(optional)")
    _require_active_lord_command(state, sd, lord_id)

    lord = state.lords[lord_id]
    if _is_besieged(state, lord_id):
        raise IllegalAction("besieged", "Active Lord is Besieged; cannot March (4.3)")
    src = lord.location
    if src is None:
        raise IllegalAction("no_location", "Lord has no location")
    # SMOKE-034 (Round 46): an active Lieutenant (Lord with a Lower
    # Lord stacked on them via 4.1.3) MUST move together with the Lower
    # Lord -- "move together in March, Retreat, etc., as if Lieutenant
    # were Marshal" (Sequence of Play 4.1.3). Reject any March group
    # that omits the Lower Lord. Likewise reject a Lower Lord
    # appearing as active here (its card resolves as Pass via
    # _h_command_reveal), but if a caller bypasses reveal we still
    # guard the group.
    if lord.has_lower_lord is not None and lord.has_lower_lord not in group:
        raise IllegalAction(
            "lower_lord_required",
            f"Active Lieutenant {lord_id} must move with Lower Lord "
            f"{lord.has_lower_lord} (4.1.3)",
        )
    # SMOKE-041 (Round 53): 4.3.1 "Marshal may take a group March."
    # Non-Marshal non-Lieutenant active Lords cannot bring additional
    # Lords. A Lieutenant may bring their Lower Lord (and only the
    # Lower Lord) per 4.1.3. Other multi-Lord groups require a
    # Marshal. The Marshal check uses Q-003's _is_currently_marshal
    # so secondary Marshals (Hermann/Andrey) qualify only when their
    # permanent counterpart is off the map.
    if len(group) > 1:
        is_marshal = _is_currently_marshal(state, lord_id)
        is_lieutenant_with_only_pair = (
            lord.has_lower_lord is not None
            and set(group) == {lord_id, lord.has_lower_lord}
        )
        if not (is_marshal or is_lieutenant_with_only_pair):
            raise IllegalAction(
                "non_marshal_group",
                f"{lord_id} is not a Marshal; only the Lieutenant + Lower Lord pair "
                f"or a Marshal-led group may March together (4.3.1 / 4.1.3)",
            )
    # PLAY-22 (Fable audit): 4.3.1 -- "The Lord beneath a Marching
    # Lieutenant (4.1.3) must move with the Lieutenant." The active-Lord
    # guard above misses a NON-active Lieutenant inside a Marshal-led
    # group: the group could March off leaving the Lower Lord behind,
    # with the (still-linked) pair now split across Locales.
    for _gid in group:
        _gl = state.lords.get(_gid)
        if (_gl is not None and _gl.has_lower_lord is not None
                and _gl.has_lower_lord not in group):
            raise IllegalAction(
                "lower_lord_required",
                f"Lieutenant {_gid} in the March group must move with "
                f"Lower Lord {_gl.has_lower_lord} (4.3.1 / 4.1.3)",
            )

    # Way check.
    # SMOKE-067 (Round 72): when the src<->dest pair has parallel Ways
    # (e.g. dorpat<->odenpah has both trackway and waterway), the agent
    # may pick which Way via args.way_type. Without explicit selection,
    # default to the first matching Way (legacy behavior).
    ways = load_ways()
    requested_way = args.get("way_type")
    candidate_types: list[str] = []
    for w in ways:
        if (w["a"] == src and w["b"] == dest) or (w["b"] == src and w["a"] == dest):
            candidate_types.append(w["type"])
    if not candidate_types:
        raise IllegalAction("no_way", f"no Way between {src} and {dest}")
    if isinstance(requested_way, str):
        if requested_way not in candidate_types:
            raise IllegalAction(
                "bad_way_type",
                f"requested way_type {requested_way!r} not among {candidate_types} between {src} and {dest}",
            )
        way_type = requested_way
    else:
        way_type = candidate_types[0]

    # Validate group: all Lords must be at src and on the active side.
    for gid in group:
        if gid not in state.lords or state.lords[gid].side != sd:
            raise IllegalAction("bad_group", f"{gid} not on your side")
        if state.lords[gid].location != src:
            raise IllegalAction("bad_group", f"{gid} not at {src}")
        if _is_besieged(state, gid):
            raise IllegalAction("besieged", f"{gid} is Besieged; cannot March")

    # 4.3.2 SHARED TRANSPORT: Lords moving together Share Transport;
    # the GROUP's combined Provender vs combined usable Transport governs
    # both the excess-discard gate and Laden status (not per-Lord). The
    # caller may pass args.discard_excess_provender=True to auto-discard
    # (1.7.2 Greed permits discard for March/Avoid/Retreat/Sail).
    excess = _group_excess_provender(state, group, way_type=way_type)
    if excess > 0:
        if args.get("discard_excess_provender"):
            remaining = excess
            for gid in group:
                if remaining <= 0:
                    break
                have = int(state.lords[gid].assets.get("provender", 0))
                take = min(have, remaining)
                if take > 0:
                    state.lords[gid].assets["provender"] = have - take
                    if state.lords[gid].assets.get("provender") == 0:
                        state.lords[gid].assets.pop("provender", None)
                    remaining -= take
        else:
            raise IllegalAction(
                "excess_provender",
                f"group has {excess} more Provender than 2x combined usable "
                f"Transport (4.3.2); pass args.discard_excess_provender=True to discard"
            )

    # Action cost: 2 if the moving group is Laden (combined), else 1.
    laden = _group_is_laden(state, group, way_type=way_type)
    cost = 2 if laden else 1
    # Converts (T3): first March of this card with Light Horse in the
    # group costs 0 actions. The active Lord need not have Converts
    # himself; any group member with Converts plus any group member
    # with Light Horse qualifies (rule 4.3.x Converts tip).
    from nevsky.capabilities import any_capability as _any_cap
    if not state.lords[lord_id].first_march_used_this_card:
        any_converts = any(_any_cap(state, gid, "Converts") for gid in group)
        any_lh = any(state.lords[gid].forces.get("light_horse", 0) > 0 for gid in group)
        if any_converts and any_lh:
            cost = 0
    if state.campaign_turn.actions_remaining < cost:
        raise IllegalAction(
            "insufficient_actions",
            f"March costs {cost} action(s); {state.campaign_turn.actions_remaining} remain",
        )

    # SMOKE-129 (Round 196): Approach (4.3.4) triggers only on enemy
    # Lords NOT in a Stronghold at the destination. A besieged-inside
    # enemy (in_stronghold=True) is not in the open and not a valid
    # Approach target; the arriving Lord simply joins the siege.
    # Pre-fix, marching Rudolf into Izborsk where Gavrilo was already
    # Withdrawn-inside fired a second Approach with Gavrilo as
    # defender, letting Russia "Withdraw" a Lord who was already
    # besieged — visible in the Round 195 Pleskau playthrough at
    # Turn 2 Rudolf's reveal.
    enemies = [
        lid for lid in _enemies_at(state, dest, sd)
        if not state.lords[lid].in_stronghold
    ]
    # 4.4.2: the attacker may Concede the Battle this March triggers,
    # at Round 1 (true / 'attacker') or a later Round (int). Captured on
    # combat_pending and applied when the Battle resolves.
    attacker_concede_round = _parse_concede_round(args.get("concede"), who="attacker")
    if attacker_concede_round is not None and not enemies:
        raise IllegalAction(
            "no_combat_to_concede",
            "concede is only valid when the March triggers a Battle",
        )
    if enemies:
        # Approach: pause and request defender response.
        from nevsky.state import CombatPending
        defender_side: Side = state.lords[enemies[0]].side
        state.combat_pending = CombatPending(
            attacker_side=sd,
            attacker_group=list(group),
            attacker_absorption_policy=_validate_absorption_policy(
                args.get("absorption_policy")),
            from_locale=src,
            to_locale=dest,
            way_type=way_type,
            defender_side=defender_side,
            defender_lords=enemies,
            pending_response_by=defender_side,
            laden=laden,
            attacker_concede_round=attacker_concede_round,
            sally_join=(list(args["sally_join"])
                        if isinstance(args.get("sally_join"), list) else None),
        )
        # SMOKE-111 (Round 173): switch active_player to the defender
        # side so legal_moves enumerates their response options
        # (stand_battle / avoid_battle / withdraw). Without this swap,
        # `side = state.meta.active_player` in legal_moves keeps
        # returning the marching side, which has zero legal moves
        # while combat_pending is owed by the defender — a deadlock
        # surfaced by self-play (Watland seed=3, RotP-Nicolle seed=1).
        state.meta.active_player = defender_side
        # Move attacking Lord(s) tentatively (we model: attackers enter the
        # locale at Approach; if defender Avoids / Withdraws into Stronghold,
        # outcome resolves below). For simplicity Phase 3b records attackers
        # at destination during Approach and rolls back if Battle resolves
        # the loser as attackers.
        for gid in group:
            state.lords[gid].location = dest
            state.lords[gid].moved_fought = True
            # SMOKE-036 (Round 47): clear in_stronghold on movement
            state.lords[gid].in_stronghold = False
        _consume_actions(state, cost)
        state.lords[lord_id].first_march_used_this_card = True
        # SMOKE-043 (Round 55): Teutonic Lord may bring the Legate
        # along on March (4.1.1). args.take_legate=True opts in.
        legate_carried = _take_legate_along(
            state, sd, src, dest, bool(args.get("take_legate", False)),
        )
        # PLAY-3 (Fable playtest): the Approach branch returns early and
        # skipped the R215 stale-siege sweep below -- if the marching
        # group were the last besiegers at src, lift that Siege (4.3.5).
        from nevsky.actions import _lift_siege_if_no_besiegers
        _lift_siege_if_no_besiegers(state, src)
        out_approach = {
            "lord_id": lord_id, "from": src, "to": dest, "way": way_type,
            "group": group, "laden": laden, "cost": cost,
            "approach": True,
            "defender_side": state.lords[enemies[0]].side,
            "defender_lords": enemies,
        }
        if legate_carried:
            out_approach["legate_carried"] = legate_carried
        return (out_approach, [])

    # No enemy Lord: just move.
    for gid in group:
        state.lords[gid].location = dest
        state.lords[gid].moved_fought = True
        # SMOKE-036 (Round 47): clear in_stronghold on any movement to a
        # new Locale. The flag tracks "inside a Stronghold at the
        # current Locale" and would otherwise leak across moves, causing
        # legal_moves and Battle Array checks to mistake a Lord in the
        # open at the new Locale for one inside a Stronghold.
        state.lords[gid].in_stronghold = False

    # SMOKE-020 (Round 34): trade-route auto-flip on uncontested entry.
    trade_flip = _flip_trade_route_if_uncontested(state, dest, sd)

    placed_siege = False
    if _has_enemy_stronghold_at(state, dest, sd):
        loc = state.locales[dest]
        if loc.siege_markers == 0:
            loc.siege_markers = 1
            placed_siege = True
            # Begin Siege ends the card per 4.3 (ends_card_when began_siege).
            state.campaign_turn.actions_remaining = 0
            _enter_feed_pay_disband(state)

    if not placed_siege:
        _consume_actions(state, cost)
    state.lords[lord_id].first_march_used_this_card = True
    # R215 (SMOKE-153): if the marching group were the last besieger(s) at
    # the source Locale, lift any now-orphaned Siege there (a Stronghold is
    # Besieged only while enemy besiegers are present, 4.3.5).
    from nevsky.actions import _lift_siege_if_no_besiegers
    _lift_siege_if_no_besiegers(state, src)

    # SMOKE-043 (Round 55): Teutonic Lord may bring the Legate
    # along on March (4.1.1). args.take_legate=True opts in.
    legate_carried = _take_legate_along(
        state, sd, src, dest, bool(args.get("take_legate", False)),
    )

    result = {
        "lord_id": lord_id, "from": src, "to": dest, "way": way_type,
        "group": group, "laden": laden, "cost": cost,
        "placed_siege": placed_siege,
    }
    if trade_flip is not None:
        result["trade_route_flip"] = trade_flip
    if legate_carried:
        result["legate_carried"] = legate_carried
    return (result, [])


def _h_avoid_battle(
    state: GameState, side: str, args: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """4.3.4 Avoid Battle: Inactive defender Lord(s) move to an adjacent
    Locale free of enemy Lord, Stronghold, and Conquered marker.

    Round 29 corrections per 4.3.4 / 1.4.1:
      - Lords may discard Loot and excess Provender to become Unladen
        and thereby Avoid Battle (no longer hard-rejecting Laden Lords).
      - Defender 'may take no Loot'; all Loot is discarded.
      - Provender capped at Transport usable on the Avoid Way; excess
        is discarded.
      - Discarded Loot + excess Provender transfer to the first
        attacker as Spoils ('as if Spoils', 4.4.3).
      - May not Avoid across the Way the enemy used to Approach: dest
        cannot be cp.from_locale via the same way_type (matches the
        retreat-restriction convention used elsewhere).
      - Service is NOT shifted on Avoid (4.3.4 has no shift; only
        4.4.3 Retreat does).
      - 1.4.1 Legate trigger: if the Avoiding Lord(s) include a
        Teutonic Lord and the Legate is at the Avoid origin Locale,
        remove the pawn and discard William of Modena.

    args.to: destination locale_id.
    """
    from nevsky.battle import _usable_transport_count_for_way

    sd = _require_side_player(state, side)
    cp = state.combat_pending
    if cp is None:
        raise IllegalAction("no_combat", "no pending combat")
    if cp.pending_response_by != sd:
        raise IllegalAction("wrong_actor", f"response owed by {cp.pending_response_by}")
    dest = args.get("to")
    if not isinstance(dest, str):
        raise IllegalAction("missing_arg", "args.to required")
    # PLAY-26 (4.3.4): optional per-Lord subset. "some or all Inactive
    # Lords may move to one or more adjacent Locales" -- args.lords names
    # which currently-outside defenders Avoid to `dest`; default = all of
    # them (backward-compatible single-destination Avoid). Different Lords
    # may Avoid to different Locales via separate avoid_battle calls.
    avoiders = args.get("lords")
    if avoiders is None:
        avoiders = list(cp.defender_lords)
    else:
        if not isinstance(avoiders, list) or not avoiders:
            raise IllegalAction("bad_arg", "args.lords must be a non-empty list")
        bad = [x for x in avoiders if x not in cp.defender_lords]
        if bad:
            raise IllegalAction("bad_lords", f"{bad} not among outside defenders {cp.defender_lords}")
    # SMOKE-115 (Round 180): T6/R6 Ambush "Block Avoid Battle" mode.
    # Per AoW Reference T6 Tip: "If played to block Avoid Battle,
    # declare Event after Defender declares Avoid Battle; any discard
    # of Assets to Avoid Battle also is blocked." When defender
    # declares avoid, check if attacker has the relevant Ambush hold.
    # If so, enter an interrupt window: stage the avoid args and let
    # the attacker decide (play_ambush_block / decline_ambush_block).
    if not args.get("_post_ambush_decline", False):
        attacker_holds = (state.decks.teutonic.holds if cp.attacker_side == "teutonic"
                          else state.decks.russian.holds)
        ambush_cid = "T6" if cp.attacker_side == "teutonic" else "R6"
        if ambush_cid in attacker_holds:
            cp.ambush_block_pending = True
            cp.pending_avoid_args = dict(args)
            cp.pending_response_by = cp.attacker_side
            state.meta.active_player = cp.attacker_side
            return ({"ambush_interrupt": True, "ambush_card": ambush_cid,
                     "owed_by": cp.attacker_side}, [])

    src = cp.to_locale  # defender currently at to_locale
    # SMOKE-068 (Round 73): for parallel-Ways pairs (dorpat<->odenpah
    # has both trackway and waterway), the defender may pick which Way
    # to Avoid via through args.way_type. Without explicit selection,
    # _way_type_between returns the first match (legacy behavior).
    from nevsky.static_data import load_ways
    candidate_types: list[str] = []
    for w in load_ways():
        if (w["a"] == src and w["b"] == dest) or (w["a"] == dest and w["b"] == src):
            candidate_types.append(w["type"])
    if not candidate_types:
        raise IllegalAction("not_adjacent", f"{dest} not adjacent to {src}")
    requested_way = args.get("way_type")
    if isinstance(requested_way, str):
        if requested_way not in candidate_types:
            raise IllegalAction(
                "bad_way_type",
                f"requested way_type {requested_way!r} not among {candidate_types} between {src} and {dest}",
            )
        dest_way_type = requested_way
    else:
        dest_way_type = candidate_types[0]

    # 4.3.4: may not Avoid Battle across the Way the enemy used to
    # Approach. We identify the approach Way by (from_locale, way_type);
    # if dest == cp.from_locale and dest_way_type == cp.way_type, the
    # defender would be retreating along the exact Way the attacker
    # used. Parallel Ways of a different type between the same Locales
    # remain available.
    if dest == cp.from_locale and dest_way_type == cp.way_type:
        raise IllegalAction(
            "approach_way_blocked",
            "may not Avoid Battle across the Way the enemy used to Approach (4.3.4)",
        )

    # PLAY-30 (4.3.4): may not Avoid to a Locale with an UNBESIEGED enemy
    # Lord or Stronghold -- the SAME gate as 4.4.3 Retreat. A Besieged
    # enemy Lord/Stronghold (siege_markers > 0, your side besieges it) does
    # NOT block; there is NO enemy-Conquered-marker clause in 4.3.4 (the old
    # code over-restricted: Besieged strongholds and enemy-Conquered Trade
    # Routes wrongly blocked). Shares _unbesieged_enemy_lord_at with Retreat.
    if _unbesieged_enemy_lord_at(state, dest, sd):
        raise IllegalAction("dest_blocked", f"{dest} has Unbesieged enemy Lord")
    if _has_enemy_stronghold_at(state, dest, sd) and state.locales[dest].siege_markers == 0:
        raise IllegalAction("dest_blocked", f"{dest} has Unbesieged enemy Stronghold")

    # 4.3.4 discards: each Avoiding defender drops ALL Loot and any
    # Provender beyond Transport usable on the Avoid Way. Discards
    # accumulate as Spoils for the Approaching attacker.
    spoils_loot = 0
    spoils_prov = 0
    per_lord_discards: list[dict[str, Any]] = []
    for did in avoiders:
        lord = state.lords[did]
        loot_n = int(lord.assets.get("loot", 0))
        if loot_n > 0:
            spoils_loot += loot_n
            lord.assets.pop("loot", None)
        usable = _usable_transport_count_for_way(state, did, dest_way_type)
        prov_n = int(lord.assets.get("provender", 0))
        excess = max(0, prov_n - usable)
        if excess > 0:
            spoils_prov += excess
            new_prov = prov_n - excess
            if new_prov > 0:
                lord.assets["provender"] = new_prov
            else:
                lord.assets.pop("provender", None)
        per_lord_discards.append({
            "lord_id": did, "loot": loot_n, "excess_provender": excess,
        })
    # Transfer discards to first attacker (Spoils, 4.4.3 "as if Spoils").
    # SMOKE-032: enforce 1.7.3 8-asset cap; excess vanishes.
    avoid_spoils_lost: dict[str, int] = {}
    if (spoils_loot > 0 or spoils_prov > 0) and cp.attacker_group:
        winner = cp.attacker_group[0]
        from nevsky.battle import _award_assets_capped
        award = _award_assets_capped(state, winner, {
            "loot": spoils_loot, "provender": spoils_prov,
        })
        spoils_loot = award["added"].get("loot", 0)
        spoils_prov = award["added"].get("provender", 0)
        avoid_spoils_lost = award["lost_to_cap"]

    # Move the Avoiding subset and mark Moved/Fought (4.3.4 explicit:
    # "Mark Avoiding Lords as Moved/Fought").
    for did in avoiders:
        state.lords[did].location = dest
        state.lords[did].moved_fought = True
        # SMOKE-036: clear in_stronghold on movement.
        state.lords[did].in_stronghold = False
    # PLAY-26: remove the Avoiders from the outside defender set.
    cp.defender_lords = [d for d in cp.defender_lords if d not in avoiders]

    # SMOKE-091 (Round 99): trade-route auto-flip on uncontested entry
    # (per Strongholds reference; SMOKE-020 wired this for cmd_march and
    # cmd_sail). Avoid Battle also moves a Lord onto a destination —
    # if that's a Russian trade_route and no native (Russian) Lord
    # contests, the flip should fire on the defender's arrival.
    _flip_trade_route_if_uncontested(state, dest, cp.defender_side)

    # 1.4.1 Legate trigger: if any Teutonic defender Avoided and the
    # Legate is at the Avoid origin (cp.to_locale, where the Lord just
    # left from), remove the pawn and discard William of Modena.
    if (cp.defender_side == "teutonic"
            and state.legate.william_of_modena_in_play
            and state.legate.location == "locale"
            and state.legate.locale_id == cp.to_locale):
        if "T13" in state.decks.teutonic.capabilities_in_play:
            state.decks.teutonic.capabilities_in_play.remove("T13")
            state.decks.teutonic.discard.append("T13")
        state.legate.william_of_modena_in_play = False
        state.legate.location = "card"
        state.legate.locale_id = None

    # PLAY-26 (4.3.4): if outside defenders remain, the Approach is not
    # yet resolved -- the Inactive side may still Avoid/Withdraw more
    # Lords or Stand with the rest. Keep the response window open; do not
    # place a Siege, clear combat, or end the attacker's card yet.
    if cp.defender_lords:
        state.meta.active_player = cp.defender_side
        return (
            {
                "avoided_to": dest,
                "avoided_lords": list(avoiders),
                "remaining_defenders": list(cp.defender_lords),
                "awaiting_response": True,
                "spoils_to_attacker": {"loot": spoils_loot, "provender": spoils_prov},
                "spoils_lost_to_cap": avoid_spoils_lost,
                "discards_per_lord": per_lord_discards,
            },
            [],
        )

    # All defenders have now Avoided/Withdrawn -> resolve the Approach.
    # Stronghold present at the Approach Locale (with no defender Lords
    # left) -> begin Siege.
    placed_siege = False
    if _has_enemy_stronghold_at(state, cp.to_locale, cp.attacker_side):
        loc2 = state.locales[cp.to_locale]
        if loc2.siege_markers == 0:
            loc2.siege_markers = 1
            placed_siege = True

    # PLAY-3 (Fable playtest): if the Avoiding Lords were themselves the
    # besiegers of a Stronghold at the Approach Locale (their Siege from a
    # prior card), their departure ends that Siege (4.3.5 "If all Besieging
    # Lords later depart, remove all Siege markers"). Pre-fix the markers
    # persisted, leaving the inside Lord "Besieged" by nobody (locked to
    # Sally/Pass, with Sally raising no_defenders).
    from nevsky.actions import _lift_siege_if_no_besiegers
    _lift_siege_if_no_besiegers(state, cp.to_locale)

    state.combat_pending = None
    # PLAY-2 (Fable playtest): 4.3.4 -- when ALL defenders Avoid Battle, no
    # Battle occurs, so the Marching side's Command card CONTINUES with any
    # remaining actions. Only Encamp (4.3.5: the Approach left the attacker
    # Besieging a Stronghold) or a Battle/Storm ends the card. Pre-fix the
    # handler unconditionally zeroed actions_remaining and entered 4.8.
    state.meta.active_player = cp.attacker_side
    if placed_siege or state.campaign_turn.actions_remaining <= 0:
        state.campaign_turn.actions_remaining = 0
        _enter_feed_pay_disband(state)
    return (
        {
            "avoided_to": dest,
            "placed_siege": placed_siege,
            "spoils_to_attacker": {"loot": spoils_loot, "provender": spoils_prov},
            "spoils_lost_to_cap": avoid_spoils_lost,
            "discards_per_lord": per_lord_discards,
        },
        [],
    )


def _h_play_ambush_block(
    state: GameState, side: str, args: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """SMOKE-115 (Round 180): T6/R6 Ambush Block Avoid Battle.

    Played in response to defender's avoid_battle declaration when
    attacker has the Ambush hold (T6 if attacker is Teutonic, R6 if
    Russian). The avoid is rejected; defender must Stand or Withdraw.
    Per AoW Reference T6 Tip: "any discard of Assets to Avoid Battle
    also is blocked; Event used to Block Avoid Battle does not
    otherwise affect the ensuing Battle."

    The Ambush card moves from holds to discard.
    """
    sd = _require_side_player(state, side)
    cp = state.combat_pending
    if cp is None:
        raise IllegalAction("no_combat", "no pending combat")
    if not cp.ambush_block_pending:
        raise IllegalAction("no_ambush_window",
                            "play_ambush_block only legal in Ambush response window")
    if cp.pending_response_by != sd:
        raise IllegalAction("wrong_actor",
                            f"Ambush response owed by {cp.pending_response_by}; got {sd}")
    if sd != cp.attacker_side:
        raise IllegalAction("wrong_side",
                            "only the attacker may play Ambush to block avoid")
    deck = state.decks.teutonic if sd == "teutonic" else state.decks.russian
    ambush_cid = "T6" if sd == "teutonic" else "R6"
    if ambush_cid not in deck.holds:
        raise IllegalAction("not_in_holds", f"{ambush_cid} not in {sd} holds")
    # Move the card from holds to discard.
    deck.holds.remove(ambush_cid)
    deck.discard.append(ambush_cid)
    # Reset combat_pending state: avoid is blocked; baton returns to defender
    # for stand_battle / withdraw choice. NO Asset discard happens (the
    # avoid is fully blocked).
    cp.ambush_block_pending = False
    cp.pending_avoid_args = {}
    cp.pending_response_by = cp.defender_side
    state.meta.active_player = cp.defender_side
    return ({"ambush_blocked": True, "card_consumed": ambush_cid,
             "owed_by": cp.defender_side,
             "remaining_options": ["stand_battle", "withdraw"]}, [])


def _h_decline_ambush_block(
    state: GameState, side: str, args: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """SMOKE-115 (Round 180): attacker declines to play T6/R6 Ambush
    to block the defender's avoid_battle. The original avoid resolves
    with the args staged when avoid_battle was declared.
    """
    sd = _require_side_player(state, side)
    cp = state.combat_pending
    if cp is None:
        raise IllegalAction("no_combat", "no pending combat")
    if not cp.ambush_block_pending:
        raise IllegalAction("no_ambush_window",
                            "decline_ambush_block only legal in Ambush response window")
    if cp.pending_response_by != sd:
        raise IllegalAction("wrong_actor",
                            f"Ambush response owed by {cp.pending_response_by}; got {sd}")
    if sd != cp.attacker_side:
        raise IllegalAction("wrong_side",
                            "only the attacker may decline Ambush")
    # Clear ambush state and re-fire avoid_battle with the staged args.
    avoid_args = dict(cp.pending_avoid_args)
    cp.ambush_block_pending = False
    cp.pending_avoid_args = {}
    cp.pending_response_by = cp.defender_side
    state.meta.active_player = cp.defender_side
    avoid_args["_post_ambush_decline"] = True
    # Re-invoke avoid_battle as the defender side.
    return _h_avoid_battle(state, cp.defender_side, avoid_args)


def _can_withdraw_into(state: GameState, locale_id: str, side: Side, n_lords: int) -> bool:
    """SMOKE-158 (R221): enumerator-side mirror of _h_withdraw eligibility
    (4.3.4). True iff `side` could Withdraw n_lords into the Stronghold at
    locale_id: an effective (non-Trade-Route) Stronghold there, Friendly /
    own-territory / own-Conquered to `side` (not enemy-Conquered), with
    Capacity >= n_lords. Keep in sync with _h_withdraw."""
    eff = _effective_stronghold(state, locale_id)
    if eff is None or eff.get("no_storm"):
        return False
    if not _is_friendly_locale(state, locale_id, side):
        static = load_locales()[locale_id]
        loc = state.locales[locale_id]
        own_terr = ((side == "teutonic" and static["territory"] in ("teutonic", "crusader"))
                    or (side == "russian" and static["territory"] == "russian"))
        own_conq = ((side == "teutonic" and loc.teutonic_conquered > 0)
                    or (side == "russian" and loc.russian_conquered > 0))
        enemy_conq = ((side == "teutonic" and loc.russian_conquered > 0)
                      or (side == "russian" and loc.teutonic_conquered > 0))
        if not (own_terr or own_conq) or enemy_conq:
            return False
    return n_lords <= int(eff.get("capacity", 1))


def _h_withdraw(
    state: GameState, side: str, args: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """4.3.4 Withdraw: defender retreats into a Friendly Stronghold at
    the Battle Locale (capacity 1/2/3).

    For Phase 3b we treat Withdraw as: defender remains at to_locale
    but is moved 'inside' the Stronghold (Besieged status). We model
    this by placing a siege marker at the locale and marking each
    withdrawn Lord with siege_markers > 0 at their location.
    """
    sd = _require_side_player(state, side)
    cp = state.combat_pending
    if cp is None:
        raise IllegalAction("no_combat", "no pending combat")
    if cp.pending_response_by != sd:
        raise IllegalAction("wrong_actor", f"response owed by {cp.pending_response_by}")
    static = load_locales()
    sloc = static[cp.to_locale]
    stype = sloc["type"]
    # SMOKE-065 (Round 70): use _effective_stronghold to recognize Castle
    # overlays on non-stronghold base types (Town with russian_castle /
    # teutonic_castle). The original static-type list excluded "town".
    eff = _effective_stronghold(state, cp.to_locale)
    if eff is None or eff.get("no_storm"):
        raise IllegalAction("no_stronghold", f"{cp.to_locale} has no Stronghold to Withdraw into")
    # Friendly to defender side?
    if not _is_friendly_locale(state, cp.to_locale, sd):
        # Strict Friendly check excludes Besieged locales AND any Locale
        # with an enemy Lord present -- but during an Approach the
        # attacker is necessarily AT the Battle Locale, so the strict
        # check always fails here. For Withdraw eligibility we mirror
        # 1.3.1's territory criterion directly: defender's own territory
        # OR a Stronghold the defender has Conquered, with no enemy
        # Conquered marker.
        #
        # SMOKE-130 (Round 197): the prior code only accepted own
        # territory and dropped the "own Conquered Stronghold" half --
        # contradicting the inline comment AND 1.3.1 ("A Lord at a
        # Stronghold Conquered FROM the enemy ... is Friendly to this
        # side", Miscellaneous Rules Reference). A defender holding a
        # Stronghold he conquered in enemy territory (e.g. Teuton-held
        # Pskov in Peipus) was wrongly denied a Withdraw into it and
        # forced to Stand. Surfaced in the Round 196.5 Peipus LLM
        # playthrough; legal_moves already offered withdraw, so this
        # was also an enumerator/handler asymmetry.
        loc_state = state.locales[cp.to_locale]
        own_terr = (sd == "teutonic" and sloc["territory"] in ("teutonic", "crusader")) or (sd == "russian" and sloc["territory"] == "russian")
        own_conq = (sd == "teutonic" and loc_state.teutonic_conquered > 0) or (sd == "russian" and loc_state.russian_conquered > 0)
        enemy_conq = (sd == "teutonic" and loc_state.russian_conquered > 0) or (sd == "russian" and loc_state.teutonic_conquered > 0)
        if not (own_terr or own_conq) or enemy_conq:
            raise IllegalAction("not_friendly", f"{cp.to_locale} not Friendly to defender")

    # SMOKE-054 (Round 63 follow-up): Withdraw capacity also respects
    # Castle markers (Castle replaces Fort/Town per T17). The
    # _effective_stronghold lookup above already accounts for Castle
    # markers; reuse `eff` for capacity.
    sh_data = eff
    capacity = int(sh_data.get("capacity", 1))
    # PLAY-26 (4.3.4): optional per-Lord subset -- "Withdraw some or all
    # Lords into its Stronghold there, a number of Lords UP TO Siege
    # Capacity". args.lords names which outside defenders go inside;
    # default = all of them (backward-compatible). The Capacity cap is
    # cumulative across partial Withdraw calls (cp.withdrawn_lords).
    withdrawers = args.get("lords")
    if withdrawers is None:
        withdrawers = list(cp.defender_lords)
    else:
        if not isinstance(withdrawers, list) or not withdrawers:
            raise IllegalAction("bad_arg", "args.lords must be a non-empty list")
        bad = [x for x in withdrawers if x not in cp.defender_lords]
        if bad:
            raise IllegalAction("bad_lords", f"{bad} not among outside defenders {cp.defender_lords}")
    total_inside = len(cp.withdrawn_lords) + len(withdrawers)
    if total_inside > capacity:
        raise IllegalAction("over_capacity",
            f"Stronghold {cp.to_locale} ({stype}) capacity {capacity}; "
            f"{len(cp.withdrawn_lords)} already inside + {len(withdrawers)} withdrawing")

    # Place a siege marker (Besieged the defenders).
    loc2 = state.locales[cp.to_locale]
    if loc2.siege_markers == 0:
        loc2.siege_markers = 1
    # 4.3.4 NOTE: "Withdrawal alone does not mark Lords as Moved/Fought."
    # Lords go inside the Stronghold (Besieged) but are not marked
    # Moved/Fought by the act of Withdrawing.
    for did in withdrawers:
        state.lords[did].in_stronghold = True
    cp.withdrawn_lords = list(cp.withdrawn_lords) + list(withdrawers)
    cp.defender_lords = [d for d in cp.defender_lords if d not in withdrawers]

    # 1.4.1 Legate trigger: if any Withdrawing Lord is Teutonic and the
    # Legate is at the Withdraw Locale, remove the pawn and discard
    # William of Modena.
    if (cp.defender_side == "teutonic"
            and state.legate.william_of_modena_in_play
            and state.legate.location == "locale"
            and state.legate.locale_id == cp.to_locale):
        if "T13" in state.decks.teutonic.capabilities_in_play:
            state.decks.teutonic.capabilities_in_play.remove("T13")
            state.decks.teutonic.discard.append("T13")
        state.legate.william_of_modena_in_play = False
        state.legate.location = "card"
        state.legate.locale_id = None

    # PLAY-26 (4.3.4): if outside defenders remain, the Approach is not yet
    # resolved -- the Inactive side may Withdraw/Avoid more or Stand with
    # the rest. Keep the response window open (the withdrawn Lords are now
    # Besieged inside); do not end the attacker's card yet.
    if cp.defender_lords:
        state.meta.active_player = cp.defender_side
        return (
            {
                "withdrew_into": cp.to_locale,
                "withdrew_lords": list(withdrawers),
                "capacity": capacity,
                "inside_total": len(cp.withdrawn_lords),
                "remaining_defenders": list(cp.defender_lords),
                "awaiting_response": True,
            },
            [],
        )

    state.combat_pending = None
    state.campaign_turn.actions_remaining = 0
    _enter_feed_pay_disband(state)
    return ({"withdrew_into": cp.to_locale, "capacity": capacity,
             "withdrew_lords": list(withdrawers)}, [])


def _parse_concede_round(value: Any, *, who: str) -> int | None:
    """Normalize a Concede declaration (4.4.2) to a Round number (>= 1)
    or None. Accepts None/False (no Concede), True or the side label
    `who` (Round 1), or an explicit int Round."""
    if value is None or value is False:
        return None
    if value is True or value == who:
        return 1
    if isinstance(value, bool):  # defensive; True handled above
        return None
    if isinstance(value, int) and value >= 1:
        return value
    raise IllegalAction(
        "bad_concede",
        f"concede must be true / {who!r} / a Round int >= 1; got {value!r}",
    )


def _merge_concede_decisions(declarations: list[tuple[int, str]]) -> dict[int, str]:
    """Fold (round, side) Concede declarations into one round -> side map.
    Per 4.4.2 the concede order is attacker-then-defender, so an attacker
    Concede wins a same-Round tie."""
    out: dict[int, str] = {}
    for rnd, who in declarations:
        if out.get(rnd) == "attacker":
            continue  # attacker already Concedes this Round; keep it
        out[rnd] = "attacker" if who == "attacker" else "defender"
    return out


def _concede_decisions_from_args(
    args: dict[str, Any], *, attacker_round: int | None = None
) -> dict[int, str]:
    """Build the per-Round Concede map (round -> "attacker"|"defender")
    passed to resolve_battle, merging (with attacker precedence):
      - an attacker's pre-declared Concede Round (e.g. from cmd_march);
      - args.concede ("attacker"|"defender") + optional args.concede_round
        (Round 1 by default) -- single-side sugar; and
      - args.concede_decisions ({round_int: side}) -- an explicit
        per-Round, per-side plan giving full control over both sides and
        all Rounds (4.4.2: either side may Concede at the start of ANY
        Round)."""
    decls: list[tuple[int, str]] = []
    if attacker_round is not None:
        decls.append((attacker_round, "attacker"))
    concede = args.get("concede")
    if concede is not None:
        if concede not in ("attacker", "defender"):
            raise IllegalAction("bad_concede", "concede must be 'attacker' or 'defender'")
        cr = args.get("concede_round", 1)
        if not isinstance(cr, int) or isinstance(cr, bool) or cr < 1:
            raise IllegalAction("bad_concede", "concede_round must be a Round int >= 1")
        decls.append((cr, concede))
    raw = args.get("concede_decisions")
    if raw is not None:
        if not isinstance(raw, dict):
            raise IllegalAction("bad_concede", "concede_decisions must be a {round: side} map")
        for k, v in raw.items():
            try:
                rnd = int(k)
            except (TypeError, ValueError):
                raise IllegalAction(
                    "bad_concede", f"concede_decisions round {k!r} is not an int") from None
            if rnd < 1:
                raise IllegalAction("bad_concede", "concede_decisions rounds must be >= 1")
            if v not in ("attacker", "defender"):
                raise IllegalAction(
                    "bad_concede", f"concede_decisions[{k}] must be 'attacker' or 'defender'")
            decls.append((rnd, v))
    return _merge_concede_decisions(decls)


def _h_stand_battle(
    state: GameState, side: str, args: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Defender chooses to Stand. Triggers full 4.4 Battle resolution."""
    from nevsky.battle import (
        _way_type_between,
        apply_retreat_service_shift,
        resolve_battle,
        transfer_spoils,
    )

    sd = _require_side_player(state, side)
    cp = state.combat_pending
    if cp is None:
        raise IllegalAction("no_combat", "no pending combat")
    if cp.pending_response_by != sd:
        raise IllegalAction("wrong_actor", f"response owed by {cp.pending_response_by}")

    # 4.4.2 Concede the Field: either side may Concede at the start of
    # ANY Round. Merge the attacker's pre-declared Concede (cmd_march ->
    # combat_pending), the defender's args.concede (+ optional
    # concede_round), and any explicit args.concede_decisions plan into a
    # single per-Round map; attacker wins same-Round ties (concede order).
    concede_decisions = _concede_decisions_from_args(
        args, attacker_round=cp.attacker_concede_round)

    # R198: defender's casualty-absorption policy (validated). The
    # attacker's was captured on cmd_march into combat_pending.
    cp.defender_absorption_policy = _validate_absorption_policy(
        args.get("absorption_policy"))
    # Tier 2 holds (Phase 4d): args.holds passes Hold-event modifiers to
    # the battle resolver. Each hold consumed (moved from holds to
    # discard) at the start of resolution. Hold cards expected on this
    # path: T4/R1 Bridge, T5/R2 Marsh, T6/R6 Ambush, T9/R5 Hill,
    # T10 Field Organ, R4 Raven's Rock.
    holds_arg = args.get("holds") or {}
    consumed_holds: list[dict[str, Any]] = []
    if holds_arg:
        from nevsky.events import _consume_battle_holds
        consumed_holds = _consume_battle_holds(state, cp, holds_arg)
    # Q-005: thread per-Lord Array positions and operator decisions
    # through resolve_battle. The cp.attacker_group's first entry is
    # the Active Lord (the one whose Command card triggered the
    # March). args may include "scripted_decisions" (list[dict]) for
    # tests/scripted play; live callers can pass a callback via
    # "decision_callback".
    from nevsky.battle import BattleDecisionContext
    scripted = args.get("scripted_decisions") or []
    decision_ctx = BattleDecisionContext(
        scripted=list(scripted),
        callback=args.get("decision_callback"),
    )
    active_attacker = (
        cp.attacker_group[0] if cp.attacker_group else None
    )
    # Q-006 Relief Sally detection (4.4.1 2E): if the marching attacker
    # side has Besieged Lords at cp.to_locale, those Lords may join the
    # Attack as Sallying Lords without spending Command actions.
    sallying_lords = [
        lid for lid, l in state.lords.items()
        if l.state == "mustered"
        and l.location == cp.to_locale
        and l.side == cp.attacker_side
        and l.in_stronghold
        and state.locales[cp.to_locale].siege_markers > 0
        and lid not in cp.attacker_group
    ]
    # PLAY-14 (Fable audit): 4.4.1 RELIEF SALLY -- "any Besieged Lords
    # MAY join any Attack". Joining is optional, chosen by the
    # Approaching side on cmd_march (cp.sally_join). None = all join
    # (previous behavior, still legal); a list restricts the joiners.
    if cp.sally_join is not None:
        _bad_join = [x for x in cp.sally_join if x not in sallying_lords]
        if _bad_join:
            raise IllegalAction(
                "bad_sally_join",
                f"sally_join names non-eligible Lords: {_bad_join}")
        sallying_lords = [lid for lid in sallying_lords if lid in cp.sally_join]
    siegeworks_for_sally = (
        state.locales[cp.to_locale].siege_markers if sallying_lords else 0
    )
    # If Relief Sally fires, all_attackers includes the Sallying Lords.
    all_attackers = list(cp.attacker_group) + sallying_lords
    # Reuse pre-set positions if cmd_stand_battle was called with them.
    pre_atk_pos = cp.attacker_positions or None
    pre_def_pos = cp.defender_positions or None
    result = resolve_battle(
        state, attacker_side=cp.attacker_side,
        attacker_lords=all_attackers,
        defender_lords=list(cp.defender_lords),
        concede_decisions=concede_decisions or None,
        holds=holds_arg,
        active_attacker=active_attacker,
        decision_ctx=decision_ctx,
        attacker_positions=pre_atk_pos,
        defender_positions=pre_def_pos,
        sallying_lords=sallying_lords or None,
        siegeworks_for_sally=siegeworks_for_sally,
        attacker_absorption_policy=cp.attacker_absorption_policy,
        defender_absorption_policy=cp.defender_absorption_policy,
    )
    if sallying_lords:
        result["relief_sally"] = {
            "sallying_lords": sallying_lords,
            "siegeworks_for_sally": siegeworks_for_sally,
        }
    if consumed_holds:
        result["holds_consumed"] = consumed_holds
    winner = result["winner"]
    loser_lords = result["attacker_lords"] if result["loser"] == cp.attacker_side else result["defender_lords"]
    winner_lords = result["defender_lords"] if winner == cp.defender_side else result["attacker_lords"]

    # SMOKE-003: agent may direct spoils via args.spoils_recipient.
    spoils_target = args.get("spoils_recipient")
    if isinstance(spoils_target, str) and spoils_target in state.lords:
        st = state.lords[spoils_target]
        if (st.side == winner and st.location == cp.to_locale
                and st.state == "mustered"):
            winner_lords = [spoils_target] + [w for w in winner_lords if w != spoils_target]

    aftermath: dict[str, Any] = {"battle": result, "retreats": [], "spoils": [], "removed": []}
    # Q-006 Relief Sally aftermath: if attackers lose AND Sallying
    # Lords joined, those Sallying Lords Withdraw BACK INTO the
    # Stronghold (not Retreat); the Locale's Siege markers are
    # reduced to one (4.4.1 / 4.5.3 2E). Sallying Lords with 0
    # Forces are still removed.
    sallying_loser_set: set[str] = set()
    if sallying_lords and result["loser"] == cp.attacker_side:
        for lid in sallying_lords:
            if lid in state.lords and state.lords[lid].forces:
                # Withdraw back inside (already at the Locale; just
                # mark in_stronghold).
                state.lords[lid].in_stronghold = True
                aftermath.setdefault("sally_withdrew", []).append(lid)
                sallying_loser_set.add(lid)
        # Reduce Siege markers to 1.
        if state.locales[cp.to_locale].siege_markers > 1:
            state.locales[cp.to_locale].siege_markers = 1
            aftermath["sally_raid_siege_to_1"] = True
    # 4.4.3: a losing DEFENDER may Withdraw into that side's Stronghold at
    # the Battle Locale (if it has one) instead of Retreating -- keeping
    # all Assets and becoming Besieged inside. The owning player selects
    # which losers Withdraw via args.withdraw_losers (True = all eligible,
    # or a list of lord_ids). Marching/Sallying Attackers cannot Withdraw
    # this way (handled elsewhere).
    withdraw_into_sh: set[str] = set()
    _wl = args.get("withdraw_losers")
    if _wl and result["loser"] == cp.defender_side:
        _eff_sh = _effective_stronghold(state, cp.to_locale)
        _sloc = load_locales()[cp.to_locale]
        _lst = state.locales[cp.to_locale]
        _own_terr = ((cp.defender_side == "teutonic" and _sloc["territory"] in ("teutonic", "crusader"))
                     or (cp.defender_side == "russian" and _sloc["territory"] == "russian"))
        _own_conq = ((cp.defender_side == "teutonic" and _lst.teutonic_conquered > 0)
                     or (cp.defender_side == "russian" and _lst.russian_conquered > 0))
        _enemy_conq = ((cp.defender_side == "teutonic" and _lst.russian_conquered > 0)
                       or (cp.defender_side == "russian" and _lst.teutonic_conquered > 0))
        if _eff_sh is not None and not _eff_sh.get("no_storm") and (_own_terr or _own_conq) and not _enemy_conq:
            _cap = int(_eff_sh.get("capacity", 1))
            # PLAY-12: a fully-Routed Lord may Withdraw too (his
            # routed pile then rolls 4.4.4 Losses at "withdrew").
            _cands = [lid for lid in loser_lords
                      if lid in state.lords
                      and (state.lords[lid].forces or state.lords[lid].routed_units)]
            if _wl is True:
                _chosen = list(_cands)
            elif isinstance(_wl, list):
                _chosen = [lid for lid in _cands if lid in _wl]
            else:
                raise IllegalAction("bad_withdraw_losers",
                                    "withdraw_losers must be true or a list of lord_ids")
            if len(_chosen) > _cap:
                raise IllegalAction(
                    "over_capacity",
                    f"{cp.to_locale} Stronghold capacity {_cap}; {len(_chosen)} Lords cannot all Withdraw")
            withdraw_into_sh = set(_chosen)
        elif isinstance(_wl, list) and _wl:
            raise IllegalAction("no_withdraw_stronghold",
                                f"no Friendly Stronghold at {cp.to_locale} to Withdraw into (4.4.3)")
    # PLAY-12 (Fable audit): 4.4.3 -- "All losing Lords must either
    # Retreat ... OR Withdraw ... OR Be permanently removed. The owning
    # player chooses each Lord's fate." A fully-Routed Lord (zero
    # unrouted Forces but a live routed pile -- the normal way to lose a
    # Battle!) is NOT auto-removed: he may Retreat or Withdraw and then
    # rolls 4.4.4 Losses per Routed unit. Only a Lord with no units at
    # all, or one whose owner chooses removal (args.remove_losers), is
    # removed outright. 4.4.3 also orders LOSSES before SPOILS, so
    # "Removed (by Losses)" Lords transfer all Assets except Ships.
    _rl = args.get("remove_losers")
    if _rl is not None and not isinstance(_rl, list):
        raise IllegalAction("bad_remove_losers",
                            "remove_losers must be a list of lord_ids")
    remove_losers_set = set(_rl or [])
    _bad_rm = [x for x in remove_losers_set if x not in loser_lords]
    if _bad_rm:
        raise IllegalAction("bad_remove_losers",
                            f"remove_losers names non-losing Lords: {_bad_rm}")
    # PLAY-29 (4.4.3): "Retreat to a SINGLE adjacent Locale ... The owning
    # player chooses." args.retreat_to = {lord_id: locale_id} names a
    # chosen Retreat destination per losing Lord (Defenders only; Marching
    # Attackers must return to from_locale). Unspecified Lords auto-pick
    # the first legal destination (backward-compatible).
    _retreat_to = args.get("retreat_to") or {}
    if not isinstance(_retreat_to, dict):
        raise IllegalAction("bad_retreat_to",
                            "retreat_to must be a {lord_id: locale_id} map")
    _bad_rt = [x for x in _retreat_to if x not in loser_lords]
    if _bad_rt:
        raise IllegalAction("bad_retreat_to",
                            f"retreat_to names non-losing Lords: {_bad_rt}")
    for lid in list(loser_lords):
        if lid not in state.lords:
            continue
        lord = state.lords[lid]
        # Q-006: skip Sallying Lords already handled by Withdraw path.
        if lid in sallying_loser_set:
            continue
        if (not lord.forces and not lord.routed_units) or lid in remove_losers_set:
            spoil = transfer_spoils(state, lid, winner_lords, "all_except_ships")
            aftermath["spoils"].append(spoil)
            from nevsky.actions import _remove_lord_permanently as _rem
            r = apply_ransom(state, lid, winner, cp.to_locale)
            if r.get("ransom"):
                aftermath.setdefault("ransom", []).append(r)
            _rem(state, lid, load_lords()[lid])
            aftermath["removed"].append(lid)
            continue
        if lid in withdraw_into_sh:
            # 4.4.3 Withdraw: keep all Assets (no Spoils), no Service shift,
            # Besieged inside the Stronghold at the Battle Locale.
            lord.in_stronghold = True
            if state.locales[cp.to_locale].siege_markers == 0:
                state.locales[cp.to_locale].siege_markers = 1
            # 4.4.4 Losses: a Lord who Withdrew is in the "any other Lord
            # (Withdrew, Conceded+Retreated, ...)" category and rolls 1d6 per
            # Routed unit at unmodified Protection range ("withdrew"
            # loss_state). This Battle-aftermath Withdraw path previously
            # skipped it (the Retreat and failed-Sally Withdraw paths already
            # roll), stranding the routed_units pile: the units were neither
            # permanently lost per the rule nor restored, and a later combat
            # win would hand them back for free via the winner-restore.
            from nevsky.battle import apply_losses_rolls
            if lord.routed_units:
                apply_losses_rolls(state, lid, "withdrew")
            # PLAY-12: 4.4.4 "Permanently remove ... any Lord who loses
            # all his Forces"; 4.4.3 Spoils "Lords who were Removed (by
            # Losses ...) transfer all their Assets except Ships".
            if not lord.forces:
                spoil = transfer_spoils(state, lid, winner_lords, "all_except_ships")
                aftermath["spoils"].append(spoil)
                from nevsky.actions import _remove_lord_permanently as _rem
                r = apply_ransom(state, lid, winner, cp.to_locale)
                if r.get("ransom"):
                    aftermath.setdefault("ransom", []).append(r)
                _rem(state, lid, load_lords()[lid])
                aftermath["removed"].append(lid)
                continue
            aftermath.setdefault("withdrew", []).append(lid)
            continue
        # Default Phase 3b behavior: loser Retreats to from_locale (attackers)
        # or stays at to_locale (defenders auto-retreat to a random friendly
        # neighbor). For attackers, retreat back to from_locale. For
        # defenders, retreat to an adjacent neighbor with no enemy Lord.
        #
        # SMOKE-069 (Round 74): capture the actual retreat Way's type
        # so the Conceded+Retreated Spoils path can compute Unladen
        # Transport correctly along that Way (matters for parallel
        # Ways pairs, e.g. dorpat<->odenpah trackway + waterway).
        retreat_way_type_actual: str | None = None
        if result["loser"] == cp.attacker_side:
            target = cp.from_locale
            # Attackers retreat back via the same Way they approached.
            retreat_way_type_actual = cp.way_type
        else:
            # AUDIT-005 / PLAY-29 (4.4.3 2E): Defenders Retreat to a single
            # adjacent Locale with no UNBESIEGED enemy Lords or Strongholds,
            # and "may not Retreat along any part of the Way that Attackers
            # used to Approach" (exclude from_locale + way_type; parallel
            # Ways of another type remain). The owning player CHOOSES the
            # destination via args.retreat_to; unspecified -> first legal.
            target = None
            _dests = _legal_retreat_dests(
                state, cp.to_locale, lord.side,
                exclude=(cp.from_locale, cp.way_type))
            if lid in _retreat_to:
                _want = _retreat_to[lid]
                _match = [(d, wt) for d, wt in _dests if d == _want]
                if not _match:
                    raise IllegalAction(
                        "bad_retreat_dest",
                        f"{_want} is not a legal Retreat destination for {lid} "
                        f"(4.4.3); legal: {sorted({d for d, _ in _dests})}")
                target, retreat_way_type_actual = _match[0]
            elif _dests:
                target, retreat_way_type_actual = _dests[0]
            if target is None:
                # No retreat possible -> permanently removed.
                spoil = transfer_spoils(state, lid, winner_lords, "all_except_ships")
                aftermath["spoils"].append(spoil)
                from nevsky.actions import _remove_lord_permanently as _rem
                # SMOKE-101 (Round 131): the zero-forces removal branch
                # above calls apply_ransom, but this no-retreat-path
                # branch previously did not — a Ransom-capable winner
                # was paid in one removal case and not the other.
                # Same audit pattern as SMOKE-098/099 (mirror gap).
                r = apply_ransom(state, lid, winner, cp.to_locale)
                if r.get("ransom"):
                    aftermath.setdefault("ransom", []).append(r)
                _rem(state, lid, load_lords()[lid])
                aftermath["removed"].append(lid)
                continue
        lord.location = target
        # SMOKE-036: clear in_stronghold on Retreat movement.
        lord.in_stronghold = False
        # SMOKE-091 (Round 99): trade-route auto-flip on Retreat entry.
        _flip_trade_route_if_uncontested(state, target, lord.side)
        shift = apply_retreat_service_shift(state, lid)
        # AUDIT-004 (4.4.3 2E): Conceded+Retreated losers transfer only
        # Loot and excess Provender beyond Unladen along the Retreat
        # Way. Retreated-without-conceding losers transfer all Assets
        # except Ships.
        conceded_side = result.get("conceded")
        if conceded_side is not None:
            # conceded_side is "attacker" or "defender" relative to combat.
            this_lord_conceded = (
                (conceded_side == "attacker" and result["loser"] == cp.attacker_side)
                or (conceded_side == "defender" and result["loser"] == cp.defender_side)
            )
        else:
            this_lord_conceded = False
        # SMOKE-093 (Round 113) + PLAY-12 reorder (Fable audit): 4.4.3
        # sequences LOSSES before SPOILS, so roll 4.4.4 Losses first --
        # a Lord "Removed (by Losses)" then transfers ALL Assets except
        # Ships regardless of Concede.
        from nevsky.battle import apply_losses_rolls
        loss_state = "conceded_then_retreated" if this_lord_conceded else "retreated_no_concede"
        if lord.routed_units:
            apply_losses_rolls(state, lid, loss_state)
        aftermath["retreats"].append({"lord": lid, "to": target, "service_shift": shift})
        if not lord.forces:
            # PLAY-12: 4.4.4 "Permanently remove ... any Lord who loses
            # all his Forces in Battle"; Spoils per the Removed bullet.
            spoil = transfer_spoils(state, lid, winner_lords, "all_except_ships")
            aftermath["spoils"].append(spoil)
            from nevsky.actions import _remove_lord_permanently as _rem
            r = apply_ransom(state, lid, winner, cp.to_locale)
            if r.get("ransom"):
                aftermath.setdefault("ransom", []).append(r)
            _rem(state, lid, load_lords()[lid])
            aftermath["removed"].append(lid)
            continue
        if this_lord_conceded:
            # The Lord just moved to `target`. SMOKE-069 (Round 74):
            # use the captured retreat_way_type_actual (set above when
            # picking the destination) rather than _way_type_between,
            # which returns the FIRST Way and can be wrong for the
            # parallel-Ways pair (dorpat<->odenpah).
            way_type = retreat_way_type_actual
            if way_type is None:  # defensive fallback (should not happen)
                way_type = _way_type_between(cp.to_locale, target)
            spoil = transfer_spoils(
                state, lid, winner_lords, "loot_and_excess",
                retreat_way_type=way_type,
            )
        else:
            spoil = transfer_spoils(state, lid, winner_lords, "all_except_ships")
        aftermath["spoils"].append(spoil)

    # SMOKE-084 (Round 88): per AoW Reference 1.4.1 Legate —
    # "Whenever a Teutonic Lord ... Retreats ... remove the pawn and
    # discard the William of Modena card." The Battle Aftermath
    # Retreat path was missing this trigger (Avoid Battle / Withdraw
    # already wired in via SMOKE-043). If any Teutonic loser
    # retreated (or was removed) AND the Legate is at cp.to_locale,
    # remove the pawn and discard William of Modena.
    if (state.legate.william_of_modena_in_play
            and state.legate.location == "locale"
            and state.legate.locale_id == cp.to_locale):
        # Check whether any Teutonic Lord was in loser_lords (they
        # retreated or were removed from cp.to_locale).
        teu_lost = any(
            lid in state.lords and state.lords[lid].side == "teutonic"
            for lid in loser_lords
        )
        if teu_lost:
            if "T13" in state.decks.teutonic.capabilities_in_play:
                state.decks.teutonic.capabilities_in_play.remove("T13")
                state.decks.teutonic.discard.append("T13")
            state.legate.william_of_modena_in_play = False
            state.legate.location = "card"
            state.legate.locale_id = None
            aftermath["legate_removed"] = True

    # PLAY-8 (Fable audit): 4.3.5 "If all Besieging Lords later depart,
    # remove all Siege markers" / 4.4.5 "If the combat ... ended a Siege
    # ... remove Siege ... markers". PLAY-3 covered the Avoid / March /
    # Sail departure paths; the battle-RETREAT departure path (losing
    # besiegers retreat alive after a Relief Battle) was missed, leaving
    # the relieved Lord Besieged-by-nobody and palette-locked to
    # Sally/Pass.
    from nevsky.actions import _lift_siege_if_no_besiegers as _lift_after_battle
    if _lift_after_battle(state, cp.to_locale):
        aftermath["siege_lifted"] = True

    # PLAY-9 (Fable audit): 4.3.5 Besiege -- "WHENEVER a side has Lord(s)
    # in a Locale outside a currently Unbesieged enemy Stronghold and no
    # enemy Lords are present outside the Stronghold, mark the Locale
    # with one Siege marker" / 4.4.5 "If the combat created ... a Siege,
    # place ... markers". Winning the field Battle outside an enemy
    # Stronghold begins the Siege immediately; pre-fix the winner had to
    # waste a later card marching out and back in.
    _loc_after = state.locales[cp.to_locale]
    if (_has_enemy_stronghold_at(state, cp.to_locale, winner)
            and _loc_after.siege_markers == 0):
        _enemies_outside = [
            L for L in state.lords.values()
            if L.state == "mustered" and L.location == cp.to_locale
            and L.side != winner and not L.in_stronghold
        ]
        _winners_outside = [
            wlid for wlid in winner_lords
            if wlid in state.lords
            and state.lords[wlid].location == cp.to_locale
            and not state.lords[wlid].in_stronghold
        ]
        if not _enemies_outside and _winners_outside:
            _loc_after.siege_markers = 1
            aftermath["placed_siege"] = True

    # PLAY-13 (Fable audit): 4.4.5 Conquest -- "If Battle in a Trade
    # Route causes it to change hands, adjust Conquered status and VP
    # accordingly (4.3.6, 5.1.1)". The flip previously fired only on
    # movement ENTRY (march/sail/avoid/retreat), so the winner standing
    # on the Trade Route gained nothing until leaving and re-entering.
    _flip_trade_route_if_uncontested(state, cp.to_locale, winner)

    # PLAY-11 (Fable audit): 4.4.4 Losses -- "BOTH SIDES determine the
    # fate of their Routed units." Winners are in the "all other Lords"
    # category (they neither Retreated-without-Concede nor Stormed):
    # each Routed unit rolls at its unmodified Protection range. The
    # previous restore-all rested on a misquote ("the Winner's Routed
    # units automatically return ... only the Loser rolls Losses",
    # SMOKE-093/098/099 comments) that appears nowhere in the rulebook
    # or the reference .txt. A winner Lord who loses every unit is
    # permanently removed (4.4.4 "any Lord who loses all his Forces in
    # Battle or Storm").
    from nevsky.battle import apply_losses_rolls as _alr_w
    for wlid in list(winner_lords):
        if wlid not in state.lords:
            continue
        if state.lords[wlid].routed_units:
            _alr_w(state, wlid, "stood_field")
        if not state.lords[wlid].forces:
            from nevsky.actions import _remove_lord_permanently as _rem_w
            _rem_w(state, wlid, load_lords()[wlid])
            aftermath.setdefault("winner_removed_by_losses", []).append(wlid)

    # Mark all participants MOVED_FOUGHT. PLAY-14 (Fable audit): 4.4.5
    # "Mark all Attacking and Defending Lords" -- Sallying joiners are
    # Attacking Lords and were previously skipped (they fought but then
    # dodged Feed, 4.8.1).
    for lid in cp.attacker_group + cp.defender_lords + sallying_lords:
        if lid in state.lords:
            state.lords[lid].moved_fought = True

    state.combat_pending = None
    state.campaign_turn.actions_remaining = 0
    _enter_feed_pay_disband(state)
    return ({"winner": winner, "loser": result["loser"], **aftermath}, [])


# ---------------------------------------------------------------------------
# Register Phase 3b handlers
# ---------------------------------------------------------------------------


HANDLERS_PHASE_3B = {
    "cmd_march": _h_cmd_march,
    "avoid_battle": _h_avoid_battle,
    "withdraw": _h_withdraw,
    "stand_battle": _h_stand_battle,
    # SMOKE-115 (Round 180): T6/R6 Ambush block-Avoid response actions
    "play_ambush_block": _h_play_ambush_block,
    "decline_ambush_block": _h_decline_ambush_block,
}

HANDLERS.update(HANDLERS_PHASE_3B)

# ---------------------------------------------------------------------------
# 4.5 Siege / Storm / Sally (Phase 3c)
# ---------------------------------------------------------------------------


def _stronghold_at(locale_id: str) -> dict[str, Any] | None:
    """Return the Strongholds-table entry for the locale's type, or None
    if the locale has no Stronghold for Siege/Storm purposes (region,
    town, commandery)."""
    from nevsky.static_data import load_locales, load_strongholds

    static = load_locales()[locale_id]
    return load_strongholds().get(static["type"])


def _effective_stronghold(state: GameState, locale_id: str) -> dict[str, Any] | None:
    """SMOKE-054 (Round 63) + SMOKE-065 (Round 70): Stronghold entry
    accounting for dynamic Castle markers. T17 Stonemasons Tip: "The
    Castle marker REPLACES the Fort or Town at its Locale." So a
    Locale with teutonic_castle or russian_castle uses Castle stats
    (capacity 2, walls 1-4, garrison 1 MaA + 1 Knight, vp 1) regardless
    of its static type — including Towns, whose base type "town" has
    no entry in strongholds.json.

    SMOKE-065 (Round 70): the prior `if base is None: return None`
    short-circuit silently broke Castle-overlay-on-Town. The function
    now returns the Castle entry whenever any Castle marker is present,
    falling back to locale territory for the 'side' field when the
    base type has no Stronghold (Town locales).

    The 'side' field continues to track the static territory's
    defender (consistent with the SMOKE-054 design; Conquered markers
    + Castle flip on Conquest jointly track ownership transitions).
    """
    from nevsky.static_data import load_strongholds
    base = _stronghold_at(locale_id)
    loc = state.locales.get(locale_id)
    has_overlay = bool(loc and (loc.teutonic_castle or loc.russian_castle))
    if not has_overlay:
        return base
    castle = load_strongholds().get("castle")
    if castle is None:
        return base
    out = dict(castle)
    if base is not None:
        # Preserve existing SMOKE-054 semantics on Castle-on-Stronghold
        # overlays (defender side = base territory's defender).
        out["side"] = base.get("side", castle.get("side"))
    else:
        # Castle-on-non-Stronghold base (Town): there is no underlying
        # Stronghold defender, so the marker color IS the defender.
        if loc.teutonic_castle:
            out["side"] = "teutonic"
        else:
            out["side"] = "russian"
    return out


def _effective_stronghold_owner(state: GameState, locale_id: str) -> "Side | None":
    """PLAY-25 (Fable audit): the Stronghold's CURRENT owner -- the side
    that would defend a Siege/Storm there -- accounting for Conquered
    markers and Castle-marker color, not just the static territory.

    strongholds.json 'side' is static by type (fort/city/novgorod ->
    russian; commandery/castle/bishopric -> teutonic). Once a
    Stronghold is Conquered (1.3.1), it is the conqueror's: a Teuton
    Withdrawn inside Teuton-Conquered Izborsk (SMOKE-130) defends any
    Russian re-Siege; pre-fix the engine treated the RUSSIANS as the
    defenders -- rolling Surrender with an enemy Lord Besieged inside,
    Storming garrison-only (the inside Lord neither Arrayed nor was
    Sacked), and offering cmd_siege/cmd_storm to the wrong side.
    """
    sh = _effective_stronghold(state, locale_id)
    if sh is None:
        return None
    loc = state.locales.get(locale_id)
    if loc is None:
        return sh.get("side")
    # Castle marker color is authoritative (flips on Conquest, 4.5.1).
    if loc.teutonic_castle:
        return "teutonic"
    if loc.russian_castle:
        return "russian"
    base_side = sh.get("side")
    if base_side == "russian" and loc.teutonic_conquered > 0:
        return "teutonic"
    if base_side == "teutonic" and loc.russian_conquered > 0:
        return "russian"
    return base_side


def _besieging_lords_at(state: GameState, locale_id: str, side: Side) -> list[str]:
    """Lords of `side` at `locale_id` who are NOT inside the Stronghold."""
    return [
        lid for lid, l in state.lords.items()
        if l.state == "mustered" and l.location == locale_id and l.side == side
        and not l.in_stronghold
    ]


def _besieged_lords_at(state: GameState, locale_id: str, side: Side) -> list[str]:
    """Lords of `side` Besieged INSIDE a Stronghold at `locale_id`."""
    return [
        lid for lid, l in state.lords.items()
        if l.state == "mustered" and l.location == locale_id and l.side == side
        and l.in_stronghold
    ]


def _refresh_vp_markers(state: GameState) -> None:
    """SMOKE-022 (Round 36) local wrapper to avoid scenarios.py import cycle."""
    from nevsky.scenarios import refresh_victory_markers
    refresh_victory_markers(state)


def _apply_conquest_or_liberation(
    state: GameState, locale_id: str, attacker_side: Side, sh_vp: int,
) -> dict[str, Any]:
    """SMOKE-021 (Round 35): place Conquered marker on Storm/Surrender
    victory, accounting for native ownership.

    If the attacker is conquering an enemy-territory Locale:
        set attacker's conquered marker += sh_vp; add attacker VP.
    If the attacker is liberating own-territory (enemy marker present):
        clear the enemy marker; subtract enemy VP. The attacker does
        NOT gain a new conquered marker (you can't conquer your own
        territory) and does NOT gain VP (the VP swing comes from the
        enemy LOSING their marker).

    Russian-territory locales: native side = russian.
    Teutonic / Crusader-territory locales: native side = teutonic.
    """
    static = load_locales()[locale_id]
    loc = state.locales[locale_id]
    native_side: Side = "russian" if static["territory"] == "russian" else "teutonic"
    # SMOKE-040 (Round 52): Castle markers flip on Conquest per T17
    # Tips ("Castles are permanent. They flip when Conquered."). Each
    # Castle marker is worth 1 VP to its color side (scenarios.py
    # _compute_vp), so a flip swings VP by 2 (-1 old, +1 new). We
    # detect the existing Castle marker color and flip it iff the
    # attacker is the opposite color.
    castle_flip: dict[str, Any] | None = None
    if attacker_side == "teutonic" and loc.russian_castle:
        loc.russian_castle = False
        loc.teutonic_castle = True
        state.calendar.russian_vp -= 1.0
        state.calendar.teutonic_vp += 1.0
        castle_flip = {"from": "russian", "to": "teutonic"}
    elif attacker_side == "russian" and loc.teutonic_castle:
        loc.teutonic_castle = False
        loc.russian_castle = True
        state.calendar.teutonic_vp -= 1.0
        state.calendar.russian_vp += 1.0
        castle_flip = {"from": "teutonic", "to": "russian"}
    if attacker_side != native_side:
        # Conquest: attacker is conquering enemy-native locale.
        # SMOKE-045 (Round 57): cap at sh_vp instead of cumulative +=.
        # A locale is either fully Conquered (sh_vp markers) or not;
        # re-Conquest by the same side should be a no-op for the marker
        # but is reachable only via contrived flows (siege state
        # gating normally prevents same-side re-Storm). Defensive: emit
        # only the delta VP so calendar.<side>_vp tracks correctly.
        if attacker_side == "teutonic":
            delta = max(0, sh_vp - loc.teutonic_conquered)
            loc.teutonic_conquered = max(loc.teutonic_conquered, sh_vp)
            state.calendar.teutonic_vp += float(delta)
        else:
            delta = max(0, sh_vp - loc.russian_conquered)
            loc.russian_conquered = max(loc.russian_conquered, sh_vp)
            state.calendar.russian_vp += float(delta)
        _refresh_vp_markers(state)
        out = {"type": "conquest", "side": attacker_side, "vp": delta}
        if castle_flip:
            out["castle_flip"] = castle_flip
        return out
    else:
        # Liberation: attacker reclaims own-native locale; clear enemy marker.
        if attacker_side == "teutonic":
            prev = loc.russian_conquered
            loc.russian_conquered = 0
            state.calendar.russian_vp -= float(prev)
            _refresh_vp_markers(state)
            out = {"type": "liberation", "side": attacker_side, "cleared_vp": prev}
        else:
            prev = loc.teutonic_conquered
            loc.teutonic_conquered = 0
            state.calendar.teutonic_vp -= float(prev)
            _refresh_vp_markers(state)
            out = {"type": "liberation", "side": attacker_side, "cleared_vp": prev}
        if castle_flip:
            out["castle_flip"] = castle_flip
        return out


def _h_cmd_siege(
    state: GameState, side: str, args: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """4.5.1 Siege. Entire card.

    Procedure:
      1. Surrender check: if no Besieged Lords inside, the besieging
         side may roll 1d6; if roll <= siege_markers, the Stronghold is
         Conquered (place Conquered marker, adjust VP; flip Castle
         marker via Stonemasons -- ENFORCED in Phase 4a (cmd_stonemasons
         action). Remove all Veche Coin if Novgorod -- 1.3.3 ENFORCED.
         No Spoils awarded on Surrender vs Sack -- ENFORCED).
      2. Siegeworks check: if besieging Lords at the locale >=
         Stronghold Capacity, add 1 Siege marker (max 4).
    """
    from nevsky.rng import roll_d6

    sd = _require_side_player(state, side)
    lord_id = args.get("lord_id", state.campaign_turn.active_lord)
    if not isinstance(lord_id, str):
        raise IllegalAction("missing_arg", "args.lord_id required")
    _require_active_lord_command(state, sd, lord_id)
    _require_full_command_card(state, lord_id, "Siege (4.5.1)")  # entire_card (R203)
    lord = state.lords[lord_id]
    if _is_besieged(state, lord_id):
        raise IllegalAction("besieged", "Active Lord is Besieged; use sally/pass")
    locale_id = lord.location
    if locale_id is None:
        raise IllegalAction("no_location", "Lord has no location")
    sh = _effective_stronghold(state, locale_id)
    if sh is None:
        raise IllegalAction("no_stronghold", f"{locale_id} has no Stronghold for Siege/Storm")
    if state.locales[locale_id].siege_markers == 0:
        raise IllegalAction("no_siege", f"no siege at {locale_id}; March in to begin a Siege")

    # Sieging side is `sd`; defending side is the Stronghold's CURRENT
    # owner (PLAY-25: Conquered markers / Castle color, not static
    # territory).
    defending_side: Side = _effective_stronghold_owner(state, locale_id) or sh["side"]
    if defending_side == sd:
        raise IllegalAction(
            "own_stronghold",
            f"{locale_id} Stronghold is currently {sd}-owned; cannot Siege it")
    # Phase 3c: Besieged Lords are own-side Lords at the locale who match
    # the Stronghold's owning side (the defenders inside).
    besieged = _besieged_lords_at(state, locale_id, defending_side)

    # Mark all Lords at the Locale MOVED_FOUGHT (4.5.1 marking rule).
    for _lid, l in state.lords.items():
        if l.location == locale_id:
            l.moved_fought = True

    surrender_result: dict[str, Any] | None = None
    dice: list[dict[str, Any]] = []
    surrendered = False
    if not besieged and args.get("decline_surrender"):
        # PLAY-7 (Fable audit): 4.5.1 "the Besieging side MAY roll for
        # Surrender ... If the Stronghold did not Surrender (including
        # because the Besieger declined to roll)" -- declining is a legal
        # choice; Siegeworks still applies below.
        surrender_result = {"conquered": False, "declined": True}
    elif not besieged:
        roll = roll_d6(state)
        sm = state.locales[locale_id].siege_markers
        success = roll <= sm
        dice.append({"surrender_roll": roll, "vs_siege_markers": sm, "success": success})
        if success:
            # Conquered. Place Conquered marker per 1.3.1 and adjust VP.
            # SMOKE-021 (Round 35): use _apply_conquest_or_liberation so
            # the marker placement correctly distinguishes conquest from
            # liberation of native territory.
            change = _apply_conquest_or_liberation(state, locale_id, sd, sh["vp"])
            # Novgorod special: remove all Veche Coin (1.3.3) -- not Sacked,
            # so Coin is removed (not transferred as spoils).
            if locale_id == "novgorod":
                lost_coin = state.veche.coin
                state.veche.coin = 0
                surrender_result = {"conquered": True, "veche_coin_removed": lost_coin, "change": change}
            else:
                surrender_result = {"conquered": True, "change": change}
            # PLAY-7 (Fable audit): 4.5.1 Surrender -- "Remove Siege
            # markers." The Siege is over; the Stronghold is Conquered.
            # Pre-fix the markers persisted (and Siegeworks below even
            # ADDED one), leaving the new owner's own city a permanent
            # "Siege Locale" (never Friendly; blocked Muster/Forage;
            # cmd_siege/cmd_storm offered against their own Stronghold).
            state.locales[locale_id].siege_markers = 0
            surrendered = True
        else:
            surrender_result = {"conquered": False}

    # Siegeworks check: add siege marker if besiegers >= Capacity.
    # PLAY-7 (Fable audit): 4.5.1 SIEGEWORKS applies only "If the
    # Stronghold did not Surrender (including because the Besieger
    # declined to roll)".
    siege_added = False
    besiegers = [
        lid for lid in _besieging_lords_at(state, locale_id, sd)
        if lid not in besieged
    ]
    # SMOKE-054 (R63): sh is from _effective_stronghold; capacity reflects Castle if marker present.
    if not surrendered and len(besiegers) >= sh["capacity"] and state.locales[locale_id].siege_markers < 4:
        state.locales[locale_id].siege_markers += 1
        siege_added = True

    # Siege ends the card.
    state.campaign_turn.actions_remaining = 0
    _enter_feed_pay_disband(state)
    return ({"locale": locale_id, "surrender": surrender_result, "siege_added": siege_added,
             "siege_markers": state.locales[locale_id].siege_markers}, dice)


def _h_cmd_storm(
    state: GameState, side: str, args: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """4.5.2 Storm. Entire card. Conduct Attack per Storm rules.

    On defender Sack (defender loses):
      - All Besieged Lords permanently removed (1.5.1).
      - Attackers Conquer Stronghold; place/remove Conquered markers.
      - Adjust VP (5.1.1).
      - Remove all siege markers.
      - Award Stronghold spoils (loot/provender/coin = VP each).
      - If Novgorod: all Veche Coin to attackers as Spoils (4.5.2 + 1.3.3).
    On attacker loss: Storm ends; siege continues; no Spoils.
    """
    from nevsky.battle import resolve_storm

    sd = _require_side_player(state, side)
    lord_id = args.get("lord_id", state.campaign_turn.active_lord)
    if not isinstance(lord_id, str):
        raise IllegalAction("missing_arg", "args.lord_id required")
    _require_active_lord_command(state, sd, lord_id)
    # Q-010 (adjudicated 2026-07-06): rulebook-literal. 4.2.1 lists only
    # Siege/Sail/Tax as entire-card; 4.5.2 says Storm uses "a Command action".
    # D-R203 narrowed to Siege/Sail/Tax -- Storm costs one action, no pristine
    # gate (4.4.5 Recovery still ends the card once the Attack resolves).
    lord = state.lords[lord_id]
    if _is_besieged(state, lord_id):
        raise IllegalAction("besieged", "Active Lord is Besieged; use sally/pass")
    locale_id = lord.location
    if locale_id is None:
        raise IllegalAction("no_location", "Lord has no location")
    sh = _effective_stronghold(state, locale_id)
    if sh is None:
        raise IllegalAction("no_stronghold", f"{locale_id} has no Stronghold")
    if sh.get("no_storm"):
        raise IllegalAction("no_storm", f"{locale_id} cannot be Stormed (e.g., Trade Route)")
    if state.locales[locale_id].siege_markers == 0:
        raise IllegalAction("no_siege", f"no siege at {locale_id}")

    defending_side: Side = _effective_stronghold_owner(state, locale_id) or sh["side"]
    # PLAY-25: dynamic ownership -- see _effective_stronghold_owner.
    if defending_side == sd:
        raise IllegalAction(
            "own_stronghold",
            f"{locale_id} Stronghold is currently {sd}-owned; cannot Storm it")
    besieged = _besieged_lords_at(state, locale_id, defending_side)
    attackers = [
        lid for lid in _besieging_lords_at(state, locale_id, sd)
        if lid not in besieged
    ]
    if not attackers:
        raise IllegalAction("no_attackers", "no besieging Lords at this Stronghold")

    # Mark all Lords at Locale MOVED_FOUGHT (4.5.2 marking).
    for _lid, l in state.lords.items():
        if l.location == locale_id:
            l.moved_fought = True

    walls_max = sh["walls_max"]
    if state.locales[locale_id].walls_plus_one:
        walls_max += 1  # Stone Kremlin (R18): Walls +1 (4.5.2)
    # Follow-up B (Q-007 candidate): operator decisions for Storm
    # Reposition flow through a BattleDecisionContext (Round 2+ swap
    # Front and Reserve Lord). Tests can pin choices via
    # args.scripted_decisions; live play uses args.decision_callback.
    from nevsky.battle import BattleDecisionContext
    storm_ctx = BattleDecisionContext(
        scripted=list(args.get("scripted_decisions") or []),
        callback=args.get("decision_callback"),
    )
    # 4.5.2 Storm Concede (attacker only): args.concede = true/'attacker'
    # or a Round int at which the attacker Concedes the Storm.
    storm_concede_round = _parse_concede_round(args.get("concede"), who="attacker")
    # T10 Field Organ in Storm (playable on Attack OR Defense): consume the
    # Teutonic hold and pass the target Lord (Knights+Sergeants Melee +1,
    # Round 1). field_organ_lord must be a Storm participant.
    storm_holds: dict[str, Any] = {}
    fo_lord = args.get("field_organ_lord")
    if fo_lord:
        if (not isinstance(fo_lord, str) or fo_lord not in (attackers + besieged)
                or state.lords[fo_lord].side != "teutonic"):
            raise IllegalAction(
                "bad_field_organ",
                "field_organ_lord must be a Teutonic Storm participant (T10)")
        cid = (args.get("holds") or {}).get("field_organ") or "T10"
        if cid not in state.decks.teutonic.holds:
            raise IllegalAction("not_in_holds", f"{cid} not in Teutonic holds")
        state.decks.teutonic.holds.remove(cid)
        state.decks.teutonic.discard.append(cid)
        storm_holds["field_organ_lord"] = fo_lord
    result = resolve_storm(
        state, attacker_side=sd,
        attacker_lords=attackers,
        defender_lords=besieged,
        locale_id=locale_id,
        walls_max=walls_max,
        siege_markers=state.locales[locale_id].siege_markers,
        garrison=dict(sh["garrison"]),
        decision_ctx=storm_ctx,
        attacker_concede_round=storm_concede_round,
        holds=storm_holds or None,
    )

    aftermath: dict[str, Any] = {"battle": result}
    if result["winner"] == "attacker":
        # Sack: permanently remove Besieged Lords.
        from nevsky.actions import _remove_lord_permanently as _rem
        from nevsky.static_data import load_lords
        for lid in list(besieged):
            spoils_from_lord = {k: state.lords[lid].assets.get(k, 0) for k in ("coin", "provender", "loot", "boat", "cart", "sled") if state.lords[lid].assets.get(k, 0) > 0}
            if attackers:
                # SMOKE-032: per-type 8 cap (1.7.3); excess vanishes.
                from nevsky.battle import _award_assets_capped
                award = _award_assets_capped(state, attackers[0], spoils_from_lord)
                spoils_from_lord = dict(award["added"])
                # Track lost-to-cap on aftermath for transparency.
                if award["lost_to_cap"]:
                    aftermath.setdefault("storm_spoils_lost_to_cap", []).append({
                        "from_lord": lid, "lost": award["lost_to_cap"],
                    })
            state.lords[lid].assets.clear()
            r = apply_ransom(state, lid, sd, locale_id)
            if r.get("ransom"):
                aftermath.setdefault("ransom", []).append(r)
            _rem(state, lid, load_lords()[lid])
        aftermath["besieged_removed"] = list(besieged)
        # Conquer/Liberate Stronghold per SMOKE-021 (Round 35).
        aftermath["conquest_change"] = _apply_conquest_or_liberation(
            state, locale_id, sd, sh["vp"]
        )
        # Remove siege markers.
        state.locales[locale_id].siege_markers = 0
        # R18: Walls +1 marker removed if Sacked.
        state.locales[locale_id].walls_plus_one = False
        # Spoils: loot/provender/coin = VP each, awarded to attacker[0].
        # SMOKE-003: route Spoils to optional args.spoils_recipient
        # (must be among attackers); else default to attackers[0].
        spoils_target = args.get("spoils_recipient")
        recipient = attackers[0] if attackers else None
        if isinstance(spoils_target, str) and spoils_target in attackers:
            recipient = spoils_target
        spoils = sh.get("spoils") or {}
        if recipient and spoils:
            w = state.lords[recipient]
            for k, v in spoils.items():
                w.assets[k] = min(8, w.assets.get(k, 0) + v)  # type: ignore[index]
        aftermath["stronghold_spoils"] = spoils
        aftermath["spoils_recipient"] = recipient
        # Novgorod Conquered (Sacked): mark the Veche state (1.3.3).
        if locale_id == "novgorod":
            state.veche.novgorod_conquered = True
        # Novgorod special: all Veche Coin to attackers.
        if locale_id == "novgorod" and state.veche.coin > 0:
            if recipient:
                w = state.lords[recipient]
                w.assets["coin"] = min(8, w.assets.get("coin", 0) + state.veche.coin)
            aftermath["veche_coin_taken"] = state.veche.coin
            state.veche.coin = 0
        # PLAY-11 (Fable audit): 4.5.2 ENDING THE STORM -- "Both sides'
        # Forces take Losses per Battle (4.4.4), except that ... Routed
        # Attacking units that fail to roll a '1' are removed." This
        # applies to the WINNING (Sacking) attackers too; the previous
        # restore-all rested on the SMOKE-098 misquote of 4.4.4. A
        # winner Lord losing every unit is permanently removed (4.4.4).
        from nevsky.battle import apply_losses_rolls as _alr_sack
        from nevsky.actions import _remove_lord_permanently as _rem_sack
        from nevsky.static_data import load_lords as _ll_sack
        for alid in list(attackers):
            if alid not in state.lords:
                continue
            if state.lords[alid].routed_units:
                _alr_sack(state, alid, "storm_attacker")
            if not state.lords[alid].forces:
                _rem_sack(state, alid, _ll_sack()[alid])
                aftermath.setdefault("winner_removed_by_losses", []).append(alid)
    else:
        # Attacker lost: Storm ends; Siege continues.
        aftermath["storm_failed"] = True
        # SMOKE-096 (Round 116): failed-Storm attackers' routed_units
        # never resolved via 4.4.4 Losses. apply_losses_rolls has an
        # explicit "storm_attacker" loss_state (keep on roll==1) but
        # had no caller. Same dead-code-surfaces pattern as
        # SMOKE-093/094/095. Resolve losses for each attacker that
        # has routed units; siege continues with what survives.
        from nevsky.battle import apply_losses_rolls
        for alid in attackers:
            if alid in state.lords and state.lords[alid].routed_units:
                apply_losses_rolls(state, alid, "storm_attacker")
        # 1.5.1 / 4.4.4 ("lord_with_zero_units": permanently remove): a
        # failed-Storm attacker whose every unit Routed and was then lost in
        # the Losses rolls above has zero units and must leave the game --
        # exactly as the failed-Sally path does (SMOKE-007). This was the
        # ONE removal site the audit missed: without it a unit-less cylinder
        # lingers Mustered, so Rule 5.2 can never see the side reach zero.
        # The winners of the failed Storm are the besieged defenders, so any
        # Ransom is paid to that side (mirror of Battle/Sally aftermath).
        from nevsky.actions import _remove_lord_permanently as _rem_storm
        from nevsky.static_data import load_lords as _ll_storm
        for alid in list(attackers):
            if alid in state.lords and not state.lords[alid].forces:
                _r = apply_ransom(state, alid, defending_side, locale_id)
                if _r.get("ransom"):
                    aftermath.setdefault("ransom", []).append(_r)
                _rem_storm(state, alid, _ll_storm()[alid])
                aftermath.setdefault("removed_after_storm", []).append(alid)
        # PLAY-11 (Fable audit): 4.5.2 -- "Routed Defending units always
        # roll against Protection" (win or lose). The previous
        # restore-all rested on the SMOKE-098 misquote of 4.4.4. A
        # defender losing every unit is permanently removed (4.4.4);
        # the empty Stronghold stays Besieged (R218 semantics).
        from nevsky.actions import _remove_lord_permanently as _rem_sd
        from nevsky.static_data import load_lords as _ll_sd
        for did in list(besieged):
            if did not in state.lords:
                continue
            if state.lords[did].routed_units:
                apply_losses_rolls(state, did, "storm_defender")
            if not state.lords[did].forces:
                _rem_sd(state, did, _ll_sd()[did])
                aftermath.setdefault("winner_removed_by_losses", []).append(did)

    # SMOKE-086 (Round 90): per AoW Reference 1.4.1 Legate, when a
    # Teutonic Stronghold is Stormed and Sacked by Russians, the
    # Besieged Teutonic Lords are permanently removed. If the Legate
    # was at the Storm Locale (the Teutonic Bishopric, etc.), the
    # post-Sack state is "Russian Lord(s) and no Teutonic Lord at the
    # Legate's Locale" — remove the pawn and discard William of
    # Modena. The trigger is gated on Russian attackers winning AND
    # any Teutonic Lord(s) being sacked at the Legate's Locale.
    if (sd == "russian"
            and result["winner"] == "attacker"
            and state.legate.william_of_modena_in_play
            and state.legate.location == "locale"
            and state.legate.locale_id == locale_id):
        # The Besieged were Teutonic (defending the Teutonic
        # Stronghold). All were sacked above (besieged_removed list).
        if aftermath.get("besieged_removed"):
            if "T13" in state.decks.teutonic.capabilities_in_play:
                state.decks.teutonic.capabilities_in_play.remove("T13")
                state.decks.teutonic.discard.append("T13")
            state.legate.william_of_modena_in_play = False
            state.legate.location = "card"
            state.legate.locale_id = None
            aftermath["legate_removed"] = True

    state.campaign_turn.actions_remaining = 0
    _enter_feed_pay_disband(state)
    return (aftermath, [])


def _h_cmd_sally(
    state: GameState, side: str, args: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """4.5.3 Sally. Entire card. Besieged Lord conducts Battle.

    Sallying side does NOT benefit from Walls or Garrison (they remain
    behind in the Stronghold). Defenders (Besiegers) receive Siegeworks
    as Walls. On Sallying Attackers loss: Withdraw back inside; reduce
    Siege markers at Locale to 1 (RAID).
    """
    from nevsky.battle import resolve_battle

    sd = _require_side_player(state, side)
    lord_id = args.get("lord_id", state.campaign_turn.active_lord)
    if not isinstance(lord_id, str):
        raise IllegalAction("missing_arg", "args.lord_id required")
    _require_active_lord_command(state, sd, lord_id)
    # Q-010 (adjudicated 2026-07-06): rulebook-literal. 4.5.3 says a Besieged
    # Lord "may use a Command to Attack Besiegers" -- one action, not the
    # entire card. D-R203 narrowed to Siege/Sail/Tax (4.4.5 Recovery still
    # ends the card once the Sally Battle resolves).
    lord = state.lords[lord_id]
    if not _is_besieged(state, lord_id):
        raise IllegalAction("not_besieged", "Sally requires Besieged Lord (4.5.3)")
    locale_id = lord.location
    if locale_id is None:
        raise IllegalAction("no_location", "Lord has no location")

    # Sallying attackers = besieged Lords of sd at locale.
    attackers = [
        lid for lid, l in state.lords.items()
        if l.state == "mustered" and l.location == locale_id and l.side == sd
    ]
    # Defending besiegers = enemy Lords at the same locale (the besiegers).
    defenders = [
        lid for lid, l in state.lords.items()
        if l.state == "mustered" and l.location == locale_id and l.side != sd
    ]
    if not defenders:
        raise IllegalAction("no_defenders", "no besieging enemy Lords to Sally against")

    # Mark all Lords at Locale MOVED_FOUGHT.
    for _lid, l in state.lords.items():
        if l.location == locale_id:
            l.moved_fought = True

    # SMOKE-050 (Round 61): simple Sally — defenders (besiegers)
    # receive Siegeworks as Walls per 4.5.3. Pass siegeworks_for_sally
    # = siege_markers and simple_sally=True so resolve_battle applies
    # the Walls protection to ALL attacker strikes (since in simple
    # Sally the sallying Lords are the attackers at regular Front
    # slots, not the sally_* row).
    siege_markers_at_locale = state.locales[locale_id].siege_markers
    # 4.4.2 Concede the Field also applies in a (Relief) Sally Battle:
    # the sallying side is the attacker, the besiegers the defender.
    sally_concede = _concede_decisions_from_args(args)
    result = resolve_battle(
        state, attacker_side=sd,
        attacker_lords=attackers,
        defender_lords=defenders,
        concede_decisions=sally_concede or None,
        siegeworks_for_sally=siege_markers_at_locale,
        simple_sally=True,
        # R198: the sallying side is the attacker in resolve_battle.
        attacker_absorption_policy=_validate_absorption_policy(
            args.get("absorption_policy")),
    )
    aftermath: dict[str, Any] = {"battle": result, "siegeworks_walls": siege_markers_at_locale}

    if result["loser"] == sd:
        # Sallying side lost: Withdraw back inside (4.5.3).
        # Siege markers reduced to 1 (RAID).
        state.locales[locale_id].siege_markers = 1
        aftermath["raid_siege_to_1"] = True
        aftermath["sally_outcome"] = "withdrew"
        # SMOKE-097 (Round 117): sallying-side-lost path withdraws
        # back into the Stronghold per 4.5.3 RAID. apply_losses_rolls
        # has a 'withdrew' loss_state (unmodified Protection range)
        # but had no caller for this specific path. Resolve 4.4.4
        # Losses for every sallying Lord that still has routed_units
        # before the SMOKE-007 zero-force removal sweep below — the
        # rolls may restore some forces and save the Lord.
        from nevsky.battle import apply_losses_rolls
        for alid in attackers:
            if alid in state.lords and state.lords[alid].routed_units:
                apply_losses_rolls(state, alid, "withdrew")
        # SMOKE-007 fix: any sallying Lord with 0 forces is permanently
        # removed per 1.5.1 (Lord with no units leaves the game).
        from nevsky.actions import _remove_lord_permanently as _rem
        from nevsky.static_data import load_lords
        # killer is the besiegers (the winners of the failed Sally).
        killer_side_failed_sally: "Side" = "russian" if sd == "teutonic" else "teutonic"
        for lid in list(attackers):
            if lid in state.lords and not state.lords[lid].forces:
                # SMOKE-101 (Round 131): failed-Sally zero-forces
                # removal — the besiegers (the winners of this Sally)
                # are the killers, so apply Ransom if it's in play
                # for them. Mirror gap relative to Battle and Storm
                # aftermath where apply_ransom is already called.
                r = apply_ransom(state, lid, killer_side_failed_sally, locale_id)
                if r.get("ransom"):
                    aftermath.setdefault("ransom", []).append(r)
                _rem(state, lid, load_lords()[lid])
                aftermath.setdefault("removed_after_sally", []).append(lid)
        # PLAY-11 (Fable audit): a Sally is a Battle (4.5.3 "Attack
        # Besiegers in a Battle (4.4)"), so 4.4.4 Losses applies to
        # BOTH sides: the winning besiegers roll each Routed unit at
        # unmodified Protection ("stood_field"). The previous
        # restore-all rested on the SMOKE-099 misquote of 4.4.4.
        from nevsky.battle import apply_losses_rolls as _alr_sw
        for did in list(defenders):
            if did not in state.lords:
                continue
            if state.lords[did].routed_units:
                _alr_sw(state, did, "stood_field")
            if not state.lords[did].forces:
                r = apply_ransom(state, did, sd, locale_id)
                if r.get("ransom"):
                    aftermath.setdefault("ransom", []).append(r)
                _rem(state, did, load_lords()[did])
                aftermath.setdefault("winner_removed_by_losses", []).append(did)
    else:
        # Sallying side won. Besieging side Lords lose per 4.4 Battle
        # aftermath. Siege is lifted (remove all siege markers).
        from nevsky.actions import _remove_lord_permanently as _rem
        from nevsky.battle import apply_retreat_service_shift, transfer_spoils
        from nevsky.static_data import load_lords
        for lid in list(defenders):
            if lid not in state.lords:
                continue
            l = state.lords[lid]
            if not l.forces:
                spoil = transfer_spoils(state, lid, attackers, "all_except_ships")
                # SMOKE-101 (Round 131): Sally-win + besieger zero-
                # forces — the sallying side (sd) killed the besieger,
                # so Ransom may apply. Mirror gap with Battle/Storm.
                r = apply_ransom(state, lid, sd, locale_id)
                if r.get("ransom"):
                    aftermath.setdefault("ransom", []).append(r)
                _rem(state, lid, load_lords()[lid])
                aftermath.setdefault("removed", []).append(lid)
                aftermath.setdefault("spoils", []).append(spoil)
            else:
                # PLAY-29 (4.4.3): the losing Besieger Retreats to a single
                # adjacent Locale with no UNBESIEGED enemy Lords or
                # Strongholds. (SMOKE-049 previously also blocked enemy-
                # Conquered Locales and omitted the "Unbesieged" qualifier;
                # 4.4.3 has no Conquered-marker clause -- an enemy-Conquered
                # Stronghold blocks only while Unbesieged, already covered by
                # the Stronghold test.) There is no Approach Way to exclude
                # in a Sally. The owning player may choose via
                # args.retreat_to; unspecified -> first legal.
                # SMOKE-071 (Round 75): capture the retreat Way's type for
                # the Conceded+Retreated Spoils Unladen computation.
                target = None
                retreat_way_type_actual: str | None = None
                _sdests = _legal_retreat_dests(state, locale_id, l.side)
                _rt_map = args.get("retreat_to") or {}
                if isinstance(_rt_map, dict) and lid in _rt_map:
                    _want = _rt_map[lid]
                    _match = [(d, wt) for d, wt in _sdests if d == _want]
                    if not _match:
                        raise IllegalAction(
                            "bad_retreat_dest",
                            f"{_want} is not a legal Retreat destination for {lid} "
                            f"(4.4.3); legal: {sorted({d for d, _ in _sdests})}")
                    target, retreat_way_type_actual = _match[0]
                elif _sdests:
                    target, retreat_way_type_actual = _sdests[0]
                if target is None:
                    spoil = transfer_spoils(state, lid, attackers, "all_except_ships")
                    # SMOKE-101 (Round 131): Sally-win + besieger has
                    # no retreat path — killer is sd. Mirror gap with
                    # Battle no-retreat and zero-forces branches.
                    r = apply_ransom(state, lid, sd, locale_id)
                    if r.get("ransom"):
                        aftermath.setdefault("ransom", []).append(r)
                    _rem(state, lid, load_lords()[lid])
                    aftermath.setdefault("removed", []).append(lid)
                    aftermath.setdefault("spoils", []).append(spoil)
                else:
                    l.location = target
                    # SMOKE-036: clear in_stronghold on Sally retreat.
                    l.in_stronghold = False
                    # SMOKE-091 (Round 99): trade-route auto-flip on Sally retreat.
                    _flip_trade_route_if_uncontested(state, target, l.side)
                    shift = apply_retreat_service_shift(state, lid)
                    # SMOKE-071 (Round 75): honor 4.4.3 Concede-the-Field
                    # Spoils. If the defender (besieger) Conceded the
                    # Field and Retreated, only Loot and excess
                    # Provender transfer. Without Concede, all assets
                    # except Ships transfer (Retreat-without-Concede).
                    conceded_side = result.get("conceded")
                    this_lord_conceded = (
                        conceded_side == "defender"
                        and result["loser"] != sd
                    )
                    if this_lord_conceded:
                        spoil = transfer_spoils(
                            state, lid, attackers, "loot_and_excess",
                            retreat_way_type=retreat_way_type_actual,
                        )
                    else:
                        spoil = transfer_spoils(state, lid, attackers, "all_except_ships")
                    # SMOKE-094 (Round 114): Sally aftermath Loser
                    # routed_units never resolved via 4.4.4 Losses
                    # (same gap as SMOKE-093 in Battle aftermath).
                    from nevsky.battle import apply_losses_rolls
                    sally_loss_state = (
                        "conceded_then_retreated"
                        if this_lord_conceded
                        else "retreated_no_concede"
                    )
                    if l.routed_units:
                        apply_losses_rolls(state, lid, sally_loss_state)
                    aftermath.setdefault("retreats", []).append({"lord": lid, "to": target, "service_shift": shift})
                    aftermath.setdefault("spoils", []).append(spoil)
        # PLAY-11 (Fable audit): 4.4.4 Losses applies to BOTH sides of
        # a Sally-Battle -- winning sallying Lords roll each Routed
        # unit at unmodified Protection ("stood_field"). The previous
        # restore-all rested on the SMOKE-099 misquote of 4.4.4.
        from nevsky.battle import apply_losses_rolls as _alr_sv
        _kill_side_sally_won: "Side" = "russian" if sd == "teutonic" else "teutonic"
        for alid in list(attackers):
            if alid not in state.lords:
                continue
            if state.lords[alid].routed_units:
                _alr_sv(state, alid, "stood_field")
            if not state.lords[alid].forces:
                r = apply_ransom(state, alid, _kill_side_sally_won, locale_id)
                if r.get("ransom"):
                    aftermath.setdefault("ransom", []).append(r)
                _rem(state, alid, load_lords()[alid])
                aftermath.setdefault("winner_removed_by_losses", []).append(alid)
        # Siege lifted.
        state.locales[locale_id].siege_markers = 0
        aftermath["siege_lifted"] = True
        aftermath["sally_outcome"] = "broken_siege"
        # PLAY-10 (Fable audit): with the Siege over, nobody at the
        # Locale is inside a Besieged Stronghold anymore. Pre-fix the
        # sallying winners kept in_stronghold=True, so a later enemy
        # March skipped the 4.3.4 Approach (no Avoid/Withdraw/Battle
        # choice) and silently re-Besieged them.
        for _lid2, _l2 in state.lords.items():
            if _l2.location == locale_id and _l2.in_stronghold:
                _l2.in_stronghold = False
                aftermath.setdefault("no_longer_besieged", []).append(_lid2)
        # SMOKE-085 (Round 89): per AoW Reference 1.4.1 Legate, a
        # Teutonic Lord that Retreats (Sally aftermath when besiegers
        # lose) triggers Legate removal if the pawn is at the locale.
        # Mirrors the Avoid Battle / Withdraw / Battle-aftermath fixes.
        if (state.legate.william_of_modena_in_play
                and state.legate.location == "locale"
                and state.legate.locale_id == locale_id):
            teu_lost = any(
                lid in state.lords and state.lords[lid].side == "teutonic"
                for lid in defenders
            )
            if teu_lost:
                if "T13" in state.decks.teutonic.capabilities_in_play:
                    state.decks.teutonic.capabilities_in_play.remove("T13")
                    state.decks.teutonic.discard.append("T13")
                state.legate.william_of_modena_in_play = False
                state.legate.location = "card"
                state.legate.locale_id = None
                aftermath["legate_removed"] = True

    state.campaign_turn.actions_remaining = 0
    _enter_feed_pay_disband(state)
    return (aftermath, [])


# Register Phase 3c handlers.
HANDLERS_PHASE_3C = {
    "cmd_siege": _h_cmd_siege,
    "cmd_storm": _h_cmd_storm,
    "cmd_sally": _h_cmd_sally,
}
HANDLERS.update(HANDLERS_PHASE_3C)


# ---------------------------------------------------------------------------
# Phase 4a: capability-driven Commands
# ---------------------------------------------------------------------------


def _h_cmd_stone_kremlin(
    state: GameState, side: str, args: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """R18 Stone Kremlin (capability action). Entire card.

    Active Lord with Stone Kremlin tucked under his mat may, for his
    full Command and no other actions, mark his current Locale\'s Walls
    +1 if it is a Russian Fort, City, or Novgorod. Lord may be Besieged.
    Walls 1-3 -> Walls 1-4. Stronghold may have only one Walls +1
    marker; up to four Walls +1 markers may be on the map.
    """
    from nevsky.capabilities import has_lord_capability
    from nevsky.static_data import load_locales

    sd = _require_side_player(state, side)
    if sd != "russian":
        raise IllegalAction("wrong_side", "Stone Kremlin is a Russian capability (R18)")
    lord_id = args.get("lord_id", state.campaign_turn.active_lord)
    if not isinstance(lord_id, str):
        raise IllegalAction("missing_arg", "args.lord_id required")
    _require_active_lord_command(state, sd, lord_id)
    if not has_lord_capability(state, lord_id, "Stone Kremlin"):
        raise IllegalAction("no_capability", f"{lord_id} does not have Stone Kremlin tucked")
    lord = state.lords[lord_id]
    loc = lord.location
    if loc is None:
        raise IllegalAction("no_location", "Lord has no location")
    static_loc = load_locales()[loc]
    if static_loc["territory"] != "russian":
        raise IllegalAction("not_russian_locale", f"{loc} is not a Russian Stronghold")
    if static_loc["type"] not in ("fort", "city", "novgorod"):
        raise IllegalAction("not_eligible_type", f"{loc} type {static_loc['type']} is not Fort/City/Novgorod")
    # SMOKE-077 (Round 78): a Castle marker overlaying this locale means
    # the base Fort/City has been REPLACED by a Castle (T17 Tip). R18
    # Stone Kremlin builds Walls +1 at "Russian Fort, City, or
    # Novgorod" — once a Castle is on the locale, the original base
    # Stronghold no longer functions as a Fort, so Walls +1 is not
    # eligible. T17 Tip explicitly notes: "removes any Walls +1 marker
    # there (see Russian Capability R18 Stone Kremlin)" — Castle and
    # Walls +1 are mutually exclusive.
    if state.locales[loc].teutonic_castle or state.locales[loc].russian_castle:
        raise IllegalAction(
            "castle_overlay",
            f"{loc} has a Castle marker; Stone Kremlin (R18) applies to Fort/City/Novgorod only (T17 Tip)",
        )
    if state.locales[loc].walls_plus_one:
        raise IllegalAction("already_marked", f"{loc} already has Walls +1")
    # Cap: up to four markers on map.
    in_play = sum(1 for l in state.locales.values() if l.walls_plus_one)
    if in_play >= 4:
        raise IllegalAction("walls_max", "four Walls +1 markers already in play")
    # Active Lord must not have taken any actions on his current card.
    _require_full_command_card(state, lord_id, "Stone Kremlin (R18)")

    state.locales[loc].walls_plus_one = True
    # R216 (Q-009): stationary Command -- does NOT set Moved/Fought,
    # so it does not trigger Feed (4.8.1). Moved/Fought is only
    # March/Avoid/Battle/Siege/Storm/Sail (SoP glossary; Misc Rules L451).
    state.campaign_turn.actions_remaining = 0
    _enter_feed_pay_disband(state)
    return ({"locale": loc, "walls_plus_one": True}, [])


def _h_cmd_stonemasons(
    state: GameState, side: str, args: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """T17 Stonemasons. Entire card + 6 Provender to convert an Unbesieged
    Fort (Russian, by rule) or Town in Rus into a Castle (own color).

    Per rule: Lord must not be Besieged; must have full Command card
    untouched; must have 6 Provender (sharing allowed). The Castle marker
    REPLACES the Fort or Town at the Locale and removes any Walls +1.
    Teutons may build at most 2 Castles in a game.
    """
    from nevsky.capabilities import has_lord_capability
    from nevsky.static_data import load_locales

    sd = _require_side_player(state, side)
    if sd != "teutonic":
        raise IllegalAction("wrong_side", "Stonemasons is a Teutonic capability (T17)")
    lord_id = args.get("lord_id", state.campaign_turn.active_lord)
    if not isinstance(lord_id, str):
        raise IllegalAction("missing_arg", "args.lord_id required")
    _require_active_lord_command(state, sd, lord_id)
    if not has_lord_capability(state, lord_id, "Stonemasons"):
        raise IllegalAction("no_capability", f"{lord_id} does not have Stonemasons tucked")
    lord = state.lords[lord_id]
    if _is_besieged(state, lord_id):
        raise IllegalAction("besieged", "Lord must not be Besieged (T17)")
    loc = lord.location
    if loc is None:
        raise IllegalAction("no_location", "Lord has no location")
    static_loc = load_locales()[loc]
    if static_loc["territory"] != "russian":
        raise IllegalAction("not_in_rus", "Stonemasons builds Castle in Rus only")
    if static_loc["type"] not in ("fort", "town"):
        raise IllegalAction("not_eligible_type", f"{loc} type {static_loc['type']} is not Fort/Town")
    # SMOKE-076 (Round 78): refuse to build a Castle if any Castle marker
    # already overlays this Locale. T17 Tip: "The Castle marker REPLACES
    # the Fort or Town at its Locale" — the replacement is of the base
    # Stronghold, not an existing Castle. Without this guard,
    # Stonemasons could overlay teutonic_castle on a locale with
    # russian_castle (e.g. liberated Russian Castle on a Fort that
    # Russians re-Conquered) resulting in BOTH markers True
    # simultaneously, which is invalid game state.
    if state.locales[loc].teutonic_castle or state.locales[loc].russian_castle:
        raise IllegalAction(
            "castle_exists",
            f"{loc} already has a Castle marker; cannot build another (T17)",
        )
    if state.locales[loc].siege_markers > 0:
        raise IllegalAction("under_siege", f"{loc} is Besieged")
    # Full card untouched.
    _require_full_command_card(state, lord_id, "Stonemasons (T17)")
    # 6 Provender (own + shared from co-located own-side Lords).
    own_p = lord.assets.get("provender", 0)
    shared = sum(
        ol.assets.get("provender", 0) for olid, ol in state.lords.items()
        if olid != lord_id and ol.side == sd and ol.state == "mustered" and ol.location == loc
    )
    if own_p + shared < 6:
        raise IllegalAction(
            "insufficient_provender",
            f"need 6 Provender; have own {own_p} + shared {shared} = {own_p + shared}",
        )
    # Cap: at most 2 Teutonic Castles (built by Stonemasons) in a game.
    # We track via Calendar.pleskau_lords_removed_teutonic? No, that\'s
    # different. Use a meta.special_rules counter.
    sr = state.meta.special_rules
    built = int(sr.get("stonemasons_castles_built", 0))
    if built >= 2:
        raise IllegalAction("castle_max", "two Stonemasons Castles already built")

    # Spend 6 Provender (own first).
    spend = 6
    if lord.assets.get("provender", 0) > 0:
        take = min(spend, lord.assets["provender"])
        lord.assets["provender"] -= take
        if lord.assets["provender"] == 0:
            del lord.assets["provender"]
        spend -= take
    if spend > 0:
        for olid, ol in state.lords.items():
            if spend <= 0:
                break
            if olid == lord_id or ol.side != sd or ol.location != loc:
                continue
            if ol.assets.get("provender", 0) <= 0:
                continue
            take = min(spend, ol.assets["provender"])
            ol.assets["provender"] -= take
            if ol.assets["provender"] == 0:
                del ol.assets["provender"]
            spend -= take

    # Place Teutonic castle marker; remove Walls +1.
    # SMOKE-023 (Round 36): Castle marker is worth 1 VP per Strongholds
    # reference ("1 VP per Castle marker of your color"). The old code
    # set the marker bool but did not increment calendar.teutonic_vp,
    # so determine_scenario_winner (which reads the incremental float)
    # missed the VP. Fix: add 1 and refresh markers.
    state.locales[loc].teutonic_castle = True
    state.locales[loc].walls_plus_one = False
    state.calendar.teutonic_vp += 1.0
    _refresh_vp_markers(state)
    sr["stonemasons_castles_built"] = built + 1

    # R216 (Q-009): stationary Command -- does NOT set Moved/Fought,
    # so it does not trigger Feed (4.8.1). Moved/Fought is only
    # March/Avoid/Battle/Siege/Storm/Sail (SoP glossary; Misc Rules L451).
    state.campaign_turn.actions_remaining = 0
    _enter_feed_pay_disband(state)
    return ({"locale": loc, "castle_built": True, "castles_built_total": built + 1}, [])


def _h_cmd_muster_serf(
    state: GameState, side: str, args: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """R4 Smerdi (capability event). 1 Command action; active Russian
    Lord Unbesieged in Rus may Muster 1 Serf (max 6 total Serfs in
    play; serfs return to Smerdi card when removed).
    """
    from nevsky.capabilities import has_side_capability
    from nevsky.static_data import load_locales

    sd = _require_side_player(state, side)
    if sd != "russian":
        raise IllegalAction("wrong_side", "Smerdi is a Russian capability (R4)")
    lord_id = args.get("lord_id", state.campaign_turn.active_lord)
    if not isinstance(lord_id, str):
        raise IllegalAction("missing_arg", "args.lord_id required")
    _require_active_lord_command(state, sd, lord_id)
    if not has_side_capability(state, "russian", "Smerdi"):
        raise IllegalAction("no_capability", "Smerdi (R4) not in play")
    lord = state.lords[lord_id]
    if _is_besieged(state, lord_id):
        raise IllegalAction("besieged", "Smerdi requires Unbesieged Russian Lord")
    if lord.location is None:
        raise IllegalAction("no_location", "Lord has no location")
    if load_locales()[lord.location]["territory"] != "russian":
        raise IllegalAction("not_in_rus", "Smerdi requires Russian Lord in Rus")
    # Pool of 6 Serfs total in the side; count current Serfs across all
    # Russian Mustered Lords.
    in_play = sum(
        l.forces.get("serfs", 0) for l in state.lords.values()
        if l.side == "russian" and l.state == "mustered"
    )
    if in_play >= 6:
        raise IllegalAction("serf_pool_empty", "Smerdi pool exhausted (6 Serfs already in play)")
    if state.campaign_turn.actions_remaining < 1:
        raise IllegalAction("insufficient_actions", "Smerdi muster costs 1 action")

    lord.forces["serfs"] = lord.forces.get("serfs", 0) + 1
    # R216 (Q-009): stationary Command -- does NOT set Moved/Fought,
    # so it does not trigger Feed (4.8.1). Moved/Fought is only
    # March/Avoid/Battle/Siege/Storm/Sail (SoP glossary; Misc Rules L451).
    _consume_actions(state, 1)
    return ({"lord_id": lord_id, "serfs_added": 1, "in_play_after": in_play + 1}, [])


HANDLERS_PHASE_4A = {
    "cmd_stone_kremlin": _h_cmd_stone_kremlin,
    "cmd_stonemasons": _h_cmd_stonemasons,
    "cmd_muster_serf": _h_cmd_muster_serf,
}
HANDLERS.update(HANDLERS_PHASE_4A)


# ---------------------------------------------------------------------------
# Phase 4b: economy / movement capabilities
# ---------------------------------------------------------------------------


def _h_cmd_raiders_ravage(
    state: GameState, side: str, args: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Raiders capability action: Ravage an adjacent Locale.

    T2 Teutonic Raiders (this-lord): requires Knight, Sergeant, or Light
      Horse on Lord; via Trackway only; once per Command card; gets
      Loot if Locale type is non-Region.
    R12 / R14 Russian Raiders (this-lord): requires Light Horse or
      Asiatic Horse; via any Way (incl. waterway); multiple uses per
      card; never gets Loot.

    Action cost: 1 action.

    args:
      lord_id   Active Lord
      to        Adjacent target Locale
    """
    from nevsky.capabilities import has_lord_capability
    from nevsky.static_data import load_locales, load_ways

    sd = _require_side_player(state, side)
    lord_id = args.get("lord_id", state.campaign_turn.active_lord)
    target = args.get("to")
    if not (isinstance(lord_id, str) and isinstance(target, str)):
        raise IllegalAction("missing_arg", "args: lord_id, to")
    _require_active_lord_command(state, sd, lord_id)

    lord = state.lords[lord_id]
    if _is_besieged(state, lord_id):
        raise IllegalAction("besieged", "Raiders Ravage requires Unbesieged Lord")
    if lord.location is None:
        raise IllegalAction("no_location", "Lord has no location")

    has_t2 = has_lord_capability(state, lord_id, "Raiders") and sd == "teutonic"
    has_r = has_lord_capability(state, lord_id, "Raiders") and sd == "russian"
    if not (has_t2 or has_r):
        raise IllegalAction("no_capability", f"{lord_id} does not have Raiders")
    if has_t2 and lord.raiders_used_this_card:
        raise IllegalAction("already_used", "Teutonic Raiders is once per Command card")

    # Way + adjacency check.
    static_locales = load_locales()
    way_type = None
    for w in load_ways():
        if (w["a"] == lord.location and w["b"] == target) or (w["b"] == lord.location and w["a"] == target):
            way_type = w["type"]
            break
    if way_type is None:
        raise IllegalAction("not_adjacent", f"{target} not adjacent to {lord.location}")
    if has_t2 and way_type != "trackway":
        raise IllegalAction("trackway_only", "Teutonic Raiders requires Trackway")

    # Force composition check.
    if has_t2:
        eligible = ["knights", "sergeants", "light_horse"]
    else:  # Russian
        eligible = ["light_horse", "asiatic_horse"]
    if not any(lord.forces.get(u, 0) > 0 for u in eligible):
        raise IllegalAction(
            "no_eligible_horse",
            f"Lord must have one of {eligible} for Raiders",
        )

    # Standard Ravage eligibility (4.7.2):
    static = static_locales[target]
    if static["territory"] == sd:
        raise IllegalAction("own_territory", "cannot Ravage own territory")
    loc = state.locales[target]
    if loc.russian_conquered > 0 or loc.teutonic_conquered > 0:
        raise IllegalAction("conquered", "Locale is Conquered")
    if loc.russian_ravaged or loc.teutonic_ravaged:
        raise IllegalAction("already_ravaged", "Locale already Ravaged")
    if any(l.state == "mustered" and l.location == target and l.side != sd for l in state.lords.values()):
        raise IllegalAction("enemy_at_target", "enemy Lord at target")

    if state.campaign_turn.actions_remaining < 1:
        raise IllegalAction("insufficient_actions", "Raiders Ravage costs 1 action")

    # Place ravaged marker.
    if sd == "teutonic":
        loc.teutonic_ravaged = True
        state.calendar.teutonic_vp += 0.5
    else:
        loc.russian_ravaged = True
        state.calendar.russian_vp += 0.5
    _refresh_vp_markers(state)

    # +1 Provender always.
    lord.assets["provender"] = min(8, lord.assets.get("provender", 0) + 1)
    # T2: +1 Loot if non-Region. R12/R14: NO Loot.
    if has_t2 and static["type"] != "region":
        lord.assets["loot"] = min(8, lord.assets.get("loot", 0) + 1)

    if has_t2:
        lord.raiders_used_this_card = True
    # R216 (Q-009): stationary Command -- does NOT set Moved/Fought,
    # so it does not trigger Feed (4.8.1). Moved/Fought is only
    # March/Avoid/Battle/Siege/Storm/Sail (SoP glossary; Misc Rules L451).
    _consume_actions(state, 1)
    return ({"lord_id": lord_id, "target": target, "loot_added": has_t2 and static["type"] != "region"}, [])


def apply_ransom(
    state: GameState, removed_lord: str, killer_side: Side, locale_id: str
) -> dict[str, Any]:
    """T16 / R7 Ransom hook (4.4 Aftermath / 4.5.2 Sack).

    Called when an enemy Lord is removed in Battle/Storm or while
    Besieged. If the killer side has Ransom in play, add Coin equal to
    removed Lord's Service rating to a friendly Lord present at the
    same locale.
    """
    from nevsky.capabilities import has_side_capability
    from nevsky.static_data import load_lords

    if not has_side_capability(state, killer_side, "Ransom"):
        return {"ransom": False}
    sl = load_lords().get(removed_lord)
    if sl is None:
        return {"ransom": False}
    coin = int(sl["ratings"]["service"])
    # Find a friendly Lord at locale_id.
    candidates = [
        lid for lid, l in state.lords.items()
        if l.state == "mustered" and l.location == locale_id and l.side == killer_side
    ]
    if not candidates:
        return {"ransom": True, "coin_lost_no_recipient": coin}
    recip = candidates[0]
    new_amt = min(8, state.lords[recip].assets.get("coin", 0) + coin)
    state.lords[recip].assets["coin"] = new_amt
    return {"ransom": True, "removed": removed_lord, "recipient": recip, "coin": coin}


def effective_ship_count(state: GameState, lord_id: str) -> int:
    """T18 Cogs / R16 Lodya: effective Ship count for this Lord.

    - Cogs: each Ship counts as 2.
    - Lodya: this Lord may temporarily count up to 2 of his Boats as
      Ships; for the harness we expose this via a separate
      lodya_ships_from_boats(), called by the agent when needed.
    Returns the count after Cogs multiplier (no Lodya conversion).
    """
    from nevsky.capabilities import has_lord_capability

    base = state.lords[lord_id].assets.get("ship", 0)
    if has_lord_capability(state, lord_id, "Cogs"):
        return base * 2
    return base


def effective_boat_count(state: GameState, lord_id: str) -> int:
    """R16 Lodya: this Lord's Boats count as 2 Boats."""
    from nevsky.capabilities import has_lord_capability

    base = state.lords[lord_id].assets.get("boat", 0)
    if has_lord_capability(state, lord_id, "Lodya"):
        return base * 2
    return base


def lodya_comparison_ships(state: GameState, lord_id: str) -> int:
    """PLAY-20 (Fable audit): R16 Lodya for the R9 Baltic Sea Trade
    Ship comparison. The card lets the Lord "temporarily designate up
    to TWO of his Ships or Boats as the other" -- so at most 2 of his
    Boats can stand in as Ships. (The other mode, doubling Boats,
    contributes no Ships at all.) The previous comparison credited the
    entire boat-doubling delta (ALL of the Lord's Boats) as Ships.
    """
    from nevsky.capabilities import has_lord_capability

    if not has_lord_capability(state, lord_id, "Lodya"):
        return 0
    return min(2, state.lords[lord_id].assets.get("boat", 0))


def _h_cmd_tax_veliky_knyaz_aware(
    state: GameState, side: str, args: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Replacement for cmd_tax that applies R17 Veliky Knyaz.

    Veliky Knyaz: this Lord's Tax also adds 2 Transport AND restores all
    Mustered Forces (lost units back up to starting forces / Mustered
    Vassal totals).

    args:
      transport_type   Required when Veliky Knyaz active: which 2
                       Transport(s) to add (boat / cart / sled / ship).
                       For Phase 4b we add 2 of the chosen type (must
                       be Ship-authorized for ship).
    """
    from nevsky.capabilities import has_lord_capability
    from nevsky.static_data import load_lords

    sd = _require_side_player(state, side)
    lord_id = args.get("lord_id", state.campaign_turn.active_lord)
    if not isinstance(lord_id, str):
        raise IllegalAction("missing_arg", "args.lord_id required")
    _require_active_lord_command(state, sd, lord_id)
    _require_full_command_card(state, lord_id, "Tax (4.7.4)")  # entire_card (R203)

    lord = state.lords[lord_id]
    if _is_besieged(state, lord_id):
        raise IllegalAction("besieged", "Tax requires Unbesieged Lord (4.7.4)")
    if lord.location is None or not _is_own_seat(state, lord_id, lord.location):
        raise IllegalAction("not_at_seat", f"{lord_id} not at own Seat")

    if lord.assets.get("coin", 0) >= 8:
        raise IllegalAction("coin_max", f"{lord_id} at Coin cap (1.7.3)")

    # Standard Tax: +1 Coin.
    lord.assets["coin"] = lord.assets.get("coin", 0) + 1
    extra: dict[str, Any] = {}

    # Veliky Knyaz add-on.
    if has_lord_capability(state, lord_id, "Veliky Knyaz"):
        # SMOKE-104 (Round 143): per AoW Reference R17 Tip — "any two
        # Transport (up to the maximum of eight per type)". The rule
        # allows mixed types (e.g. 1 Cart + 1 Boat). Backward-compatible:
        # legacy `transport_type` (single str) still works → 2 of that
        # type. New `transport_choices` (dict {type: count}) totals 2
        # and may mix types. Same audit pattern as SMOKE-046/048/067/
        # 102 (rule-cite-but-no-enforce → relax).
        sl = load_lords()[lord_id]
        choices = args.get("transport_choices")
        if choices is None:
            ttype = args.get("transport_type", "cart")
            choices = {ttype: 2}
        if not isinstance(choices, dict):
            raise IllegalAction(
                "bad_transport",
                "transport_choices must be a dict {type: count} summing to 2",
            )
        # Validate types + count sum.
        total_requested = 0
        for k, n in choices.items():
            if k not in ("boat", "cart", "sled", "ship"):
                raise IllegalAction("bad_transport", f"transport type {k!r} invalid")
            if not isinstance(n, int) or n < 0:
                raise IllegalAction("bad_transport", f"transport count {n!r} invalid for {k}")
            total_requested += n
        if total_requested != 2:
            raise IllegalAction(
                "bad_transport",
                f"transport_choices must total 2 (got {total_requested})",
            )
        if "ship" in choices and choices["ship"] > 0 and not sl.get("ships_authorized", False):
            raise IllegalAction("ship_unauthorized", f"{lord_id} not Ship-authorized")
        # Apply per-type with 8-cap.
        added_per_type: dict[str, int] = {}
        for k, n in choices.items():
            if n == 0:
                continue
            cap_room = 8 - lord.assets.get(k, 0)
            actually = min(n, cap_room)
            if actually > 0:
                lord.assets[k] = lord.assets.get(k, 0) + actually
                added_per_type[k] = actually
        if len(added_per_type) == 1:
            # Legacy summary shape for backward-compat readers.
            only_type = next(iter(added_per_type))
            extra["veliky_knyaz_transport_added"] = {
                "type": only_type, "count": added_per_type[only_type],
            }
        else:
            extra["veliky_knyaz_transport_added"] = {
                "by_type": added_per_type,
                "count": sum(added_per_type.values()),
            }
        # Restore Mustered Forces: bring forces back up to starting +
        # Mustered Vassals. Phase 4b approximates "Mustered Vassal
        # totals" by checking Vassal.mustered=True and adding their
        # forces back.
        starting = sl["starting_forces"]
        target_forces: dict[str, int] = {k: int(v) for k, v in starting.items()}
        for v in sl.get("vassals", []):
            if lord.vassals.get(v["vassal_id"], None) and lord.vassals[v["vassal_id"]].mustered:
                for k, n in v.get("forces", {}).items():
                    target_forces[k] = target_forces.get(k, 0) + int(n)
        restored: dict[str, int] = {}
        for k, n in target_forces.items():
            cur = lord.forces.get(k, 0)
            if cur < n:
                lord.forces[k] = n  # type: ignore[index]
                restored[k] = n - cur
        extra["veliky_knyaz_restored"] = restored

    # R216 (Q-009): stationary Command -- does NOT set Moved/Fought,
    # so it does not trigger Feed (4.8.1). Moved/Fought is only
    # March/Avoid/Battle/Siege/Storm/Sail (SoP glossary; Misc Rules L451).
    state.campaign_turn.actions_remaining = 0
    _enter_feed_pay_disband(state)
    return ({"lord_id": lord_id, "added": "coin", **extra}, [])


HANDLERS_PHASE_4B = {
    "cmd_raiders_ravage": _h_cmd_raiders_ravage,
}
# Replace cmd_tax with the Veliky-Knyaz-aware variant.
HANDLERS["cmd_tax"] = _h_cmd_tax_veliky_knyaz_aware
HANDLERS.update(HANDLERS_PHASE_4B)


# ---------------------------------------------------------------------------
# Phase 4b: 4.8 Feed hook for Hillforts (T8)
# ---------------------------------------------------------------------------


def _hillforts_skip_lord(state: GameState, side: Side) -> str | None:
    """T8 Hillforts: at any 4.8 Feed, one Unbesieged Teutonic Lord in
    Livonia may skip Feed (his forces don't need feeding). Phase 4b
    picks the first eligible Lord deterministically (alphabetical id).
    Returns the chosen lord_id or None.
    """
    from nevsky.capabilities import has_side_capability
    from nevsky.static_data import load_locales

    if side != "teutonic":
        return None
    if not has_side_capability(state, "teutonic", "Hillforts of the Sword Brethren"):
        return None
    eligible = _hillforts_eligible_lords(state, side)
    return eligible[0] if eligible else None


def _hillforts_eligible_lords(state: GameState, side: Side) -> list[str]:
    """Sorted list of Teutonic Lords eligible to skip Feed via T8 Hillforts
    (Unbesieged, Moved/Fought, in Crusader Livonia). Empty if T8 not in
    play or side != teutonic. The owner may pick any of these (PLAY-31);
    the first is the deterministic default."""
    from nevsky.capabilities import has_side_capability
    from nevsky.static_data import load_locales
    if side != "teutonic":
        return []
    if not has_side_capability(state, "teutonic", "Hillforts of the Sword Brethren"):
        return []
    static = load_locales()
    eligible = []
    for lid, l in state.lords.items():
        if l.side != "teutonic" or l.state != "mustered":
            continue
        if not l.moved_fought:
            continue
        if _is_besieged(state, lid):
            continue
        if l.location is None:
            continue
        if static[l.location].get("subregion") != "crusader_livonia":
            continue
        eligible.append(lid)
    return sorted(eligible)
