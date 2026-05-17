"""SMOKE-081 (Round 85): T10 Field Organ target validation + API
inconsistency between _consume_battle_holds and resolve_battle.

Issue 1 — API inconsistency: `_consume_battle_holds` expects
`holds["field_organ"] = "T10"` (card_id), while resolve_battle reads
`H.get("field_organ")` as a lord_id. The same holds_arg dict is
passed to both via stand_battle, making it impossible to both
consume the card AND apply the effect with a single call. Fix:
resolve_battle now reads `field_organ_lord = H.get("field_organ_lord")`
with a legacy fallback to `H.get("field_organ")` when it's a valid
lord_id. Bridge has the analogous fix (`bridge_target_lord` key).

Issue 2 — Missing target validation: T10's event_eligibility is
"any Teuton" — target must be a Teutonic Lord in the current
combat. Previously the consumption succeeded with any string value
(Russian Lord, invalid id, etc.). Fix raises bad_target when target
isn't a Teutonic Lord in cp.attacker_group | cp.defender_lords.
"""
from __future__ import annotations

import pytest

import nevsky.actions  # noqa: F401 — register handlers
from nevsky.actions import IllegalAction
from nevsky.events import _consume_battle_holds
from nevsky.scenarios import load_scenario
from nevsky.state import CombatPending


def _mk_cp(attacker_group=None, defender_lords=None):
    return CombatPending(
        attacker_side="teutonic",
        attacker_group=attacker_group or ["hermann"],
        defender_lords=defender_lords or ["aleksandr"],
        from_locale="dorpat", to_locale="ostrov", way_type="trackway",
        defender_side="russian", pending_response_by="russian", laden=False,
    )


def test_field_organ_rejects_missing_target():
    s = load_scenario("crusade_on_novgorod", seed=1)
    s.meta.box = 1
    s.decks.teutonic.holds.append("T10")
    with pytest.raises(IllegalAction) as e:
        _consume_battle_holds(s, _mk_cp(), {"field_organ": "T10"})
    assert e.value.code == "missing_target"


def test_field_organ_rejects_russian_target():
    s = load_scenario("crusade_on_novgorod", seed=1)
    s.meta.box = 1
    s.decks.teutonic.holds.append("T10")
    with pytest.raises(IllegalAction) as e:
        _consume_battle_holds(
            s, _mk_cp(),
            {"field_organ": "T10", "field_organ_lord": "aleksandr"},
        )
    assert e.value.code == "bad_target"


def test_field_organ_rejects_unknown_lord():
    s = load_scenario("crusade_on_novgorod", seed=1)
    s.meta.box = 1
    s.decks.teutonic.holds.append("T10")
    with pytest.raises(IllegalAction) as e:
        _consume_battle_holds(
            s, _mk_cp(),
            {"field_organ": "T10", "field_organ_lord": "not_a_lord"},
        )
    assert e.value.code == "bad_target"


def test_field_organ_rejects_lord_not_in_combat():
    s = load_scenario("crusade_on_novgorod", seed=1)
    s.meta.box = 1
    s.decks.teutonic.holds.append("T10")
    # Teu Lord 'rudolf' is not in cp.attacker_group ["hermann"].
    with pytest.raises(IllegalAction) as e:
        _consume_battle_holds(
            s, _mk_cp(),
            {"field_organ": "T10", "field_organ_lord": "rudolf"},
        )
    assert e.value.code == "bad_target"


def test_field_organ_accepts_attacker_teu_lord():
    s = load_scenario("crusade_on_novgorod", seed=1)
    s.meta.box = 1
    s.decks.teutonic.holds.append("T10")
    consumed = _consume_battle_holds(
        s, _mk_cp(),
        {"field_organ": "T10", "field_organ_lord": "hermann"},
    )
    assert consumed == [{"card": "T10", "key": "field_organ"}]


def test_field_organ_accepts_defender_teu_lord():
    """Teutonic defender variant: rus attacker, teu defender; T10
    targets the Teutonic defender Lord."""
    s = load_scenario("crusade_on_novgorod", seed=1)
    s.meta.box = 1
    s.decks.teutonic.holds.append("T10")
    cp = CombatPending(
        attacker_side="russian", attacker_group=["aleksandr"],
        defender_lords=["hermann"],
        from_locale="ostrov", to_locale="dorpat", way_type="trackway",
        defender_side="teutonic", pending_response_by="teutonic", laden=False,
    )
    consumed = _consume_battle_holds(
        s, cp,
        {"field_organ": "T10", "field_organ_lord": "hermann"},
    )
    assert consumed == [{"card": "T10", "key": "field_organ"}]


def test_resolve_battle_reads_field_organ_lord_key():
    """Regression: resolve_battle should honor the new `field_organ_lord`
    key. The legacy `field_organ` key holding a lord_id is also
    accepted (test_round_18 path uses lord_id in field_organ key)."""
    import inspect
    from nevsky import battle
    src = inspect.getsource(battle)
    # New key accepted.
    assert 'H.get("field_organ_lord")' in src
    # Legacy fallback present.
    assert 'H.get("field_organ")' in src


def test_resolve_battle_reads_bridge_target_lord_key():
    import inspect
    from nevsky import battle
    src = inspect.getsource(battle)
    assert 'H.get("bridge_target_lord")' in src
    assert 'H.get("bridge")' in src
