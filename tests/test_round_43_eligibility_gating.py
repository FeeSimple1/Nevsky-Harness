"""Round 43 — SMOKE-029: Eligibility-gating in capability Levy paths.

The AoW Reference update (commit 44f7694) added an explicit
``Eligibility:`` line to every card, documenting which Lord(s) may
Levy / be the target of the Capability or Event. Per the new header
paragraph (lines 5-6 of the updated reference, citing Rules 1.9.1 and
3.4.4): "For Capabilities, [Eligibility] is who may Levy the
Capability AND who is affected by it."

Before R43, ``_h_levy_capability`` and the ``_h_aow_implement_card``
first-Levy this_lord branch did NOT consult the Eligibility metadata.
Probes confirmed eleven distinct same-side ineligible Levies were
silently accepted (Domash levying R5 Druzhina, Heinrich levying T7
Warrior Monks, Hermann levying T11 Crusade, Karelians levying R3
Streltsy onto themselves, etc.), plus two first-Levy auto-implement
cases (T7 under Hermann, R3 under Karelians).

The fix is a single helper ``_check_capability_eligibility`` invoked
from both paths after the existing side / Mustered checks.

Eligibility scopes (per cards.json):
  - ``lords``: by_lord (and target_lord for this_lord) must be in
    the explicit list.
  - ``any`` / ``all``: any same-side Lord qualifies; side already
    checked by surrounding logic.
  - ``any_except``: by_lord / target_lord must NOT be in
    ``excluded``.
  - ``none``: events-only; capabilities never carry this.
"""
from __future__ import annotations

import pytest
from nevsky.actions import apply_action, IllegalAction
from nevsky.scenarios import load_scenario


def _fresh(scenario: str = "crusade_on_novgorod"):
    s = load_scenario(scenario, seed=42)
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "russian", "args": {}})
    s.meta.phase = "levy"
    s.meta.levy_step = "muster"
    return s


def _force_muster(s, lord_id, loc=None):
    sl = s.lords[lord_id]
    sl.state = "mustered"
    if loc is None:
        loc = "reval" if sl.side == "teutonic" else "novgorod"
    sl.location = loc
    sl.lordship_used = 0


def _ensure_in_deck(s, cid):
    side = "teutonic" if cid.startswith("T") else "russian"
    deck = s.decks.teutonic if side == "teutonic" else s.decks.russian
    if cid not in (deck.deck + deck.discard + deck.capabilities_in_play):
        deck.deck.append(cid)


def _try_levy(s, by_lord, cid, target=None):
    s.meta.active_player = s.lords[by_lord].side
    return apply_action(s, {
        "type": "levy_capability",
        "side": s.lords[by_lord].side,
        "args": {"by_lord": by_lord, "card_id": cid,
                  "lord_id": target if target else by_lord},
    })


# --- scope == "lords" rejections ---

def test_smoke_029_levy_rejects_by_lord_not_on_explicit_list():
    """Domash cannot Levy R5 Druzhina (Eligibility: Aleksandr/Gavrilo/Andrey)."""
    s = _fresh()
    _force_muster(s, "domash")
    _ensure_in_deck(s, "R5")
    with pytest.raises(IllegalAction) as e:
        _try_levy(s, "domash", "R5", target="domash")
    assert e.value.code == "ineligible_levyer"


def test_smoke_029_levy_rejects_side_wide_by_lord_not_on_list():
    """Hermann cannot Levy T11 Crusade side-wide (Eligibility: Andreas/Rudolf)."""
    s = _fresh()
    _force_muster(s, "hermann")
    _ensure_in_deck(s, "T11")
    with pytest.raises(IllegalAction) as e:
        _try_levy(s, "hermann", "T11")
    assert e.value.code == "ineligible_levyer"


def test_smoke_029_levy_rejects_target_not_on_list():
    """For a this_lord cap, target_lord must also be on the list.
    (Probe via R5 Druzhina: Aleksandr Levies onto Vladislav.)"""
    s = _fresh()
    _force_muster(s, "aleksandr")
    _force_muster(s, "vladislav")
    _ensure_in_deck(s, "R5")
    with pytest.raises(IllegalAction) as e:
        _try_levy(s, "aleksandr", "R5", target="vladislav")
    assert e.value.code == "ineligible_target"


