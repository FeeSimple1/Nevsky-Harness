"""SMOKE-075 (Round 77): legal_moves missed Siege/Storm options at
Castle-on-Town overlays.

`legal_moves._campaign_moves` used `_stronghold_at(active.location)` to
detect whether the active Lord was at a stormable Stronghold for
adding cmd_siege / cmd_storm options. `_stronghold_at` keys off the
base type and returns None for Town, so a besieger at a
Castle-on-Town locale never saw the Siege/Storm options surfaced in
legal_moves.

Fix: use `_effective_stronghold` (campaign helper that accounts for
Castle overlays — SMOKE-054 / SMOKE-065).
"""
from __future__ import annotations

import inspect

import nevsky.actions  # noqa: F401 — register handlers first
import nevsky.legal_moves


def test_legal_moves_storm_check_uses_effective_stronghold():
    """The Siege/Storm legal_moves branch should consult
    _effective_stronghold so Castle overlays are recognized."""
    src = inspect.getsource(nevsky.legal_moves)
    # The replacement should be in place; flag the regression if the
    # branch reverts to _stronghold_at (which misses Castle-on-Town).
    assert "_effective_stronghold(state, active.location)" in src, (
        "legal_moves campaign branch should use _effective_stronghold to "
        "recognize Castle overlays on Town locales for Siege/Storm"
    )


def test_legal_moves_storm_check_imports_effective_stronghold():
    """The targeted import is from nevsky.campaign import _effective_stronghold."""
    src = inspect.getsource(nevsky.legal_moves)
    # SMOKE-075 fix introduces an import for _effective_stronghold from
    # nevsky.campaign in the campaign-moves branch.
    assert "from nevsky.campaign import _effective_stronghold" in src, (
        "expected import of _effective_stronghold in legal_moves campaign branch"
    )


def test_legal_moves_storm_check_dropped_stronghold_at_for_siege():
    """The earlier _stronghold_at(active.location) usage for the
    Siege/Storm gate should be gone (Castle-on-Town required the
    overlay-aware helper)."""
    src = inspect.getsource(nevsky.legal_moves)
    # _stronghold_at may still appear elsewhere in this module, but the
    # Siege/Storm branch's specific call site should now use
    # _effective_stronghold.
    siege_block = src[src.find("Siege/Storm if Lord"):]
    siege_block = siege_block[:siege_block.find("# Pursue") + 200] if "# Pursue" in siege_block else siege_block[:2000]
    assert "_stronghold_at(active.location)" not in siege_block, (
        "legal_moves Siege/Storm branch should no longer call _stronghold_at"
    )
