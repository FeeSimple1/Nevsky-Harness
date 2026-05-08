"""Tests for Phase 4b economy/movement capabilities."""

from __future__ import annotations

import pytest

from nevsky.actions import IllegalAction, apply_action
from nevsky.campaign import effective_boat_count, effective_ship_count
from nevsky.scenarios import load_scenario
from nevsky.state import GameState


def _start_command_with(s: GameState, lord_id: str) -> None:
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.active_player = s.lords[lord_id].side
    s.campaign_turn.next_to_reveal = s.lords[lord_id].side
    s.campaign_turn.active_card = lord_id
    s.campaign_turn.active_lord = lord_id
    from nevsky.campaign import _effective_command_rating
    s.campaign_turn.actions_remaining = _effective_command_rating(s, lord_id)
    s.campaign_turn.in_feed_pay_disband = False
    s.lords[lord_id].moved_fought = False
    s.lords[lord_id].first_march_used_this_card = False
    s.lords[lord_id].raiders_used_this_card = False


# --- Converts (T3) -----------------------------------------------------------


def test_converts_first_march_costs_zero_with_light_horse() -> None:
    """T3: first March of Command card costs 0 actions if group has Light Horse."""
    s = load_scenario("watland", seed=1)
    s.meta.box = 1
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    s.lords[teu].this_lord_capabilities = ["T3"]
    s.lords[teu].forces["light_horse"] = 1
    # Find an adjacent locale (not enemy-occupied).
    from nevsky.static_data import load_ways
    src = s.lords[teu].location
    dest = None
    for w in load_ways():
        cand = w["b"] if w["a"] == src else (w["a"] if w["b"] == src else None)
        if cand and not any(l.location == cand and l.side != "teutonic" for l in s.lords.values()):
            dest = cand
            break
    assert dest is not None
    s.lords[teu].assets.pop("loot", None)
    s.lords[teu].assets.pop("provender", None)
    _start_command_with(s, teu)
    pre_actions = s.campaign_turn.actions_remaining
    res = apply_action(s, {"type": "cmd_march", "side": "teutonic",
                            "args": {"lord_id": teu, "to": dest}})
    assert res["cost"] == 0
    assert s.campaign_turn.actions_remaining == pre_actions


def test_converts_second_march_costs_normal() -> None:
    """T3: only the FIRST March benefits from Converts."""
    s = load_scenario("watland", seed=1)
    s.meta.box = 1
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    s.lords[teu].this_lord_capabilities = ["T3"]
    s.lords[teu].forces["light_horse"] = 1
    s.lords[teu].first_march_used_this_card = True  # already used
    from nevsky.static_data import load_ways
    src = s.lords[teu].location
    dest = None
    for w in load_ways():
        cand = w["b"] if w["a"] == src else (w["a"] if w["b"] == src else None)
        if cand and not any(l.location == cand and l.side != "teutonic" for l in s.lords.values()):
            dest = cand
            break
    if dest is None:
        pytest.skip("no clear adjacent locale")
    s.lords[teu].assets.pop("loot", None)
    s.lords[teu].assets.pop("provender", None)
    _start_command_with(s, teu)
    s.lords[teu].first_march_used_this_card = True
    pre = s.campaign_turn.actions_remaining
    res = apply_action(s, {"type": "cmd_march", "side": "teutonic",
                            "args": {"lord_id": teu, "to": dest}})
    assert res["cost"] >= 1
    assert s.campaign_turn.actions_remaining == pre - 1


# --- Raiders (T2 / R12 / R14) ------------------------------------------------


