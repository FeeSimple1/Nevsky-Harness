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
from nevsky import battle
from tests.test_cross_game_relief_retreat import place
from tests.test_sally_hit_groups import _capability, _position


def test_simple_sally_passes_siegeworks_and_flag():
    """Source-inspection regression: _h_cmd_sally now passes
    siegeworks_for_sally and simple_sally=True to resolve_battle."""
    import inspect
    from nevsky import campaign
    src = inspect.getsource(campaign._h_cmd_sally)
    assert "siegeworks_for_sally=siege_markers" in src
    assert "simple_sally=True" in src


def test_simple_sally_flag_applies_siegeworks_to_the_front_center_striker():
    state = _position(2, "gavrilo")
    place(state, "gavrilo", {"militia": 1})
    place(state, "hermann", {"knights": 1})
    _capability(state, "gavrilo", "R1")

    def archery_distribution(simple_sally):
        result = battle.resolve_battle(
            state.model_copy(deep=True), "russian", ["gavrilo"], ["hermann"],
            concede="defender", siegeworks_for_sally=1, simple_sally=simple_sally)
        return next(step["distribution"] for step in result["log"][0]["steps"]
                    if step["step"] == "archery_attacker")

    assert archery_distribution(True) == [
        {"lord": "hermann", "target": "siegeworks_vs_sally", "absorbed": 1}]
    ordinary, = archery_distribution(False)
    assert ordinary["routed"] == [{"unit": "knights", "absorbed": True}]


def test_sally_aftermath_reports_siegeworks_walls():
    """Sanity: simple Sally aftermath dict includes siegeworks_walls key."""
    import inspect
    from nevsky import campaign
    src = inspect.getsource(campaign._h_cmd_sally)
    assert '"siegeworks_walls"' in src
