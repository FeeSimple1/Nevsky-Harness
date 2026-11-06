"""LLM-facing tool functions.

These are the only ways the LLM should interact with the harness.
Each tool returns structured data the LLM can use directly.
"""
from __future__ import annotations

from typing import Any

from nevsky.actions import IllegalAction, apply_action
from nevsky.legal_moves import legal_moves


def legal_actions_for_side(state, side: str) -> list[dict[str, Any]]:
    """Return legal moves available to `side`. Pre-filters by
    state.meta.active_player so only the requesting side's options
    are returned. On the other side's turn, only that requesting side's
    legal any-time Hold interruptions are returned; ordinary commands
    and the opponent's held cards are never exposed. Each move has either `args` (concrete) or
    `args_template` + `candidates` (templated). The LLM should not
    see illegal options — only what this function returns.

    For combat-pending response windows, the moves include
    stand_battle / avoid_battle / withdraw / play_ambush_block etc.
    """
    if side not in ("teutonic", "russian") or state.meta.game_over:
        return []
    if state.meta.active_player != side:
        from nevsky.rewards import pending_reward
        if pending_reward(state) is not None:
            return []
        from nevsky.held_actions import held_actions_for_side
        return held_actions_for_side(state, side, interrupts_only=True)
    moves = legal_moves(state, with_previews=False)
    for move in moves:
        if "holds_available" in move:
            move["holds_available"] = [hold for hold in move["holds_available"]
                                       if hold["side"] == side]
            if not move["holds_available"]:
                move.pop("holds_available")
                move.pop("holds_template", None)
        if "retreat_keep_order_options" in move:
            move["retreat_keep_order_options"] = [
                lid for lid in move["retreat_keep_order_options"] if state.lords[lid].side == side]
            if not move["retreat_keep_order_options"]:
                move.pop("retreat_keep_order_options")
                move.pop("retreat_keep_order_template", None)
    # Add a strategic note if the move type has one (legal_moves
    # already adds notes for many moves). Return as-is.
    return moves


_BATTLE_HOLD_CARDS = {
    "marsh": ("T5", "R2"),
    "hill": ("T9", "R5"),
    "ambush": ("T6", "R6"),
    "field_organ": ("T10",),
    "raven_rock": ("R4",),
    "bridge": ("T4", "R1"),
}


def _validate_combat_owner(state, side: str, kind: str, args: dict[str, Any]) -> None:
    from nevsky.campaign import _concede_decisions_from_args
    from nevsky.static_data import load_cards

    if kind in ("stand_battle", "cmd_sally"):
        role = "defender" if kind == "stand_battle" else "attacker"
        _concede_decisions_from_args(args, owner_role=role)

    # The raw referee API can submit decisions for both combatants.
    if args.get("scripted_decisions") or args.get("decision_callback") is not None:
        raise IllegalAction("wrong_actor", "two-sided combat scripts require the referee API")

    for field in ("remove_losers", "withdraw_losers", "retreat_to", "retreat_keep_order",
                  "spoils_recipient", "spoils_allocation"):
        election = args.get(field)
        if not election:
            continue
        if field == "withdraw_losers" and election is True and kind == "stand_battle":
            continue
        if isinstance(election, str) and field == "spoils_recipient":
            election = [election]
        if not isinstance(election, (dict, list)) or any(
            not isinstance(lid, str) or lid not in state.lords or state.lords[lid].side != side
            for lid in election
        ):
            raise IllegalAction("wrong_actor", f"{field} may only name the caller's own Lords")

    holds = args.get("holds") or {}
    if not isinstance(holds, dict):
        raise IllegalAction("bad_holds", "holds must be a Battle Hold argument map")
    cards = load_cards() if holds else {}
    for key, card in holds.items():
        if key in ("field_organ_lord", "bridge_target_lord"):
            continue
        if card not in _BATTLE_HOLD_CARDS.get(key, ()):
            raise IllegalAction("bad_hold", f"{key} requires its printed Hold card ID")
        if cards[card]["side"] != side:
            raise IllegalAction("wrong_actor", f"{key} requires the caller's own Held card")
    hold_targets = (("field_organ_lord", "field_organ"), ("bridge_target_lord", "bridge"))
    for target_key, card_key in hold_targets:
        if target_key in holds and card_key not in holds:
            raise IllegalAction("bad_hold", f"{target_key} requires its Held card")
    if kind == "cmd_storm" and args.get("field_organ_lord") and side != "teutonic":
        raise IllegalAction("wrong_actor", "only the Teutonic player may play Field Organ")


