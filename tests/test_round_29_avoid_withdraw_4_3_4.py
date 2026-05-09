"""Round 29: 4.3.4 / 1.4.1 correctness tests for Avoid Battle + Withdraw.

Bugs surfaced by the Round 29 rule-correctness audit:

(1) legal_moves Avoid Battle note wrongly claimed Service shift; rule
    4.3.4 has none. (Service shifts only on Retreat per 4.4.3.)
(2) Avoid Battle handler hard-rejected Laden Lords. Rule 4.3.4: "Lords
    may discard their Loot and any Provender as needed to become
    Unladen and thereby Avoid Battle". Discarded items go to
    Approaching attackers as Spoils (4.4.3 'as if Spoils').
(3) Avoid Battle accepted dest == cp.from_locale. Rule 4.3.4: "Lords
    may not Avoid Battle across any part of the Way that the enemy
    used to Approach the Locale" — reusing the (from_locale + way_type)
    convention already used for Retreat.
(4) Withdraw handler set moved_fought = True. Rule 4.3.4: "Withdrawal
    alone does not mark Lords as Moved/Fought."
(5) Legate-removal trigger (1.4.1, 4.3.4) was not implemented for
    Teutonic Lords Avoiding Battle or Withdrawing.

Plus regression coverage for behavior already correct:
- Handler does NOT shift Service on Avoid (4.3.4 has no shift).
- Withdraw capacity check rejects over-cap.
"""
from __future__ import annotations

import pytest

from nevsky.actions import IllegalAction, apply_action
from nevsky.legal_moves import legal_moves
from nevsky.scenarios import load_scenario
from nevsky.state import CombatPending


def _place_svc(state, lord_id: str, box: int):
    for cb in state.calendar.boxes:
        if lord_id in cb.service_markers:
            cb.service_markers.remove(lord_id)
    state.calendar.boxes[box - 1].service_markers.append(lord_id)


def _svc_box(state, lord_id: str):
    for cb in state.calendar.boxes:
        if lord_id in cb.service_markers:
            return cb.box
    return None


def _make_combat(side_attacker="teutonic", scenario="pleskau",
                 attacker="hermann", defender="domash",
                 from_loc="izborsk", to_loc="pskov",
                 way_type="trackway"):
    state = load_scenario(scenario, seed=1)
    state.meta.phase = "campaign"
    state.meta.active_player = "russian" if side_attacker == "teutonic" else "teutonic"
    if attacker in state.lords:
        state.lords[attacker].state = "mustered"
        # After Approach, attackers are at to_loc (they just Marched in).
        state.lords[attacker].location = to_loc
    if defender in state.lords:
        state.lords[defender].state = "mustered"
        state.lords[defender].location = to_loc
    _place_svc(state, defender, 7)
    state.combat_pending = CombatPending(
        attacker_side=side_attacker,
        attacker_group=[attacker],
        from_locale=from_loc, to_locale=to_loc,
        way_type=way_type,
        defender_side="russian" if side_attacker == "teutonic" else "teutonic",
        defender_lords=[defender],
        pending_response_by="russian" if side_attacker == "teutonic" else "teutonic",
        laden=False,
    )
    return state


# ---------------------------------------------------------------------------
# (1) legal_moves note text
# ---------------------------------------------------------------------------
def test_legal_moves_avoid_battle_note_does_not_claim_service_shift():
    """4.3.4 has no Service shift. The legal_moves preview note must not
    claim one."""
    state = _make_combat()
    moves = legal_moves(state)
    avoids = [m for m in moves if m.get("type") == "avoid_battle"]
    assert avoids, "expected at least one avoid_battle option from pskov"
    for m in avoids:
        note = m.get("note", "").lower()
        # The note must not claim that the Avoiding Lord's Service marker
        # shifts (which would be the bug). It MAY mention "no Service
        # shift" — that's the correct disclaimer.
        assert "marker shifts" not in note, (
            f"avoid_battle note wrongly claims Service marker shift: {m['note']!r}"
        )
        assert "shifts 1 box right" not in note, (
            f"avoid_battle note wrongly claims +1 box right shift: {m['note']!r}"
        )


# ---------------------------------------------------------------------------
# (2) Handler does NOT shift Service (regression)
# ---------------------------------------------------------------------------
def test_avoid_battle_handler_does_not_shift_service():
    state = _make_combat()
    pre = _svc_box(state, "domash")
    apply_action(state, {"type": "avoid_battle", "side": "russian", "args": {"to": "ostrov"}})
    post = _svc_box(state, "domash")
    assert pre == post, f"Service should not shift on Avoid (4.3.4); was {pre}->{post}"


# ---------------------------------------------------------------------------
# (3) Approach-Way restriction
# ---------------------------------------------------------------------------
def test_avoid_battle_dest_cannot_be_approach_locale():
    """4.3.4: 'may not Avoid Battle across any part of the Way that the
    enemy used to Approach the Locale.' Using the same
    (from_locale, way_type) convention used elsewhere for Retreat."""
    state = _make_combat(from_loc="izborsk", to_loc="pskov", way_type="trackway")
    with pytest.raises(IllegalAction) as exc:
        apply_action(state, {"type": "avoid_battle", "side": "russian",
                             "args": {"to": "izborsk"}})
    assert "approach" in str(exc.value).lower() or "way" in str(exc.value).lower()


