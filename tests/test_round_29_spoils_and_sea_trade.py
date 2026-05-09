"""Round 29: Spoils modes (4.4.5) + R8/R9 Sea Trade Coin gates (3.5.2).

Spoils modes per 4.4.5 / Battle and Storm Reference:
  - removed                        -> all_except_ships
  - retreated WITHOUT conceding    -> all_except_ships
  - conceded then retreated        -> loot + excess_provender
  - withdrew                       -> none
  - Storm Sack: from each removed Besieged Lord (all_except_ships)
                + from Stronghold {loot, prov, coin} = stronghold VP
                + Novgorod special: Veche Coin to attackers

Sea Trade gates per 3.5.2:
  - R8 Black Sea Trade: +1 Coin / Call to Arms,
       blocked if Novgorod or Lovat Conquered.
  - R9 Baltic Sea Trade: +2 Coin / non-Winter Call to Arms,
       blocked if Novgorod or Neva Conquered, or Teuton ships > Rus.
"""
from __future__ import annotations

import pytest

from nevsky.actions import IllegalAction, apply_action
from nevsky.battle import transfer_spoils
from nevsky.scenarios import load_scenario


# ---------------------------------------------------------------------------
# 4.4.5 Spoils modes
# ---------------------------------------------------------------------------
def _seed_assets(state, lord_id, **assets):
    for k, v in assets.items():
        state.lords[lord_id].assets[k] = v


def test_spoils_all_except_ships_transfers_everything_but_ships():
    """4.4.5: removed/retreated-without-conceding -> all Coin/Prov/Loot
    /Boat/Cart/Sled to winner; Ships stay with the loser."""
    s = load_scenario("watland", seed=1)
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    rus = next(lid for lid, l in s.lords.items() if l.side == "russian" and l.state == "mustered")
    _seed_assets(s, rus, coin=2, provender=3, loot=2, boat=1, cart=2, sled=1, ship=2)
    teu_ship_pre = int(s.lords[teu].assets.get("ship", 0))
    res = transfer_spoils(s, from_lord=rus, to_lords=[teu], mode="all_except_ships")
    # Ships stay
    assert s.lords[rus].assets.get("ship", 0) == 2
    # Everything else goes
    for k in ("coin", "provender", "loot", "boat", "cart", "sled"):
        assert s.lords[rus].assets.get(k, 0) == 0, f"loser kept {k}"
    # Winner gains all but ships
    assert s.lords[teu].assets.get("coin", 0) == 2
    assert s.lords[teu].assets.get("provender", 0) >= 3
    assert s.lords[teu].assets.get("loot", 0) == 2
    assert s.lords[teu].assets.get("ship", 0) == teu_ship_pre  # unchanged


def test_spoils_loot_and_excess_keeps_ok_provender_and_coin():
    """4.4.5: conceded+retreated -> loot + excess_provender only.
    Coin and other Transport stay with the loser. Provender within
    Retreat-Way Transport stays."""
    s = load_scenario("watland", seed=1)
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    rus = next(lid for lid, l in s.lords.items() if l.side == "russian" and l.state == "mustered")
    s.meta.box = 1  # Summer
    _seed_assets(s, rus, coin=2, provender=4, loot=3, cart=2, ship=1)
    res = transfer_spoils(s, from_lord=rus, to_lords=[teu], mode="loot_and_excess",
                          retreat_way_type="trackway")
    # All Loot transferred
    assert s.lords[rus].assets.get("loot", 0) == 0
    assert s.lords[teu].assets.get("loot", 0) >= 3
    # Coin stays
    assert s.lords[rus].assets.get("coin", 0) == 2
    # Cart stays
    assert s.lords[rus].assets.get("cart", 0) == 2
    # Ship stays
    assert s.lords[rus].assets.get("ship", 0) == 1
    # Provender: cart=2 usable on trackway in Summer; excess = 4-2 = 2.
    assert s.lords[rus].assets.get("provender", 0) == 2


def test_spoils_none_is_no_op_for_withdraw():
    """4.4.5: Withdrawal yields no Spoils."""
    s = load_scenario("watland", seed=1)
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    rus = next(lid for lid, l in s.lords.items() if l.side == "russian" and l.state == "mustered")
    _seed_assets(s, rus, coin=2, provender=3, loot=1)
    teu_assets_pre = dict(s.lords[teu].assets)
    transfer_spoils(s, from_lord=rus, to_lords=[teu], mode="none")
    # Loser unchanged
    assert s.lords[rus].assets.get("coin", 0) == 2
    assert s.lords[rus].assets.get("provender", 0) == 3
    assert s.lords[rus].assets.get("loot", 0) == 1
    # Winner unchanged
    assert dict(s.lords[teu].assets) == teu_assets_pre


def test_spoils_loot_and_excess_keeps_loot_when_retreat_way_unspecified():
    """Documented fallback: when retreat_way_type is None, only Loot
    transfers (provender excess can't be computed). This is for legacy
    callers; the prod path passes retreat_way_type."""
    s = load_scenario("watland", seed=1)
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    rus = next(lid for lid, l in s.lords.items() if l.side == "russian" and l.state == "mustered")
    _seed_assets(s, rus, loot=2, provender=5, cart=1)
    transfer_spoils(s, from_lord=rus, to_lords=[teu], mode="loot_and_excess",
                    retreat_way_type=None)
    assert s.lords[rus].assets.get("loot", 0) == 0
    # Provender unchanged in fallback path
    assert s.lords[rus].assets.get("provender", 0) == 5