def apply_action_for_side(state, side: str, action: dict) -> dict:
    """Apply an action on behalf of `side`. Returns the harness's
    result dict. Raises IllegalAction if the action is invalid; the
    LLM should retry or fall back to a safe phase-appropriate
    action.

    The LLM should always include "side" matching its play side. If
    the action's "side" field is missing, fill it from `side`. Conflicting
    sides reject before any engine setup or private card draw.
    Combat elections must belong to the caller.
    """
    if side not in ("teutonic", "russian"):
        raise IllegalAction("wrong_actor", "side must be 'teutonic' or 'russian'")
    if not isinstance(action, dict):
        raise IllegalAction("bad_envelope", "action must be a JSON object")
    action = dict(action)
    action.setdefault("side", side)
    if action["side"] != side:
        raise IllegalAction("wrong_actor",
                            f"caller is {side}; action declares side={action['side']!r}")
    kind = action.get("type")
    args = action.get("args")
    if kind in ("stand_battle", "cmd_sally", "cmd_storm") and isinstance(args, dict):
        _validate_combat_owner(state, side, kind, args)
    return apply_action(state, action)


def safe_fallback_for_side(state, side: str) -> dict:
    """Return a safe phase-appropriate fallback action. Used after
    repeated illegal-action retries. The LLM doesn't typically call
    this directly; the orchestrating loop calls it.
    """
    from nevsky.rewards import REWARD_ACTION, pending_reward

    if pending_reward(state) is not None:
        return {"type": REWARD_ACTION, "side": side, "args": {}}
    phase = state.meta.phase
    levy_step = state.meta.levy_step
    camp_step = state.meta.campaign_step
    if phase == "levy":
        if levy_step == "arts_of_war":
            # Draw/reveal/resolve are mandatory. Reuse the current palette
            # so an Event awaiting the other player's choice also resumes.
            moves = legal_actions_for_side(state, side)
            for kind in ("aow_draw", "aow_implement_card", "advance_step"):
                action = next((m for m in moves if m["type"] == kind), None)
                if action is not None:
                    return {k: action[k] for k in ("type", "side", "args")}
        if levy_step == "call_to_arms" and side == "teutonic":
            return {"type": "legate_skip", "side": side, "args": {}}
        if levy_step == "disband":
            # PLAY-19: advance_step is rejected (must_disband) while a
            # mandatory 3.3 Disband is owed; the safe fallback must
            # resolve it, not spin on advance_step.
            _resolved = (state.meta.disband_resolved_t if side == "teutonic"
                         else state.meta.disband_resolved_r)
            if not _resolved:
                return {"type": "disband_resolve", "side": side, "args": {}}
        return {"type": "advance_step", "side": side, "args": {}}
    if phase == "campaign":
        if camp_step == "command":
            if state.campaign_turn.in_feed_pay_disband:
                return {"type": "fpd_resolve", "side": side, "args": {}}
            if state.combat_pending is not None and state.combat_pending.pending_response_by == side:
                if state.combat_pending.avoid_spoils:
                    return {"type": "allocate_avoid_spoils", "side": side, "args": {}}
                if state.combat_pending.ambush_block_pending:
                    return {"type": "decline_ambush_block", "side": side, "args": {}}
                return {"type": "stand_battle", "side": side, "args": {}}
            if state.campaign_turn.actions_remaining > 0 and state.campaign_turn.active_lord:
                return {"type": "end_card", "side": side, "args": {}}
            return {"type": "command_reveal", "side": side, "args": {}}
        if camp_step == "plan":
            return {"type": "plan_add_card", "side": side, "args": {"card": "pass"}}
        if camp_step == "end_campaign":
            return {"type": "end_campaign_resolve", "side": side, "args": {}}
    return {"type": "advance_step", "side": side, "args": {}}


