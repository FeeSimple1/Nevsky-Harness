"""Action grammar and dispatcher.

An Action is a JSON dict with shape:

  { "type": "<action_type>", "side": "teutonic"|"russian"|"system", "args": {...} }

The dispatcher (`apply_action`) validates the action against the current
state, mutates state in place if legal, appends a HistoryEntry, and
returns a result dict describing the outcome. Illegal actions raise
`IllegalAction`; the state is not mutated when this happens (except for
the rng_state field if any roll was consumed in validation, which we
avoid by validating-before-rolling).

Phase 2 covers all Levy-phase actions (3.1 Arts of War through 3.5
Call to Arms). Phase 3 will add Campaign actions (March, Battle, etc.).

Action types implemented in Phase 2:

  Arts of War (3.1):
    aow_shuffle           shuffle own AoW deck
    aow_draw              draw 2 cards into pending_draw
    aow_implement_card    implement next pending_draw card
                          (event vs capability per first_levy_done)

  Pay (3.2):
    pay_with_coin         spend Coin to shift Service marker(s) right
    pay_with_loot         spend Loot at Friendly Locale to shift Service

  Disband (3.3):
    disband_resolve       process all Lords whose Service marker is
                          at-or-left-of Levy this segment

  Muster (3.4):
    muster_lord           Lordship-1: Fealty roll to bring Ready Lord on
    muster_vassal         Lordship-1: deploy a ready Vassal
    levy_transport        Lordship-1: add a Boat/Cart/Sled/Ship
    levy_capability       Lordship-1: tuck this-lord or side-wide cap

  Call to Arms (3.5):
    legate_arrives        place pawn at a Bishopric
    legate_move           Option 1: move pawn to a Friendly Locale
    legate_use            Option 2: USE the Legate (sub-options 2a/2b/2c)
    veche_action          Russian Veche option A/B/C/D
    aow_discard_this_levy 3.5.3 -- both sides discard "This Levy" events

  Step transitions:
    advance_step          finish current side's segment of current step;
                          when both sides done, advance to next levy_step

System actions:
    system_setup_complete clear scenario-setup PendingDecisions (Phase 1
                          residue) so Phase 2 can proceed
"""

from __future__ import annotations

from typing import Any

from nevsky.state import (
    AssetType,
    ForceType,
    GameState,
    HistoryEntry,
    Side,
)

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class IllegalAction(ValueError):
    """Raised when an action cannot be executed against the current state.

    The state is NOT mutated when this is raised. Carries a `code`
    attribute identifying the specific rule violation; the message text
    is suitable for an LLM agent that needs to choose a different move.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


# ---------------------------------------------------------------------------
# Public dispatcher
# ---------------------------------------------------------------------------


def apply_action(state: GameState, action: dict[str, Any]) -> dict[str, Any]:
    """Validate, execute, and record an action.

    Mutates `state` in place. Returns a dict of the action's result.
    Raises IllegalAction on any rule violation; in that case the state
    is left untouched (per BRIEF: validators must return precise errors
    before any mutation).
    """
    if not isinstance(action, dict):
        raise IllegalAction("bad_envelope", "action must be a JSON object")
    atype = action.get("type")
    side = action.get("side")
    args = action.get("args", {}) or {}
    if not isinstance(atype, str):
        raise IllegalAction("bad_envelope", "action 'type' missing or not a string")
    if side not in ("teutonic", "russian", "system"):
        raise IllegalAction(
            "bad_envelope", f"action 'side' must be teutonic|russian|system; got {side!r}"
        )
    if not isinstance(args, dict):
        raise IllegalAction("bad_envelope", "action 'args' must be a JSON object")

    handler = _HANDLERS.get(atype)
    if handler is None:
        raise IllegalAction("unknown_action", f"unknown action type {atype!r}")

    # Q-001: auto-confirm setup_transport_choice decisions for the
    # active side at first Levy action (skipping the explicit
    # confirm/set/confirm_all actions and system actions). This lets
    # Levy proceed normally without forcing the agent to clear
    # default-confirm decisions one-by-one.
    auto_confirmed: list[dict[str, Any]] = []
    if (
        state.meta.phase == "levy"
        and side in ("teutonic", "russian")
        and atype not in (
            "confirm_setup_transport",
            "set_setup_transport",
            "confirm_all_setup_transports",
            "system_setup_complete",
        )
    ):
        auto_confirmed = _auto_confirm_setup_transport_choices(state, side)  # type: ignore[arg-type]

    # Each handler returns (result_dict, dice_list).
    result, dice = handler(state, side, args)  # may raise IllegalAction
    if auto_confirmed:
        # Surface the auto-confirms in the result for transparency.
        if isinstance(result, dict):
            result.setdefault("_auto_confirmed_setup_transports", auto_confirmed)

    state.meta.sequence += 1
    state.history.append(
        HistoryEntry(
            sequence=state.meta.sequence,
            actor=side,  # Literal-typed in HistoryEntry
            action={"type": atype, "side": side, "args": args},
            dice=dice,
            result=result,
        )
    )
    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require_side_player(state: GameState, side: str) -> Side:
    """Verify side is a real player (not 'system'). Returns the side."""
    if side == "system":
        raise IllegalAction("wrong_actor", "this action requires a player side, not 'system'")
    return side  # type: ignore[return-value]


def _require_levy_phase(state: GameState) -> None:
    if state.meta.phase != "levy":
        raise IllegalAction(
            "wrong_phase", f"action only allowed during Levy; phase={state.meta.phase}"
        )


def _require_levy_step(state: GameState, step: str) -> None:
    if state.meta.levy_step != step:
        raise IllegalAction(
            "wrong_step",
            f"action requires levy_step={step}; current={state.meta.levy_step}",
        )


def _require_active(state: GameState, side: Side) -> None:
    if state.meta.active_player != side:
        raise IllegalAction(
            "wrong_actor",
            f"action requires active_player={side}; current={state.meta.active_player}",
        )


def _side_deck(state: GameState, side: Side):
    return state.decks.teutonic if side == "teutonic" else state.decks.russian


def _other(side: Side) -> Side:
    return "russian" if side == "teutonic" else "teutonic"


# ---------------------------------------------------------------------------
# Step-transition action: advance_step
# ---------------------------------------------------------------------------


def _h_advance_step(
    state: GameState, side: str, args: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Mark current side's segment of current Levy step finished.

    SoP 2.2.4: T-then-R within each Levy step. Both T and R must call
    advance_step (in T then R order) before the step is considered
    complete and the next step begins. Call to Arms differs: T does only
    Legate (3.5.1), R does only Veche (3.5.2), then 3.5.3 discard runs.
    """
    sd = _require_side_player(state, side)
    _require_levy_phase(state)
    _require_active(state, sd)

    if sd == "teutonic":
        if state.meta.levy_step_completed_t:
            raise IllegalAction("already_done", "Teutonic side already finished this step")
        state.meta.levy_step_completed_t = True
        state.meta.active_player = "russian"
    else:
        if state.meta.levy_step_completed_r:
            raise IllegalAction("already_done", "Russian side already finished this step")
        state.meta.levy_step_completed_r = True

    next_step = None
    if state.meta.levy_step_completed_t and state.meta.levy_step_completed_r:
        # Advance to next step.
        order: list[str] = ["arts_of_war", "pay", "disband", "muster", "call_to_arms", "done"]
        i = order.index(state.meta.levy_step)
        next_step = order[i + 1]
        state.meta.levy_step = next_step  # type: ignore[assignment]
        state.meta.levy_step_completed_t = False
        state.meta.levy_step_completed_r = False
        state.meta.active_player = "teutonic"
        if next_step == "muster":
            # Reset per-Lord Lordship counters at start of Muster (3.4).
            for lord in state.lords.values():
                lord.lordship_used = 0
            # SMOKE-044 (Round 56): transition disbanded -> ready for
            # Lords whose cylinder is on the Calendar at or before the
            # Levy marker. Without this transition, a Lord Disbanded at
            # limit (3.3.2) in a prior Levy stays state="disbanded"
            # forever and _h_muster_lord rejects them. Per rules a
            # Disbanded Lord re-Musters in future Levies when the Levy
            # marker catches up to their cylinder.
            try:
                levy_box = _find_levy_marker_box(state)
            except IllegalAction:
                levy_box = None
            if levy_box is not None:
                for lord_id, lord in state.lords.items():
                    if lord.state != "disbanded":
                        continue
                    cyl_box = _find_cylinder_box(state, lord_id)
                    if cyl_box is None:
                        continue
                    # off_left (0) or boxes 1..levy_box: Ready
                    if cyl_box <= levy_box:
                        lord.state = "ready"  # type: ignore[assignment]
        if next_step == "call_to_arms":
            # Reset call-to-arms once-per-segment flags (3.5.1, 3.5.2).
            state.legate.acted_this_call_to_arms = False
            state.veche.acted_this_call_to_arms = False
            # Advanced Vassal Service (3.4.2): "After a side finishes
            # all Vassal Muster for this Levy, flip up all Service
            # markers that are Coat-of-Arms side down (3.3.2), making
            # them Ready for Muster later in the game."
            if state.meta.optional_rules.get("advanced_vassal_service", False):
                for lord in state.lords.values():
                    for vstate in lord.vassals.values():
                        if not vstate.ready and not vstate.mustered:
                            vstate.ready = True
        if next_step == "done":
            # SMOKE-039 (Round 51): auto-fire 3.5.3 ("both sides discard
            # This-Levy events") on the call_to_arms -> done transition.
            # The explicit aow_discard_this_levy action stays available
            # for tests/agents that prefer to call it manually; calling
            # it before advance_step leaves the list empty, so this
            # post-call_to_arms sweep is idempotent. Without this auto-
            # fire, agents that skip the action leak events into the
            # next Levy / Campaign decks (3.5.3 is mandatory per rules).
            for _sd_deck in (state.decks.teutonic, state.decks.russian):
                if _sd_deck.this_levy_events:
                    _sd_deck.discard.extend(_sd_deck.this_levy_events)
                    _sd_deck.this_levy_events = []
            # Levy complete -- transition to Campaign Plan (4.0).
            state.meta.phase = "campaign"
            state.meta.campaign_step = "plan"
            state.meta.plan_complete_t = False
            state.meta.plan_complete_r = False
            state.meta.active_player = "teutonic"
            # Phase 4c: clear per-Levy block lists and Lordship bonuses.
            state.meta.block_lords_this_levy_t = []
            state.meta.block_lords_this_levy_r = []
            state.meta.lordship_bonus = {}
            state.meta.special_rules.pop("block_william_of_modena_this_levy", None)
            # 4.0 capability discard (in excess of own Mustered Lord count).
            # SMOKE-031: route each discard through _discard_side_capability
            # so per-card cleanup (Summer Crusaders Disband on T11, Mongols/
            # Kipchaqs Disband on R10, Legate-leaves-map on T13) cascades.
            from nevsky.campaign import _discard_side_capability as _disc_cap
            rule_4_0_cleanup: list[dict[str, Any]] = []
            for sd_ in ("teutonic", "russian"):
                deck = state.decks.teutonic if sd_ == "teutonic" else state.decks.russian
                mustered_count = sum(
                    1 for lord in state.lords.values()
                    if lord.side == sd_ and lord.state == "mustered"
                )
                while len(deck.capabilities_in_play) > mustered_count:
                    cid_to_drop = deck.capabilities_in_play[-1]
                    rule_4_0_cleanup.append(_disc_cap(state, sd_, cid_to_drop))

    return ({"new_step": state.meta.levy_step,
             "phase": state.meta.phase,
             "campaign_step": state.meta.campaign_step if state.meta.phase == "campaign" else None,
             "active_player": state.meta.active_player}, [])


# ---------------------------------------------------------------------------
# 3.1 Arts of War handlers
# ---------------------------------------------------------------------------


