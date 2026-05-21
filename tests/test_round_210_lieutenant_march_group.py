"""Round 210 (smoke batch 2): SMOKE-151.

Follow-on to SMOKE-146. The Lieutenant March now carries the
[lieutenant, lower_lord] group, but the handler computes BOTH the Laden
action-cost and the 4.3.2 excess-Provender gate across ALL group members.
The enumerator was computing them only for the active Lord, so a
Lieutenant whose Lower Lord is Laden / carries excess Provender was
over-enumerated (rejected with insufficient_actions / excess_provender).
The enumerator now computes laden+excess over the whole March group.
"""
from __future__ import annotations

from nevsky.actions import apply_action
import nevsky.campaign as camp
from nevsky.legal_moves import legal_moves
from nevsky.scenarios import load_scenario
from nevsky.state import GameState


def _march_moves(s: GameState, side: str):
    return [m for m in legal_moves(s, with_previews=False)
            if m.get("type") == "cmd_march" and m.get("side") == side]


def _setup_lieutenant_pair(seed: int = 1):
    s = load_scenario("crusade_on_novgorod", seed=seed)
    teu = [lid for lid, l in s.lords.items()
           if l.side == "teutonic" and l.state == "mustered"
           and not camp._is_currently_marshal(s, lid)]
    assert len(teu) >= 2
    lt, ll = teu[0], teu[1]
    s.lords[ll].location = s.lords[lt].location
    s.lords[lt].has_lower_lord = ll
    s.lords[ll].lieutenant_of = lt
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.active_player = "teutonic"
    s.campaign_turn.active_lord = lt
    s.campaign_turn.next_to_reveal = "teutonic"
    s.campaign_turn.in_feed_pay_disband = False
    s.campaign_turn.actions_remaining = camp._effective_command_rating(s, lt)
    return s, lt, ll


def test_lieutenant_march_handles_lower_lord_excess_provender():
    s, lt, ll = _setup_lieutenant_pair()
    # Clear the lieutenant's confounds; load the LOWER LORD with excess
    # Provender and strip its transport so it trips the 4.3.2 gate.
    s.lords[lt].assets.pop("provender", None)
    s.lords[lt].assets.pop("loot", None)
    for k in ("boat", "cart", "sled", "ship"):
        s.lords[ll].assets.pop(k, None)
    s.lords[ll].assets["provender"] = 8  # >> 2x usable transport (0)
    s.lords[ll].assets.pop("loot", None)
    # Ensure the Lord has budget for a (possibly Laden) March.
    s.campaign_turn.actions_remaining = max(2, camp._effective_command_rating(s, lt))
    marches = _march_moves(s, "teutonic")
    assert marches, "expected a Lieutenant march"
    for m in marches:
        assert m["args"].get("group") == [lt, ll]
        # Lower Lord has excess Provender -> the move must carry the
        # auto-discard flag so the enumerated march is legal.
        assert m["args"].get("discard_excess_provender") is True
    # And it applies cleanly (no excess_provender / insufficient_actions).
    apply_action(s, marches[0])
    assert s.lords[lt].location == marches[0]["args"]["to"]
    assert s.lords[ll].location == marches[0]["args"]["to"]