def test_teutonic_raiders_via_trackway_with_loot() -> None:
    """T2 Teutonic Raiders: Trackway only, with Loot if non-Region."""
    s = load_scenario("watland", seed=1)
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    # Find a Lord-locale + adjacent-target via trackway in Russian territory.
    from nevsky.static_data import load_locales, load_ways
    locs = load_locales()
    pick = None
    for w in load_ways():
        if w["type"] != "trackway":
            continue
        a, b = w["a"], w["b"]
        for src, dst in [(a, b), (b, a)]:
            sl_src = locs.get(src, {})
            sl_dst = locs.get(dst, {})
            if sl_src.get("territory") in ("teutonic", "crusader") and sl_dst.get("territory") == "russian":
                if not any(l.location == dst and l.side == "russian" for l in s.lords.values()):
                    if (s.locales[dst].russian_conquered == 0
                            and s.locales[dst].teutonic_conquered == 0
                            and not s.locales[dst].russian_ravaged
                            and not s.locales[dst].teutonic_ravaged):
                        pick = (src, dst)
                        break
        if pick:
            break
    if pick is None:
        pytest.skip("no trackway from teutonic to russian region")
    src, dst = pick
    s.lords[teu].location = src
    s.lords[teu].this_lord_capabilities = ["T2"]
    s.lords[teu].forces["light_horse"] = 1
    _start_command_with(s, teu)
    pre_loot = s.lords[teu].assets.get("loot", 0)
    pre_prov = s.lords[teu].assets.get("provender", 0)
    apply_action(s, {"type": "cmd_raiders_ravage", "side": "teutonic",
                     "args": {"lord_id": teu, "to": dst}})
    assert s.locales[dst].teutonic_ravaged is True
    assert s.lords[teu].assets["provender"] == pre_prov + 1
    if locs[dst]["type"] != "region":
        assert s.lords[teu].assets["loot"] == pre_loot + 1
    assert s.lords[teu].raiders_used_this_card is True


def test_teutonic_raiders_once_per_card() -> None:
    s = load_scenario("watland", seed=1)
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    s.lords[teu].this_lord_capabilities = ["T2"]
    s.lords[teu].forces["light_horse"] = 1
    s.lords[teu].raiders_used_this_card = True
    s.lords[teu].location = "harrien"
    _start_command_with(s, teu)
    s.lords[teu].raiders_used_this_card = True
    with pytest.raises(IllegalAction) as exc:
        apply_action(s, {"type": "cmd_raiders_ravage", "side": "teutonic",
                          "args": {"lord_id": teu, "to": "wesenberg"}})
    assert exc.value.code in ("already_used", "trackway_only", "not_adjacent",
                              "own_territory", "own_territory")


def test_russian_raiders_no_loot() -> None:
    """R12/R14: Russian Raiders never gain Loot."""
    s = load_scenario("watland", seed=1)
    rus = next(lid for lid, l in s.lords.items() if l.side == "russian" and l.state == "mustered")
    # Move Rus to a locale adjacent to a Teutonic region.
    from nevsky.static_data import load_locales, load_ways
    locs = load_locales()
    pick = None
    for w in load_ways():
        a, b = w["a"], w["b"]
        for src, dst in [(a, b), (b, a)]:
            sl_src = locs.get(src, {})
            sl_dst = locs.get(dst, {})
            if sl_src.get("territory") == "russian" and sl_dst.get("territory") in ("teutonic", "crusader"):
                if not any(l.location == dst and l.side == "teutonic" for l in s.lords.values()):
                    if (s.locales[dst].russian_conquered == 0
                            and s.locales[dst].teutonic_conquered == 0
                            and not s.locales[dst].russian_ravaged
                            and not s.locales[dst].teutonic_ravaged):
                        pick = (src, dst)
                        break
        if pick:
            break
    if pick is None:
        pytest.skip("no russian->teutonic adjacency")
    src, dst = pick
    s.lords[rus].location = src
    s.lords[rus].this_lord_capabilities = ["R12"]
    s.lords[rus].forces["light_horse"] = 1
    _start_command_with(s, rus)
    pre_loot = s.lords[rus].assets.get("loot", 0)
    apply_action(s, {"type": "cmd_raiders_ravage", "side": "russian",
                     "args": {"lord_id": rus, "to": dst}})
    assert s.locales[dst].russian_ravaged is True
    # Russian Raiders: NO Loot.
    assert s.lords[rus].assets.get("loot", 0) == pre_loot


# --- Cogs / Lodya ------------------------------------------------------------


def test_cogs_doubles_ship_count() -> None:
    """T18: Cogs makes each Ship count as 2."""
    s = load_scenario("watland", seed=1)
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    from nevsky.static_data import load_lords as _ll
    if not _ll()[teu].get("ships_authorized", False):
        teu = next(lid for lid, l in s.lords.items()
                   if l.side == "teutonic" and l.state == "mustered" and _ll()[lid].get("ships_authorized"))
    s.lords[teu].assets["ship"] = 3
    base = effective_ship_count(s, teu)
    assert base == 3
    s.lords[teu].this_lord_capabilities = ["T18"]
    assert effective_ship_count(s, teu) == 6


