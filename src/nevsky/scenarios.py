"""Scenario loader.

Phase 0: returns the raw scenario JSON dict. Phase 1 turns this into a
fully-populated GameState (Lords, Locales, decks, Calendar setup) using
reference data not yet wired up.
"""

from __future__ import annotations

import json
from importlib import resources
from typing import Any

SCENARIO_IDS: tuple[str, ...] = (
    "pleskau",
    "watland",
    "return_of_the_prince",
    "return_of_the_prince_nicolle",
    "peipus",
    "crusade_on_novgorod",
    "quickstart",
)


def load_scenario_raw(scenario_id: str) -> dict[str, Any]:
    """Load and parse a scenario JSON file by id.

    Phase 0: returns the parsed dict only. Quickstart returns its
    placeholder body; the loader does NOT raise on it here. Phase 1's
    state-building loader will reject placeholder scenarios with a clear
    error.
    """
    if scenario_id not in SCENARIO_IDS:
        raise ValueError(
            f"unknown scenario id: {scenario_id!r}. "
            f"known ids: {', '.join(SCENARIO_IDS)}"
        )
    package = "nevsky.data.scenarios"
    filename = f"{scenario_id}.json"
    text = resources.files(package).joinpath(filename).read_text(encoding="utf-8")
    return json.loads(text)
