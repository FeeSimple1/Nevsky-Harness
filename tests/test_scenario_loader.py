"""Tests for the state-building scenario loader.

Per BRIEF every rule encoded in code must have a citing test.
"""

from __future__ import annotations

import pytest

from nevsky.scenarios import (
    SCENARIO_IDS,
    ScenarioPlaceholderError,
    load_scenario,
)
from nevsky.state import GameState


PLAYABLE = [s for s in SCENARIO_IDS if s != "quickstart"]


@pytest.mark.parametrize("scenario_id", PLAYABLE)
def test_loader_returns_valid_gamestate(scenario_id: str) -> None:
    """6.0: each playable scenario produces a valid GameState."""
    g = load_scenario(scenario_id, seed=42)
    assert isinstance(g, GameState)
    assert g.meta.scenario_id == scenario_id
    assert g.meta.seed == 42
    assert g.meta.phase == "levy"
    assert g.meta.active_player == "teutonic"  # Sequence of Play 2.2.4: T_then_R.


def test_quickstart_rejected() -> None:
    """6.0: the Quickstart placeholder is not playable until its setup
    is published; loader rejects with ScenarioPlaceholderError."""
    with pytest.raises(ScenarioPlaceholderError):
        load_scenario("quickstart")


def test_pleskau_mustered_lords() -> None:
    """6.0 Pleskau setup: Hermann@Dorpat, Knud&Abel@Reval,
    Yaroslav@Odenpah, Gavrilo@Pskov, Vladislav@Neva."""
    g = load_scenario("pleskau")
    expected = {
        "hermann": "dorpat",
        "knud_and_abel": "reval",
        "yaroslav": "odenpah",
        "gavrilo": "pskov",
        "vladislav": "neva",
    }
    for lid, expected_locale in expected.items():
        l = g.lords[lid]
        assert l.state == "mustered", f"{lid} should be Mustered"
        assert l.location == expected_locale, f"{lid} at {l.location} != {expected_locale}"


def test_pleskau_removed_lords() -> None:
    """6.0 Pleskau setup: Andreas, Heinrich, Aleksandr, Andrey,
    Karelians removed from play."""
    g = load_scenario("pleskau")
    for lid in ("andreas", "heinrich", "aleksandr", "andrey", "karelians"):
        assert g.lords[lid].state == "removed", f"{lid} should be Removed"


def test_watland_aleksandr_not_mustered() -> None:
    """6.0 Watland setup: Aleksandr is on the Calendar (not yet
    Mustered) and not Removed; only the Veche may bring him in."""
    g = load_scenario("watland")
    # Aleksandr is not in Watland's mustered_lords; he's left ready.
    # Watland's removed_from_play is gavrilo only.
    assert g.lords["aleksandr"].state == "ready"
    assert g.lords["gavrilo"].state == "removed"


def test_starting_forces_match_static() -> None:
    """1.6 / 1.5.1: Mustered Lords start with their mat's listed
    Forces, no more, no less. Vassal forces are deployed only on Muster
    Vassal action (3.4.2), so Mustered Lord forces == starting_forces
    from static data, period."""
    from nevsky.static_data import load_lords as static
    g = load_scenario("crusade_on_novgorod")
    for lid, lord in g.lords.items():
        if lord.state != "mustered":
            continue
        expected = {k: v for k, v in static()[lid]["starting_forces"].items() if v}
        assert dict(lord.forces) == expected, f"{lid} forces mismatch"


def test_starting_assets_match_static_minus_transport_choice() -> None:
    """1.7 / 3.4.1: Mustered Lord starting Assets are the static
    starting_assets dict (with explicit Transport types). 'Transport
    (any)' slots are unresolved at scenario start and captured as
    pending decisions (Q-001), not pre-defaulted."""
    from nevsky.static_data import load_lords as static
    g = load_scenario("peipus")
    for lid, lord in g.lords.items():
        if lord.state != "mustered":
            continue
        expected = {k: v for k, v in static()[lid]["starting_assets"].items() if v}
        assert dict(lord.assets) == expected, f"{lid} asset mismatch"


