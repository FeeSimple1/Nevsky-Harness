"""One-shot follow-up to the checksum-pinned long-campaign patch."""
from pathlib import Path

path = Path('src/nevsky/actions.py')
source = path.read_text()
old = '''            state.meta.lordship_bonus = {}
            state.meta.special_rules.pop("block_william_of_modena_this_levy", None)
'''
new = '''            state.meta.lordship_bonus = {}
            # Completed Muster expenditure expires with the Levy's budget.
            # Otherwise spending a legal +2 bonus leaves a stale over-budget
            # counter after the bonus is cleared on entering Campaign.
            for lord in state.lords.values():
                lord.lordship_used = 0
            state.meta.special_rules.pop("block_william_of_modena_this_levy", None)
'''
assert source.count(old) == 1
path.write_text(source.replace(old, new))

path = Path('tests/test_long_campaign_fixes_20261010.py')
source = path.read_text()
assert 'test_completed_lordship_expires_with_bonus_on_campaign_entry' not in source
source += '''

@pytest.mark.parametrize("name", [
    "bonus_budget_hidden_teutonic", "bonus_budget_hidden_russian",
])
def test_completed_lordship_expires_with_bonus_on_campaign_entry(name):
    state = position(name)
    for action in INDEX[name]["actions"]:
        apply_action(state, action)
    lid = INDEX[name]["actions"][0]["args"]["lord_id"]
    assert state.meta.lordship_bonus[lid] == 2
    assert state.lords[lid].lordship_used == _lordship_budget(state, lid)
    # Isolate the real Call-to-Arms -> Campaign boundary after expenditure.
    state.meta.levy_step = "call_to_arms"
    state.meta.levy_step_completed_t = False
    state.meta.levy_step_completed_r = False
    state.meta.active_player = "teutonic"
    for side in ("teutonic", "russian"):
        apply_action(state, {"type": "advance_step", "side": side, "args": {}})
    assert state.meta.phase == "campaign"
    assert state.meta.lordship_bonus == {}
    assert all(lord.lordship_used == 0 for lord in state.lords.values())


@pytest.mark.parametrize("scenario,seed", [("watland", 371), ("pleskau", 163)])
def test_bonus_expiration_property_failure_seeds(scenario, seed):
    spec = importlib.util.spec_from_file_location(
        "longfix_property_helper", ROOT / "tests" / "test_property_advanced_invariants.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    state = module._run_self_play(scenario, seed=seed, max_steps=400)
    assert all(lord.lordship_used <= _lordship_budget(state, lid)
               for lid, lord in state.lords.items())
'''
path.write_text(source)

path = Path('docs/LONG_CAMPAIGN_FIXES_20261010.md')
source = path.read_text().replace('contains 34 cases', 'contains 38 cases')
source += '''

## Additional property-test repair

Exercising the newly visible bonus actions exposed stale end-of-Levy
accounting: the bonus was cleared at Campaign entry, but its completed
expenditure was not. The same boundary now clears both, as the state model's
per-Levy counter contract requires. Four additional regressions cover both
factions' boundary transitions and the observed Watland seed 371 and Pleskau
seed 163 failures. Existing property assertions remain unchanged.
'''
path.write_text(source)