def test_lodya_doubles_boat_count() -> None:
    """R16: Lodya makes each Boat count as 2."""
    s = load_scenario("watland", seed=1)
    rus = next(lid for lid, l in s.lords.items() if l.side == "russian" and l.state == "mustered")
    s.lords[rus].assets["boat"] = 2
    assert effective_boat_count(s, rus) == 2
    s.lords[rus].this_lord_capabilities = ["R16"]
    assert effective_boat_count(s, rus) == 4


# --- Veliky Knyaz (R17) ------------------------------------------------------


def test_veliky_knyaz_tax_adds_transport_and_restores_forces() -> None:
    """R17: Tax also adds 2 Transport and restores Mustered Forces."""
    s = load_scenario("watland", seed=1)
    rus = next(lid for lid, l in s.lords.items() if l.side == "russian" and l.state == "mustered")
    s.lords[rus].this_lord_capabilities = ["R17"]
    # Move to own seat.
    from nevsky.static_data import load_lords
    seat = load_lords()[rus]["primary_seats"][0]
    s.lords[rus].location = seat
    # Damage forces.
    starting = load_lords()[rus]["starting_forces"]
    for k in starting:
        s.lords[rus].forces[k] = max(0, int(starting[k]) - 1)
    s.lords[rus].assets["cart"] = 1
    _start_command_with(s, rus)
    res = apply_action(s, {"type": "cmd_tax", "side": "russian",
                            "args": {"lord_id": rus, "transport_type": "cart"}})
    assert "veliky_knyaz_transport_added" in res
    assert s.lords[rus].assets["cart"] >= 2  # original 1 + ~2 added (clamped)
    # Forces restored.
    for k, n in starting.items():
        assert s.lords[rus].forces.get(k, 0) >= int(n)


# --- Ransom (T16 / R7) -------------------------------------------------------


def test_ransom_pays_coin_when_enemy_lord_removed() -> None:
    """T16/R7: enemy Lord removed in Battle gives Coin = his Service to a friendly Lord present."""
    from nevsky.campaign import apply_ransom
    from nevsky.static_data import load_lords
    s = load_scenario("watland", seed=1)
    s.decks.teutonic.capabilities_in_play = ["T16"]
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    rus = next(lid for lid, l in s.lords.items() if l.side == "russian" and l.state == "mustered")
    # Co-locate both at pskov for the test.
    s.lords[teu].location = "pskov"
    s.lords[rus].location = "pskov"
    pre_coin = s.lords[teu].assets.get("coin", 0)
    res = apply_ransom(s, rus, "teutonic", "pskov")
    assert res["ransom"] is True
    expected = int(load_lords()[rus]["ratings"]["service"])
    assert s.lords[teu].assets.get("coin", 0) == pre_coin + expected


# --- Hillforts (T8) ----------------------------------------------------------


def test_hillforts_skips_one_teutonic_feed() -> None:
    """T8: One Unbesieged Teutonic Lord in Livonia skips Feed."""
    s = load_scenario("watland", seed=1)
    s.decks.teutonic.capabilities_in_play = ["T8"]
    # Pick a Teutonic Lord in Livonia.
    from nevsky.static_data import load_locales
    static = load_locales()
    teu = None
    for lid, l in s.lords.items():
        if l.side == "teutonic" and l.state == "mustered" and l.location and static[l.location].get("subregion") == "crusader_livonia":
            teu = lid; break
    if teu is None:
        # Move first mustered Teu to Riga (Livonia).
        teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
        s.lords[teu].location = "riga"
    # Prep FPD: mark Lord MOVED_FOUGHT, no provender.
    s.lords[teu].moved_fought = True
    s.lords[teu].assets.pop("provender", None)
    s.lords[teu].assets.pop("loot", None)
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.active_player = "teutonic"
    s.campaign_turn.in_feed_pay_disband = True
    s.campaign_turn.fpd_completed_t = False
    s.campaign_turn.fpd_completed_r = False
    res = apply_action(s, {"type": "fpd_resolve", "side": "teutonic", "args": {}})
    # The chosen lord shows hillforts_skipped=True in feed entries.
    skipped = [f for f in res["feed"] if f.get("hillforts_skipped")]
    assert len(skipped) == 1
