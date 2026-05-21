"""Round 209: over-enumeration fixes surfaced by a 20-game strategic-agent
smoke test of the R203-R208 changes.

The smoke test flagged steps where a CONCRETE enumerated move was rejected
by its handler (enumerator/handler asymmetry). One was exposed by R204
(SMOKE-146); the rest were pre-existing.

SMOKE-146: a Lieutenant's March was enumerated without the required Lower
           Lord group (4.1.3) -> handler raised lower_lord_required. Only
           reachable in agent play once R204 made place_lieutenant usable.
SMOKE-147: a Lord blocked this Levy (R11/R17) was offered as a Muster
           TARGET (the by_lord was filtered, the target was not).
SMOKE-148: veche sea_trade (R8/R9) offered when already used this CtA or
           blocked (Novgorod/Lovat/Neva Conquered, R9 ship parity).
SMOKE-149: T13 William of Modena offered while R15 Death of the Pope had
           blocked it this Levy.
SMOKE-150: cmd_ravage offered when it costs 2 actions (Unbesieged enemy
           Lord adjacent) but the Lord has only 1 action.
"""
from __future__ import annotations

from nevsky.actions import apply_action
import nevsky.campaign as camp
from nevsky.legal_moves import legal_moves
from nevsky.scenarios import load_scenario
from nevsky.state import GameState


def _types(s: GameState, side: str) -> set[str]:
    return {m["type"] for m in legal_moves(s, with_previews=False) if m.get("side") == side}


def _march_moves(s: GameState, side: str):
    return [m for m in legal_moves(s, with_previews=False)
            if m.get("type") == "cmd_march" and m.get("side") == side]


# SMOKE-146 -----------------------------------------------------------------

def test_lieutenant_march_enumerated_with_lower_lord_group():
    s = load_scenario("crusade_on_novgorod", seed=1)
    # Two co-located mustered Teutonic lords; pair them as Lieutenant+Lower.
    teu = [lid for lid, l in s.lords.items()
           if l.side == "teutonic" and l.state == "mustered"
           and not camp._is_currently_marshal(s, lid)]
    assert len(teu) >= 2
    lt, ll = teu[0], teu[1]
    s.lords[ll].location = s.lords[lt].location
    s.lords[lt].has_lower_lord = ll
    s.lords[ll].lieutenant_of = lt
    # Clear Provender so the march doesn't trip the unrelated
    # excess-provender (4.3.2) gate; this test isolates SMOKE-146.
    for _lid in (lt, ll):
        s.lords[_lid].assets.pop("provender", None)
        s.lords[_lid].assets.pop("loot", None)
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.active_player = "teutonic"
    s.campaign_turn.active_lord = lt
    s.campaign_turn.next_to_reveal = "teutonic"
    s.campaign_turn.in_feed_pay_disband = False
    s.campaign_turn.actions_remaining = camp._effective_command_rating(s, lt)
    marches = _march_moves(s, "teutonic")
    assert marches, "expected at least one cmd_march for the Lieutenant"
    for m in marches:
        assert m["args"].get("group") == [lt, ll], "march must carry the Lower Lord group"
    # And applying one succeeds (no lower_lord_required rejection).
    apply_action(s, marches[0])
    assert s.lords[lt].location == marches[0]["args"]["to"]
    assert s.lords[ll].location == marches[0]["args"]["to"]


# SMOKE-147 -----------------------------------------------------------------

def test_blocked_lord_not_offered_as_muster_target():
    s = load_scenario("crusade_on_novgorod", seed=1)
    s.meta.phase = "levy"
    s.meta.levy_step = "muster"
    s.meta.active_player = "teutonic"
    # Find a Ready Teutonic lord that would otherwise be a muster target.
    ready = [lid for lid, l in s.lords.items()
             if l.side == "teutonic" and l.state == "ready"]
    if not ready:
        return  # scenario without ready teu lords; nothing to assert
    blocked = ready[0]
    s.meta.block_lords_this_levy_t = [blocked]
    for m in legal_moves(s, with_previews=False):
        if m.get("type") == "muster_lord":
            assert m["args"].get("target_lord") != blocked


# SMOKE-148 -----------------------------------------------------------------

def test_sea_trade_not_offered_when_already_used():
    s = load_scenario("crusade_on_novgorod", seed=1)
    s.decks.russian.capabilities_in_play = ["R8"]
    s.meta.phase = "levy"
    s.meta.levy_step = "call_to_arms"
    s.meta.active_player = "russian"
    s.meta.special_rules["sea_trade_r8_used_this_cta"] = True
    moves = [m for m in legal_moves(s, with_previews=False)
             if m.get("type") == "veche_action"
             and m["args"].get("option") == "sea_trade"]
    assert moves == []


# SMOKE-149 -----------------------------------------------------------------

def test_t13_not_offered_when_william_blocked():
    s = load_scenario("crusade_on_novgorod", seed=1)
    s.meta.phase = "levy"
    s.meta.levy_step = "muster"
    s.meta.active_player = "teutonic"
    # Ensure Heinrich is on map so only the William block can suppress T13.
    h = s.lords.get("heinrich")
    if h is not None and h.state != "mustered":
        h.state = "mustered"
        h.location = "leal"
    if "T13" not in (s.decks.teutonic.deck + s.decks.teutonic.discard):
        s.decks.teutonic.deck.append("T13")
    s.meta.special_rules["block_william_of_modena_this_levy"] = True
    t13 = [m for m in legal_moves(s, with_previews=False)
           if m.get("type") == "levy_capability" and m["args"].get("card_id") == "T13"]
    assert t13 == []


# SMOKE-150 -----------------------------------------------------------------

def test_ravage_not_offered_when_two_action_cost_unaffordable():
    s = load_scenario("crusade_on_novgorod", seed=1)
    from nevsky.static_data import load_locales, load_ways
    locs = load_locales()
    # Find a ravageable enemy Locale (russian terr) for a Teutonic Lord,
    # adjacent to a Locale where we can place an enemy (Russian) Lord.
    ways = load_ways()
    target = None
    for w in ways:
        for a, b in ((w["a"], w["b"]), (w["b"], w["a"])):
            la = locs.get(a)
            if la and la.get("territory") == "russian" and la.get("type") not in (None,):
                # a = ravage target, b = adjacency where we put an enemy
                target, adj = a, b
                break
        if target:
            break
    assert target
    teu = next(lid for lid, l in s.lords.items()
               if l.side == "teutonic" and l.state == "mustered")
    s.lords[teu].location = target
    # Put a Russian (enemy) Lord, unbesieged, at an adjacent locale -> cost 2.
    rus = next(lid for lid, l in s.lords.items() if l.side == "russian")
    s.lords[rus].state = "mustered"
    s.lords[rus].location = adj
    s.lords[rus].in_stronghold = False
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.active_player = "teutonic"
    s.campaign_turn.active_lord = teu
    s.campaign_turn.next_to_reveal = "teutonic"
    s.campaign_turn.in_feed_pay_disband = False
    s.campaign_turn.actions_remaining = 1  # only 1 action; ravage needs 2
    assert "cmd_ravage" not in _types(s, "teutonic")
    # With 2 actions it should be offered.
    s.campaign_turn.actions_remaining = 2
    assert "cmd_ravage" in _types(s, "teutonic")
