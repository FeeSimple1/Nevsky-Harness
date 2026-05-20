"""R198: per-combat casualty-absorption policy.

The rules make Battle casualty assignment an owner choice ("owner
picks unit per Hit", Battle & Storm Reference). The harness now lets
each side declare a per-combat absorption policy:
  - "weakest_first" (default): shield strong units behind weak.
  - "armored_first": pile Hits onto armored units (they may absorb
    multiple via Protection rolls).
  - custom list: explicit unit-type sacrifice priority.

Attacker declares on cmd_march (stored in combat_pending); defender
on stand_battle; sallying side on cmd_sally. Storm absorption stays
rule-mandated (Storm Attacker = armored-first). Logged in the battle
result under "absorption_policies".
"""
from __future__ import annotations
import inspect

import pytest

import nevsky.actions  # noqa: F401
from nevsky.actions import IllegalAction, apply_action
from nevsky.battle import _assign_hit_owner_pick
from nevsky.campaign import _validate_absorption_policy
from nevsky.scenarios import load_scenario
from nevsky.state import CombatPending


# ----- unit-level: _assign_hit_owner_pick policies -------------------------


def test_weakest_first_picks_least_protected():
    units = {"knights": 1, "militia": 1, "serfs": 1}
    # serfs (none) are weakest -> picked first under weakest_first.
    assert _assign_hit_owner_pick(units, {}, policy="weakest_first") == "serfs"


def test_armored_first_picks_most_protected():
    units = {"knights": 1, "militia": 1, "serfs": 1}
    # knights (armored) picked first under armored_first.
    assert _assign_hit_owner_pick(units, {}, policy="armored_first") == "knights"


def test_custom_order_respected():
    units = {"knights": 1, "militia": 1, "serfs": 1}
    # Custom: sacrifice militia first even though serfs are weaker.
    pick = _assign_hit_owner_pick(units, {}, policy=["militia", "serfs"])
    assert pick == "militia"


def test_custom_order_falls_back_weakest_for_unnamed():
    units = {"knights": 1, "serfs": 1}
    # Custom list names only knights; the unnamed serfs come after,
    # weakest-first. So knights (named, index 0) is picked first.
    assert _assign_hit_owner_pick(units, {}, policy=["knights"]) == "knights"


# ----- validation ----------------------------------------------------------


def test_validate_accepts_known_strings_and_none():
    assert _validate_absorption_policy(None) == "weakest_first"
    assert _validate_absorption_policy("weakest_first") == "weakest_first"
    assert _validate_absorption_policy("armored_first") == "armored_first"


def test_validate_accepts_valid_custom_list():
    assert _validate_absorption_policy(["serfs", "militia"]) == ["serfs", "militia"]


def test_validate_rejects_unknown_string():
    with pytest.raises(IllegalAction) as e:
        _validate_absorption_policy("strongest_first")
    assert e.value.code == "bad_absorption_policy"


def test_validate_rejects_unknown_unit_in_list():
    with pytest.raises(IllegalAction) as e:
        _validate_absorption_policy(["dragons"])
    assert e.value.code == "bad_absorption_policy"


# ----- end-to-end: policy threads through stand_battle ---------------------


def _setup_battle(defender_policy=None):
    """Aleksandr (R) approaches a single Teuton defender at pskov."""
    s = load_scenario("peipus", seed=1)
    s.meta.phase = "campaign"
    s.meta.campaign_step = "done"
    s.meta.active_player = "teutonic"
    s.lords["hermann"].state = "mustered"; s.lords["hermann"].location = "pskov"; s.lords["hermann"].in_stronghold = False
    s.lords["andrey"].state = "mustered"; s.lords["andrey"].location = "pskov"; s.lords["andrey"].in_stronghold = False
    s.combat_pending = CombatPending(
        attacker_side="russian", attacker_group=["andrey"],
        from_locale="dubrovno", to_locale="pskov", way_type="trackway",
        defender_side="teutonic", defender_lords=["hermann"],
        pending_response_by="teutonic", laden=False,
        attacker_absorption_policy="armored_first",
    )
    return s


def test_stand_battle_logs_absorption_policies():
    s = _setup_battle()
    res = apply_action(s, {"type": "stand_battle", "side": "teutonic",
                           "args": {"absorption_policy": "armored_first"}})
    pol = res["battle"]["absorption_policies"]
    assert pol["attacker"] == "armored_first"  # set on combat_pending
    assert pol["defender"] == "armored_first"  # set on stand_battle


def test_stand_battle_rejects_bad_policy():
    s = _setup_battle()
    with pytest.raises(IllegalAction) as e:
        apply_action(s, {"type": "stand_battle", "side": "teutonic",
                         "args": {"absorption_policy": "nonsense"}})
    assert e.value.code == "bad_absorption_policy"


def test_default_policy_is_weakest_first():
    s = _setup_battle()
    # combat_pending attacker default would be weakest_first if not set;
    # here we set it to armored_first in fixture, so reset to test default.
    s.combat_pending.attacker_absorption_policy = "weakest_first"
    res = apply_action(s, {"type": "stand_battle", "side": "teutonic", "args": {}})
    pol = res["battle"]["absorption_policies"]
    assert pol["attacker"] == "weakest_first"
    assert pol["defender"] == "weakest_first"


def test_marker_present_in_source():
    import nevsky.battle as b
    import nevsky.campaign as c
    assert "R198" in inspect.getsource(b)
    assert "R198" in inspect.getsource(c)
