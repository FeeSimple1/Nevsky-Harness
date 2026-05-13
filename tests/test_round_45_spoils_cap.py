"""Round 45 — SMOKE-032: Spoils transfers ignored the 8-asset cap.

Rule 1.7.3 (Wastage — Per Lord): "Each Lord's mat may hold AT MOST 8 of
each Asset type. Any excess gained beyond 8 is lost immediately."
``reference/Nevsky Miscellaneous Rules Reference.txt`` lines 50-54.

Three Spoils transfer paths bypassed the cap:

  1. ``_h_avoid_battle`` (4.3.4) — defender drops Loot + excess
     Provender to first attacker as Spoils. The transfer did
     ``wa["loot"] = wa.get("loot", 0) + spoils_loot`` with no cap.

  2. ``transfer_spoils`` (4.4.3 / 4.4.5) in battle.py — Battle
     aftermath transferred Loot / Provender / Coin / Transport from
     loser to winner. Same uncapped ``+=``.

  3. Storm Sack (4.5.2) in ``_h_cmd_storm`` — inter-Lord asset
     transfer from removed Besieged Lord to first attacker. Same
     uncapped pattern.

Fix: new helper ``battle._award_assets_capped(state, lord_id, assets)``
caps every asset type at 8, returns ``{added, lost_to_cap}``. All
three sites now route through it.

(Note: Stronghold spoils (loot/provender/coin = VP) at the same Storm
aftermath site already used ``min(8, ...)``, and Forage / Supply /
Tax / Raiders Ravage all pre-checked or pre-capped. Only the three
inter-Lord transfer paths above were uncapped.)
"""
from __future__ import annotations

import pytest
from nevsky.actions import apply_action
from nevsky.scenarios import load_scenario
from nevsky.battle import transfer_spoils, _award_assets_capped
from nevsky.state import CombatPending


# --- helper ---

def _award_assets_helper_caps_at_8():
    """The unified helper itself: each asset capped at 8 per call."""
    s = load_scenario("crusade_on_novgorod", seed=42)
    s.lords["heinrich"].state = "mustered"
    s.lords["heinrich"].location = "reval"
    s.lords["heinrich"].assets = {"loot": 6, "coin": 7, "provender": 4}
    r = _award_assets_capped(s, "heinrich", {"loot": 5, "coin": 3, "provender": 5})
    return s.lords["heinrich"].assets, r


def test_smoke_032_helper_caps_each_asset_independently():
    assets, r = _award_assets_helper_caps_at_8()
    assert assets["loot"] == 8       # 6 + 5, capped to 8 (lost 3)
    assert assets["coin"] == 8       # 7 + 3, capped to 8 (lost 2)
    assert assets["provender"] == 8  # 4 + 5, capped to 8 (lost 1)
    assert r["added"] == {"loot": 2, "coin": 1, "provender": 4}
    assert r["lost_to_cap"] == {"loot": 3, "coin": 2, "provender": 1}


def test_smoke_032_helper_no_excess_no_loss():
    """Adding less than the cap leaves capacity; no excess loss."""
    s = load_scenario("crusade_on_novgorod", seed=42)
    s.lords["heinrich"].state = "mustered"
    s.lords["heinrich"].location = "reval"
    s.lords["heinrich"].assets = {"loot": 2}
    r = _award_assets_capped(s, "heinrich", {"loot": 3})
    assert s.lords["heinrich"].assets["loot"] == 5
    assert r["added"] == {"loot": 3}
    assert r["lost_to_cap"] == {}


# --- Avoid Battle (path 1) ---

def test_smoke_032_avoid_battle_spoils_capped_at_8():
    """Defender drops 5 Loot to attacker who already has 7 -> attacker
    ends at 8 with 4 lost to cap."""
    s = load_scenario("crusade_on_novgorod", seed=42)
    heinrich = s.lords["heinrich"]
    heinrich.state = "mustered"
    heinrich.location = "pskov"
    heinrich.assets = {"loot": 7, "provender": 7}
    gavrilo = s.lords["gavrilo"]
    gavrilo.state = "mustered"
    gavrilo.location = "pskov"
    gavrilo.assets = {"loot": 5, "provender": 5, "cart": 2}
    s.combat_pending = CombatPending(
        attacker_side="teutonic", attacker_group=["heinrich"],
        from_locale="izborsk", to_locale="pskov", way_type="trackway",
        defender_side="russian", defender_lords=["gavrilo"],
        pending_response_by="russian", laden=False,
    )
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.campaign_turn.active_card = "heinrich"
    s.campaign_turn.active_lord = "heinrich"
    s.campaign_turn.actions_remaining = 2
    s.meta.active_player = "russian"
    r = apply_action(s, {"type": "avoid_battle", "side": "russian",
                          "args": {"to": "dubrovno"}})
    # Heinrich was at 7 loot; defender dropped 5; cap allowed 1 transfer.
    assert heinrich.assets["loot"] == 8
    # Heinrich was at 7 provender; defender dropped 3 excess provender
    # (5 carried, 2 carts → 2 usable on trackway → excess 3); cap
    # allowed 1 transfer.
    assert heinrich.assets["provender"] == 8
    # lost_to_cap surfaced in result
    lost = r["spoils_lost_to_cap"]
    assert lost.get("loot", 0) == 4    # 5 dropped, 1 accepted, 4 lost
    assert lost.get("provender", 0) == 2  # 3 dropped, 1 accepted, 2 lost


