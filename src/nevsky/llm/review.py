"""Post-game self-critique tool.

The LLM, at game-end or on human request, summarizes the trace and
reflects on its play. This file provides the structured replay
artifact the LLM consumes. The LLM does the actual critique in
natural language; we just hand it the data.
"""
from __future__ import annotations

from collections import Counter
from typing import Any


def build_review_artifact(session) -> dict[str, Any]:
    """Bundle a session's history into a compact dict the LLM can
    reflect on. Returned shape:

      {
        "scenario": str,
        "seed": int,
        "llm_side": str,
        "winner": dict | None,
        "final_box": int,
        "final_t_vp": float,
        "final_r_vp": float,
        "action_counts": dict[str, int],  # per-type frequency
        "key_events": list[dict],         # battles, conquests, removals
        "phase_transitions": list[dict],  # box transitions with VP
        "llm_reasoning_log": list[dict],  # turns where LLM noted reasoning
      }
    """
    s = session.state
    history = session.history

    # Action type frequencies
    counts = Counter(h["action"]["type"] for h in history)

    # Key events: anything with a battle, conquest, removal, ransom
    key_events = []
    for h in history:
        rs = h.get("result_summary") or {}
        if not rs:
            continue
        if any(k in rs for k in ("battle", "conquest_change", "removed",
                                  "ransom", "siege_lifted",
                                  "ambush_blocked", "advanced")):
            key_events.append({
                "who": h["who"],
                "action_type": h["action"]["type"],
                "side": h["side"],
                "phase": h.get("phase"),
                "step": h.get("step"),
                "summary": rs,
            })

    # Phase transitions (we don't capture box-by-box; surface via
    # detecting "advanced" markers in the result_summaries).
    phase_transitions = []
    for h in history:
        rs = h.get("result_summary") or {}
        if "advanced" in rs and rs["advanced"]:
            phase_transitions.append({
                "step_in_history": history.index(h),
                "action": h["action"]["type"],
                "side": h["side"],
            })

    # LLM reasoning log (turns where reasoning was provided)
    reasoning_log = [
        {"who": h["who"], "side": h["side"],
         "action": h["action"]["type"], "reasoning": h["reasoning"]}
        for h in history if h.get("reasoning")
    ]

    return {
        "scenario": session.scenario_id,
        "seed": s.meta.seed,
        "llm_side": session.llm_side,
        "human_side": session.human_side,
        "winner": session.winner(),
        "final_box": s.meta.box,
        "final_t_vp": s.calendar.teutonic_vp,
        "final_r_vp": s.calendar.russian_vp,
        "final_t_mustered": [
            lid for lid, l in s.lords.items()
            if l.side == "teutonic" and l.state == "mustered"
        ],
        "final_r_mustered": [
            lid for lid, l in s.lords.items()
            if l.side == "russian" and l.state == "mustered"
        ],
        "total_actions": len(history),
        "action_counts": dict(counts.most_common()),
        "key_events": key_events,
        "phase_transitions_count": len(phase_transitions),
        "llm_reasoning_log": reasoning_log,
    }


def review_prompt_for_llm(session) -> str:
    """Render a textual review packet for the LLM to read and
    critique. Includes the artifact + suggested reflection prompts.
    """
    import json as _json
    art = build_review_artifact(session)
    lines = [
        f"# Post-game review — {art['scenario']} (seed {art['seed']})",
        f"You played {art['llm_side']}. Final result:",
        f"  Winner: {art['winner']}",
        f"  Final VPs: T={art['final_t_vp']} R={art['final_r_vp']}",
        f"  Final mustered T: {art['final_t_mustered']}",
        f"  Final mustered R: {art['final_r_mustered']}",
        f"  Total actions: {art['total_actions']}",
        f"",
        "## Action mix",
    ]
    for typ, n in art["action_counts"].items():
        lines.append(f"  {typ}: {n}")
    lines.append(f"")
    lines.append(f"## Key events ({len(art['key_events'])})")
    for ev in art["key_events"][:30]:
        lines.append(f"  - {ev['action_type']} ({ev['side']}, {ev.get('step')}): "
                     f"{_json.dumps(ev['summary'], default=str)[:120]}")
    lines.append(f"")
    lines.append(f"## Your reasoning log ({len(art['llm_reasoning_log'])} entries)")
    for r in art["llm_reasoning_log"][:20]:
        lines.append(f"  - {r['action']}: {r['reasoning'][:200]}")
    lines.append("")
    lines.append("## Reflection prompts")
    lines.append("Answer in your own words:")
    lines.append("1. What was your strategic plan at start? Did you stick to it?")
    lines.append("2. Identify your single biggest decision; was it the right one?")
    lines.append("3. What did the opponent do that surprised you?")
    lines.append("4. If you replayed this, what would you change?")
    lines.append("5. Was there a moment you should have ended a card early, "
                 "or refused a Battle?")
    return "\n".join(lines)
