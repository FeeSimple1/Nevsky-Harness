"""Round 42 — Arts of War Reference Eligibility metadata.

The AoW Reference was updated (commit 44f7694 on origin/main) to add
an explicit "Eligibility: ..." line under each card title plus a
header paragraph explaining the convention. The diff was purely
additive — no Tip rewording, no card-text rewording, no mechanical
changes. Per the R41 blast-radius audit, this is Tier 0 (text-only
clarification) across the board.

This round encodes the new metadata as structured
``event_eligibility`` and ``capability_eligibility`` fields on each
numbered card in ``src/nevsky/data/static/cards.json``. The fields
have the shape:

  {
    "raw": str,                    # original wording from the AoW Reference
    "scope": "lords" | "any" | "all" | "any_except" | "none",
    "side": "teutonic" | "russian" | None,
    "lords": [lord_id, ...],       # populated for scope=="lords"
    "excluded": [lord_id, ...],    # populated for scope=="any_except"
  }

These tests lock the metadata invariants so they cannot silently
drift in future card-data edits.

No mechanical behavior is gated on these fields yet — that would be
a Tier 1 follow-up (e.g., having ``legal_moves`` enumerate only
eligible Lords for capability Levy). For now this is reference data
for the LLM consumer to read.
"""
from __future__ import annotations

from nevsky.static_data import load_cards, load_lords


VALID_SCOPES = {"lords", "any", "all", "any_except", "none"}
VALID_SIDES = {"teutonic", "russian", None}


def _all_lord_ids() -> set[str]:
    return set(load_lords().keys())


def test_every_numbered_card_has_both_eligibility_fields():
    """T1-T18 and R1-R18 each carry both event_eligibility and
    capability_eligibility, except where no_event/no_capability."""
    cards = load_cards()
    expected_ids = {f"T{i}" for i in range(1, 19)} | {f"R{i}" for i in range(1, 19)}
    seen_ids = set()
    for cid, c in cards.items():
        if cid not in expected_ids:
            continue
        seen_ids.add(cid)
        if not c.get("no_event", False):
            assert "event_eligibility" in c, f"{cid} missing event_eligibility"
            assert isinstance(c["event_eligibility"], dict)
        if not c.get("no_capability", False):
            assert "capability_eligibility" in c, f"{cid} missing capability_eligibility"
            assert isinstance(c["capability_eligibility"], dict)
    assert seen_ids == expected_ids


def test_eligibility_scope_is_valid_enum():
    """scope is always one of the 5 known values."""
    cards = load_cards()
    for cid, c in cards.items():
        for key in ("event_eligibility", "capability_eligibility"):
            e = c.get(key)
            if e is None:
                continue
            assert e["scope"] in VALID_SCOPES, (
                f"{cid}.{key} bad scope {e['scope']!r}"
            )


def test_eligibility_side_is_valid_enum():
    """side is teutonic, russian, or None."""
    cards = load_cards()
    for cid, c in cards.items():
        for key in ("event_eligibility", "capability_eligibility"):
            e = c.get(key)
            if e is None:
                continue
            assert e.get("side") in VALID_SIDES, (
                f"{cid}.{key} bad side {e.get('side')!r}"
            )


def test_eligibility_lords_are_real_lord_ids():
    """Every lord_id in scope=='lords' lists must exist in
    static lords.json."""
    cards = load_cards()
    real_ids = _all_lord_ids()
    for cid, c in cards.items():
        for key in ("event_eligibility", "capability_eligibility"):
            e = c.get(key)
            if e is None or e["scope"] != "lords":
                continue
            for lid in e.get("lords", []):
                assert lid in real_ids, (
                    f"{cid}.{key} references unknown lord_id {lid!r}"
                )


def test_eligibility_excluded_are_real_lord_ids():
    """Every lord_id in scope=='any_except' excluded lists must exist."""
    cards = load_cards()
    real_ids = _all_lord_ids()
    for cid, c in cards.items():
        for key in ("event_eligibility", "capability_eligibility"):
            e = c.get(key)
            if e is None or e["scope"] != "any_except":
                continue
            for lid in e.get("excluded", []):
                assert lid in real_ids, (
                    f"{cid}.{key} excludes unknown lord_id {lid!r}"
                )