def test_smoke_032_avoid_battle_under_cap_no_loss():
    """Defender drops < capacity remaining → no loss."""
    s = load_scenario("crusade_on_novgorod", seed=42)
    heinrich = s.lords["heinrich"]
    heinrich.state = "mustered"; heinrich.location = "pskov"
    heinrich.assets = {"loot": 2, "provender": 2}
    gavrilo = s.lords["gavrilo"]
    gavrilo.state = "mustered"; gavrilo.location = "pskov"
    gavrilo.assets = {"loot": 3, "provender": 3, "cart": 1}
    s.combat_pending = CombatPending(
        attacker_side="teutonic", attacker_group=["heinrich"],
        from_locale="izborsk", to_locale="pskov", way_type="trackway",
        defender_side="russian", defender_lords=["gavrilo"],
        pending_response_by="russian", laden=False,
    )
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.campaign_turn.active_card = "heinrich"
    s.campaign_turn.active_lord = "heinrich"
    s.campaign_turn.actions_remaining = 2
    s.meta.active_player = "russian"
    r = apply_action(s, {"type": "avoid_battle", "side": "russian",
                          "args": {"to": "dubrovno"}})
    assert heinrich.assets.get("loot", 0) == 5
    assert r["spoils_lost_to_cap"] == {}


# --- transfer_spoils (path 2) ---

def test_smoke_032_transfer_spoils_all_except_ships_capped():
    """transfer_spoils all_except_ships: winner Loot/Provender/Coin
    each capped at 8."""
    s = load_scenario("crusade_on_novgorod", seed=42)
    h = s.lords["heinrich"]
    h.state = "mustered"; h.location = "reval"
    h.assets = {"loot": 7, "provender": 6, "coin": 5}
    loser = s.lords["domash"]
    loser.state = "mustered"; loser.location = "novgorod"
    loser.assets = {"loot": 4, "provender": 5, "coin": 6}
    r = transfer_spoils(s, "domash", ["heinrich"], "all_except_ships")
    # Heinrich loot: 7 + 4 = 11 → capped 8, lost 3
    assert h.assets["loot"] == 8
    # Heinrich prov: 6 + 5 = 11 → capped 8, lost 3
    assert h.assets["provender"] == 8
    # Heinrich coin: 5 + 6 = 11 → capped 8, lost 3
    assert h.assets["coin"] == 8
    # lost_to_cap surfaced
    assert r["lost_to_cap"]["loot"] == 3
    assert r["lost_to_cap"]["provender"] == 3
    assert r["lost_to_cap"]["coin"] == 3
    # Loser is cleared (those assets removed before transfer)
    assert loser.assets.get("loot", 0) == 0
    assert loser.assets.get("provender", 0) == 0
    assert loser.assets.get("coin", 0) == 0


def test_smoke_032_transfer_spoils_preserves_ships_on_loser():
    """all_except_ships keeps Ships on loser per name and existing
    behavior."""
    s = load_scenario("crusade_on_novgorod", seed=42)
    h = s.lords["heinrich"]
    h.state = "mustered"; h.location = "reval"; h.assets = {}
    loser = s.lords["domash"]
    loser.state = "mustered"; loser.location = "novgorod"
    loser.assets = {"ship": 3, "boat": 2}
    r = transfer_spoils(s, "domash", ["heinrich"], "all_except_ships")
    assert loser.assets.get("ship", 0) == 3
    assert h.assets.get("boat", 0) == 2
    assert "ship" not in r["transferred"]


def test_smoke_032_transfer_spoils_none_mode_unchanged():
    """mode='none' (Withdraw, 4.4.3) — no transfer, no cap interaction."""
    s = load_scenario("crusade_on_novgorod", seed=42)
    h = s.lords["heinrich"]
    h.state = "mustered"; h.location = "reval"
    h.assets = {"loot": 7}
    loser = s.lords["domash"]
    loser.state = "mustered"; loser.location = "novgorod"
    loser.assets = {"loot": 5}
    r = transfer_spoils(s, "domash", ["heinrich"], "none")
    assert h.assets["loot"] == 7
    assert loser.assets["loot"] == 5
    assert r["transferred"] == {}


# --- Storm Sack (path 3) ---

def test_smoke_032_storm_sack_uses_capped_helper():
    """Confirm the Storm Sack inter-Lord transfer routes through
    _award_assets_capped (regression on the previously uncapped block).
    Inspect the source to lock the pattern."""
    import nevsky.campaign as camp
    import inspect
    src = inspect.getsource(camp._h_cmd_storm)
    # The uncapped pattern is dead.
    assert "w.assets[k] = w.assets.get(k, 0) + v" not in src, (
        "Storm Sack still has uncapped += pattern"
    )
    # The helper-routed pattern is present.
    assert "_award_assets_capped" in src
