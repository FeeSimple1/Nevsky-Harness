"""R193 — Q-R190-A auto-discard for un-implementable this_lord
Capability at first Levy.

Per user adjudication (RULES_DECISIONS.md Q-R190-A): when
_h_aow_implement_card is invoked for a this_lord Capability and
NO Mustered own-side Lord matches the coats of arms (the same
eligibility predicate 3.4.4 uses, evaluated automatically at
first Levy), the handler must pop pending_draw, append to
deck.discard, return outcome='discarded_no_eligible_lord'
with reason='no_eligible_lord'. The card may resurface as an
Event in later Levies.

Eligibility predicate reuses _check_capability_eligibility so
all four scope codes (lords/any/all/any_except) are honored
identically to SMOKE-029's player-pick gate.
"""
from __future__ import annotations

import nevsky.actions  # noqa: F401
from nevsky.actions import apply_action
from nevsky.legal_moves import legal_moves
from nevsky.scenarios import load_scenario


def _setup_arts_of_war(s, side: str):
    s.meta.phase = "levy"
    s.meta.levy_step = "arts_of_war"
    s.meta.active_player = side
    s.meta.first_levy_done = False


# ----- R193: Handler auto-discard --------------------------------------------


def test_r193_r11_in_pleskau_auto_discards():
    """R11 House of Suzdal (this_lord, eligibility: aleksandr+andrey).
    In pleskau both are in removed_from_play. Handler must
    auto-discard."""
    s = load_scenario("pleskau", seed=1)
    s.decks.russian.pending_draw = ["R11"]
    _setup_arts_of_war(s, "russian")
    res = apply_action(s, {"type": "aow_implement_card",
                           "side": "russian",
                           "args": {"card_id": "R11"}})
    assert res["outcome"] == "discarded_no_eligible_lord"
    assert res["reason"] == "no_eligible_lord"
    assert "rule" in res  # citation pin
    assert s.decks.russian.pending_draw == []
    assert "R11" in s.decks.russian.discard
    # Card NOT permanently removed — it can resurface as an Event
    # in later Levies.
    assert "R11" not in s.decks.russian.removed


def test_r193_eligible_lord_path_unchanged():
    """Positive control: when an eligible Lord IS mustered, the
    Capability tucks under that Lord normally — no auto-discard."""
    s = load_scenario("pleskau", seed=1)
    # R1 Luchniki: eligibility ['gavrilo', 'domash', 'vladislav',
    # 'karelians']. Gavrilo IS mustered in pleskau.
    s.decks.russian.pending_draw = ["R1"]
    _setup_arts_of_war(s, "russian")
    res = apply_action(s, {"type": "aow_implement_card",
                           "side": "russian",
                           "args": {"card_id": "R1",
                                    "lord_id": "gavrilo"}})
    assert res["outcome"] == "tucked_under_lord"
    assert res["lord_id"] == "gavrilo"
    assert "R1" in s.lords["gavrilo"].this_lord_capabilities
    assert "R1" not in s.decks.russian.discard


def test_r193_only_one_eligible_lord_needed():
    """Per adjudication: only ONE Mustered Lord matching the coats
    of arms is required. Construct a state where one eligible Lord
    is mustered and another isn't — handler must NOT auto-discard."""
    s = load_scenario("watland", seed=1)
    # R5 Druzhina: eligibility ['aleksandr', 'gavrilo', 'andrey'].
    # Watland: aleksandr / gavrilo / andrey states vary; force one
    # of them mustered and the other two not.
    for lid in ("aleksandr", "andrey"):
        if lid in s.lords:
            s.lords[lid].state = "ready"
            s.lords[lid].location = None
    # Muster gavrilo manually so he's the only eligible target.
    if "gavrilo" in s.lords:
        s.lords["gavrilo"].state = "mustered"
        s.lords["gavrilo"].location = "novgorod"
    s.decks.russian.pending_draw = ["R5"]
    _setup_arts_of_war(s, "russian")
    # With Gavrilo eligible, handler must NOT auto-discard — must
    # require lord_id.
    moves = legal_moves(s, with_previews=False)
    imp = [m for m in moves if m.get("type") == "aow_implement_card"]
    # At least one option should be offered with lord_id=gavrilo
    has_gavrilo = any(m["args"].get("lord_id") == "gavrilo" for m in imp)
    assert has_gavrilo, (
        f"enumerator should offer R5 implementation on gavrilo: {imp}"
    )


def test_r193_all_scope_capability_auto_discards_when_no_mustered():
    """Edge case: scope='all'/'any' (e.g. R5 with NO Russian Lord
    mustered). Handler must auto-discard, not require lord_id."""
    s = load_scenario("watland", seed=1)
    # Remove ALL Russian Mustered Lords so no scope='all' or 'any'
    # capability has a target.
    for lid, lord in s.lords.items():
        if lord.side == "russian" and lord.state == "mustered":
            lord.state = "ready"
            lord.location = None
    s.decks.russian.pending_draw = ["R5"]  # eligibility list ['aleksandr', 'gavrilo', 'andrey']
    _setup_arts_of_war(s, "russian")
    res = apply_action(s, {"type": "aow_implement_card",
                           "side": "russian",
                           "args": {"card_id": "R5"}})
    assert res["outcome"] == "discarded_no_eligible_lord"
    assert "R5" in s.decks.russian.discard


# ----- R193: Enumerator emits the discard option -----------------------------


def test_r193_enumerator_emits_single_discard_option():
    """SMOKE-124 enumerator update: when no Lord is eligible, emit
    a single aow_implement_card option WITHOUT lord_id that the
    handler will route through auto-discard."""
    s = load_scenario("pleskau", seed=1)
    s.decks.russian.pending_draw = ["R11"]
    _setup_arts_of_war(s, "russian")
    moves = legal_moves(s, with_previews=False)
    imp = [m for m in moves if m.get("type") == "aow_implement_card"]
    assert len(imp) == 1, f"expected exactly 1 discard option; got {imp}"
    assert imp[0]["args"]["card_id"] == "R11"
    assert "lord_id" not in imp[0]["args"]
    # And it round-trips cleanly.
    snap = s.model_copy(deep=True)
    res = apply_action(snap, imp[0])
    assert res["outcome"] == "discarded_no_eligible_lord"


# ----- Source-marker guardrails ----------------------------------------------


def test_r193_source_markers_present():
    """Q-R190-A marker must persist in both actions.py and
    legal_moves.py so future refactors don't silently drop the path."""
    import inspect
    import nevsky.actions as a
    import nevsky.legal_moves as lm
    assert "Q-R190-A" in inspect.getsource(a), (
        "Q-R190-A marker missing from actions.py")
    assert "Q-R190-A" in inspect.getsource(lm), (
        "Q-R190-A marker missing from legal_moves.py")