def test_watland_starting_vp() -> None:
    """5.1 / 5.3 / 6.0 Watland: starting markers yield Russian VP=1
    (Veche only) and Teutonic VP=4 (1 Izborsk + 2 Pskov + 0.5 ravage
    Pskov + 0.5 ravage Dubrovno)."""
    g = load_scenario("watland")
    assert g.calendar.russian_vp == 1.0
    assert g.calendar.teutonic_vp == 4.0


def test_peipus_starting_vp_includes_castle() -> None:
    """5.1 / 5.3 / 6.0 Peipus: White Castle at Koporye gives Russian
    VP. Russian total = Veche 4 + 1 Castle = 5. Teutonic = 1 conq +
    2 conq + 6 ravage*0.5 = 6. Matches the scenario reference's
    'Box 5 white Victory marker, Box 6 black Victory marker.'"""
    g = load_scenario("peipus")
    assert g.calendar.russian_vp == 5.0
    assert g.calendar.teutonic_vp == 6.0
    assert g.calendar.boxes[4].russian_victory_marker  # box 5
    assert g.calendar.boxes[5].teutonic_victory_marker  # box 6


def test_rotp_starting_vp_includes_castle() -> None:
    """5.1 / 5.3 / 6.0 Return of the Prince: Black Castle at Koporye
    gives 1 Teutonic VP. Total Teutonic = 4 conquered + 1 castle +
    6*0.5 ravage = 9. Russian = Veche 3."""
    g = load_scenario("return_of_the_prince")
    assert g.calendar.russian_vp == 3.0
    assert g.calendar.teutonic_vp == 9.0
    assert g.calendar.boxes[2].russian_victory_marker  # box 3
    assert g.calendar.boxes[8].teutonic_victory_marker  # box 9


def test_pleskau_decks_remove_no_event_cards() -> None:
    """6.0 Pleskau Special Rule: 'Remove all No Event Arts of War cards
    before play.' All 3 No-Event cards per side go to deck.removed."""
    g = load_scenario("pleskau")
    # 18 numbered, no No-Event in deck:
    assert len(g.decks.teutonic.deck) == 18
    assert len(g.decks.russian.deck) == 18
    assert len(g.decks.teutonic.removed) == 3
    assert len(g.decks.russian.removed) == 3
    for cid in g.decks.teutonic.removed:
        assert "no_event" in cid
    for cid in g.decks.russian.removed:
        assert "no_event" in cid


def test_crusade_on_novgorod_keeps_no_event_cards() -> None:
    """6.0 Crusade on Novgorod Special Rule: 'Do NOT remove No Event /
    No Capability cards.' All 21 cards per side start in deck."""
    g = load_scenario("crusade_on_novgorod")
    assert len(g.decks.teutonic.deck) == 21
    assert len(g.decks.russian.deck) == 21
    assert len(g.decks.teutonic.removed) == 0
    assert len(g.decks.russian.removed) == 0


def test_other_scenarios_keep_no_event_cards_in_deck_at_setup() -> None:
    """3.1.3 (2E): standard scenarios start with No-Event cards in the
    deck; the 'remove on draw' behavior is a runtime mechanic, not a
    setup mechanic. Pleskau is the only setup-time exception."""
    for sid in ("watland", "return_of_the_prince", "return_of_the_prince_nicolle", "peipus"):
        g = load_scenario(sid)
        assert len(g.decks.teutonic.deck) == 21, sid
        assert len(g.decks.russian.deck) == 21, sid


def test_all_locales_in_state() -> None:
    """The loader populates every static locale into the GameState's
    locales dict (default-empty if not in scenario.markers_on_map)."""
    g = load_scenario("watland")
    assert len(g.locales) == 53


