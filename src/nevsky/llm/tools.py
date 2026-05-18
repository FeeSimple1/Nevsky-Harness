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
    are returned. Each move has either `args` (concrete) or
    `args_template` + `candidates` (templated). The LLM should not
    see illegal options — only what this function returns.

    For combat-pending response windows, the moves include
    stand_battle / avoid_battle / withdraw / play_ambush_block etc.
    """
    if state.meta.active_player != side:
        return []
    moves = legal_moves(state, with_previews=False)
    # Add a strategic note if the move type has one (legal_moves
    # already adds notes for many moves). Return as-is.
    return moves


def apply_action_for_side(state, side: str, action: dict) -> dict:
    """Apply an action on behalf of `side`. Returns the harness's
    result dict. Raises IllegalAction if the action is invalid; the
    LLM should retry or fall back to a safe phase-appropriate
    action.

    The LLM should always include "side" matching its play side. If
    the action's "side" field is missing, fill it from `side`.
    """
    action = dict(action)
    action.setdefault("side", side)
    return apply_action(state, action)


def safe_fallback_for_side(state, side: str) -> dict:
    """Return a safe phase-appropriate fallback action. Used after
    repeated illegal-action retries. The LLM doesn't typically call
    this directly; the orchestrating loop calls it.
    """
    phase = state.meta.phase
    levy_step = state.meta.levy_step
    camp_step = state.meta.campaign_step
    if phase == "levy":
        if levy_step == "call_to_arms" and side == "teutonic":
            return {"type": "legate_skip", "side": side, "args": {}}
        return {"type": "advance_step", "side": side, "args": {}}
    if phase == "campaign":
        if camp_step == "command":
            if state.campaign_turn.in_feed_pay_disband:
                return {"type": "fpd_resolve", "side": side, "args": {}}
            if state.combat_pending is not None and state.combat_pending.pending_response_by == side:
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
