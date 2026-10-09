"""4.4.2: after Relief-Sally rows turn, Reserve Lords advance normally.

The former SMOKE-014 freeze hid missing row normalization and could strand
both surviving armies. Adjust Rows now establishes opposed Front rows first.
"""

from __future__ import annotations

from nevsky.battle import _adjust_rows_for_relief_sally, _reposition
from nevsky.scenarios import load_scenario


def _mk_decision_ctx() -> object:
    """Minimal fake decision_ctx. The suppressed branch returns early and
    the non-suppressed tests have unique candidates, so no which-Lord
    decision is ever asked. PLAY-33: a lone Reserve advancing while open
    slots outnumber Reserves now legitimately asks a `reserve_advance_slot`
    decision -- answer leftmost (the pre-PLAY-33 deterministic slot);
    any other decision type is still an error."""
    class _Ctx:
        def decide(self, decision_type, side, options, info=None):  # noqa: ANN001
            if decision_type == "reserve_advance_slot":
                return options[0]
            raise AssertionError(
                f"decide should not be called (got {decision_type!r})")
    return _Ctx()


def test_reposition_advances_old_front_defender_against_remaining_sally() -> None:
    """4.4.2: old Front Defenders become Reserve, then face the Sally.

    No Rearguard remains, so normal Advance Lords must fill the new Front.
    """
    s = load_scenario("watland", seed=1)
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic")
    rus = next(lid for lid, l in s.lords.items() if l.side == "russian")
    s.lords[teu].state = "mustered"
    s.lords[teu].forces = {"sergeants": 1}
    s.lords[rus].state = "mustered"
    s.lords[rus].forces = {"militia": 1}

    def_pos = {teu: "center"}
    atk_pos = {rus: "sally_center"}
    _adjust_rows_for_relief_sally(s, atk_pos, def_pos)
    assert def_pos[teu] == "reserve"
    assert atk_pos[rus] == "center"
    log = _reposition(s, def_pos, "defender", _mk_decision_ctx(),
                      opposing_positions=atk_pos)
    assert "suppressed" not in log
    assert def_pos[teu] == "center"
    assert any(move["step"] == "advance" for move in log["moves"])


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