def test_calendar_levy_marker_at_start_box() -> None:
    """2.2.2: scenarios begin with the Levy/Campaign marker on the
    start box, Levy face up."""
    for sid, expected_box in [
        ("pleskau", 1),
        ("watland", 4),
        ("return_of_the_prince", 9),
        ("return_of_the_prince_nicolle", 9),
        ("peipus", 13),
        ("crusade_on_novgorod", 1),
    ]:
        g = load_scenario(sid)
        cb = g.calendar.boxes[expected_box - 1]
        assert cb.has_levy_campaign_marker, sid
        assert cb.levy_campaign_face == "levy", sid


def test_pleskau_calendar_setup() -> None:
    """6.0 Pleskau Calendar:
      Box 1: white Victory marker, Levy marker, Rudolf cylinder, Domash cylinder.
      Box 2: Yaroslav Service marker.
      Box 3: Knud & Abel Service marker, Vladislav Service marker.
      Box 4: Hermann Service marker, Gavrilo Service marker."""
    g = load_scenario("pleskau")
    b1, b2, b3, b4 = g.calendar.boxes[:4]
    assert sorted(b1.cylinders) == sorted(["rudolf", "domash"])
    assert b1.has_levy_campaign_marker and b1.levy_campaign_face == "levy"
    assert b1.russian_victory_marker
    assert sorted(b2.service_markers) == ["yaroslav"]
    assert sorted(b3.service_markers) == sorted(["knud_and_abel", "vladislav"])
    assert sorted(b4.service_markers) == sorted(["gavrilo", "hermann"])


def test_setup_pending_transport_choices_match_lord_count() -> None:
    """Q-001 / 3.4.1: each Mustered Lord with 'Transport (any)' starts
    with one pending setup_transport_choice per any-slot. Removed and
    Ready Lords do not generate pending choices."""
    g = load_scenario("crusade_on_novgorod")
    pds = [pd for pd in g.pending_decisions if pd.kind == "setup_transport_choice"]
    # Mustered: hermann (1 any), yaroslav (1 any), gavrilo (1 any),
    # vladislav (1 any). Knud&Abel are explicitly Ship x2 (no any).
    expected_lords = sorted(["hermann", "yaroslav", "gavrilo", "vladislav"])
    actual_lords = sorted(pd.context["lord_id"] for pd in pds)
    assert actual_lords == expected_lords


def test_vassals_special_start_unready() -> None:
    """3.4.2 (special vassals): Special Vassals (Summer Crusaders,
    Mongols, Kipchaqs) start ready=False because their gating
    Capability is not in play at scenario start."""
    g = load_scenario("crusade_on_novgorod")
    aleksandr = g.lords["aleksandr"]
    # aleksandr_mongols_1 / aleksandr_mongols_2 -> not ready.
    assert aleksandr.vassals["aleksandr_mongols_1"].ready is False
    assert aleksandr.vassals["aleksandr_mongols_2"].ready is False
    # aleksandr_pereyaslavl -> ready (no special)
    assert aleksandr.vassals["aleksandr_pereyaslavl"].ready is True


def test_round_trip_json_is_bit_identical() -> None:
    """BRIEF Determinism: state files are portable across sessions and
    loading + saving reproduces the same bytes."""
    g = load_scenario("pleskau", seed=123)
    s1 = g.model_dump_json(indent=2)
    g2 = GameState.model_validate_json(s1)
    s2 = g2.model_dump_json(indent=2)
    assert s1 == s2


def test_watland_special_victory_rule_recorded_in_meta() -> None:
    """6.0 Watland: Teutons win only with >=7 VP AND >=2x Russian VP;
    otherwise Russians (no tie). The flag must be carried in
    meta.special_rules so Phase 3 victory check can reach it."""
    g = load_scenario("watland")
    sr = g.meta.special_rules
    assert sr.get("victory_override") == "watland"


def test_pleskau_victory_lord_removed_bonus_flagged() -> None:
    """6.0 Pleskau: scenario-only +1 VP per enemy Lord removed must be
    discoverable from state (meta.special_rules)."""
    g = load_scenario("pleskau")
    assert g.meta.special_rules.get("victory_lord_removed_bonus") is True
