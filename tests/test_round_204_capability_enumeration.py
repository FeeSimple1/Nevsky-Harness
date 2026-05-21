"""Round 204: enumerate every command-step / plan-step / combat action
that had a working handler but was never offered by legal_moves, so a
player driving off legal_actions could never use it.

Gaps fixed (all under-enumeration, the inverse of CROSS_PROJECT_LESSONS
§1): T17 Stonemasons, R4 Smerdi (cmd_muster_serf), Raiders
(cmd_raiders_ravage, T2/R12/R14), the T6/R6 Ambush response window
(play_ambush_block / decline_ambush_block), and 4.1.3 Lieutenant pairing
(place_lieutenant).
"""
from __future__ import annotations

from nevsky.actions import apply_action
import nevsky.campaign as camp
from nevsky.legal_moves import legal_moves
from nevsky.scenarios import load_scenario
from nevsky.state import CombatPending, GameState
from nevsky.static_data import load_locales, load_ways


def _types(s: GameState, side: str) -> set[str]:
    return {m["type"] for m in legal_moves(s, with_previews=False) if m.get("side") == side}


def _set_pristine_command(s: GameState, lord_id: str, side: str) -> None:
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.active_player = side
    s.campaign_turn.active_lord = lord_id
    s.campaign_turn.next_to_reveal = side
    s.campaign_turn.in_feed_pay_disband = False
    s.campaign_turn.actions_remaining = camp._effective_command_rating(s, lord_id)


# --- Stonemasons (T17) ---------------------------------------------------

def test_stonemasons_enumerated_and_applies():
    s = load_scenario("crusade_on_novgorod", seed=1)
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    locs = load_locales()
    target = next(k for k, v in locs.items()
                  if v.get("territory") == "russian" and v.get("type") in ("fort", "town"))
    s.lords[teu].this_lord_capabilities = ["T17"]
    s.lords[teu].location = target
    s.lords[teu].assets["provender"] = 6
    s.locales[target].teutonic_castle = False
    s.locales[target].russian_castle = False
    s.locales[target].siege_markers = 0
    _set_pristine_command(s, teu, "teutonic")
    assert "cmd_stonemasons" in _types(s, "teutonic")
    apply_action(s, {"type": "cmd_stonemasons", "side": "teutonic", "args": {"lord_id": teu}})
    assert s.locales[target].teutonic_castle is True


def test_stonemasons_not_enumerated_without_provender():
    s = load_scenario("crusade_on_novgorod", seed=1)
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    locs = load_locales()
    target = next(k for k, v in locs.items()
                  if v.get("territory") == "russian" and v.get("type") in ("fort", "town"))
    s.lords[teu].this_lord_capabilities = ["T17"]
    s.lords[teu].location = target
    s.lords[teu].assets["provender"] = 2  # < 6, no co-located helpers
    _set_pristine_command(s, teu, "teutonic")
    assert "cmd_stonemasons" not in _types(s, "teutonic")


# --- Smerdi (R4 -> cmd_muster_serf) --------------------------------------

def test_smerdi_muster_serf_enumerated_and_applies():
    s = load_scenario("crusade_on_novgorod", seed=1)
    rus = next(lid for lid, l in s.lords.items() if l.side == "russian" and l.state == "mustered")
    locs = load_locales()
    target = next(k for k, v in locs.items() if v.get("territory") == "russian")
    s.decks.russian.capabilities_in_play = ["R4"]
    s.lords[rus].location = target
    _set_pristine_command(s, rus, "russian")
    assert "cmd_muster_serf" in _types(s, "russian")
    before = s.lords[rus].forces.get("serfs", 0)
    apply_action(s, {"type": "cmd_muster_serf", "side": "russian", "args": {"lord_id": rus}})
    assert s.lords[rus].forces.get("serfs", 0) == before + 1


