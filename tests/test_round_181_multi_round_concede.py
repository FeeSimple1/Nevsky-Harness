"""SMOKE-116 (Round 181): Concede was only honored at Round 1; per
rule 4.4.2 concede may be declared at the start of ANY Round.

Previously documented as a feature gap (R162). Implementation adds
`concede_decisions: dict[int, str] | None` arg to resolve_battle
mapping round_number → side that concedes at start of that round.

The legacy `concede` arg still drives Round 1 behavior; new
`concede_decisions` drives Round 2+. Both the Pursuit halving and
the outcome resolution use the per-round value.
"""
from __future__ import annotations

import inspect

import nevsky.battle as battle


def test_smoke_116_marker_present():
    src = inspect.getsource(battle.resolve_battle)
    assert "SMOKE-116" in src
    assert "concede_decisions" in src
    assert "round_concede" in src


def test_smoke_116_concede_decisions_arg_accepted():
    """resolve_battle accepts concede_decisions arg without error."""
    from nevsky.scenarios import load_scenario
    s = load_scenario("watland", seed=1)
    teu = next(lid for lid, l in s.lords.items()
               if l.side == "teutonic" and l.state == "mustered")
    rus = next(lid for lid, l in s.lords.items()
               if l.side == "russian" and l.state == "mustered")
    # Teutonic attacker concedes at Round 2
    res = battle.resolve_battle(
        s, attacker_side="teutonic",
        attacker_lords=[teu], defender_lords=[rus],
        concede_decisions={2: "attacker"},
    )
    # Should still resolve to a winner/loser
    assert res["winner"] in ("teutonic", "russian")


def test_smoke_116_round_2_concede_resolves_immediately():
    """Concede at Round 2 ends Battle at Round 2 — conceder loses."""
    from nevsky.scenarios import load_scenario
    s = load_scenario("watland", seed=1)
    teu = next(lid for lid, l in s.lords.items()
               if l.side == "teutonic" and l.state == "mustered")
    rus = next(lid for lid, l in s.lords.items()
               if l.side == "russian" and l.state == "mustered")
    # Concede at Round 2; teutonic attacker concedes
    res = battle.resolve_battle(
        s, attacker_side="teutonic",
        attacker_lords=[teu], defender_lords=[rus],
        concede_decisions={2: "attacker"},
    )
    assert res["winner"] == "russian"
    assert res["loser"] == "teutonic"
    assert res.get("conceded") == "attacker"
    # Should have run at most 2 Rounds
    assert res["rounds"] <= 2


def test_smoke_116_round_1_concede_still_works_legacy_arg():
    """Legacy `concede` arg drives Round 1 concede (no regression)."""
    from nevsky.scenarios import load_scenario
    s = load_scenario("watland", seed=1)
    teu = next(lid for lid, l in s.lords.items()
               if l.side == "teutonic" and l.state == "mustered")
    rus = next(lid for lid, l in s.lords.items()
               if l.side == "russian" and l.state == "mustered")
    res = battle.resolve_battle(
        s, attacker_side="teutonic",
        attacker_lords=[teu], defender_lords=[rus],
        concede="attacker",
    )
    assert res["winner"] == "russian"
    assert res.get("conceded") == "attacker"
    assert res["rounds"] == 1


def test_smoke_116_pursuit_halves_conceder_round_n():
    """When defender concedes at Round 2, defender's Round 2 Strikes
    have Pursuit halving applied (round_concede consulted in the
    Pursuit block)."""
    src = inspect.getsource(battle.resolve_battle)
    # Verify the Pursuit halving uses round_concede, not the static concede
    idx = src.find("Pursuit: halve conceder Hits")
    assert idx > 0
    block = src[idx:idx + 800]
    assert "round_concede" in block
    # Old check used `concede is not None and rounds == 1`; new uses round_concede
    assert "round_concede is not None and striker_role == round_concede" in block


def test_smoke_116_round_log_includes_concede():
    """The per-Round log now records concede=<side> when that Round
    had a concede declaration."""
    from nevsky.scenarios import load_scenario
    s = load_scenario("watland", seed=1)
    teu = next(lid for lid, l in s.lords.items()
               if l.side == "teutonic" and l.state == "mustered")
    rus = next(lid for lid, l in s.lords.items()
               if l.side == "russian" and l.state == "mustered")
    res = battle.resolve_battle(
        s, attacker_side="teutonic",
        attacker_lords=[teu], defender_lords=[rus],
        concede_decisions={2: "defender"},
    )
    # Find the Round 2 log entry; concede field should be "defender"
    for r in res.get("log", []):
        if r.get("round") == 2:
            assert r.get("concede") == "defender"


def test_smoke_116_no_concede_passes_through_normally():
    """If neither concede arg nor concede_decisions is set, Battle
    resolves through normal rounds with concede=None throughout."""
    from nevsky.scenarios import load_scenario
    s = load_scenario("watland", seed=1)
    teu = next(lid for lid, l in s.lords.items()
               if l.side == "teutonic" and l.state == "mustered")
    rus = next(lid for lid, l in s.lords.items()
               if l.side == "russian" and l.state == "mustered")
    res = battle.resolve_battle(
        s, attacker_side="teutonic",
        attacker_lords=[teu], defender_lords=[rus],
    )
    assert res["winner"] in ("teutonic", "russian")
    assert res.get("conceded") is None or res.get("conceded") in (None,)
