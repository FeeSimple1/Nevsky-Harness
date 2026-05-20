"""SMOKE-130 (R197): Withdraw into an own-Conquered Stronghold.

Per 1.3.1 (Miscellaneous Rules Reference: "A Lord at a Stronghold
Conquered FROM the enemy ... is Friendly to this side"), a defender
holding a Stronghold he conquered is Friendly there even when the
Stronghold sits in enemy territory. Withdraw (4.3.4) goes into a
Friendly Stronghold at the Battle Locale, so such a defender may
Withdraw into his conquest.

Pre-fix, _h_withdraw's fallback accepted only own *territory* and
dropped the "own Conquered Stronghold" half (despite its own inline
comment). A Teuton defending Teuton-conquered Pskov in Peipus was
forced to Stand. legal_moves already offered withdraw, so this was
also an enumerator/handler asymmetry.

Surfaced in the Peipus LLM self-play (Hermann alone at conquered
Pskov, turn 194): the correct play was Withdraw-and-shelter, but
the bug forced a Stand that lost Hermann.
"""
from __future__ import annotations
import inspect

import nevsky.actions  # noqa: F401
from nevsky.actions import IllegalAction, apply_action
from nevsky.legal_moves import legal_moves
from nevsky.scenarios import load_scenario
from nevsky.state import CombatPending


def _approach(defender_side, to_loc):
    s = load_scenario("peipus", seed=1)
    s.meta.phase = "campaign"
    s.meta.campaign_step = "done"
    s.meta.active_player = defender_side
    deff = "hermann" if defender_side == "teutonic" else "domash"
    atk_side = "russian" if defender_side == "teutonic" else "teutonic"
    atk = "andrey" if atk_side == "russian" else "hermann"
    for lid in (deff, atk):
        s.lords[lid].state = "mustered"
        s.lords[lid].location = to_loc
        s.lords[lid].in_stronghold = False
    s.combat_pending = CombatPending(
        attacker_side=atk_side, attacker_group=[atk],
        from_locale="dubrovno", to_locale=to_loc, way_type="trackway",
        defender_side=defender_side, defender_lords=[deff],
        pending_response_by=defender_side, laden=False)
    return s, deff


def test_smoke_130_withdraw_into_own_conquered_stronghold():
    """Teuton defending Teuton-conquered Pskov (russian territory) may
    Withdraw into it."""
    s, deff = _approach("teutonic", "pskov")
    assert s.locales["pskov"].teutonic_conquered > 0
    assert s.locales["pskov"].russian_conquered == 0
    res = apply_action(s, {"type": "withdraw", "side": "teutonic", "args": {}})
    assert s.lords[deff].in_stronghold is True
    assert s.locales["pskov"].siege_markers == 1


def test_smoke_130_own_territory_withdraw_still_works():
    """Positive control: Russian defending an own-territory Stronghold
    (novgorod) still withdraws normally."""
    s, deff = _approach("russian", "novgorod")
    apply_action(s, {"type": "withdraw", "side": "russian", "args": {}})
    assert s.lords[deff].in_stronghold is True


def test_smoke_130_enemy_conquered_still_rejected():
    """Negative control: a side may NOT Withdraw into a Stronghold the
    ENEMY has conquered. Russian at Teuton-conquered Pskov is rejected."""
    s, deff = _approach("russian", "pskov")
    assert s.locales["pskov"].teutonic_conquered > 0
    with __import__("pytest").raises(IllegalAction) as exc:
        apply_action(s, {"type": "withdraw", "side": "russian", "args": {}})
    assert exc.value.code == "not_friendly"


def test_smoke_130_enumerator_handler_roundtrip_aligned():
    """The enumerator offers withdraw AND the handler accepts it for a
    conquered-Stronghold defender (closes the asymmetry)."""
    s, deff = _approach("teutonic", "pskov")
    offered = [m["type"] for m in legal_moves(s, with_previews=False)]
    assert "withdraw" in offered
    snap = s.model_copy(deep=True)
    # Must not raise.
    apply_action(snap, {"type": "withdraw", "side": "teutonic", "args": {}})


def test_smoke_130_marker_present_in_source():
    import nevsky.campaign as c
    assert "SMOKE-130" in inspect.getsource(c)
