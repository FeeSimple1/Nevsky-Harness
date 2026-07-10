"""PLAY-38 regression tests (audit item #9): Tier 2 Battle Holds are
NAMED in the palette.

Tier 2 Battle Holds (T4/R1 Bridge, T5/R2 Marsh, T6/R6 Ambush, T9/R5
Hill, T10 Field Organ, R4 Raven's Rock) are consumed via `stand_battle
args.holds` (and T10 via `cmd_storm args.field_organ_lord`), but the
palette never mentioned them -- a palette-driven agent could not
discover they existed. This was a parity/UX gap, not a rules
divergence: PLAY-38 attaches a `holds_available` block (plus
`holds_template`) to the bare `stand_battle` palette entry and to
`cmd_storm`, mirroring the `_consume_battle_holds` gates exactly
(in-holds, SMOKE-079 season gates, SMOKE-080 Defending-only gates, T10
Teutonic-participant targets, Bridge enemy-Lord targets). The entry's
concrete `args` are unchanged, so sweep probing semantics are
untouched.
"""
from __future__ import annotations

import nevsky.actions  # noqa: F401
from nevsky.actions import apply_action
from nevsky.legal_moves import legal_moves
from nevsky.scenarios import load_scenario
from nevsky.state import CombatPending, GameState


def _pending(s: GameState, atk=("heinrich",), dfn=("gavrilo",)):
    for lid in atk:
        s.lords[lid].state = "mustered"
        s.lords[lid].location = "pskov"
        s.lords[lid].forces = {"knights": 3}
    for lid in dfn:
        s.lords[lid].state = "mustered"
        s.lords[lid].location = "pskov"
        s.lords[lid].forces = {"militia": 3}
    s.combat_pending = CombatPending(
        attacker_side="teutonic", attacker_group=list(atk),
        from_locale="izborsk", to_locale="pskov", way_type="trackway",
        defender_side="russian", defender_lords=list(dfn),
        pending_response_by="russian", laden=False,
    )
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.campaign_turn.active_card = atk[0]
    s.campaign_turn.active_lord = atk[0]
    s.campaign_turn.actions_remaining = 2
    s.meta.active_player = "russian"


def _stand_entry(s: GameState):
    for m in legal_moves(s, with_previews=False):
        if m.get("type") == "stand_battle" and m.get("args") == {}:
            return m
    return None


def test_palette_names_holds_of_both_sides():
    """Summer, Russians defending: R2 Marsh / R5 Hill (defending-only)
    and the attacker's T6 Ambush all appear, each with its args key."""
    s = load_scenario("crusade_on_novgorod", seed=42)  # summer
    _pending(s)
    s.decks.russian.holds = ["R2", "R5"]
    s.decks.teutonic.holds = ["T6"]
    m = _stand_entry(s)
    ha = {e["card"]: e for e in m.get("holds_available", [])}
    assert set(ha) == {"R2", "R5", "T6"}
    assert ha["R2"]["key"] == "marsh"
    assert ha["R5"]["key"] == "hill"
    assert ha["T6"]["key"] == "ambush"
    assert "holds_template" in m
    # The entry's concrete args stay bare (sweep semantics unchanged).
    assert m["args"] == {}


def test_defending_only_gate_mirrored():
    """T5/T9 are Defending-only: with the TEUTONS attacking they must
    NOT be listed even though the cards sit in Teutonic holds."""
    s = load_scenario("crusade_on_novgorod", seed=42)
    _pending(s)
    s.decks.teutonic.holds = ["T5", "T9", "T6"]
    s.decks.russian.holds = []
    ha = {e["card"] for e in _stand_entry(s).get("holds_available", [])}
    assert "T5" not in ha and "T9" not in ha
    assert "T6" in ha  # ambush has no Defending-only gate


def test_season_gates_mirrored():
    """Winter (watland): Bridge/Marsh excluded; Summer: Raven's Rock
    excluded."""
    s = load_scenario("watland", seed=1)  # early_winter
    _pending(s, atk=("hermann",), dfn=("gavrilo",))
    s.decks.teutonic.holds = ["T4", "T5", "T6"]
    s.decks.russian.holds = ["R4"]
    ha = {e["card"] for e in _stand_entry(s).get("holds_available", [])}
    assert "T4" not in ha and "T5" not in ha   # non-Winter cards
    assert "T6" in ha                            # no season gate
    assert "R4" in ha                            # non-Summer card, Winter OK

    s2 = load_scenario("crusade_on_novgorod", seed=42)  # summer
    _pending(s2)
    s2.decks.russian.holds = ["R4"]
    s2.decks.teutonic.holds = []
    ha2 = {e["card"] for e in _stand_entry(s2).get("holds_available", [])}
    assert "R4" not in ha2


def test_t10_and_bridge_list_targets():
    s = load_scenario("crusade_on_novgorod", seed=42)
    _pending(s)
    s.decks.teutonic.holds = ["T10", "T4"]
    s.decks.russian.holds = []
    ha = {e["card"]: e for e in _stand_entry(s).get("holds_available", [])}
    assert ha["T10"]["requires"]["field_organ_lord"] == ["heinrich"]
    assert ha["T4"]["requires"]["bridge_target_lord"] == ["gavrilo"]


def test_no_holds_no_block():
    s = load_scenario("crusade_on_novgorod", seed=42)
    _pending(s)
    s.decks.teutonic.holds = []
    s.decks.russian.holds = []
    m = _stand_entry(s)
    assert "holds_available" not in m


def test_named_hold_roundtrips_through_stand_battle():
    """A palette-named hold must be consumable exactly as advertised:
    args.holds = {key: card} on stand_battle."""
    s = load_scenario("crusade_on_novgorod", seed=42)
    _pending(s)
    s.decks.russian.holds = ["R2"]
    s.decks.teutonic.holds = []
    e = next(x for x in _stand_entry(s).get("holds_available", [])
             if x["card"] == "R2")
    res = apply_action(s, {"type": "stand_battle", "side": "russian",
                           "args": {"holds": {e["key"]: e["card"]}}})
    assert any(h.get("card") == "R2"
               for h in res["battle"].get("holds_consumed", []))
    assert "R2" not in s.decks.russian.holds
    assert "R2" in s.decks.russian.discard


def test_cmd_storm_surfaces_t10():
    from nevsky.static_data import load_lords
    s = load_scenario("pleskau", seed=2)  # summer
    teu = next(lid for lid, l in s.lords.items()
               if l.side == "teutonic" and l.state == "mustered")
    rus = next(lid for lid, l in s.lords.items()
               if l.side == "russian" and l.state == "mustered")
    s.lords[teu].location = "pskov"
    s.lords[teu].in_stronghold = False
    s.lords[rus].location = "pskov"
    s.lords[rus].in_stronghold = True
    s.locales["pskov"].siege_markers = 2
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.active_player = "teutonic"
    s.campaign_turn.active_card = teu
    s.campaign_turn.active_lord = teu
    s.campaign_turn.actions_remaining = int(
        load_lords()[teu]["ratings"]["command"])
    s.campaign_turn.in_feed_pay_disband = False
    s.decks.teutonic.holds = ["T10"]
    storm = next(m for m in legal_moves(s, with_previews=False)
                 if m.get("type") == "cmd_storm")
    ha = storm.get("holds_available", [])
    assert ha and ha[0]["card"] == "T10"
    assert teu in ha[0]["requires"]["field_organ_lord"]