# ---------------------------------------------------------------------------
# (4) Loot/Provender discard + Spoils transfer
# ---------------------------------------------------------------------------
def test_avoid_battle_with_loot_discards_loot_and_transfers_to_attacker():
    """4.3.4: 'They may take no Loot' + 'Lords may discard their Loot and
    any Provender as needed to become Unladen and thereby Avoid Battle.'
    Discarded items go to Approaching enemy as Spoils."""
    state = _make_combat()
    # Defender carries Loot — currently makes him Laden. Rule says
    # discard-then-Avoid is permitted.
    state.lords["domash"].assets["loot"] = 2
    state.lords["domash"].assets["provender"] = 1
    state.lords["domash"].assets["cart"] = 5  # provender <= transport
    atk_loot_pre = state.lords["hermann"].assets.get("loot", 0)
    res = apply_action(state, {"type": "avoid_battle", "side": "russian",
                               "args": {"to": "ostrov"}})
    # Defender keeps no Loot.
    assert state.lords["domash"].assets.get("loot", 0) == 0, (
        "Avoid Battle: defender 'may take no Loot' (4.3.4)"
    )
    # Attacker gains the Loot as Spoils.
    atk_loot_post = state.lords["hermann"].assets.get("loot", 0)
    assert atk_loot_post == atk_loot_pre + 2, (
        f"attacker should gain 2 Loot as Spoils; was {atk_loot_pre}->{atk_loot_post}"
    )


def test_avoid_battle_excess_provender_transferred_as_spoils():
    """4.3.4: 'take only Provender equal to ... Transport that is usable
    on the Way across which they are moving'. Excess goes to attacker as
    Spoils."""
    state = _make_combat()
    state.lords["domash"].assets["provender"] = 5
    state.lords["domash"].assets["cart"] = 2  # Way is trackway → carts in Summer
    atk_prov_pre = state.lords["hermann"].assets.get("provender", 0)
    apply_action(state, {"type": "avoid_battle", "side": "russian",
                         "args": {"to": "ostrov"}})
    # Defender keeps at most cart count of Provender (maps to usable
    # transport on the destination Way). Pleskau scenario starts in
    # Summer, so all 2 carts are usable on a trackway.
    assert state.lords["domash"].assets.get("provender", 0) <= 2, (
        "defender should keep no more Provender than usable Transport on the Avoid Way"
    )
    atk_prov_post = state.lords["hermann"].assets.get("provender", 0)
    assert atk_prov_post >= atk_prov_pre + 3, (
        f"attacker should gain at least 3 excess Provender as Spoils; "
        f"was {atk_prov_pre}->{atk_prov_post}"
    )


# ---------------------------------------------------------------------------
# (5) Withdraw moved_fought
# ---------------------------------------------------------------------------
def test_withdraw_does_not_mark_moved_fought():
    """Rule 4.3.4: 'Withdrawal alone does not mark Lords as Moved/Fought.'"""
    state = _make_combat()
    apply_action(state, {"type": "withdraw", "side": "russian", "args": {}})
    assert state.lords["domash"].moved_fought is False, (
        "Withdraw alone must not set moved_fought (4.3.4)"
    )


# ---------------------------------------------------------------------------
# Withdraw capacity (regression)
# ---------------------------------------------------------------------------
def test_withdraw_rejects_over_capacity():
    state = _make_combat()
    extras = []
    for cand in ("gavrilo", "aleksandr", "andrey", "vladislav"):
        if cand in state.lords:
            state.lords[cand].state = "mustered"
            state.lords[cand].location = "pskov"
            extras.append(cand)
    state.combat_pending.defender_lords = ["domash"] + extras  # 5 defenders
    with pytest.raises(IllegalAction) as exc:
        apply_action(state, {"type": "withdraw", "side": "russian", "args": {}})
    assert "capacity" in str(exc.value).lower()


# ---------------------------------------------------------------------------
# (6) Legate removal on Teutonic Avoid / Withdraw
# ---------------------------------------------------------------------------
def test_legate_removed_on_teutonic_avoid_battle():
    """1.4.1 + 4.3.4: 'is with a Teutonic Lord who Avoids Battle or
    Withdraws, remove the pawn and discard William of Modena.'"""
    state = _make_combat(side_attacker="russian",
                         attacker="domash", defender="hermann",
                         from_loc="ugaunia", to_loc="dorpat")
    state.legate.william_of_modena_in_play = True
    state.legate.location = "locale"
    state.legate.locale_id = "dorpat"
    apply_action(state, {"type": "avoid_battle", "side": "teutonic",
                         "args": {"to": "uzmen"}})
    assert state.legate.william_of_modena_in_play is False, (
        "Legate should be removed when Teutonic Lord Avoids Battle (1.4.1, 4.3.4)"
    )
    assert state.legate.location == "card"
    assert state.legate.locale_id is None


def test_legate_removed_on_teutonic_withdraw():
    """1.4.1 + 4.3.4: same trigger for Withdraw."""
    state = _make_combat(side_attacker="russian",
                         attacker="domash", defender="hermann",
                         from_loc="ugaunia", to_loc="dorpat")
    state.legate.william_of_modena_in_play = True
    state.legate.location = "locale"
    state.legate.locale_id = "dorpat"
    apply_action(state, {"type": "withdraw", "side": "teutonic", "args": {}})
    assert state.legate.william_of_modena_in_play is False
    assert state.legate.location == "card"
    assert state.legate.locale_id is None


def test_legate_not_removed_on_russian_avoid():
    """The 1.4.1 trigger is Teutonic Lord Avoids/Withdraws (or alone
    with Russian). A Russian Lord Avoiding doesn't itself remove the
    Legate."""
    state = _make_combat()  # Russian defender Avoids
    state.legate.william_of_modena_in_play = True
    state.legate.location = "locale"
    # Place Legate at attacker locale (a Teutonic Lord is there) — far
    # from the Russian's path, no trigger.
    state.legate.locale_id = "izborsk"
    apply_action(state, {"type": "avoid_battle", "side": "russian",
                         "args": {"to": "ostrov"}})
    assert state.legate.william_of_modena_in_play is True