def test_smoke_029_levy_accepts_eligible_lord_on_list():
    """Andreas Levies T7 Warrior Monks onto himself (Eligibility: Andreas/Rudolf)."""
    s = _fresh()
    _force_muster(s, "andreas")
    _ensure_in_deck(s, "T7")
    r = _try_levy(s, "andreas", "T7", target="andreas")
    assert r["card_id"] == "T7"
    assert r["target_lord"] == "andreas"


# --- scope == "any_except" rejections ---

def test_smoke_029_levy_rejects_by_lord_in_excluded_list():
    """Karelians cannot Levy R3 Streltsy (Eligibility: NOT Karelians)."""
    s = _fresh()
    _force_muster(s, "karelians")
    _ensure_in_deck(s, "R3")
    with pytest.raises(IllegalAction) as e:
        _try_levy(s, "karelians", "R3", target="karelians")
    assert e.value.code == "ineligible_levyer"


def test_smoke_029_levy_rejects_target_in_excluded_list():
    """Aleksandr cannot Levy R3 Streltsy onto Karelians (NOT Karelians)."""
    s = _fresh()
    _force_muster(s, "aleksandr")
    _force_muster(s, "karelians")
    _ensure_in_deck(s, "R3")
    with pytest.raises(IllegalAction) as e:
        _try_levy(s, "aleksandr", "R3", target="karelians")
    assert e.value.code == "ineligible_target"


def test_smoke_029_levy_accepts_excluded_alt_target():
    """Aleksandr Levies R3 Streltsy onto Domash (eligible; Domash is not Karelians)."""
    s = _fresh()
    _force_muster(s, "aleksandr")
    _force_muster(s, "domash")
    _ensure_in_deck(s, "R3")
    r = _try_levy(s, "aleksandr", "R3", target="domash")
    assert r["card_id"] == "R3"
    assert r["target_lord"] == "domash"


# --- scope == "any" / "all" admit any same-side ---

def test_smoke_029_levy_any_scope_admits_any_same_side():
    """Hermann Levies T3 Converts (Eligibility: any Teuton) — should pass."""
    s = _fresh()
    _force_muster(s, "hermann")
    _ensure_in_deck(s, "T3")
    r = _try_levy(s, "hermann", "T3", target="hermann")
    assert r["card_id"] == "T3"


def test_smoke_029_levy_all_scope_admits_any_same_side():
    """Gavrilo Levies R8 Black Sea Trade (Eligibility: ALL Russian, side_wide)."""
    s = _fresh()
    _force_muster(s, "gavrilo")
    _ensure_in_deck(s, "R8")
    r = _try_levy(s, "gavrilo", "R8")
    assert r["card_id"] == "R8"
    assert r["scope"] == "side_wide"


# --- aow_implement_card (first-Levy this_lord branch) ---

def test_smoke_029_aow_implement_rejects_ineligible_target():
    """Hermann cannot receive T7 Warrior Monks via first-Levy implement
    (Eligibility: Andreas/Rudolf)."""
    s = load_scenario("watland", seed=42)
    s.lords["hermann"].state = "mustered"
    s.lords["hermann"].location = "reval"
    s.lords["hermann"].lordship_used = 0
    s.meta.active_player = "teutonic"
    s.decks.teutonic.deck = []
    s.decks.teutonic.pending_draw = ["T7"]
    with pytest.raises(IllegalAction) as e:
        apply_action(s, {"type": "aow_implement_card", "side": "teutonic",
                          "args": {"lord_id": "hermann"}})
    assert e.value.code == "ineligible_target"


def test_smoke_029_aow_implement_rejects_excluded_target():
    """Karelians cannot receive R3 Streltsy via first-Levy implement (NOT Karelians)."""
    s = load_scenario("watland", seed=42)
    s.lords["karelians"].state = "mustered"
    s.lords["karelians"].location = "novgorod"
    s.lords["karelians"].lordship_used = 0
    s.meta.active_player = "russian"
    s.decks.russian.deck = []
    s.decks.russian.pending_draw = ["R3"]
    with pytest.raises(IllegalAction) as e:
        apply_action(s, {"type": "aow_implement_card", "side": "russian",
                          "args": {"lord_id": "karelians"}})
    assert e.value.code == "ineligible_target"