def lookup_card(card_id: str) -> dict:
    """Look up the printed text + Tip for a card.

    Returns a dict with: card_id, side, event_name, event_text,
    event_persistence, capability_name, capability_text,
    capability_scope, event_eligibility, capability_eligibility.
    """
    from nevsky.static_data import load_cards
    cards = load_cards()
    if card_id not in cards:
        return {"error": f"unknown card {card_id!r}"}
    return cards[card_id]


def lookup_strategy(topic: str) -> str:
    """Look up a section of STRATEGY_DIGEST.md by topic.

    `topic` is a substring match against section headers. Returns
    the section text (header + body up to next ## or # at same
    level).
    """
    from pathlib import Path
    digest_path = Path(__file__).parent.parent.parent.parent / "STRATEGY_DIGEST.md"
    if not digest_path.exists():
        return "STRATEGY_DIGEST.md not found"
    src = digest_path.read_text()
    lines = src.split("\n")
    # Find header matching topic (case-insensitive substring)
    topic_lower = topic.lower()
    header_re = None
    for i, line in enumerate(lines):
        s = line.lstrip("#").strip()
        if line.startswith("#") and topic_lower in s.lower():
            header_re = (i, line)
            break
    if header_re is None:
        # Return list of available headers
        all_headers = [l for l in lines if l.startswith("#") and l.strip()]
        return f"No section matching {topic!r}. Available sections:\n" + "\n".join(all_headers[:60])
    start, header_line = header_re
    level = len(header_line) - len(header_line.lstrip("#"))
    # Find next same-or-higher-level header
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if lines[j].startswith("#"):
            j_level = len(lines[j]) - len(lines[j].lstrip("#"))
            if j_level <= level:
                end = j
                break
    return "\n".join(lines[start:end])


def lookup_aow_reference(card_id: str) -> str:
    """Look up a card in the AoW Reference text file (more detail
    than lookup_card's structured data — includes full Tip
    paragraphs).
    """
    from pathlib import Path
    ref_path = Path(__file__).parent.parent.parent.parent / "reference" / "Nevsky_Arts_of_War_Reference.txt"
    if not ref_path.exists():
        return "AoW Reference not found"
    src = ref_path.read_text()
    lines = src.split("\n")
    # Find the line that starts with "{card_id}. " or "{card_id} —"
    cid_marker = f"{card_id}."
    start = None
    for i, line in enumerate(lines):
        if line.lstrip().startswith(cid_marker):
            start = i
            break
    if start is None:
        return f"Card {card_id} not found in AoW Reference"
    # Read until the next card line (matching X##. or X##.-X##.)
    import re
    next_card_re = re.compile(r"^[TR]\d+(\.-[TR]\d+)?\. ")
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if next_card_re.match(lines[j].lstrip()):
            end = j
            break
    return "\n".join(lines[start:end]).strip()


def preview_combat(state, attacker_side: str, attacker_lords: list[str],
                   defender_lords: list[str], human_requested: bool = False,
                   **kwargs) -> dict:
    """Combat preview (Battle, not Storm). GATED by human_requested
    per the LLM-play philosophy: the LLM may not preview on its own
    initiative; only when the human explicitly asks "what's the
    chance?" or similar.

    Returns a dict with expected outcomes from a Monte Carlo on the
    state. Internally runs `resolve_battle` against a deep-copied
    state with multiple seed offsets.
    """
    if not human_requested:
        return {
            "preview_blocked": True,
            "reason": "LLM may not preview combat without explicit "
                      "human request (per LLM-play design)",
        }
    from copy import deepcopy
    from nevsky.battle import resolve_battle
    outcomes = []
    for seed_off in range(20):
        s2 = deepcopy(state)
        s2.meta.rng_state += seed_off * 100
        try:
            res = resolve_battle(
                s2, attacker_side=attacker_side,
                attacker_lords=attacker_lords,
                defender_lords=defender_lords,
                **kwargs,
            )
            outcomes.append({
                "winner": res.get("winner"),
                "rounds": res.get("rounds"),
            })
        except Exception as e:
            outcomes.append({"error": str(e)[:80]})
    winners = [o.get("winner") for o in outcomes]
    return {
        "samples": 20,
        "attacker_win_pct": winners.count(attacker_side) / max(1, len(winners)) * 100,
        "defender_win_pct": winners.count("teutonic" if attacker_side == "russian" else "russian") / max(1, len(winners)) * 100,
        "outcomes": outcomes,
    }
