"""Tests for static reference data (lords, locales, ways, cards).

Per BRIEF every rule encoded in code must have a citing test.
"""

from __future__ import annotations

import pytest

from nevsky.static_data import load_cards, load_locales, load_lords, load_ways, neighbors


def test_twelve_lords_six_per_side() -> None:
    """1.5.1: 12 Lords total, 6 per side."""
    lords = load_lords()
    assert len(lords) == 12
    teu = [lid for lid, l in lords.items() if l["side"] == "teutonic"]
    rus = [lid for lid, l in lords.items() if l["side"] == "russian"]
    assert len(teu) == 6
    assert len(rus) == 6


def test_aleksandr_has_no_fealty() -> None:
    """1.5.3 / 3.4.1: Aleksandr has no Fealty rating;
    only the Veche may Muster him (3.5.2)."""
    aleksandr = load_lords()["aleksandr"]
    assert aleksandr["ratings"]["fealty"] is None
    assert aleksandr["muster_restriction"] == "veche_only"


def test_marshals_one_permanent_per_side() -> None:
    """1.5.1: each side has one permanent Marshal (Andreas, Aleksandr)
    and one secondary Marshal (Hermann if Andreas off; Andrey if
    Aleksandr off)."""
    lords = load_lords()
    perms = [lid for lid, l in lords.items() if l.get("marshal_role") == "permanent"]
    secs = [lid for lid, l in lords.items() if l.get("marshal_role") == "secondary"]
    assert sorted(perms) == ["aleksandr", "andreas"]
    assert sorted(secs) == ["andrey", "hermann"]


def test_ships_authorized_subset_per_2e() -> None:
    """3.4.3 + Lord mat notations: only Lords whose mat carries the
    Ships notation may Levy Ships. Per 2nd Edition: Hermann/Rudolf/
    Yaroslav are 'no Ship'."""
    lords = load_lords()
    no_ships = [lid for lid, l in lords.items() if not l["ships_authorized"]]
    assert sorted(no_ships) == ["hermann", "rudolf", "yaroslav"]


def test_2e_force_changes_applied() -> None:
    """2nd Edition Changes Summary: Hermann and Knud & Abel each replace
    1 Men-at-Arms with 1 Militia; Knud & Abel gain Coin x1."""
    lords = load_lords()
    hermann = lords["hermann"]["starting_forces"]
    assert hermann.get("militia", 0) == 1
    assert hermann.get("men_at_arms", 0) == 1
    knud_abel = lords["knud_and_abel"]
    assert knud_abel["starting_forces"].get("militia", 0) == 1
    assert knud_abel["starting_assets"].get("coin", 0) == 1


def test_special_vassals_gated_by_capability() -> None:
    """3.4.2 (special vassals): Summer Crusaders require T11 Crusade;
    Mongols (Aleksandr) and Kipchaqs (Andrey) require R10 Steppe
    Warriors."""
    lords = load_lords()
    by_special = {}
    for lord_id, lord in lords.items():
        for v in lord["vassals"]:
            sp = v.get("special")
            if sp:
                by_special.setdefault(sp, []).append((lord_id, v["vassal_id"]))
    # Summer Crusaders: 2 (Andreas, Rudolf)
    sc_lords = sorted({lid for lid, _ in by_special["summer_crusaders"]})
    assert sc_lords == ["andreas", "rudolf"]
    # Steppe Warriors: 4 entries (2 Mongols on Aleksandr, 2 Kipchaqs on Andrey)
    sw_lords = sorted({lid for lid, _ in by_special["steppe_warriors"]})
    assert sw_lords == ["aleksandr", "andrey"]
    assert len(by_special["steppe_warriors"]) == 4


def test_locales_count_and_subregions() -> None:
    """Map reference: 51 trackways + 34 waterways across the 53 locales
    listed under Danish Estonia (7), Crusader Livonia (17), Novgorodan
    Rus (29). Header count of '51 total' in the reference is
    inconsistent with the listings; tests follow the listings."""
    locales = load_locales()
    assert len(locales) == 53
    by_subregion: dict[str, int] = {}
    for loc in locales.values():
        by_subregion[loc["subregion"]] = by_subregion.get(loc["subregion"], 0) + 1
    assert by_subregion == {
        "danish_estonia": 7,
        "crusader_livonia": 17,
        "novgorodan_rus": 29,
    }


def test_way_graph_counts() -> None:
    """Map reference: 51 Trackways + 34 Waterways = 85 edges."""
    ways = load_ways()
    tways = [w for w in ways if w["type"] == "trackway"]
    wways = [w for w in ways if w["type"] == "waterway"]
    assert len(tways) == 51
    assert len(wways) == 34


def test_way_graph_only_references_known_locales() -> None:
    """No edge endpoint outside the locale set."""
    locales = load_locales()
    for w in load_ways():
        assert w["a"] in locales, w["a"]
        assert w["b"] in locales, w["b"]


def test_riga_has_only_one_way_waterway() -> None:
    """Map reference 'NOTES': Riga's only connection is a Waterway to
    Wenden -- Riga is one of the 'no trackway' locales."""
    nb = neighbors("riga")
    assert nb == [("wenden", "waterway")]


def test_no_trackway_locales() -> None:
    """Map reference 'LOCALES WITH NO TRACKWAY (Waterway-only)': Riga,
    Luga, Volkhov, Lovat, Rusa."""
    expected_no_track = {"riga", "luga", "volkhov", "lovat", "rusa"}
    actual = set()
    for lid in load_locales():
        nb = neighbors(lid)
        if nb and all(t == "waterway" for _, t in nb):
            actual.add(lid)
    assert expected_no_track <= actual


def test_seaports_eight() -> None:
    """Map reference: Reval, Narwia, Leal, Pernau, Riga, Luga, Koporye,
    Neva are seaports."""
    locales = load_locales()
    seaports = sorted(lid for lid, l in locales.items() if l["seaport"])
    assert seaports == sorted(["reval", "narwia", "leal", "pernau", "riga", "luga", "koporye", "neva"])


def test_novgorod_is_three_vp() -> None:
    """Strongholds reference: Novgorod (Archbishopric) is worth 3 VP
    when Conquered."""
    assert load_locales()["novgorod"]["vp_when_conquered"] == 3


def test_card_count_and_no_event_distribution() -> None:
    """3.1.2-3.1.3: each side has 18 numbered cards + 3 No Event/No
    Capability cards = 21 per deck, 42 total."""
    cards = load_cards()
    assert len(cards) == 42
    teu = [c for c in cards.values() if c["side"] == "teutonic"]
    rus = [c for c in cards.values() if c["side"] == "russian"]
    assert len(teu) == 21
    assert len(rus) == 21
    teu_no = [c for c in teu if c["no_event"]]
    rus_no = [c for c in rus if c["no_event"]]
    assert len(teu_no) == 3
    assert len(rus_no) == 3


def test_card_persistence_types_are_valid() -> None:
    """3.1.3 / 1.9.1: Event persistence is one of immediate / hold /
    this_levy / this_campaign. None for No-Event cards."""
    valid = {"immediate", "hold", "this_levy", "this_campaign", None}
    for c in load_cards().values():
        assert c["event_persistence"] in valid, c
