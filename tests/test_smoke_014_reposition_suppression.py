"""SMOKE-014 regression: Reposition Advance must be suppressed on the
side whose Front is empty *by design* under Adjust Rows Rule 4
(opposing Front empty AND opposing Sally alive). Otherwise Rule 4 fires
every round in long-tail Sally-vs-Defender phases and pollutes the log.

Documented in SMOKE_TEST_FINDINGS.md Round 11. Fix landed in Round 12.
"""

from __future__ import annotations

from nevsky.battle import _reposition
from nevsky.scenarios import load_scenario


def _mk_decision_ctx() -> object:
    """Minimal fake decision_ctx: never consulted because the suppressed
    branch returns early. The non-suppressed tests have unique candidates
    so .decide is also never called."""
    class _Ctx:
        def decide(self, *args, **kwargs):  # noqa: ANN001, ANN003
            raise AssertionError("decide should not be called")
    return _Ctx()


def test_reposition_suppressed_when_opposing_front_empty_and_sally_alive() -> None:
    """Defender side has empty Front and Reserve Lord (just demoted by
    Rule 4); attacker has empty Front and an alive Sally row. The
    Defender's Reposition Advance MUST be suppressed; otherwise the
    Reserve Lord would re-Advance to Front and Rule 4 would re-fire
    next round forever."""
    s = load_scenario("watland", seed=1)
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic")
    rus = next(lid for lid, l in s.lords.items() if l.side == "russian")
    s.lords[teu].state = "mustered"
    s.lords[teu].forces = {"sergeants": 1}
    s.lords[rus].state = "mustered"
    s.lords[rus].forces = {"militia": 1}

    # Defender: Front empty, Reserve Lord alive (the just-demoted Front
    # Defender from Rule 4).
    def_pos = {teu: "reserve"}
    # Attacker: Front empty, Sally row alive.
    atk_pos = {rus: "sally_center"}

    log = _reposition(s, def_pos, "defender", _mk_decision_ctx(),
                      opposing_positions=atk_pos)
    assert log.get("suppressed") == "frozen_under_rule_4"
    assert log["moves"] == []
    # Critical: the demoted Lord stays at Reserve, not promoted back to Front.
    assert def_pos[teu] == "reserve"


def test_reposition_not_suppressed_when_opposing_front_alive() -> None:
    """When the opposing Front has any alive Lord, Rule 4 hasn't fired
    on this side, so normal Reposition Advance runs."""
    s = load_scenario("watland", seed=1)
    teus = [lid for lid, l in s.lords.items() if l.side == "teutonic"][:2]
    rus = next(lid for lid, l in s.lords.items() if l.side == "russian")
    for t in teus:
        s.lords[t].state = "mustered"
        s.lords[t].forces = {"sergeants": 1}
    s.lords[rus].state = "mustered"
    s.lords[rus].forces = {"militia": 1}

    # Attacker has alive Front Lord.
    atk_pos = {rus: "center"}
    # Defender: Front empty, one Reserve Lord. Should Advance normally.
    def_pos = {teus[0]: "reserve"}

    log = _reposition(s, def_pos, "defender", _mk_decision_ctx(),
                      opposing_positions=atk_pos)
    # No suppression key.
    assert "suppressed" not in log
    # Reserve Lord advanced to a Front slot.
    assert def_pos[teus[0]] in ("left", "center", "right")
    assert any(m["step"] == "advance" for m in log["moves"])


def test_reposition_not_suppressed_when_opposing_sally_dead() -> None:
    """Opposing Front is empty but opposing Sally row is also dead.
    This is not a Rule 4 freeze scenario -- it's just a normal Battle
    where everyone on one side is gone -- so Reposition should run
    normally (and the Battle ends-of-round check will end it)."""
    s = load_scenario("watland", seed=1)
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic")
    rus = next(lid for lid, l in s.lords.items() if l.side == "russian")
    s.lords[teu].state = "mustered"
    s.lords[teu].forces = {"sergeants": 1}
    s.lords[rus].state = "mustered"
    s.lords[rus].forces = {}  # Routed Sally.

    atk_pos = {rus: "sally_center"}  # Sally row, but Lord has no forces.
    def_pos = {teu: "reserve"}

    log = _reposition(s, def_pos, "defender", _mk_decision_ctx(),
                      opposing_positions=atk_pos)
    # Sally row exists positionally but Lord has 0 forces, so opp_sally_alive is False.
    assert "suppressed" not in log
    assert def_pos[teu] in ("left", "center", "right")


def test_reposition_no_opposing_positions_arg_runs_normally() -> None:
    """Backwards compatibility: callers that don't pass opposing_positions
    get the original Reposition behavior."""
    s = load_scenario("watland", seed=1)
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic")
    s.lords[teu].state = "mustered"
    s.lords[teu].forces = {"sergeants": 1}

    def_pos = {teu: "reserve"}
    log = _reposition(s, def_pos, "defender", _mk_decision_ctx())
    assert "suppressed" not in log
    assert def_pos[teu] in ("left", "center", "right")