def test_smoke_029_aow_implement_accepts_eligible_target():
    """Andreas can receive T7 Warrior Monks via first-Levy implement."""
    s = load_scenario("watland", seed=42)
    s.decks.teutonic.deck = []
    s.decks.teutonic.pending_draw = ["T7"]
    r = apply_action(s, {"type": "aow_implement_card", "side": "teutonic",
                          "args": {"lord_id": "andreas"}})
    assert r["card"] == "T7"
    assert r["outcome"] == "tucked_under_lord"
    assert r["lord_id"] == "andreas"


# --- Comprehensive positive controls (the AoW Reference's explicit lists) ---

@pytest.mark.parametrize("by_lord,cid,target", [
    ("andreas",       "T7",  "andreas"),       # Warrior Monks → Andreas eligible
    ("rudolf",        "T9",  "rudolf"),        # Halbbrueder → Rudolf eligible
    ("knud_and_abel", "T1",  None),            # Stensby → K&A eligible (side_wide)
    ("heinrich",      "T1",  None),            # Stensby → Heinrich eligible
    ("heinrich",      "T18", "heinrich"),      # Cogs → Heinrich eligible
    ("andreas",       "T18", "andreas"),       # Cogs → Andreas eligible (3-Lord list)
    ("aleksandr",     "R11", "aleksandr"),     # House of Suzdal → Aleksandr eligible
    ("andrey",        "R11", "andrey"),        # House of Suzdal → Andrey eligible
    ("gavrilo",       "R1",  "gavrilo"),       # Luchniki → Gavrilo eligible
    ("karelians",     "R1",  "karelians"),     # Luchniki → Karelians eligible
    ("aleksandr",     "R10", None),            # Steppe Warriors → Aleksandr eligible (side_wide)
])
def test_smoke_029_levy_positive_controls(by_lord, cid, target):
    s = _fresh()
    _force_muster(s, by_lord)
    if target and target != by_lord:
        _force_muster(s, target)
    _ensure_in_deck(s, cid)
    r = _try_levy(s, by_lord, cid, target)
    assert r["card_id"] == cid


# --- Comprehensive negative controls (each of the AoW restricted cards) ---

@pytest.mark.parametrize("by_lord,cid,target,expected_code", [
    ("domash",     "R5",  "domash",     "ineligible_levyer"),   # Druzhina excludes Domash
    ("heinrich",   "T7",  "heinrich",   "ineligible_levyer"),   # Warrior Monks excludes Heinrich
    ("hermann",    "T11", None,         "ineligible_levyer"),   # Crusade excludes Hermann
    ("hermann",    "T9",  "hermann",    "ineligible_levyer"),   # Halbbrueder excludes Hermann
    ("yaroslav",   "T1",  None,         "ineligible_levyer"),   # Stensby excludes Yaroslav
    ("domash",     "R10", None,         "ineligible_levyer"),   # Steppe Warriors excludes Domash
    ("gavrilo",    "R10", None,         "ineligible_levyer"),   # Steppe Warriors excludes Gavrilo
    ("vladislav",  "R11", "vladislav",  "ineligible_levyer"),   # House of Suzdal excludes Vladislav
    ("aleksandr",  "R1",  "aleksandr",  "ineligible_levyer"),   # Luchniki excludes Aleksandr
    ("karelians",  "R3",  "karelians",  "ineligible_levyer"),   # Streltsy excludes Karelians (NOT)
    ("aleksandr",  "R13", "karelians",  "ineligible_target"),   # Streltsy alt (R13) excludes target Karelians
])
def test_smoke_029_levy_negative_controls(by_lord, cid, target, expected_code):
    s = _fresh()
    _force_muster(s, by_lord)
    if target and target != by_lord:
        _force_muster(s, target)
    _ensure_in_deck(s, cid)
    with pytest.raises(IllegalAction) as e:
        _try_levy(s, by_lord, cid, target)
    assert e.value.code == expected_code
