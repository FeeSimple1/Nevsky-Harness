"""SMOKE-071 (Round 75): Sally aftermath retreat captures way_type and
honors result['conceded'] flag for 4.4.3 Spoils accounting.

The Sally aftermath defender-loss branch (besiegers lose the Sally
Battle) previously:
  - Always used transfer_spoils mode 'all_except_ships' regardless of
    whether the besieger Conceded the Field.
  - Did not capture the retreat Way's type, so the loot_and_excess
    path would have no way to compute Unladen Transport along the
    Retreat Way.

The R75 fix mirrors SMOKE-069's pattern in the regular Battle
aftermath: capture retreat_way_type_actual from the for-loop, and
check result['conceded']. If conceded_side == 'defender' (besieger
loser), use loot_and_excess + retreat_way_type. Otherwise keep
all_except_ships.

These are source-inspection regressions (matching SMOKE-069 style).
The end-to-end Sally Spoils transfer is exercised by adjacent siege
suite tests.
"""

import inspect

import nevsky.actions  # noqa: F401 — register handlers
from nevsky.campaign import _h_cmd_sally


def test_sally_aftermath_captures_retreat_way_type() -> None:
    src = inspect.getsource(_h_cmd_sally)
    # The fix introduces retreat_way_type_actual.
    assert "retreat_way_type_actual" in src, (
        "Sally aftermath should capture retreat_way_type_actual from the "
        "for-w-in-load_ways loop so loot_and_excess can compute Unladen Transport"
    )


def test_sally_aftermath_checks_conceded_flag() -> None:
    src = inspect.getsource(_h_cmd_sally)
    # The fix consults result["conceded"] to decide between
    # loot_and_excess and all_except_ships.
    assert 'result.get("conceded")' in src or "result['conceded']" in src, (
        "Sally aftermath should consult result['conceded'] to decide spoils mode"
    )


def test_sally_aftermath_uses_loot_and_excess_for_conceded() -> None:
    src = inspect.getsource(_h_cmd_sally)
    # The fix uses loot_and_excess for Conceded-then-Retreated defenders.
    assert "loot_and_excess" in src, (
        "Sally aftermath should use transfer_spoils mode 'loot_and_excess' "
        "for besiegers who Conceded the Field and Retreated (4.4.3)"
    )


def test_sally_aftermath_passes_retreat_way_type_to_transfer_spoils() -> None:
    src = inspect.getsource(_h_cmd_sally)
    # The loot_and_excess call must pass retreat_way_type so
    # _usable_transport_count_for_way can be invoked.
    # Look for the specific keyword pass-through.
    assert "retreat_way_type=retreat_way_type_actual" in src, (
        "Sally aftermath loot_and_excess transfer_spoils call should pass "
        "retreat_way_type=retreat_way_type_actual so Unladen Transport can "
        "be computed along the retreat Way"
    )