def _h_aow_shuffle(
    state: GameState, side: str, args: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Shuffle own AoW deck (3.1.1).

    Per 3.1.1 the side shuffles all own unused AoW cards plus all 3
    No-Event/No-Capability cards into a fresh deck. Held events
    (3.1.3) and capabilities-in-play (3.4.4) are NOT included in the
    shuffle. We model "unused" as `deck` + `discard`; cards in
    `removed`, `capabilities_in_play`, `holds`, `this_levy_events`,
    `this_campaign_events`, and `pending_draw` stay where they are.
    """
    from nevsky.rng import shuffle

    sd = _require_side_player(state, side)
    _require_levy_phase(state)
    _require_levy_step(state, "arts_of_war")
    _require_active(state, sd)

    deck = _side_deck(state, sd)
    pool = deck.deck + deck.discard
    shuffled = shuffle(state, pool)
    deck.deck = shuffled
    deck.discard = []
    return ({"deck_size": len(deck.deck)}, [])


def _h_aow_draw(
    state: GameState, side: str, args: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Draw 2 cards into pending_draw (3.1)."""
    sd = _require_side_player(state, side)
    _require_levy_phase(state)
    _require_levy_step(state, "arts_of_war")
    _require_active(state, sd)

    deck = _side_deck(state, sd)
    if deck.pending_draw:
        raise IllegalAction(
            "pending_draw_nonempty",
            "cannot draw: implement existing pending_draw cards first",
        )
    n_draw = min(2, len(deck.deck))
    drawn = deck.deck[:n_draw]
    deck.deck = deck.deck[n_draw:]
    deck.pending_draw.extend(drawn)
    return ({"drawn": drawn, "deck_remaining": len(deck.deck)}, [])


def _h_aow_implement_card(
    state: GameState, side: str, args: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Implement the next pending_draw card.

    Per 3.1.2 (first Levy of scenario): implement bottom-half = Capability.
    Per 3.1.3 (any subsequent Levy): implement top-half = Event.

    No-Event / No-Capability cards: in the matching half, they vaporize
    per 3.1.3 (2E) -- removed from play permanently. Pleskau scenario
    pre-removes them (handled at scenario-load time, so they should not
    be in the deck). Crusade-on-Novgorod retains them; in that case we
    return the No-Event card to the discard so it shuffles back.

    Other cards:
      - first_levy_done=False -> tuck capability bottom-half
        (this-lord vs side-wide is decided here based on capability_scope)
        For Phase 2, capability scope `this_lord` requires args.lord_id.
      - first_levy_done=True -> reveal event:
        - persistence=immediate -> resolve effect (Phase 3 wires effects;
          Phase 2 records the reveal and discards)
        - persistence=hold -> add to side's holds
        - persistence=this_levy -> add to side's this_levy_events
        - persistence=this_campaign -> add to side's this_campaign_events
    """
    from nevsky.static_data import load_cards

    sd = _require_side_player(state, side)
    _require_levy_phase(state)
    _require_levy_step(state, "arts_of_war")
    _require_active(state, sd)

    deck = _side_deck(state, sd)
    if not deck.pending_draw:
        raise IllegalAction("nothing_to_implement", "pending_draw is empty")

    cards = load_cards()
    cid = deck.pending_draw[0]
    card = cards[cid]
    # SMOKE-010 fix: do NOT pop pending_draw yet. Pop after success so
    # a failed resolver leaves state consistent.

    if card["no_event"]:
        # 3.1.3 (2E): No-Event / No-Capability cards drawn during play
        # are permanently removed from play. Crusade-on-Novgorod scenario
        # special-cases this (the deck retains them).
        sr = state.meta.special_rules
        if sr.get("keep_no_event_cards"):
            deck.pending_draw = deck.pending_draw[1:]
            deck.discard.append(cid)
            return (
                {
                    "card": cid,
                    "outcome": "retained_to_discard",
                    "scenario_rule": "crusade_on_novgorod",
                },
                [],
            )
        deck.pending_draw = deck.pending_draw[1:]
        deck.removed.append(cid)
        return ({"card": cid, "outcome": "removed_from_play"}, [])

    if not state.meta.first_levy_done:
        # First Levy: implement as capability (bottom half).
        scope = card["capability_scope"]
        if scope == "this_lord":
            lord_id = args.get("lord_id")
            if not isinstance(lord_id, str) or lord_id not in state.lords:
                raise IllegalAction(
                    "missing_arg",
                    "this-lord capability requires args.lord_id targeting a Mustered Lord",
                )
            lord = state.lords[lord_id]
            if lord.side != sd or lord.state != "mustered":
                raise IllegalAction(
                    "bad_target",
                    f"capability lord_id must be a Mustered own-side Lord (got {lord.side}/{lord.state})",
                )
            if len(lord.this_lord_capabilities) >= 2:
                raise IllegalAction(
                    "cap_limit",
                    f"{lord_id} already has 2 this-lord capabilities (3.4.4)",
                )
            for existing in lord.this_lord_capabilities:
                if cards[existing]["capability_name"] == card["capability_name"]:
                    raise IllegalAction(
                        "duplicate_capability",
                        f"{lord_id} already has capability '{card['capability_name']}' (3.4.4)",
                    )
            # SMOKE-029: enforce capability_eligibility on first-Levy
            # auto-implement too. The chosen Lord must be allowed to
            # carry this Capability per the AoW Reference (3.1.2 / 3.4.4).
            _check_capability_eligibility(card, lord_id, role="target")
            deck.pending_draw = deck.pending_draw[1:]
            lord.this_lord_capabilities.append(cid)
            return ({"card": cid, "outcome": "tucked_under_lord", "lord_id": lord_id}, [])
        else:  # side_wide
            deck.pending_draw = deck.pending_draw[1:]
            deck.capabilities_in_play.append(cid)
            return ({"card": cid, "outcome": "side_capability_in_play"}, [])

    # Subsequent Levy: implement as event (top half).
    persistence = card["event_persistence"]
    if persistence == "hold":
        deck.pending_draw = deck.pending_draw[1:]
        deck.holds.append(cid)
        return ({"card": cid, "outcome": "held"}, [])
    if persistence == "this_levy":
        # Phase 4c: this_levy events that have an immediate effect
        # (R11 Valdemar, R17 Dietrich) resolve their effect now AND
        # leave a tracking entry in this_levy_events so end-of-Levy
        # discard (3.5.3) cleans the block list.
        from nevsky.events import resolve_immediate_event
        # SMOKE-010: resolver may raise; if it does, leave pending_draw
        # untouched so the agent can retry with corrected args.
        result = resolve_immediate_event(state, cid, args)
        deck.pending_draw = deck.pending_draw[1:]
        deck.this_levy_events.append(cid)
        return ({"card": cid, "outcome": "this_levy_event", "effect": result}, [])
    if persistence == "this_campaign":
        deck.pending_draw = deck.pending_draw[1:]
        deck.this_campaign_events.append(cid)
        return ({"card": cid, "outcome": "this_campaign_event"}, [])
    # immediate -- resolve effect FIRST (may raise; then card stays
    # in pending_draw for retry) then commit pop and discard.
    from nevsky.events import resolve_immediate_event
    result = resolve_immediate_event(state, cid, args)
    deck.pending_draw = deck.pending_draw[1:]
    deck.discard.append(cid)
    return ({"card": cid, "outcome": "immediate_event_discarded", "effect": result}, [])


def _h_aow_discard_this_levy(
    state: GameState, side: str, args: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """3.5.3 -- discard all This-Levy events for the actor's side."""
    sd = _require_side_player(state, side)
    _require_levy_phase(state)
    _require_levy_step(state, "call_to_arms")

    deck = _side_deck(state, sd)
    discarded = list(deck.this_levy_events)
    deck.discard.extend(discarded)
    deck.this_levy_events = []
    return ({"discarded": discarded}, [])


# ---------------------------------------------------------------------------
# 3.2 Pay handlers
# ---------------------------------------------------------------------------


def _is_friendly_locale(state: GameState, locale_id: str, side: Side) -> bool:
    """Friendly Locale per 1.3.1.

    All four required:
      - Locale in own territory OR Conquered Stronghold by own side.
      - No enemy Lord at the Locale.
      - No enemy Stronghold at the Locale (covered by Conquered logic).
      - No enemy Conquered marker at the Locale.
    A Siege Locale is never Friendly.
    """
    from nevsky.static_data import load_locales

    static = load_locales()[locale_id]
    loc = state.locales[locale_id]
    if loc.siege_markers > 0:
        return False
    own_terr = static["territory"] == ("teutonic" if side == "teutonic" else "russian")
    own_conquered = (
        loc.teutonic_conquered > 0 if side == "teutonic" else loc.russian_conquered > 0
    )
    if not (own_terr or own_conquered):
        return False
    enemy_conquered = (
        loc.russian_conquered > 0 if side == "teutonic" else loc.teutonic_conquered > 0
    )
    if enemy_conquered:
        return False
    for lord in state.lords.values():
        if lord.state == "mustered" and lord.location == locale_id and lord.side != side:
            return False
    return True


def _is_besieged(state: GameState, lord_id: str) -> bool:
    """A Lord is Besieged when he is INSIDE a Stronghold (in_stronghold=True)
    at a Locale with siege_markers > 0 (4.3.5). A besieging Lord at the
    same Locale is NOT Besieged: he is the besieger.
    """
    lord = state.lords[lord_id]
    if lord.state != "mustered" or lord.location is None:
        return False
    if not lord.in_stronghold:
        return False
    return state.locales[lord.location].siege_markers > 0


def _shift_service_right(state: GameState, lord_id: str, boxes: int) -> int:
    """Shift a Lord's Service marker `boxes` boxes to the right.

    Returns the resulting box index (1..16). Past 16 lands in
    calendar.off_right (rule 2.2.3). The Service marker is identified
    on the Calendar by the lord_id string in `service_markers` lists.
    """
    cal = state.calendar
    # Find current Service-marker box; off_right_service covers past-right.
    cur_box: int | None = None
    if lord_id in cal.off_right_service:
        cur_box = 17
    else:
        for cb in cal.boxes:
            if lord_id in cb.service_markers:
                cur_box = cb.box
                cal.boxes[cb.box - 1].service_markers.remove(lord_id)
                break
    if cur_box is None:
        raise IllegalAction(
            "no_service_marker",
            f"{lord_id} has no Service marker on Calendar",
        )
    if cur_box == 17:
        cal.off_right_service.remove(lord_id)
    new_box = cur_box + boxes
    if new_box > 16:
        cal.off_right_service.append(lord_id)
        result_box = 17
    else:
        cal.boxes[new_box - 1].service_markers.append(lord_id)
        result_box = new_box

    # Advanced Vassal Service (3.4.2): shift all this Lord's on-Calendar
    # Vassal markers the same number of boxes in the same direction.
    if state.meta.optional_rules.get("advanced_vassal_service", False):
        if lord_id in state.lords:
            for vid, vstate in state.lords[lord_id].vassals.items():
                if not vstate.on_calendar or vstate.calendar_box is None:
                    continue
                # Find and remove from current calendar box.
                old_box = vstate.calendar_box
                if 1 <= old_box <= 16:
                    cb = cal.boxes[old_box - 1]
                    if vid in cb.vassal_service_markers:
                        cb.vassal_service_markers.remove(vid)
                # Compute new box (same shift amount, may go off-right).
                target = old_box + boxes
                if target > 16:
                    # Per rule 2.2.3, vassal markers off-right are still
                    # tracked. We don't have an off_right_vassal list;
                    # use calendar_box=17 as a sentinel.
                    vstate.calendar_box = 17
                elif target < 1:
                    vstate.calendar_box = 0
                else:
                    cal.boxes[target - 1].vassal_service_markers.append(vid)
                    vstate.calendar_box = target
    return result_box


def _h_pay_with_coin(
    state: GameState, side: str, args: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """3.2.1 Pay with Coin.

    args:
      from: "lord:<id>" or "veche" (Russian only)
      target_lord: Lord whose Service marker is shifted
      units: number of Coin to spend (>=1)

    Eligible targets:
      - paying Lord's own Service
      - Service of another Lord at SAME locale
      - if from veche: any Russian Lord who is not Besieged
    Besieged constraint: a Besieged Lord's Service can be shifted only
    by his own Coin or Coin from another Lord besieged TOGETHER.
    """
    sd = _require_side_player(state, side)
    _require_levy_phase(state)
    _require_levy_step(state, "pay")
    _require_active(state, sd)

    src = args.get("from")
    target_id = args.get("target_lord")
    units = args.get("units", 1)
    if not isinstance(src, str) or not isinstance(target_id, str) or not isinstance(units, int):
        raise IllegalAction("missing_arg", "args: from (str), target_lord (str), units (int)")
    if units < 1:
        raise IllegalAction("bad_units", "units must be >= 1")
    if target_id not in state.lords:
        raise IllegalAction("bad_target", f"unknown target_lord {target_id!r}")
    target = state.lords[target_id]
    if target.state != "mustered":
        raise IllegalAction("bad_target", f"{target_id} is not Mustered")
    if target.side != sd:
        raise IllegalAction("bad_target", f"{target_id} is not on your side")

    if src == "veche":
        if sd != "russian":
            raise IllegalAction("bad_source", "only Russians may spend Veche Coin (3.2.1)")
        if state.veche.coin < units:
            raise IllegalAction(
                "insufficient_funds",
                f"Veche has {state.veche.coin} Coin; need {units}",
            )
        if _is_besieged(state, target_id):
            raise IllegalAction(
                "veche_cannot_reach_besieged",
                f"{target_id} is Besieged; Veche Coin cannot reach (3.2.1)",
            )
        state.veche.coin -= units
        new_box = _shift_service_right(state, target_id, units)
        return (
            {"source": "veche", "target_lord": target_id, "units": units, "new_box": new_box},
            [],
        )

    # from = "lord:<id>"
    if not src.startswith("lord:"):
        raise IllegalAction("bad_source", "from must be 'veche' or 'lord:<id>'")
    payer_id = src.split(":", 1)[1]
    if payer_id not in state.lords:
        raise IllegalAction("bad_source", f"unknown payer {payer_id!r}")
    payer = state.lords[payer_id]
    if payer.state != "mustered" or payer.side != sd:
        raise IllegalAction("bad_source", f"{payer_id} must be your Mustered Lord")
    if payer.assets.get("coin", 0) < units:
        raise IllegalAction(
            "insufficient_funds",
            f"{payer_id} has {payer.assets.get('coin', 0)} Coin; need {units}",
        )

    target_besieged = _is_besieged(state, target_id)
    payer_besieged = _is_besieged(state, payer_id)
    if target_besieged:
        # only own Coin, or Coin from another Lord besieged WITH target
        if payer_id != target_id:
            if not payer_besieged or payer.location != target.location:
                raise IllegalAction(
                    "besieged_pay_constraint",
                    "Besieged Lord's Service can be shifted only by his own Coin "
                    "or Coin from another Lord besieged with him (3.2.1)",
                )
    else:
        # eligible: own Service or another Lord at same locale
        if payer_id != target_id:
            if payer.location is None or payer.location != target.location:
                raise IllegalAction(
                    "pay_target_not_collocated",
                    "Lord-Coin can only Pay own Service or co-located Lord's Service (3.2.1)",
                )

    payer.assets["coin"] = payer.assets.get("coin", 0) - units
    if payer.assets["coin"] == 0:
        del payer.assets["coin"]
    new_box = _shift_service_right(state, target_id, units)
    return (
        {
            "source": f"lord:{payer_id}",
            "target_lord": target_id,
            "units": units,
            "new_box": new_box,
        },
        [],
    )


def _h_pay_with_loot(
    state: GameState, side: str, args: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """3.2.2 Pay with Loot.

    args: from_lord, target_lord, units. Loot may only be spent at a
    Friendly Locale (1.3.1). Eligible targets: paying Lord's own Service
    or Service of another Lord at SAME Friendly Locale. Sieges excluded.
    """
    sd = _require_side_player(state, side)
    _require_levy_phase(state)
    _require_levy_step(state, "pay")
    _require_active(state, sd)

    payer_id = args.get("from_lord")
    target_id = args.get("target_lord")
    units = args.get("units", 1)
    if not (isinstance(payer_id, str) and isinstance(target_id, str) and isinstance(units, int)):
        raise IllegalAction("missing_arg", "args: from_lord, target_lord, units")
    if units < 1:
        raise IllegalAction("bad_units", "units must be >= 1")
    for lid in (payer_id, target_id):
        if lid not in state.lords:
            raise IllegalAction("bad_target", f"unknown lord {lid!r}")
        if state.lords[lid].state != "mustered" or state.lords[lid].side != sd:
            raise IllegalAction("bad_target", f"{lid} must be your Mustered Lord")

    payer = state.lords[payer_id]
    target = state.lords[target_id]
    if payer.assets.get("loot", 0) < units:
        raise IllegalAction(
            "insufficient_funds",
            f"{payer_id} has {payer.assets.get('loot', 0)} Loot; need {units}",
        )
    if payer.location is None or not _is_friendly_locale(state, payer.location, sd):
        raise IllegalAction(
            "loot_locale_constraint",
            f"{payer_id} must be at a Friendly Locale to Pay with Loot (3.2.2)",
        )
    if payer_id != target_id and (target.location != payer.location):
        raise IllegalAction(
            "pay_target_not_collocated",
            "Loot can Pay own Service or co-located Lord's Service only (3.2.2)",
        )

    payer.assets["loot"] = payer.assets.get("loot", 0) - units
    if payer.assets["loot"] == 0:
        del payer.assets["loot"]
    new_box = _shift_service_right(state, target_id, units)
    return ({"from_lord": payer_id, "target_lord": target_id, "units": units, "new_box": new_box}, [])


# ---------------------------------------------------------------------------
# 3.3 Disband handler
# ---------------------------------------------------------------------------


def _h_disband_resolve(
    state: GameState, side: str, args: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Process Disband for the active side (3.3).

    For each Mustered Lord on the active side, locate his Service marker:
      - Service marker LEFT of Levy marker box -> 3.3.1 beyond limit:
        permanently remove Lord (mat, cylinder, vassal markers, this-lord
        capabilities return to deck).
      - Service marker IN SAME box as Levy/Campaign marker -> 3.3.2
        at limit: place cylinder on Calendar SERVICE_RATING boxes RIGHT
        of CURRENT box (during Levy); pool forces/assets, discard cards.
      - Otherwise no Disband.
    """
    from nevsky.static_data import load_lords

    sd = _require_side_player(state, side)
    _require_levy_phase(state)
    _require_levy_step(state, "disband")
    _require_active(state, sd)

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
            # 3.3.1 permanent removal
            _remove_lord_permanently(state, lord_id, static[lord_id])
            permanently_removed.append(lord_id)
        elif sm_box == levy_box:
            # 3.3.2 at-limit Disband, cylinder counts from CURRENT box during Levy
            srating = int(static[lord_id]["ratings"]["service"])
            new_box = sm_box + srating  # current_box + service rating (during Levy)
            _disband_at_limit(state, lord_id, new_box)
            disbanded.append({"lord_id": lord_id, "new_box": min(new_box, 17)})

    # Advanced Vassal Service (3.4.2 optional): also process Vassal
    # markers — left of current box -> permanent remove + Forces return;
    # at current box -> face-down on mat + Forces return.
    vassal_disband = _advanced_vassal_disband_step(state, sd)

    return ({"permanently_removed": permanently_removed,
             "disbanded": disbanded,
             "vassal_advanced": vassal_disband}, [])


def _find_levy_marker_box(state: GameState) -> int:
    for cb in state.calendar.boxes:
        if cb.has_levy_campaign_marker:
            return cb.box
    raise IllegalAction("no_levy_marker", "Levy/Campaign marker not on Calendar")


def _find_service_marker_box(state: GameState, lord_id: str) -> int | None:
    if lord_id in state.calendar.off_right_service:
        return 17
    if lord_id in state.calendar.off_left_service:
        return 0
    for cb in state.calendar.boxes:
        if lord_id in cb.service_markers:
            return cb.box
    return None


def _remove_lord_permanently(state: GameState, lord_id: str, sl: dict[str, Any]) -> None:
    """3.3.1: permanent removal of a Lord.

    - Lord state -> 'removed', forces/assets cleared, vassals cleared.
    - Cylinder removed from Calendar.
    - Service marker removed from Calendar.
    - This-lord capabilities returned to side's deck (3.4.4).
    - Pleskau: +1 VP per enemy Lord removed (calendar.pleskau_lords_
      removed_* counters; +1 to the OPPOSING side's tally).
    """
    lord = state.lords[lord_id]
    side: Side = lord.side
    # Skip double-counting if already removed.
    if lord.state == "removed":
        return
    # Pleskau bonus: increment counter for the OTHER side.
    # SMOKE-024 (Round 36): also mirror the bonus into the
    # calendar.<other_side>_vp incremental float, since
    # determine_scenario_winner reads that float (not _compute_vp from
    # markers). Without this mirror, the Pleskau "+1 VP per enemy Lord
    # removed" rule didn't reach the winner determination at all.
    if state.meta.special_rules.get("victory_lord_removed_bonus", False):
        if side == "russian":
            state.calendar.pleskau_lords_removed_russian += 1
            state.calendar.teutonic_vp += 1.0
        else:
            state.calendar.pleskau_lords_removed_teutonic += 1
            state.calendar.russian_vp += 1.0
        from nevsky.scenarios import refresh_victory_markers
        refresh_victory_markers(state)
    deck = _side_deck(state, side)
    for cid in lord.this_lord_capabilities:
        deck.deck.append(cid)
    lord.this_lord_capabilities = []
    lord.forces = {}
    lord.assets = {}
    cal = state.calendar
    # SMOKE-038 (Round 50): remove Vassal Service markers from the
    # Calendar before clearing the vassals dict, mirroring the
    # _disband_at_limit treatment.
    for vid, v in lord.vassals.items():
        if v.on_calendar and v.calendar_box is not None:
            if 1 <= v.calendar_box <= 16:
                if vid in cal.boxes[v.calendar_box - 1].vassal_service_markers:
                    cal.boxes[v.calendar_box - 1].vassal_service_markers.remove(vid)
    lord.vassals = {}
    lord.state = "removed"
    lord.location = None
    for cb in cal.boxes:
        if lord_id in cb.cylinders:
            cb.cylinders.remove(lord_id)
        if lord_id in cb.service_markers:
            cb.service_markers.remove(lord_id)
    if lord_id in cal.off_left:
        cal.off_left.remove(lord_id)
    if lord_id in cal.off_right:
        cal.off_right.remove(lord_id)
    if lord_id in cal.off_left_service:
        cal.off_left_service.remove(lord_id)
    if lord_id in cal.off_right_service:
        cal.off_right_service.remove(lord_id)
    # SMOKE-033 (Round 46): Marshal/Lieutenant unstack on removal
    # (Sequence of Play 4.1.3: "if either is removed/Disbanded, the
    # survivor reverts to a normal Lord"). Clear the partner's pointer
    # and this Lord's own stack pointers; otherwise the surviving
    # Marshal still believes it has a Lower Lord (blocking new
    # stacking and warping group-move behavior).
    if lord.lieutenant_of is not None:
        partner_id = lord.lieutenant_of
        partner = state.lords.get(partner_id)
        if partner is not None and partner.has_lower_lord == lord_id:
            partner.has_lower_lord = None
        lord.lieutenant_of = None
    if lord.has_lower_lord is not None:
        partner_id = lord.has_lower_lord
        partner = state.lords.get(partner_id)
        if partner is not None and partner.lieutenant_of == lord_id:
            partner.lieutenant_of = None
        lord.has_lower_lord = None
    # SMOKE-055 (Round 64): Rule 5.2 Campaign Victory — "If at any
    # moment during a Campaign one side has zero Mustered Lords on
    # the map, the game ends immediately." Check after each
    # permanent removal during Campaign and short-circuit the game
    # state. Skip during Levy (Disband at 3.3.1 also calls this
    # helper; the rule specifies Campaign-only).
    if state.meta.phase == "campaign":
        teu = sum(1 for L in state.lords.values()
                  if L.side == "teutonic" and L.state == "mustered")
        rus = sum(1 for L in state.lords.values()
                  if L.side == "russian" and L.state == "mustered")
        if teu == 0 or rus == 0:
            state.meta.campaign_step = "done"
            state.campaign_turn.actions_remaining = 0
            state.campaign_turn.active_card = None
            state.campaign_turn.active_lord = None
            state.campaign_turn.in_feed_pay_disband = False


def _advanced_vassal_disband_step(state: GameState, side: str) -> dict[str, Any]:
    """Apply Advanced Vassal Service (3.4.2) Disband cleanup for `side`.

    Per the rule:
      - Vassal markers LEFT of current box: permanently remove. Return
        the Vassal's Forces from the Lord's mat to the pool. If that
        leaves the Lord without Forces, Disband him (1.6).
      - Vassal markers IN the current box (Service limit): move to
        Lord's mat face-down (Unready) and return Forces to pool too.
        After the next Vassal Muster step, face-down markers flip up.
      - Vassal markers RIGHT of current box: keep on Calendar.

    Returns a result dict tracking removals and downgrades.
    """
    from nevsky.static_data import load_lords
    if not state.meta.optional_rules.get("advanced_vassal_service", False):
        return {"side": side, "removed": [], "to_mat_unready": [],
                "lord_disbanded_due_to_no_forces": []}
    static = load_lords()
    levy_box = _find_levy_marker_box(state)
    cal = state.calendar
    removed: list[dict[str, Any]] = []
    to_mat_unready: list[dict[str, Any]] = []
    lord_disbanded: list[str] = []

    # Iterate per-Lord on this side.
    for lord_id, lord in list(state.lords.items()):
        if lord.side != side or lord.state != "mustered":
            continue
        sl = static.get(lord_id, {})
        for vid, vstate in list(lord.vassals.items()):
            if not vstate.on_calendar or vstate.calendar_box is None:
                continue
            box = vstate.calendar_box
            vdata = next((v for v in sl.get("vassals", [])
                           if v["vassal_id"] == vid), None)
            if vdata is None:
                continue
            v_forces = vdata.get("forces", {}) or {}
            if box < levy_box:
                # Permanent removal.
                # Remove marker from calendar (could be on a box or off-right=17).
                if 1 <= box <= 16 and vid in cal.boxes[box - 1].vassal_service_markers:
                    cal.boxes[box - 1].vassal_service_markers.remove(vid)
                # Return Forces to pool: subtract from Lord's force totals
                # to the degree able.
                returned = {}
                for k, v in v_forces.items():
                    avail = lord.forces.get(k, 0)
                    take = min(int(v), avail)
                    if take > 0:
                        lord.forces[k] = avail - take
                        if lord.forces[k] == 0:
                            del lord.forces[k]
                        returned[k] = take
                vstate.on_calendar = False
                vstate.calendar_box = None
                vstate.mustered = False
                vstate.ready = False  # Vassal removed; no longer available
                removed.append({"lord_id": lord_id, "vassal_id": vid,
                                 "from_box": box, "returned_forces": returned})
                # If the Lord has no Forces left, Disband him (1.6).
                if not lord.forces:
                    _disband_at_limit(state, lord_id,
                                      _find_service_marker_box(state, lord_id) or levy_box)
                    lord_disbanded.append(lord_id)
            elif box == levy_box:
                # At Service limit: move to mat face-down (Unready) and
                # return Forces.
                if vid in cal.boxes[box - 1].vassal_service_markers:
                    cal.boxes[box - 1].vassal_service_markers.remove(vid)
                returned = {}
                for k, v in v_forces.items():
                    avail = lord.forces.get(k, 0)
                    take = min(int(v), avail)
                    if take > 0:
                        lord.forces[k] = avail - take
                        if lord.forces[k] == 0:
                            del lord.forces[k]
                        returned[k] = take
                vstate.on_calendar = False
                vstate.calendar_box = None
                vstate.mustered = False
                vstate.ready = False  # Coat-of-Arms side down
                to_mat_unready.append({"lord_id": lord_id, "vassal_id": vid,
                                        "from_box": box, "returned_forces": returned})
                if not lord.forces:
                    _disband_at_limit(state, lord_id,
                                      _find_service_marker_box(state, lord_id) or levy_box)
                    lord_disbanded.append(lord_id)
            # else box > levy_box: no change.

    return {
        "side": side, "removed": removed,
        "to_mat_unready": to_mat_unready,
        "lord_disbanded_due_to_no_forces": lord_disbanded,
    }


def _disband_at_limit(state: GameState, lord_id: str, new_box_with_overflow: int) -> None:
    """3.3.2 at-limit Disband.

    - Place cylinder at `new_box_with_overflow` (cap at off_right if >16).
    - Service marker removed (it returns to Lord's mat / Unused area; we
      drop it from the Calendar; mat is implicitly the Lord object).
    - Forces / Assets returned to pool (cleared).
    - This-lord capabilities returned to side's deck.
    - Vassals returned to ready=True, mustered=False, on_calendar=False.
    - Lord state -> 'disbanded'.
    """
    lord = state.lords[lord_id]
    side: Side = lord.side
    deck = _side_deck(state, side)
    for cid in lord.this_lord_capabilities:
        deck.deck.append(cid)
    lord.this_lord_capabilities = []
    lord.forces = {}
    lord.assets = {}
    cal = state.calendar
    # SMOKE-038 (Round 50): remove Vassal Service markers from the
    # Calendar before clearing the per-vassal flags. Otherwise the
    # marker stays on the Calendar even though VassalState says
    # on_calendar=False, which breaks later Vassal-marker reads (3.4.2
    # Advanced Vassal Service).
    for vid, v in lord.vassals.items():
        if v.on_calendar and v.calendar_box is not None:
            if 1 <= v.calendar_box <= 16:
                if vid in cal.boxes[v.calendar_box - 1].vassal_service_markers:
                    cal.boxes[v.calendar_box - 1].vassal_service_markers.remove(vid)
        v.ready = True
        v.mustered = False
        v.on_calendar = False
        v.calendar_box = None
    lord.state = "disbanded"
    lord.location = None
    lord.lordship_used = 0
    # Remove service marker from Calendar (boxes + off_*_service).
    for cb in cal.boxes:
        if lord_id in cb.service_markers:
            cb.service_markers.remove(lord_id)
    if lord_id in cal.off_left_service:
        cal.off_left_service.remove(lord_id)
    if lord_id in cal.off_right_service:
        cal.off_right_service.remove(lord_id)
    # Remove cylinder from current location, then place at new_box.
    for cb in cal.boxes:
        if lord_id in cb.cylinders:
            cb.cylinders.remove(lord_id)
    if lord_id in cal.off_left:
        cal.off_left.remove(lord_id)
    if lord_id in cal.off_right:
        cal.off_right.remove(lord_id)
    # SMOKE-018 (Round 32): explicit bounds check. Production paths
    # (Levy disband, Campaign FPD disband) always compute new_box >= 2,
    # but a defensive guard prevents silent Python negative-index wrap
    # to box 16 if a future caller passes 0 or negative.
    if new_box_with_overflow > 16:
        cal.off_right.append(lord_id)
    elif new_box_with_overflow < 1:
        cal.off_left.append(lord_id)
    else:
        cal.boxes[new_box_with_overflow - 1].cylinders.append(lord_id)
    # SMOKE-033 (Round 46): Marshal/Lieutenant unstack on Disband
    # (Sequence of Play 4.1.3: "if either is removed/Disbanded, the
    # survivor reverts to a normal Lord"). A Lord exiting the Mustered
    # state must release any stack partner; otherwise the surviving
    # partner retains a dangling pointer that survives across Levy and
    # would have to be cleared by the End-Campaign reset (4.9.5), which
    # is too late.
    if lord.lieutenant_of is not None:
        partner_id = lord.lieutenant_of
        partner = state.lords.get(partner_id)
        if partner is not None and partner.has_lower_lord == lord_id:
            partner.has_lower_lord = None
        lord.lieutenant_of = None
    if lord.has_lower_lord is not None:
        partner_id = lord.has_lower_lord
        partner = state.lords.get(partner_id)
        if partner is not None and partner.lieutenant_of == lord_id:
            partner.lieutenant_of = None
        lord.has_lower_lord = None


# ---------------------------------------------------------------------------
# 3.4 Muster handlers
# ---------------------------------------------------------------------------


def _seats_of(state: GameState, lord_id: str) -> list[str]:
    """All Seats for `lord_id` (primary + active conditional). 3.4.1.

    Conditional seat schema (lords.json):
      {capability, scope}             -> active when capability in play
      {capability, locale_id}         -> single locale gated by capability
      {capability, locale_id, requirement} -> single locale gated by capability
                                              and a locale-state requirement
    Capability ids in conditional_seats use the "<CARD>_<slug>" form
    (e.g. "T12_ordensburgen", "R15_archbishopric"); we strip the suffix
    to compare against the side\'s capabilities_in_play list of card ids.
    """
    from nevsky.static_data import load_locales, load_lords

    sl = load_lords()[lord_id]
    side: Side = sl["side"]
    sd = _side_deck(state, side)
    seats: list[str] = list(sl.get("primary_seats", []))
    static_locales = load_locales()
    for c in sl.get("conditional_seats", []):
        cap = c.get("capability")
        cap_card = cap.split("_", 1)[0] if isinstance(cap, str) else None
        cap_active = (
            cap_card is None
            or cap_card in sd.capabilities_in_play
            or cap_card in state.lords[lord_id].this_lord_capabilities
        )
        if not cap_active:
            continue
        scope = c.get("scope")
        if scope == "all_commanderies":
            # AUDIT-006 (Round 9): the rules (1.3.1, T12 Ordensburgen)
            # define Commanderies as Strongholds with the Order seat
            # symbol. Per Playbook (pages 5/6/8/36), the confirmed set
            # is Wenden, Fellin, Adsel, and Leal. Locales now carry a
            # `commandery: true` flag rather than relying on a
            # non-existent `type == "commandery"` (the Locale's actual
            # type — Castle, Bishopric — is preserved for Stronghold
            # mechanics). See Q-004 for full-list verification.
            for loc_id, loc in static_locales.items():
                if loc.get("commandery") and loc.get("territory") in ("teutonic", "crusader"):
                    seats.append(loc_id)
        elif scope == "all_russian_lords_novgorod_extra_seat":
            seats.append("novgorod")
        if "locale_id" in c:
            req = c.get("requirement")
            if req == "pskov_conquered_by_teutons":
                if state.locales.get("pskov") and state.locales["pskov"].teutonic_conquered > 0:
                    seats.append(c["locale_id"])
            elif req is None:
                seats.append(c["locale_id"])
    # de-dupe preserving order
    seen: set[str] = set()
    out: list[str] = []
    for s_ in seats:
        if s_ in seen:
            continue
        seen.add(s_)
        out.append(s_)
    return out


def _free_seats_for(state: GameState, lord_id: str) -> list[str]:
    """Return list of Free Seats for `lord_id` -- Seats free of enemy
    Lords AND not Conquered by enemy (3.4.1)."""
    from nevsky.static_data import load_lords

    sl = load_lords()[lord_id]
    side: Side = sl["side"]
    seats = _seats_of(state, lord_id)
    free: list[str] = []
    for sid in seats:
        if sid not in state.locales:
            continue
        loc = state.locales[sid]
        if side == "teutonic" and loc.russian_conquered > 0:
            continue
        if side == "russian" and loc.teutonic_conquered > 0:
            continue
        enemy_present = any(
            l.state == "mustered" and l.location == sid and l.side != side
            for l in state.lords.values()
        )
        if enemy_present:
            continue
        free.append(sid)
    return free


def _conditional_seat_satisfied(state: GameState, lord_id: str, c: dict[str, Any]) -> bool:
    """Compatibility wrapper for legacy callers; uses _seats_of internally
    by checking whether c\'s implied locale_id is in the active seats list.
    """
    seats = _seats_of(state, lord_id)
    if "locale_id" in c:
        return c["locale_id"] in seats
    return True


def _spend_lordship(state: GameState, lord_id: str) -> None:
    """Decrement an action against a Lord's Lordship budget (3.4)."""
    from nevsky.static_data import load_lords

    sl = load_lords()[lord_id]
    lord = state.lords[lord_id]
    if lord.state != "mustered":
        raise IllegalAction("not_mustered", f"{lord_id} is not Mustered")
    if lord.just_arrived_this_levy:
        raise IllegalAction(
            "just_arrived",
            f"{lord_id} arrived this Levy and cannot use Lordship in same Muster (3.4)",
        )
    if _is_besieged(state, lord_id):
        raise IllegalAction(
            "besieged_no_muster",
            f"{lord_id} is Besieged; cannot Muster (3.4 actor_eligibility)",
        )
    if lord.location is None or not _is_friendly_locale(state, lord.location, lord.side):
        raise IllegalAction(
            "muster_location",
            f"{lord_id} must be at a Friendly Locale to use Lordship (3.4)",
        )
    # Phase 4c: this-levy block (R11 Valdemar, R17 Dietrich).
    block = (
        state.meta.block_lords_this_levy_t
        if lord.side == "teutonic"
        else state.meta.block_lords_this_levy_r
    )
    if lord_id in block:
        raise IllegalAction(
            "blocked_this_levy",
            f"{lord_id} cannot use Lordship this Levy (R11 / R17)",
        )
    base = int(sl["ratings"]["lordship"])
    bonus = int(state.meta.lordship_bonus.get(lord_id, 0))
    budget = base + bonus
    if lord.lordship_used >= budget:
        raise IllegalAction(
            "lordship_exhausted",
            f"{lord_id} has spent {lord.lordship_used}/{budget} Lordship this Muster",
        )
    lord.lordship_used += 1


def _h_muster_lord(
    state: GameState, side: str, args: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """3.4.1 Muster a Ready Lord at a Free Seat. Costs 1 Lordship.

    args:
      by_lord    Lord spending his Lordship (must be Mustered, not Besieged)
      target_lord Ready Lord with at least one Free Seat
      seat       chosen Free Seat (locale_id)
    Roll d6: success on roll <= target.fealty.
    On success: place cylinder at Seat, deploy starting forces/assets/
    vassals, place Service marker SERVICE_RATING boxes RIGHT of Levy box.
    Aleksandr exception: NEVER Muster by Lord (3.4.1).
    """
    from nevsky.rng import roll_d6
    from nevsky.static_data import load_lords

    sd = _require_side_player(state, side)
    _require_levy_phase(state)
    _require_levy_step(state, "muster")
    _require_active(state, sd)

    by_id = args.get("by_lord")
    target_id = args.get("target_lord")
    seat = args.get("seat")
    for k, v in (("by_lord", by_id), ("target_lord", target_id), ("seat", seat)):
        if not isinstance(v, str):
            raise IllegalAction("missing_arg", f"args.{k} must be a string")

    if by_id not in state.lords or state.lords[by_id].side != sd:
        raise IllegalAction("bad_actor", f"{by_id} must be your Lord")
    if target_id not in state.lords or state.lords[target_id].side != sd:
        raise IllegalAction("bad_target", f"{target_id} must be on your side")
    if target_id == "aleksandr":
        raise IllegalAction(
            "aleksandr_veche_only",
            "Aleksandr can only enter play via Veche auto-Muster (3.4.1, 3.5.2)",
        )
    block = (
        state.meta.block_lords_this_levy_t
        if sd == "teutonic"
        else state.meta.block_lords_this_levy_r
    )
    if target_id in block:
        raise IllegalAction(
            "blocked_this_levy",
            f"{target_id} cannot be Mustered this Levy (R11 / R17)",
        )

    target = state.lords[target_id]
    if target.state != "ready":
        raise IllegalAction("bad_target", f"{target_id} state is {target.state} (not 'ready')")

    levy_box = _find_levy_marker_box(state)
    cyl_box = _find_cylinder_box(state, target_id)
    if cyl_box is None or cyl_box > levy_box:
        raise IllegalAction(
            "not_ready",
            f"{target_id} cylinder is at {cyl_box}; Levy is at {levy_box}; not Ready (3.4.1)",
        )

    free = _free_seats_for(state, target_id)
    if seat not in free:
        raise IllegalAction(
            "no_free_seat",
            f"{seat} is not a Free Seat for {target_id}. Free: {free}",
        )

    # Spend Lordship before rolling. (Failed roll still consumes the action.)
    _spend_lordship(state, by_id)
    roll = roll_d6(state)
    fealty = int(load_lords()[target_id]["ratings"]["fealty"])
    success = roll <= fealty
    dice = [{"d6": roll, "vs_fealty": fealty, "success": success}]
    if not success:
        return (
            {
                "outcome": "fealty_failed",
                "by_lord": by_id,
                "target_lord": target_id,
                "seat": seat,
                "roll": roll,
                "fealty": fealty,
            },
            dice,
        )

    _place_lord_on_map(state, target_id, seat, levy_box)
    return (
        {
            "outcome": "mustered",
            "by_lord": by_id,
            "target_lord": target_id,
            "seat": seat,
            "roll": roll,
            "fealty": fealty,
        },
        dice,
    )


def _find_cylinder_box(state: GameState, lord_id: str) -> int | None:
    if lord_id in state.calendar.off_right:
        return 17
    if lord_id in state.calendar.off_left:
        return 0
    for cb in state.calendar.boxes:
        if lord_id in cb.cylinders:
            return cb.box
    return None


def _place_lord_on_map(state: GameState, lord_id: str, seat: str, levy_box: int) -> None:
    """Apply the on-success Muster procedure (3.4.1)."""
    from nevsky.static_data import load_lords

    sl = load_lords()[lord_id]
    lord = state.lords[lord_id]
    cal = state.calendar
    # Remove cylinder from Calendar.
    for cb in cal.boxes:
        if lord_id in cb.cylinders:
            cb.cylinders.remove(lord_id)
    if lord_id in cal.off_left:
        cal.off_left.remove(lord_id)
    if lord_id in cal.off_right:
        cal.off_right.remove(lord_id)
    # Place mat in front: deploy starting forces/assets.
    forces: dict[ForceType, int] = {
        k: int(v) for k, v in sl["starting_forces"].items() if int(v) != 0
    }
    assets: dict[AssetType, int] = {
        k: int(v) for k, v in sl["starting_assets"].items() if int(v) != 0
    }
    lord.forces = forces  # type: ignore[assignment]
    lord.assets = assets  # type: ignore[assignment]
    lord.location = seat
    lord.state = "mustered"
    lord.just_arrived_this_levy = True
    lord.lordship_used = 0
    # SMOKE-037 (Round 48): a fresh Muster places the Lord at a Seat in
    # the open. Clear flags that could be stale from a prior Mustered
    # life (Disbanded -> re-Mustered cycle).
    lord.in_stronghold = False
    lord.first_march_used_this_card = False
    lord.raiders_used_this_card = False
    # Vassal Service markers face up where their Capability is in effect;
    # special vassals stay aside if their gating Capability is not in
    # effect (Steppe Warriors / Crusade).
    for v in sl.get("vassals", []):
        special = v.get("special")
        ready = special is None
        if special == "summer_crusaders":
            ready = "T11" in state.decks.teutonic.capabilities_in_play
        elif special == "steppe_warriors":
            # Mongols/Kipchaqs require R10 Steppe Warriors in play
            # (3.4.2). The static data tags them as "steppe_warriors";
            # earlier code mistakenly looked for "mongols"/"kipchaqs"
            # which never matched (SMOKE-012 fix).
            ready = "R10" in state.decks.russian.capabilities_in_play
        lord.vassals[v["vassal_id"]].ready = ready
        lord.vassals[v["vassal_id"]].mustered = False
    # Place Service marker at SERVICE_RATING boxes right of Levy box.
    srating = int(sl["ratings"]["service"])
    sm_box = levy_box + srating
    # Drop any existing service marker.
    for cb in cal.boxes:
        if lord_id in cb.service_markers:
            cb.service_markers.remove(lord_id)
    if lord_id in cal.off_right_service:
        cal.off_right_service.remove(lord_id)
    if sm_box > 16:
        cal.off_right_service.append(lord_id)
    else:
        cal.boxes[sm_box - 1].service_markers.append(lord_id)

    # Q-002: emit setup_transport_choice PendingDecisions for any
    # starting_transport_choice slots on the Lord's mat. Apply the
    # heuristic default per Q-001 / Q-002 spec; the player may override.
    from nevsky.scenarios import (
        _SETUP_TRANSPORT_DEFAULTS,
        _Q001_NO_AUTO_CONFIRM,
        _heuristic_setup_transport_default,
    )
    scenario_id = state.meta.scenario_id
    season = _season_of_box(state.meta.box)
    scenario_defaults = _SETUP_TRANSPORT_DEFAULTS.get(scenario_id, {}).get(lord_id, [])
    no_auto = lord_id in _Q001_NO_AUTO_CONFIRM.get(scenario_id, set())
    slot_count_total = sum(int(slot["count"]) for slot in sl.get("starting_transport_choice", []))
    if slot_count_total > 0:
        first_slot_allowed = list(sl["starting_transport_choice"][0]["options"])
        heuristic = _heuristic_setup_transport_default(
            scenario_id, lord_id, seat, season,
            slot_count_total, first_slot_allowed,
        )
    else:
        heuristic = []
    slot_idx_global = 0
    from nevsky.state import PendingDecision
    for slot in sl.get("starting_transport_choice", []):
        allowed = list(slot["options"])
        count = int(slot["count"])
        for _ in range(count):
            if slot_idx_global < len(scenario_defaults):
                chosen = scenario_defaults[slot_idx_global]
            elif slot_idx_global < len(heuristic):
                chosen = heuristic[slot_idx_global]
            else:
                chosen = allowed[0]
            if chosen not in allowed:
                chosen = allowed[0]
            lord.assets[chosen] = lord.assets.get(chosen, 0) + 1  # type: ignore[index]
            state.pending_decisions.append(
                PendingDecision(
                    kind="setup_transport_choice",
                    owed_by=lord.side,
                    context={
                        "lord_id": lord_id,
                        "slot_index": slot_idx_global,
                        "default_value": chosen,
                        "current_value": chosen,
                        "allowed_values": allowed,
                        "auto_confirm_on_levy": not no_auto,
                        "resolved": False,
                        "emitted_at_muster": True,
                    },
                    note=(
                        f"{lord_id} Mustered with Transport-(any) slot {slot_idx_global}; "
                        f"default = {chosen} (Q-001 / Q-002)."
                    ),
                )
            )
            slot_idx_global += 1


def _h_muster_vassal(
    state: GameState, side: str, args: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """3.4.2 Muster a Vassal. Costs 1 Lordship.

    args: by_lord (the parent Lord), vassal_id.
    Vassal must be ready (face up) on by_lord's mat. Vassal's Forces are
    added to the parent's forces dict. Special Vassals require their
    gating Capability in play (R10 Steppe Warriors for Mongols/Kipchaqs;
    T11 Crusade + Summer season for Summer Crusaders).
    """
    from nevsky.static_data import load_lords

    sd = _require_side_player(state, side)
    _require_levy_phase(state)
    _require_levy_step(state, "muster")
    _require_active(state, sd)

    by_id = args.get("by_lord")
    vid = args.get("vassal_id")
    if not (isinstance(by_id, str) and isinstance(vid, str)):
        raise IllegalAction("missing_arg", "args: by_lord, vassal_id")
    if by_id not in state.lords or state.lords[by_id].side != sd:
        raise IllegalAction("bad_actor", f"{by_id} must be your Lord")
    lord = state.lords[by_id]
    if vid not in lord.vassals:
        raise IllegalAction("unknown_vassal", f"{by_id} has no Vassal {vid!r}")
    vstate = lord.vassals[vid]
    if vstate.mustered:
        raise IllegalAction("already_mustered", f"Vassal {vid} already Mustered")

    sl = load_lords()[by_id]
    vdata = next((v for v in sl["vassals"] if v["vassal_id"] == vid), None)
    if vdata is None:
        raise IllegalAction("unknown_vassal", f"static data missing Vassal {vid!r}")

    special = vdata.get("special")
    if special == "summer_crusaders":
        if "T11" not in state.decks.teutonic.capabilities_in_play:
            raise IllegalAction(
                "vassal_gated",
                "Summer Crusaders require T11 Crusade in play (3.4.2)",
            )
        # SMOKE-059 (Round 67): AoW Reference T11 Tip — "Teutons may
        # Levy the Crusade Capability card in any Season, but Crusader
        # Forces still would Muster only in Summer." Reject Muster in
        # non-Summer seasons even when T11 is in play.
        from nevsky.campaign import _season_of_box
        if _season_of_box(state.meta.box) != "summer":
            raise IllegalAction(
                "vassal_season",
                "Summer Crusaders may Muster only in Summer (T11 Tip)",
            )
    elif special == "steppe_warriors":
        # Mongols/Kipchaqs (SMOKE-013 fix: was checking
        # "mongols"/"kipchaqs" which never matched).
        if "R10" not in state.decks.russian.capabilities_in_play:
            raise IllegalAction(
                "vassal_gated",
                "Steppe Warriors (Mongols/Kipchaqs) require R10 in play (3.4.2)",
            )

    if not vstate.ready:
        raise IllegalAction("vassal_unready", f"Vassal {vid} is not face-up Ready")

    _spend_lordship(state, by_id)
    # Add Vassal forces to parent.
    for k, v in vdata.get("forces", {}).items():
        lord.forces[k] = lord.forces.get(k, 0) + int(v)  # type: ignore[index]
    vstate.mustered = True
    # Advanced Vassal Service (3.4.2 optional): place Service marker on
    # Calendar at (current_levy_box + vassal.service) IF that's left of
    # the Lord's Service marker. Otherwise the marker stays on the mat
    # (the default) because the Lord's Service governs.
    if state.meta.optional_rules.get("advanced_vassal_service", False):
        levy_box = _find_levy_marker_box(state)
        v_service = int(vdata.get("service", 0))
        target_box = levy_box + v_service
        lord_svc_box = _find_service_marker_box(state, by_id)
        # off_right_service Lord = effectively box 17.
        lord_svc_box_eff = lord_svc_box if lord_svc_box is not None else 17
        if 1 <= target_box <= 16 and target_box < lord_svc_box_eff:
            # Place Vassal marker on Calendar.
            state.calendar.boxes[target_box - 1].vassal_service_markers.append(vid)
            vstate.on_calendar = True
            vstate.calendar_box = target_box
    return ({"by_lord": by_id, "vassal_id": vid, "added_forces": vdata.get("forces", {})}, [])


def _h_levy_transport(
    state: GameState, side: str, args: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """3.4.3 Levy Transport. 1 Lordship per asset added.

    args: by_lord, transport_type (boat|cart|sled|ship).
    Ship requires by_lord.ships_authorized=True (mat states "Ships").
    Max 8 of any one type per Lord.
    """
    from nevsky.static_data import load_lords

    sd = _require_side_player(state, side)
    _require_levy_phase(state)
    _require_levy_step(state, "muster")
    _require_active(state, sd)

    by_id = args.get("by_lord")
    ttype = args.get("transport_type")
    if not (isinstance(by_id, str) and isinstance(ttype, str)):
        raise IllegalAction("missing_arg", "args: by_lord, transport_type")
    if ttype not in ("boat", "cart", "sled", "ship"):
        raise IllegalAction("bad_transport", f"transport_type {ttype!r} invalid")
    if by_id not in state.lords or state.lords[by_id].side != sd:
        raise IllegalAction("bad_actor", f"{by_id} must be your Lord")

    sl = load_lords()[by_id]
    if ttype == "ship" and not sl.get("ships_authorized", False):
        raise IllegalAction("ship_unauthorized", f"{by_id} mat does not state 'Ships' (3.4.3)")

    lord = state.lords[by_id]
    if lord.assets.get(ttype, 0) >= 8:  # type: ignore[arg-type]
        raise IllegalAction("transport_max", f"{by_id} already at max 8 {ttype} (3.4.3)")

    _spend_lordship(state, by_id)
    lord.assets[ttype] = lord.assets.get(ttype, 0) + 1  # type: ignore[index]
    return ({"by_lord": by_id, "transport_type": ttype, "new_count": lord.assets[ttype]}, [])  # type: ignore[index]


def _check_capability_eligibility(card: dict[str, Any], lord_id: str, role: str) -> None:
    """SMOKE-029: enforce ``capability_eligibility`` printed on the AoW card.

    Reference: ``reference/Nevsky_Arts_of_War_Reference.txt`` header
    (added in commit 44f7694, 2026-05): "For Capabilities, [Eligibility]
    is who may Levy the Capability and who is affected by it (per Rules
    1.9.1 and 3.4.4)."

    Scopes:
      - ``lords``: ``lord_id`` MUST appear in the explicit list.
      - ``any``: any same-side Lord qualifies (caller already side-checked).
      - ``all``: any same-side Lord qualifies (same as ``any`` for gating).
      - ``any_except``: ``lord_id`` MUST NOT appear in ``excluded``.
      - ``none``: events-only marker; capabilities never carry this scope.

    ``role`` is ``"levyer"`` or ``"target"`` for the error code.

    Raises IllegalAction("ineligible_" + role) on violation.
    """
    e = card.get("capability_eligibility")
    if e is None:
        return
    scope = e.get("scope")
    if scope == "lords":
        if lord_id not in e.get("lords", []):
            raise IllegalAction(
                f"ineligible_{role}",
                f"{lord_id} not on {card['card_id']} capability_eligibility "
                f"({e.get('raw', '')}) (3.4.4)",
            )
    elif scope == "any_except":
        if lord_id in e.get("excluded", []):
            raise IllegalAction(
                f"ineligible_{role}",
                f"{lord_id} is excluded from {card['card_id']} "
                f"({e.get('raw', '')}) (3.4.4)",
            )
    # scope in ("any", "all"): no further restriction beyond side (caller).
    # scope == "none": capabilities don't carry this scope; ignore.


def _h_levy_capability(
    state: GameState, side: str, args: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """3.4.4 Levy Capability.

    args:
      by_lord    Lord spending Lordship
      card_id    capability card from own side's deck/discard
      lord_id    (optional) target Lord for this-lord capability
                 (defaults to by_lord)
    For this_lord: tucked under target Lord's mat. Max 2 per Lord; no
    duplicate-named (e.g., T7 + T15 Warrior Monks).
    For side_wide: tucked at side's board edge.
    """
    from nevsky.static_data import load_cards

    sd = _require_side_player(state, side)
    _require_levy_phase(state)
    _require_levy_step(state, "muster")
    _require_active(state, sd)

    by_id = args.get("by_lord")
    cid = args.get("card_id")
    if not (isinstance(by_id, str) and isinstance(cid, str)):
        raise IllegalAction("missing_arg", "args: by_lord, card_id")
    if by_id not in state.lords or state.lords[by_id].side != sd:
        raise IllegalAction("bad_actor", f"{by_id} must be your Lord")

    cards = load_cards()
    if cid not in cards or cards[cid]["side"] != sd:
        raise IllegalAction("bad_card", f"{cid} not in your deck (3.4.4)")
    deck = _side_deck(state, sd)
    # Card must be available (in deck or discard, not held / in play / removed / pending_draw).
    if cid in deck.deck:
        from_loc = "deck"
    elif cid in deck.discard:
        from_loc = "discard"
    else:
        raise IllegalAction(
            "card_unavailable",
            f"{cid} not in your unused pile (deck/discard) (3.4.4)",
        )

    card = cards[cid]
    if card["no_event"]:
        raise IllegalAction("bad_card", "No-Event/No-Capability cards have no Capability (3.4.4)")

    target_lord_id = args.get("lord_id", by_id) if card["capability_scope"] == "this_lord" else None

    # SMOKE-029: enforce capability_eligibility from the AoW Reference
    # (printed Lord coats of arms; AoW Reference header re: Rules 1.9.1
    # and 3.4.4). by_lord must be an eligible Levyer; for this_lord
    # capabilities, target_lord must also be eligible (the card is "who
    # is affected by it").
    _check_capability_eligibility(card, by_id, role="levyer")
    if card["capability_scope"] == "this_lord" and isinstance(target_lord_id, str):
        _check_capability_eligibility(card, target_lord_id, role="target")

    _spend_lordship(state, by_id)

    if card["capability_scope"] == "this_lord":
        if not isinstance(target_lord_id, str) or target_lord_id not in state.lords:
            raise IllegalAction("missing_arg", "this-lord capability requires args.lord_id")
        target = state.lords[target_lord_id]
        if target.side != sd or target.state != "mustered":
            raise IllegalAction("bad_target", f"{target_lord_id} must be your Mustered Lord")
        if len(target.this_lord_capabilities) >= 2:
            raise IllegalAction("cap_limit", f"{target_lord_id} already has 2 capabilities (3.4.4)")
        for existing in target.this_lord_capabilities:
            if cards[existing]["capability_name"] == card["capability_name"]:
                raise IllegalAction(
                    "duplicate_capability",
                    f"{target_lord_id} already has '{card['capability_name']}' (3.4.4)",
                )
        target.this_lord_capabilities.append(cid)
        if from_loc == "deck":
            deck.deck.remove(cid)
        else:
            deck.discard.remove(cid)
        return (
            {
                "by_lord": by_id,
                "card_id": cid,
                "scope": "this_lord",
                "target_lord": target_lord_id,
                "from": from_loc,
            },
            [],
        )
    # side_wide
    deck.capabilities_in_play.append(cid)
    if from_loc == "deck":
        deck.deck.remove(cid)
    else:
        deck.discard.remove(cid)
    return ({"by_lord": by_id, "card_id": cid, "scope": "side_wide", "from": from_loc}, [])


# ---------------------------------------------------------------------------
# 3.5 Call to Arms handlers
# ---------------------------------------------------------------------------


_BISHOPRICS = {"riga", "dorpat", "leal", "reval"}


def _h_legate_arrives(
    state: GameState, side: str, args: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """3.5.1 ARRIVES: place Legate pawn at any of the four Bishoprics.

    Requires William of Modena (T13) Capability in play. Pawn must be
    on the William of Modena card (location='card') at start of Call
    to Arms; the action moves it to the chosen Bishopric.
    """
    sd = _require_side_player(state, side)
    if sd != "teutonic":
        raise IllegalAction("wrong_side", "only Teutons act in 3.5.1 (Papal Legate)")
    _require_levy_phase(state)
    _require_levy_step(state, "call_to_arms")
    _require_active(state, sd)

    if not state.legate.william_of_modena_in_play:
        raise IllegalAction("no_william", "William of Modena (T13) not in play (3.5.1)")
    if state.legate.location != "card":
        raise IllegalAction("legate_already_on_map", "Legate is already on the map (3.5.1)")
    bishopric = args.get("bishopric")
    if bishopric not in _BISHOPRICS:
        raise IllegalAction("bad_bishopric", f"bishopric must be one of {sorted(_BISHOPRICS)}")
    state.legate.location = "locale"
    state.legate.locale_id = bishopric
    return ({"placed_at": bishopric}, [])


def _h_legate_move(
    state: GameState, side: str, args: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """3.5.1 Option 1: move pawn to any Friendly Locale."""
    sd = _require_side_player(state, side)
    if sd != "teutonic":
        raise IllegalAction("wrong_side", "only Teutons act in 3.5.1")
    _require_levy_phase(state)
    _require_levy_step(state, "call_to_arms")
    _require_active(state, sd)

    if not state.legate.william_of_modena_in_play:
        raise IllegalAction("no_william", "William of Modena (T13) not in play (3.5.1)")
    if state.legate.location != "locale":
        raise IllegalAction("legate_off_map", "Legate must be on map to Move (3.5.1)")
    if state.legate.acted_this_call_to_arms:
        raise IllegalAction("already_acted", "Legate has already acted this Call to Arms (3.5.1)")

    locale_id = args.get("locale_id")
    if not isinstance(locale_id, str) or locale_id not in state.locales:
        raise IllegalAction("bad_locale", "args.locale_id required")
    if not _is_friendly_locale(state, locale_id, "teutonic"):
        raise IllegalAction("not_friendly", f"{locale_id} is not Friendly to Teutons (1.3.1)")
    state.legate.locale_id = locale_id
    state.legate.acted_this_call_to_arms = True
    return ({"moved_to": locale_id}, [])


def _h_legate_use(
    state: GameState, side: str, args: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """3.5.1 Option 2: USE the Legate. sub-options 2a/2b/2c.

    args:
      sub_option: "2a" | "2b" | "2c"
      target_lord:  required for 2a, 2b, 2c
    Pawn returns to William of Modena card after use.
    """

    sd = _require_side_player(state, side)
    if sd != "teutonic":
        raise IllegalAction("wrong_side", "only Teutons act in 3.5.1")
    _require_levy_phase(state)
    _require_levy_step(state, "call_to_arms")
    _require_active(state, sd)

    if not state.legate.william_of_modena_in_play:
        raise IllegalAction("no_william", "William of Modena (T13) not in play (3.5.1)")
    if state.legate.location != "locale":
        raise IllegalAction("legate_off_map", "Legate must be on map to USE (3.5.1)")
    if state.legate.acted_this_call_to_arms:
        raise IllegalAction("already_acted", "Legate has already acted this Call to Arms (3.5.1)")

    sub = args.get("sub_option")
    target_id = args.get("target_lord")
    if sub not in ("2a", "2b", "2c"):
        raise IllegalAction("bad_sub_option", "sub_option must be 2a, 2b, or 2c")
    if not isinstance(target_id, str) or target_id not in state.lords:
        raise IllegalAction("missing_arg", "args.target_lord required")

    target = state.lords[target_id]
    if target.side != "teutonic":
        raise IllegalAction("bad_target", "Legate USE targets Teutonic Lord")

    pawn_locale = state.legate.locale_id
    levy_box = _find_levy_marker_box(state)

    if sub == "2a":
        # auto-Muster a Ready Lord at his Seat (no Fealty roll)
        if target.state != "ready":
            raise IllegalAction("bad_target", f"{target_id} must be Ready (state={target.state})")
        cyl_box = _find_cylinder_box(state, target_id)
        if cyl_box is None or cyl_box > levy_box:
            raise IllegalAction("not_ready", f"{target_id} not Ready (3.4.1)")
        if pawn_locale not in _seats_of(state, target_id):
            raise IllegalAction("not_at_seat", f"Legate must be at a Seat of {target_id}")
        free = _free_seats_for(state, target_id)
        if pawn_locale not in free:
            raise IllegalAction("seat_not_free", f"{pawn_locale} is not a Free Seat for {target_id}")
        _place_lord_on_map(state, target_id, pawn_locale, levy_box)  # type: ignore[arg-type]
        result_extra: dict[str, Any] = {"target_lord": target_id, "seat": pawn_locale}
    elif sub == "2b":
        # slide cylinder of a Lord on the Calendar 1 box LEFT, requires
        # pawn at that Lord's Seat
        if pawn_locale not in _seats_of(state, target_id):
            raise IllegalAction("not_at_seat", f"Legate must be at a Seat of {target_id}")
        cyl_box = _find_cylinder_box(state, target_id)
        if cyl_box is None or cyl_box >= 17 or cyl_box == 0:
            raise IllegalAction("no_cylinder", f"{target_id} cylinder not on Calendar")
        if cyl_box <= 1:
            raise IllegalAction("cylinder_at_left_edge", f"{target_id} already at box 1")
        cb = state.calendar.boxes[cyl_box - 1]
        cb.cylinders.remove(target_id)
        state.calendar.boxes[cyl_box - 2].cylinders.append(target_id)
        result_extra = {"target_lord": target_id, "from_box": cyl_box, "to_box": cyl_box - 1}
    else:  # 2c
        if target.state != "mustered" or target.location is None:
            raise IllegalAction("bad_target", f"{target_id} must be Mustered with a location")
        if pawn_locale != target.location:
            raise IllegalAction("not_co_located", f"Legate must be at {target_id}'s location")
        if not _is_friendly_locale(state, target.location, "teutonic"):
            raise IllegalAction("not_friendly", "Legate USE 2c requires Friendly Locale")
        # Grant an extra Muster: reset lordship_used so target gets full
        # Lordship to spend during the immediate continuation. The Lord
        # then performs his extra Muster via subsequent muster_* actions
        # (we do not trigger them here -- the agent emits them next).
        target.lordship_used = 0
        target.just_arrived_this_levy = False  # already-Mustered Lord
        result_extra = {"target_lord": target_id, "extra_muster": True}

    state.legate.acted_this_call_to_arms = True
    state.legate.location = "card"
    state.legate.locale_id = None
    return ({"sub_option": sub, **result_extra}, [])


def _h_legate_skip(
    state: GameState, side: str, args: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Teutons explicitly do nothing in 3.5.1 (always available)."""
    sd = _require_side_player(state, side)
    if sd != "teutonic":
        raise IllegalAction("wrong_side", "only Teutons act in 3.5.1")
    _require_levy_phase(state)
    _require_levy_step(state, "call_to_arms")
    _require_active(state, sd)
    state.legate.acted_this_call_to_arms = True
    return ({"outcome": "skipped"}, [])


def _h_veche_action(
    state: GameState, side: str, args: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """3.5.2 Veche action. options: A | B | C | D | sea_trade | skip.

    A: SLIDE LEFT (cost 1 VP) -- slide one Russian Lord cylinder 2 boxes LEFT
    B: AUTO-MUSTER (cost 1 VP) -- auto-Muster a Ready Russian Lord
    C: EXTRA MUSTER (cost 1 VP) -- enable a non-Besieged Russian Lord at
       a Friendly Locale to perform an immediate extra Muster
    D: DECLINE (gain 1 VP) -- slide Aleksandr/Andrey if Ready 1 box RIGHT
    sea_trade: add R8 / R9 Coin to Veche box (3.5.2 + R8/R9)
    skip: pass
    """

    sd = _require_side_player(state, side)
    if sd != "russian":
        raise IllegalAction("wrong_side", "only Russians act in 3.5.2 (Veche)")
    _require_levy_phase(state)
    _require_levy_step(state, "call_to_arms")
    _require_active(state, sd)

    option = args.get("option")
    if option not in ("A", "B", "C", "D", "sea_trade", "skip"):
        raise IllegalAction("bad_option", "option must be A|B|C|D|sea_trade|skip")

    if option == "sea_trade":
        return _veche_sea_trade(state, args)

    # All other options consume the once-per-segment slot.
    if option == "skip":
        state.veche.acted_this_call_to_arms = True
        return ({"outcome": "skipped"}, [])

    if state.veche.acted_this_call_to_arms:
        raise IllegalAction("already_acted", "Veche has already acted this Call to Arms (3.5.2)")

    if option == "A":
        target_id = args.get("target_lord")
        if not isinstance(target_id, str) or target_id not in state.lords:
            raise IllegalAction("missing_arg", "Option A requires args.target_lord")
        target = state.lords[target_id]
        if target.side != "russian":
            raise IllegalAction("bad_target", f"{target_id} not Russian")
        if state.veche.vp_markers < 1:
            raise IllegalAction("insufficient_vp", "Veche box has 0 VP markers (3.5.2)")
        cyl_box = _find_cylinder_box(state, target_id)
        if cyl_box is None or cyl_box >= 17 or cyl_box == 0:
            raise IllegalAction("no_cylinder", f"{target_id} cylinder not on Calendar")
        new_box = max(1, cyl_box - 2)
        cb = state.calendar.boxes[cyl_box - 1]
        cb.cylinders.remove(target_id)
        state.calendar.boxes[new_box - 1].cylinders.append(target_id)
        state.veche.vp_markers -= 1
        state.calendar.russian_vp = max(0.0, state.calendar.russian_vp - 1.0)
        state.veche.acted_this_call_to_arms = True
        return (
            {"option": "A", "target_lord": target_id, "from_box": cyl_box, "to_box": new_box},
            [],
        )

    if option == "B":
        target_id = args.get("target_lord")
        if not isinstance(target_id, str) or target_id not in state.lords:
            raise IllegalAction("missing_arg", "Option B requires args.target_lord")
        target = state.lords[target_id]
        if target.side != "russian":
            raise IllegalAction("bad_target", f"{target_id} not Russian")
        if state.veche.vp_markers < 1:
            raise IllegalAction("insufficient_vp", "Veche box has 0 VP markers (3.5.2)")
        if target.state != "ready":
            raise IllegalAction("bad_target", f"{target_id} not Ready (state={target.state})")
        levy_box = _find_levy_marker_box(state)
        cyl_box = _find_cylinder_box(state, target_id)
        if cyl_box is None or cyl_box > levy_box:
            raise IllegalAction("not_ready", f"{target_id} cylinder not Ready")
        free = _free_seats_for(state, target_id)
        seat = args.get("seat")
        if not isinstance(seat, str) or seat not in free:
            raise IllegalAction("no_free_seat", f"args.seat must be a Free Seat: {free}")
        _place_lord_on_map(state, target_id, seat, levy_box)
        state.veche.vp_markers -= 1
        state.calendar.russian_vp = max(0.0, state.calendar.russian_vp - 1.0)
        state.veche.acted_this_call_to_arms = True
        return ({"option": "B", "target_lord": target_id, "seat": seat}, [])

    if option == "C":
        target_id = args.get("target_lord")
        if not isinstance(target_id, str) or target_id not in state.lords:
            raise IllegalAction("missing_arg", "Option C requires args.target_lord")
        target = state.lords[target_id]
        if target.side != "russian":
            raise IllegalAction("bad_target", f"{target_id} not Russian")
        if state.veche.vp_markers < 1:
            raise IllegalAction("insufficient_vp", "Veche box has 0 VP markers (3.5.2)")
        if target.state != "mustered" or target.location is None:
            raise IllegalAction("bad_target", f"{target_id} not Mustered")
        if _is_besieged(state, target_id):
            raise IllegalAction("besieged", f"{target_id} is Besieged; Option C unavailable (3.5.2)")
        if not _is_friendly_locale(state, target.location, "russian"):
            raise IllegalAction("not_friendly", f"{target_id} not at Friendly Locale (3.5.2 Option C)")
        if target.just_arrived_this_levy:
            # Note: a Lord brought on via Option B in same Call to Arms cannot be subject of C.
            raise IllegalAction(
                "just_arrived",
                f"{target_id} just arrived this Levy; cannot use Lordship same Call to Arms (3.5.2)",
            )
        target.lordship_used = 0
        state.veche.vp_markers -= 1
        state.calendar.russian_vp = max(0.0, state.calendar.russian_vp - 1.0)
        state.veche.acted_this_call_to_arms = True
        return ({"option": "C", "target_lord": target_id, "extra_muster": True}, [])

    # option == "D" Decline
    levy_box = _find_levy_marker_box(state)
    aleks_ready = _is_ready(state, "aleksandr", levy_box)
    andrey_ready = _is_ready(state, "andrey", levy_box)
    if not (aleks_ready or andrey_ready):
        raise IllegalAction(
            "decline_unavailable",
            "Option D requires Aleksandr or Andrey to be Ready (3.5.2 Option D)",
        )
    slid: list[str] = []
    target_box = levy_box + 1
    if target_box > 16:
        target_box = 17
    for lord_id, ready in (("aleksandr", aleks_ready), ("andrey", andrey_ready)):
        if ready:
            cyl_box = _find_cylinder_box(state, lord_id)
            if cyl_box is None:
                continue
            # SMOKE-058 (Round 66): handle cyl_box=0 (off_left). The
            # previous `cyl_box <= 16` branch tried boxes[-1] which
            # crashes with ValueError; the Lord was actually in
            # cal.off_left. _is_ready accepts cyl_box <= levy_box,
            # which includes 0 for early scenarios.
            if cyl_box == 0:
                state.calendar.off_left.remove(lord_id)
            elif cyl_box <= 16:
                state.calendar.boxes[cyl_box - 1].cylinders.remove(lord_id)
            else:
                state.calendar.off_right.remove(lord_id)
            if target_box > 16:
                state.calendar.off_right.append(lord_id)
            else:
                state.calendar.boxes[target_box - 1].cylinders.append(lord_id)
            slid.append(lord_id)
    if state.veche.vp_markers < 8:
        state.veche.vp_markers += 1
        state.calendar.russian_vp += 1.0
        from nevsky.scenarios import refresh_victory_markers
        refresh_victory_markers(state)
    # else: cap forfeit per 1.4.2.
    state.veche.acted_this_call_to_arms = True
    return ({"option": "D", "slid": slid, "vp_added": min(1, 8 - (state.veche.vp_markers - 1))}, [])


def _is_ready(state: GameState, lord_id: str, levy_box: int) -> bool:
    if lord_id not in state.lords:
        return False
    lord = state.lords[lord_id]
    if lord.state != "ready":
        return False
    cyl_box = _find_cylinder_box(state, lord_id)
    if cyl_box is None:
        return False
    return cyl_box <= levy_box


def _veche_sea_trade(
    state: GameState, args: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """R8 Black Sea Trade / R9 Baltic Sea Trade Coin addition (3.5.2).

    This action can occur any time during Russian Call to Arms; it does
    NOT consume the once-per-segment slot.
    args: card_id ("R8" or "R9").
    R8: requires R8 in capabilities_in_play; blocked if Novgorod or
    Lovat Conquered by Teutons.
    R9: requires R9 in capabilities_in_play; blocked if Novgorod or
    Neva Conquered by Teutons; season-restricted to non-Winter; ship
    comparison (Phase 3 will refine -- for Phase 2 we assume Russians
    have ship parity unless noted).
    """
    cid = args.get("card_id")
    if cid not in ("R8", "R9"):
        raise IllegalAction("bad_card", "sea_trade card_id must be R8 or R9")
    deck = state.decks.russian
    if cid not in deck.capabilities_in_play:
        raise IllegalAction("not_in_play", f"{cid} not in Russian capabilities_in_play")

    nov = state.locales["novgorod"]
    if cid == "R8":
        lov = state.locales["lovat"]
        if nov.teutonic_conquered > 0 or lov.teutonic_conquered > 0:
            raise IllegalAction(
                "sea_trade_blocked",
                "R8 Black Sea Trade blocked while Novgorod or Lovat Conquered",
            )
        amount = 1
    else:  # R9
        neva = state.locales["neva"]
        if nov.teutonic_conquered > 0 or neva.teutonic_conquered > 0:
            raise IllegalAction(
                "sea_trade_blocked",
                "R9 Baltic Sea Trade blocked while Novgorod or Neva Conquered",
            )
        season = _season_of_box(state.meta.box)
        if season in ("early_winter", "late_winter"):
            raise IllegalAction(
                "sea_trade_winter",
                "R9 Baltic Sea Trade blocked in Winter seasons",
            )
        # Teutons may not have more Ships than Rus (Cogs / Lodya apply).
        from nevsky.campaign import effective_ship_count, effective_boat_count
        teu_ships = sum(
            effective_ship_count(state, lid)
            for lid, l in state.lords.items()
            if l.side == "teutonic" and l.state == "mustered"
        )
        rus_ships = sum(
            effective_ship_count(state, lid) + (effective_boat_count(state, lid) - state.lords[lid].assets.get("boat", 0))
            for lid, l in state.lords.items()
            if l.side == "russian" and l.state == "mustered"
        )
        # Lodya doubles a Russian Lord's Boats; we treat that as +Boats
        # for the comparison only on the Russian side.
        if teu_ships > rus_ships:
            raise IllegalAction(
                "sea_trade_blocked",
                "R9 Baltic Sea Trade blocked while Teutons have more Ships than Rus",
            )
        amount = 2

    added = min(amount, 8 - state.veche.coin)
    state.veche.coin += added
    return ({"card": cid, "added": added, "lost_to_cap": amount - added}, [])


def _season_of_box(box: int) -> str:
    """Calendar season per box (Calendar reference)."""
    table = {
        1: "summer", 2: "summer",
        3: "early_winter", 4: "early_winter",
        5: "late_winter", 6: "late_winter",
        7: "rasputitsa", 8: "rasputitsa",
        9: "summer", 10: "summer",
        11: "early_winter", 12: "early_winter",
        13: "late_winter", 14: "late_winter",
        15: "rasputitsa", 16: "rasputitsa",
    }
    return table.get(box, "summer")


# ---------------------------------------------------------------------------
# System actions
# ---------------------------------------------------------------------------


def _h_system_setup_complete(
    state: GameState, side: str, args: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Drop scenario-setup PendingDecisions (Q-001 Transport-(any) slots).

    Phase 1 emits one `setup_transport_choice` PendingDecision per
    "any" Transport slot in scenario starting forces. This system
    action clears them as a no-op so Phase 2 Levy mechanics can
    proceed; the unresolved Transport-type choice is recorded as a
    history entry for the rules-questions log.
    """
    if side != "system":
        raise IllegalAction("wrong_actor", "system_setup_complete requires side='system'")
    cleared = [pd.kind for pd in state.pending_decisions if pd.kind == "setup_transport_choice"]
    state.pending_decisions = [pd for pd in state.pending_decisions if pd.kind != "setup_transport_choice"]
    return ({"cleared": cleared}, [])


# ---------------------------------------------------------------------------
# Handler registry
# ---------------------------------------------------------------------------




# ---------------------------------------------------------------------------
# Q-001 setup_transport_choice handlers (RULES_DECISIONS.md)
# ---------------------------------------------------------------------------


def _find_setup_transport_pd(
    state: GameState, lord_id: str, slot_index: int
) -> int | None:
    """Return the index of the matching PendingDecision, or None."""
    for i, pd in enumerate(state.pending_decisions):
        if pd.kind != "setup_transport_choice":
            continue
        if pd.context.get("lord_id") == lord_id and pd.context.get("slot_index") == slot_index:
            return i
    return None


def _h_confirm_setup_transport(
    state: GameState, side: str, args: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Accept the default Transport pre-populated by the loader. The
    asset is already in Lord.assets; this just resolves and removes
    the PendingDecision.
    """
    sd = _require_side_player(state, side)
    lord_id = args.get("lord_id")
    slot_index = args.get("slot_index")
    if not isinstance(lord_id, str) or not isinstance(slot_index, int):
        raise IllegalAction("missing_arg", "args: lord_id (str), slot_index (int)")
    idx = _find_setup_transport_pd(state, lord_id, slot_index)
    if idx is None:
        raise IllegalAction("not_found", f"no setup_transport_choice for {lord_id} slot {slot_index}")
    pd = state.pending_decisions[idx]
    if pd.owed_by != sd:
        raise IllegalAction("wrong_actor", f"decision owed by {pd.owed_by}; got {sd}")
    state.pending_decisions.pop(idx)
    return ({"lord_id": lord_id, "slot_index": slot_index,
             "value": pd.context.get("current_value")}, [])


def _h_set_setup_transport(
    state: GameState, side: str, args: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Override the default Transport. Updates Lord.assets to reflect
    the new choice (decrement old, increment new) and resolves the PD.
    """
    sd = _require_side_player(state, side)
    lord_id = args.get("lord_id")
    slot_index = args.get("slot_index")
    value = args.get("value")
    if not isinstance(lord_id, str) or not isinstance(slot_index, int) or not isinstance(value, str):
        raise IllegalAction("missing_arg", "args: lord_id (str), slot_index (int), value (str)")
    idx = _find_setup_transport_pd(state, lord_id, slot_index)
    if idx is None:
        raise IllegalAction("not_found", f"no setup_transport_choice for {lord_id} slot {slot_index}")
    pd = state.pending_decisions[idx]
    if pd.owed_by != sd:
        raise IllegalAction("wrong_actor", f"decision owed by {pd.owed_by}; got {sd}")
    allowed = pd.context.get("allowed_values", [])
    if value not in allowed:
        raise IllegalAction("bad_value", f"value must be in {allowed}; got {value!r}")
    old = pd.context.get("current_value")
    if old != value:
        # Move 1 unit from old asset to new asset on the Lord.
        lord = state.lords[lord_id]
        if old in lord.assets:
            lord.assets[old] = max(0, lord.assets.get(old, 0) - 1)  # type: ignore[index]
            if lord.assets[old] == 0:  # type: ignore[index]
                del lord.assets[old]  # type: ignore[arg-type]
        lord.assets[value] = lord.assets.get(value, 0) + 1  # type: ignore[index]
    state.pending_decisions.pop(idx)
    return ({"lord_id": lord_id, "slot_index": slot_index, "old": old, "new": value}, [])


def _h_confirm_all_setup_transports(
    state: GameState, side: str, args: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Bulk-confirm all setup_transport_choice decisions for the side."""
    sd = _require_side_player(state, side)
    confirmed: list[dict[str, Any]] = []
    for pd in list(state.pending_decisions):
        if pd.kind != "setup_transport_choice" or pd.owed_by != sd:
            continue
        confirmed.append({
            "lord_id": pd.context.get("lord_id"),
            "slot_index": pd.context.get("slot_index"),
            "value": pd.context.get("current_value"),
        })
        state.pending_decisions.remove(pd)
    return ({"side": sd, "confirmed": confirmed}, [])


def _auto_confirm_setup_transport_choices(state: GameState, side: Side) -> list[dict[str, Any]]:
    """Auto-confirm setup_transport_choice PendingDecisions for `side`
    that have auto_confirm_on_levy=True. Called from Levy entry path
    (first Levy action by that side). PendingDecisions with
    auto_confirm_on_levy=False persist and the player must explicitly
    confirm or override.
    """
    auto_confirmed: list[dict[str, Any]] = []
    for pd in list(state.pending_decisions):
        if pd.kind != "setup_transport_choice" or pd.owed_by != side:
            continue
        if not pd.context.get("auto_confirm_on_levy", True):
            continue
        auto_confirmed.append({
            "lord_id": pd.context.get("lord_id"),
            "slot_index": pd.context.get("slot_index"),
            "value": pd.context.get("current_value"),
        })
        state.pending_decisions.remove(pd)
    return auto_confirmed


def _h_aow_play_hold(
    state: "GameState", side: str, args: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Play a Hold event from the side's `holds` list. The event's
    effect resolves immediately; the card is discarded (per "discard the
    moment used"). args.card_id required, plus event-specific args.
    Phase 4c covers a subset; uncovered holds get a deferred placeholder.
    """
    from nevsky.events import resolve_hold_event
    sd = _require_side_player(state, side)
    cid = args.get("card_id")
    if not isinstance(cid, str):
        raise IllegalAction("missing_arg", "args.card_id required")
    deck = _side_deck(state, sd)
    if cid not in deck.holds:
        raise IllegalAction("not_in_holds", f"{cid} not in your holds")
    # SMOKE-056 (Round 65): verify card belongs to playing side.
    # Holds drift into the wrong list only via state-edits / fixtures,
    # but the play handler should never let a Teutonic player resolve
    # a Russian Hold (or vice versa) per 1.9.1 eligibility.
    from nevsky.static_data import load_cards
    card_meta = load_cards().get(cid)
    if card_meta is not None and card_meta.get("side") != sd:
        raise IllegalAction(
            "wrong_side",
            f"{cid} belongs to {card_meta['side']}; {sd} cannot play it",
        )
    result = resolve_hold_event(state, cid, args)
    deck.holds.remove(cid)
    deck.discard.append(cid)
    return ({"card": cid, "result": result}, [])


def _h_aow_lordship_plus_2(
    state: "GameState", side: str, args: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Use a Lordship-or-shift Hold event for +2 Lordship to a target Lord.
    Card discarded the moment used. Allowed in Muster (3.4) and Call to
    Arms (3.5).
    args.card_id, args.lord_id, args.mode = "lordship" | "shift",
    args.direction (when mode=shift): "left" | "right".
    """
    from nevsky.events import apply_calendar_shift_hold, apply_lordship_plus_2
    sd = _require_side_player(state, side)
    cid = args.get("card_id")
    lord_id = args.get("lord_id")
    mode = args.get("mode", "lordship")
    if not (isinstance(cid, str) and isinstance(lord_id, str)):
        raise IllegalAction("missing_arg", "args.card_id and args.lord_id required")
    if state.meta.phase != "levy":
        raise IllegalAction("wrong_phase", "Lordship +2 hold play allowed in Levy only")
    if state.meta.levy_step not in ("muster", "call_to_arms"):
        raise IllegalAction("wrong_step", "Lordship +2 hold allowed in Muster or Call to Arms")
    deck = _side_deck(state, sd)
    if cid not in deck.holds:
        raise IllegalAction("not_in_holds", f"{cid} not in your holds")
    # SMOKE-056 (Round 65) extension: side-validate the card here too.
    from nevsky.static_data import load_cards
    card_meta = load_cards().get(cid)
    if card_meta is not None and card_meta.get("side") != sd:
        raise IllegalAction(
            "wrong_side",
            f"{cid} belongs to {card_meta['side']}; {sd} cannot play it",
        )
    if mode == "lordship":
        result = apply_lordship_plus_2(state, cid, lord_id)
    elif mode == "shift":
        direction = args.get("direction", "left")
        result = apply_calendar_shift_hold(state, cid, lord_id, direction)
    else:
        raise IllegalAction("bad_mode", "mode must be lordship or shift")
    deck.holds.remove(cid)
    deck.discard.append(cid)
    return ({"card": cid, "result": result}, [])


_HANDLERS: dict[str, Any] = {
    "advance_step": _h_advance_step,
    "confirm_setup_transport": _h_confirm_setup_transport,
    "set_setup_transport": _h_set_setup_transport,
    "confirm_all_setup_transports": _h_confirm_all_setup_transports,
    "aow_play_hold": _h_aow_play_hold,
    "aow_lordship_plus_2": _h_aow_lordship_plus_2,
    # 3.1
    "aow_shuffle": _h_aow_shuffle,
    "aow_draw": _h_aow_draw,
    "aow_implement_card": _h_aow_implement_card,
    "aow_discard_this_levy": _h_aow_discard_this_levy,
    # 3.2
    "pay_with_coin": _h_pay_with_coin,
    "pay_with_loot": _h_pay_with_loot,
    # 3.3
    "disband_resolve": _h_disband_resolve,
    # 3.4
    "muster_lord": _h_muster_lord,
    "muster_vassal": _h_muster_vassal,
    "levy_transport": _h_levy_transport,
    "levy_capability": _h_levy_capability,
    # 3.5
    "legate_arrives": _h_legate_arrives,
    "legate_move": _h_legate_move,
    "legate_use": _h_legate_use,
    "legate_skip": _h_legate_skip,
    "veche_action": _h_veche_action,
    # system
    "system_setup_complete": _h_system_setup_complete,
}


# Phase 3 campaign handlers are registered at import time.
def _register_campaign_handlers() -> None:
    from nevsky.campaign import HANDLERS as CAMPAIGN_HANDLERS

    _HANDLERS.update(CAMPAIGN_HANDLERS)


_register_campaign_handlers()