def test_eligibility_any_and_all_carry_a_side():
    """scope=='any' or 'all' MUST carry a side label."""
    cards = load_cards()
    for cid, c in cards.items():
        for key in ("event_eligibility", "capability_eligibility"):
            e = c.get(key)
            if e is None or e["scope"] not in ("any", "all"):
                continue
            assert e.get("side") in {"teutonic", "russian"}, (
                f"{cid}.{key} scope={e['scope']} has no side"
            )


def test_known_anchors_match_aow_text():
    """Spot-check a handful of cards whose Eligibility text was
    cited explicitly in the AoW Reference update commit. If these
    drift, something has gone wrong with the parsing or with future
    AoW updates."""
    cards = load_cards()
    # T1 Event: Aleksandr, Andrey (Russian cylinders the Teuton may shift).
    assert cards["T1"]["event_eligibility"]["scope"] == "lords"
    assert set(cards["T1"]["event_eligibility"]["lords"]) == {"aleksandr", "andrey"}
    # T1 Capability "Treaty of Stensby": Heinrich, Knud & Abel.
    assert cards["T1"]["capability_eligibility"]["scope"] == "lords"
    assert set(cards["T1"]["capability_eligibility"]["lords"]) == {
        "heinrich", "knud_and_abel"
    }
    # T11 Capability "Crusade": Andreas, Rudolf (the only Levy-able Lords).
    assert cards["T11"]["capability_eligibility"]["scope"] == "lords"
    assert set(cards["T11"]["capability_eligibility"]["lords"]) == {"andreas", "rudolf"}
    # R3 Capability "Streltsy": NOT Karelians (any Russian except Karelians).
    assert cards["R3"]["capability_eligibility"]["scope"] == "any_except"
    assert cards["R3"]["capability_eligibility"]["side"] == "russian"
    assert cards["R3"]["capability_eligibility"]["excluded"] == ["karelians"]
    # T18 Capability "Cogs": Heinrich, Knud & Abel, Andreas.
    assert cards["T18"]["capability_eligibility"]["scope"] == "lords"
    assert set(cards["T18"]["capability_eligibility"]["lords"]) == {
        "heinrich", "knud_and_abel", "andreas"
    }
    # R1 Capability "Luchniki": Gavrilo, Domash, Vladislav, Karelians.
    assert cards["R1"]["capability_eligibility"]["scope"] == "lords"
    assert set(cards["R1"]["capability_eligibility"]["lords"]) == {
        "gavrilo", "domash", "vladislav", "karelians"
    }
    # T14 Event "Bountiful Harvest": dash (no Lord targeting — map effect).
    assert cards["T14"]["event_eligibility"]["scope"] == "none"
    # T5 Event "Marsh": ALL Russian (side-wide block on R Horse).
    assert cards["T5"]["event_eligibility"]["scope"] == "all"
    assert cards["T5"]["event_eligibility"]["side"] == "russian"


def test_no_event_cards_have_no_event_eligibility():
    """The 3 No-Event/No-Capability structural cards per side are
    not subject to AoW eligibility metadata."""
    cards = load_cards()
    for cid, c in cards.items():
        if c.get("no_event", False):
            assert "event_eligibility" not in c, (
                f"{cid} no_event but has event_eligibility"
            )
        if c.get("no_capability", False):
            assert "capability_eligibility" not in c, (
                f"{cid} no_capability but has capability_eligibility"
            )


def test_eligibility_raw_text_matches_aow_reference_quotes():
    """Some specific raw strings are documented in the harness; if
    they drift it likely means cards.json was re-derived against a
    different AoW Reference revision."""
    cards = load_cards()
    assert cards["T1"]["event_eligibility"]["raw"] == "Aleksandr, Andrey"
    assert cards["T11"]["capability_eligibility"]["raw"] == "Andreas, Rudolf"
    assert cards["R3"]["capability_eligibility"]["raw"] == "NOT Karelians"
    assert cards["T5"]["event_eligibility"]["raw"] == "ALL Russian"
    assert cards["T14"]["event_eligibility"]["raw"] in ("-", "—")
