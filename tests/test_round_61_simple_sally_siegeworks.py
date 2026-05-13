"""Round 61 (continued) — SMOKE-050 regression tests.

Per 4.5.3 Sally: "Defenders (Besiegers) receive Siegeworks as Walls".
The harness's Siegeworks-as-Walls logic previously only fired for
Relief Sally (where Sallying Lords occupy sally_* slots). In a
simple Sally the sallying Lords ARE all the attackers, positioned
at regular Front slots, so the Walls protection didn't apply.

Fix: pass `simple_sally=True` to resolve_battle in _h_cmd_sally so
ALL attacker strikes count as Sally strikes for the Walls roll.
"""

import nevsky.actions  # noqa
from nevsky.scenarios import load_scenario


def test_simple_sally_passes_siegeworks_and_flag():
    """Source-inspection regression: _h_cmd_sally now passes
    siegeworks_for_sally and simple_sally=True to resolve_battle."""
    import inspect
    from nevsky import campaign
    src = inspect.getsource(campaign._h_cmd_sally)
    assert "siegeworks_for_sally=siege_markers" in src
    assert "simple_sally=True" in src


def test_resolve_battle_accepts_simple_sally_param():
    """Source-inspection regression: resolve_battle has the simple_sally
    parameter and its Walls-vs-Sally logic uses it."""
    import inspect
    from nevsky import battle
    sig = inspect.signature(battle.resolve_battle)
    assert "simple_sally" in sig.parameters
    src = inspect.getsource(battle.resolve_battle)
    assert "simple_sally" in src
    assert "is_sally_strike" in src


def test_sally_aftermath_reports_siegeworks_walls():
    """Sanity: simple Sally aftermath dict includes siegeworks_walls key."""
    import inspect
    from nevsky import campaign
    src = inspect.getsource(campaign._h_cmd_sally)
    assert '"siegeworks_walls"' in src
