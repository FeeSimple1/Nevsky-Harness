"""Phase 0 smoke tests.

These tests do not exercise game logic (Phase 0 has none). They verify
that the package, CLI, schema file, and scenario data files are present
and parseable.
"""

from __future__ import annotations

import json
from importlib import resources

import pytest
from typer.testing import CliRunner

from nevsky.cli import app
from nevsky.scenarios import SCENARIO_IDS, load_scenario_raw
from nevsky.state import GameState

EXPECTED_TOP_KEYS = {
    "meta",
    "calendar",
    "veche",
    "lords",
    "locales",
    "decks",
    "legate",
    "campaign_turn",
    "pending_decisions",
    "history",
}

EXPECTED_SCENARIOS = {
    "pleskau",
    "watland",
    "return_of_the_prince",
    "return_of_the_prince_nicolle",
    "peipus",
    "crusade_on_novgorod",
    "quickstart",
}


runner = CliRunner()


def test_version_command_exits_zero() -> None:
    """`nevsky version` prints the version and exits 0."""
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0, result.output
    assert "nevsky-harness" in result.output
    assert "state schema" in result.output


def test_state_schema_file_is_valid_json() -> None:
    """The committed state schema file is valid JSON with expected top-level keys."""
    schema_text = (
        resources.files("nevsky.data.schema").joinpath("state.schema.json").read_text("utf-8")
    )
    schema = json.loads(schema_text)
    assert "properties" in schema
    assert EXPECTED_TOP_KEYS.issubset(set(schema["properties"].keys()))


def test_pydantic_schema_generation_top_keys_match() -> None:
    """The pydantic model emits a schema with the expected top-level keys."""
    generated = GameState.model_json_schema()
    assert EXPECTED_TOP_KEYS == set(generated["properties"].keys())


def test_seven_scenarios_exist() -> None:
    """We have exactly the seven expected scenarios."""
    assert set(SCENARIO_IDS) == EXPECTED_SCENARIOS


@pytest.mark.parametrize("scenario_id", sorted(EXPECTED_SCENARIOS))
def test_scenario_files_parse(scenario_id: str) -> None:
    """Each of the seven scenario JSON files parses and has expected fields."""
    data = load_scenario_raw(scenario_id)
    assert data["id"] == scenario_id
    if scenario_id == "quickstart":
        assert data.get("status") == "placeholder"
    else:
        assert "span" in data
        assert "setup" in data