def test_smerdi_not_enumerated_without_capability():
    s = load_scenario("crusade_on_novgorod", seed=1)
    rus = next(lid for lid, l in s.lords.items() if l.side == "russian" and l.state == "mustered")
    locs = load_locales()
    target = next(k for k, v in locs.items() if v.get("territory") == "russian")
    s.decks.russian.capabilities_in_play = []
    s.lords[rus].location = target
    _set_pristine_command(s, rus, "russian")
    assert "cmd_muster_serf" not in _types(s, "russian")


# --- Raiders (R12 -> cmd_raiders_ravage) ---------------------------------

def test_raiders_ravage_enumerated_and_applies():
    s = load_scenario("crusade_on_novgorod", seed=1)
    rus = next(lid for lid, l in s.lords.items() if l.side == "russian" and l.state == "mustered")
    locs = load_locales()
    # Find a russian-territory locale adjacent to a non-russian, ravageable one.
    src = dest = None
    for w in load_ways():
        for a, b in ((w["a"], w["b"]), (w["b"], w["a"])):
            la, lb = locs.get(a), locs.get(b)
            if not la or not lb:
                continue
            if la.get("territory") == "russian" and lb.get("territory") != "russian":
                ls = s.locales.get(b)
                if (ls and ls.russian_conquered == 0 and ls.teutonic_conquered == 0
                        and not ls.russian_ravaged and not ls.teutonic_ravaged):
                    src, dest = a, b
                    break
        if src:
            break
    assert src and dest, "no suitable raiders target on map"
    # Clear any enemy lord at dest.
    for l in s.lords.values():
        if l.location == dest:
            l.location = None
    s.lords[rus].this_lord_capabilities = ["R12"]
    s.lords[rus].location = src
    s.lords[rus].forces["light_horse"] = 1
    _set_pristine_command(s, rus, "russian")
    moves = [m for m in legal_moves(s, with_previews=False)
             if m.get("type") == "cmd_raiders_ravage" and m["args"].get("to") == dest]
    assert moves, f"cmd_raiders_ravage to {dest} not enumerated"
    apply_action(s, {"type": "cmd_raiders_ravage", "side": "russian",
                     "args": {"lord_id": rus, "to": dest}})
    assert s.locales[dest].russian_ravaged is True


# --- Ambush response window ----------------------------------------------

def test_ambush_window_enumerated_and_suppresses_battle_options():
    s = load_scenario("crusade_on_novgorod", seed=1)
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.active_player = "teutonic"
    s.combat_pending = CombatPending(
        attacker_side="teutonic",
        attacker_group=[],
        from_locale="dorpat",
        to_locale="pskov",
        way_type="trackway",
        defender_side="russian",
        defender_lords=[],
        pending_response_by="teutonic",
        ambush_block_pending=True,
    )
    t = _types(s, "teutonic")
    assert "play_ambush_block" in t
    assert "decline_ambush_block" in t
    # No stand/avoid/withdraw during the ambush window.
    assert "stand_battle" not in t
    assert "avoid_battle" not in t
    assert "withdraw" not in t


# --- Lieutenant pairing (place_lieutenant) -------------------------------

def test_place_lieutenant_enumerated():
    s = load_scenario("crusade_on_novgorod", seed=1)
    rus_lords = [lid for lid, l in s.lords.items()
                 if l.side == "russian" and l.state == "mustered"
                 and not camp._is_currently_marshal(s, lid)
                 and not l.lieutenant_of and not l.has_lower_lord]
    assert len(rus_lords) >= 2, "need two eligible Russian Lords"
    a, b = rus_lords[0], rus_lords[1]
    s.lords[b].location = s.lords[a].location  # co-locate
    s.meta.phase = "campaign"
    s.meta.campaign_step = "plan"
    s.meta.active_player = "russian"
    s.meta.plan_complete_r = False
    pairs = [(m["args"]["lieutenant"], m["args"]["lower_lord"])
             for m in legal_moves(s, with_previews=False)
             if m.get("type") == "place_lieutenant"]
    assert (a, b) in pairs or (b, a) in pairs
    apply_action(s, {"type": "place_lieutenant", "side": "russian",
                     "args": {"lieutenant": a, "lower_lord": b}})
    assert s.lords[a].has_lower_lord == b