# ---------------------------------------------------------------------------
# 3.5.2 Sea Trade Coin gates
# ---------------------------------------------------------------------------
def _setup_call_to_arms_with_capability(scenario: str, capability: str):
    s = load_scenario(scenario, seed=1)
    s.meta.phase = "levy"
    s.meta.levy_step = "call_to_arms"
    s.meta.active_player = "russian"
    s.decks.russian.capabilities_in_play.append(capability)
    return s


def test_r8_black_sea_trade_adds_one_coin():
    s = _setup_call_to_arms_with_capability("crusade_on_novgorod", "R8")
    pre = s.veche.coin
    res = apply_action(s, {"type": "veche_action", "side": "russian", "args": {"option": "sea_trade", "card_id": "R8"}})
    assert s.veche.coin == min(pre + 1, 8)
    assert res["card"] == "R8"
    assert res["added"] == min(1, 8 - pre)


def test_r8_blocked_when_novgorod_conquered():
    s = _setup_call_to_arms_with_capability("crusade_on_novgorod", "R8")
    s.locales["novgorod"].teutonic_conquered = 1
    with pytest.raises(IllegalAction) as exc:
        apply_action(s, {"type": "veche_action", "side": "russian", "args": {"option": "sea_trade", "card_id": "R8"}})
    assert "blocked" in str(exc.value).lower()
    assert s.veche.coin == 0  # no coin added on rejection


def test_r8_blocked_when_lovat_conquered():
    s = _setup_call_to_arms_with_capability("crusade_on_novgorod", "R8")
    s.locales["lovat"].teutonic_conquered = 1
    with pytest.raises(IllegalAction):
        apply_action(s, {"type": "veche_action", "side": "russian", "args": {"option": "sea_trade", "card_id": "R8"}})


def test_r9_baltic_sea_trade_adds_two_coin_in_summer():
    s = _setup_call_to_arms_with_capability("crusade_on_novgorod", "R9")
    s.meta.box = 1  # Summer
    # Ensure Russians don't have fewer ships than Teutons (R9 gate).
    # Easy approach: zero out Teuton ships entirely, then ensure at
    # least one Russian Lord has Boats so the comparison is non-strict.
    for lid, l in s.lords.items():
        if l.side == "teutonic":
            l.assets.pop("ship", None)
    rus = next(lid for lid, l in s.lords.items() if l.side == "russian" and l.state == "mustered")
    s.lords[rus].assets["boat"] = max(1, s.lords[rus].assets.get("boat", 0))
    pre = s.veche.coin
    res = apply_action(s, {"type": "veche_action", "side": "russian", "args": {"option": "sea_trade", "card_id": "R9"}})
    assert s.veche.coin == min(pre + 2, 8)
    assert res["card"] == "R9"


def test_r9_blocked_in_winter():
    s = _setup_call_to_arms_with_capability("crusade_on_novgorod", "R9")
    s.meta.box = 3  # Early Winter
    with pytest.raises(IllegalAction) as exc:
        apply_action(s, {"type": "veche_action", "side": "russian", "args": {"option": "sea_trade", "card_id": "R9"}})
    assert "winter" in str(exc.value).lower()


def test_r9_blocked_when_novgorod_or_neva_conquered():
    s1 = _setup_call_to_arms_with_capability("crusade_on_novgorod", "R9")
    s1.meta.box = 1
    s1.locales["novgorod"].teutonic_conquered = 1
    with pytest.raises(IllegalAction):
        apply_action(s1, {"type": "veche_action", "side": "russian", "args": {"option": "sea_trade", "card_id": "R9"}})

    s2 = _setup_call_to_arms_with_capability("crusade_on_novgorod", "R9")
    s2.meta.box = 1
    s2.locales["neva"].teutonic_conquered = 1
    with pytest.raises(IllegalAction):
        apply_action(s2, {"type": "veche_action", "side": "russian", "args": {"option": "sea_trade", "card_id": "R9"}})


def test_sea_trade_rejected_when_capability_not_in_play():
    s = load_scenario("crusade_on_novgorod", seed=1)
    s.meta.phase = "levy"
    s.meta.levy_step = "call_to_arms"
    s.meta.active_player = "russian"
    # Note: not adding R8 to capabilities_in_play
    with pytest.raises(IllegalAction) as exc:
        apply_action(s, {"type": "veche_action", "side": "russian", "args": {"option": "sea_trade", "card_id": "R8"}})
    assert "not_in_play" in str(exc.value).lower() or "not in play" in str(exc.value).lower()


def test_veche_coin_caps_at_eight():
    s = _setup_call_to_arms_with_capability("crusade_on_novgorod", "R8")
    s.veche.coin = 8
    res = apply_action(s, {"type": "veche_action", "side": "russian", "args": {"option": "sea_trade", "card_id": "R8"}})
    # The handler should report 0 added (cap) but not error.
    assert res["added"] == 0
    assert res["lost_to_cap"] == 1
    assert s.veche.coin == 8
