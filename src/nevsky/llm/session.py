"""LLMSession: orchestrates a game session for LLM play.

Holds the GameState, tracks which side the LLM plays, persists state
to a session file, and provides high-level entry points for the
LLM's tool surface.
"""
from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

from nevsky.actions import IllegalAction, apply_action
from nevsky.scenarios import (SCENARIO_IDS, determine_scenario_winner,
                              load_scenario)
from nevsky.state import GameState


_LOADABLE_SCENARIOS = [
    "watland", "pleskau", "peipus",
    "return_of_the_prince", "return_of_the_prince_nicolle",
    "crusade_on_novgorod",
]  # quickstart is a placeholder; excluded


class LLMSession:
    """One game session. Wraps a GameState and the LLM's play side.

    The LLM constructs this once (or loads from disk) and uses it
    across all turns. The harness state is the source of truth; the
    LLM's chat history is the strategic memory.
    """

    def __init__(self, state: GameState, llm_side: str, scenario_id: str,
                 session_id: str | None = None):
        if llm_side not in ("teutonic", "russian"):
            raise ValueError(f"llm_side must be 'teutonic' or 'russian'; got {llm_side!r}")
        self.state = state
        self.llm_side = llm_side
        self.human_side = "russian" if llm_side == "teutonic" else "teutonic"
        self.scenario_id = scenario_id
        self.session_id = session_id or f"{scenario_id}_seed{state.meta.seed}"
        # Action history with per-step LLM reasoning notes (for replay review)
        self.history: list[dict[str, Any]] = []

    # -- factory methods --

    @classmethod
    def start_new(cls, scenario: str, llm_side: str | None = None,
                  seed: int | None = None, randomize_side: bool = False
                  ) -> "LLMSession":
        """Start a fresh game.

        Args:
            scenario: scenario_id (one of LOADABLE_SCENARIOS)
            llm_side: "teutonic" | "russian" | None (must pick if not randomized)
            seed: RNG seed (None → 1 for reproducibility)
            randomize_side: if True, randomly pick the LLM's side
        """
        if scenario not in _LOADABLE_SCENARIOS:
            raise ValueError(
                f"unknown scenario {scenario!r}; loadable: {_LOADABLE_SCENARIOS}"
            )
        if randomize_side:
            llm_side = random.choice(["teutonic", "russian"])
        if llm_side is None:
            raise ValueError("must specify llm_side or set randomize_side=True")
        seed = seed if seed is not None else 1
        state = load_scenario(scenario, seed=seed)
        # Auto-confirm setup transports (these are Q-001 mechanical
        # defaults the LLM doesn't need to micro-manage).
        for side in ("teutonic", "russian"):
            try:
                apply_action(state, {"type": "confirm_all_setup_transports",
                                      "side": side, "args": {}})
            except Exception:
                pass
        return cls(state=state, llm_side=llm_side, scenario_id=scenario)

    @classmethod
    def load(cls, path: str | Path) -> "LLMSession":
        """Load a session from disk."""
        p = Path(path)
        data = json.loads(p.read_text())
        state = GameState.model_validate_json(data["state_json"])
        session = cls(
            state=state,
            llm_side=data["llm_side"],
            scenario_id=data["scenario_id"],
            session_id=data.get("session_id"),
        )
        session.history = data.get("history", [])
        return session

    # -- persistence --

    def save(self, path: str | Path) -> None:
        """Save session to disk."""
        p = Path(path)
        data = {
            "session_id": self.session_id,
            "scenario_id": self.scenario_id,
            "llm_side": self.llm_side,
            "state_json": self.state.model_dump_json(),
            "history": self.history,
        }
        p.write_text(json.dumps(data, indent=2))

    # -- LLM tool surface --

    def briefing(self) -> str:
        """Per-turn briefing for the LLM (~2-3 KB natural language)."""
        from nevsky.llm.briefing import briefing_for_side
        return briefing_for_side(self.state, self.llm_side)

    def legal_actions(self) -> list[dict[str, Any]]:
        """Legal actions for the LLM's side (only this side; if it's
        the human's turn, returns [])."""
        from nevsky.llm.tools import legal_actions_for_side
        return legal_actions_for_side(self.state, self.llm_side)

    def legal_actions_for_human(self) -> list[dict[str, Any]]:
        """Legal actions for the human's side. The LLM uses this to
        translate human free-text into structured calls."""
        from nevsky.llm.tools import legal_actions_for_side
        return legal_actions_for_side(self.state, self.human_side)

    def apply(self, action: dict, *, who: str = "llm",
              reasoning: str | None = None) -> dict:
        """Apply an action. who="llm" or "human". Captures action +
        optional reasoning into history for replay review."""
        if who not in ("llm", "human"):
            raise ValueError(f"who must be 'llm' or 'human'; got {who!r}")
        side = self.llm_side if who == "llm" else self.human_side
        action = dict(action)
        action.setdefault("side", side)
        # Authorization: actions must come from the correct side
        if action.get("side") != side:
            raise IllegalAction(
                "wrong_actor",
                f"{who} is {side}; action declares side={action.get('side')!r}",
            )
        result = apply_action(self.state, action)
        # Capture for replay
        self.history.append({
            "who": who,
            "side": side,
            "action": action,
            "reasoning": reasoning,
            "phase": self.state.meta.phase,
            "step": self.state.meta.levy_step or self.state.meta.campaign_step,
            "result_summary": _summarize_result(result),
        })
        return result

    # -- introspection --

    def is_terminal(self) -> bool:
        return (self.state.meta.phase == "campaign"
                and self.state.meta.campaign_step == "done")

    def whose_turn(self) -> str:
        """Return 'llm' | 'human'."""
        if self.state.meta.active_player == self.llm_side:
            return "llm"
        return "human"

    def winner(self) -> dict | None:
        if not self.is_terminal():
            return None
        try:
            return determine_scenario_winner(self.state)
        except Exception as e:
            return {"error": str(e)}

    def full_state(self) -> dict:
        """Return the state with hidden-info filter applied for the
        LLM's side. The LLM gets this only on explicit request — the
        briefing covers ~all routine needs at ~3 KB."""
        from nevsky.llm.view import view_for_side
        return view_for_side(self.state, self.llm_side)


def _summarize_result(r):
    if not isinstance(r, dict):
        return None
    keys = ["outcome", "winner", "loser", "added", "removed",
            "ravaged_color", "battle", "conquest_change", "ransom",
            "siege_lifted", "no_op", "advanced", "game_over",
            "ambush_interrupt", "ambush_blocked"]
    return {k: r[k] for k in keys if k in r}
