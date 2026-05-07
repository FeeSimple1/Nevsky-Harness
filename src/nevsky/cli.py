"""CLI entry point for the Nevsky harness.

Phase 2 commands implemented: version, new, state, save, load, history,
pending, legal-moves, do.
"""

from __future__ import annotations

import json
from pathlib import Path

import typer

from nevsky import SCHEMA_VERSION, __version__
from nevsky.actions import IllegalAction, apply_action
from nevsky.legal_moves import legal_moves as enumerate_legal_moves
from nevsky.render import render_focus, render_summary, render_verbose
from nevsky.scenarios import (
    SCENARIO_IDS,
    ScenarioPlaceholderError,
    load_scenario,
)
from nevsky.state import GameState

app = typer.Typer(
    name="nevsky",
    help="Python harness for Nevsky: Teutons and Rus in Collision, 1240-1242.",
    no_args_is_help=True,
)


@app.command()
def version() -> None:
    """Print the harness version and the state schema version."""
    typer.echo(f"nevsky-harness {__version__}")
    typer.echo(f"state schema {SCHEMA_VERSION}")


@app.command()
def new(
    scenario: str = typer.Argument(..., help=f"Scenario id, one of: {', '.join(SCENARIO_IDS)}."),
    output: Path = typer.Option(..., "--output", "-o", help="Path to write the new state JSON file."),
    seed: int = typer.Option(0, "--seed", help="RNG seed; stored in state for determinism."),
) -> None:
    """Initialize a state file from a scenario."""
    try:
        state = load_scenario(scenario, seed=seed)
    except ScenarioPlaceholderError as e:
        typer.echo(f"error: {e}", err=True)
        raise typer.Exit(code=2)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(state.model_dump_json(indent=2) + "\n", encoding="utf-8")
    typer.echo(f"wrote {output}")


@app.command()
def state(
    state_file: Path = typer.Argument(..., exists=True, dir_okay=False, help="Path to a state JSON file."),
    mode: str = typer.Option("summary", "--mode", "-m", help="summary | verbose | focus"),
    focus: str | None = typer.Option(
        None, "--focus", "-f",
        help="Required when mode=focus. Format: lord:<id> | locale:<id> | calendar | veche | deck:<side>",
    ),
) -> None:
    """Render current state in the requested mode."""
    s = _read_state(state_file)
    if mode == "summary":
        typer.echo(render_summary(s))
    elif mode == "verbose":
        typer.echo(render_verbose(s))
    elif mode == "focus":
        if not focus:
            typer.echo("error: --focus is required when mode=focus", err=True)
            raise typer.Exit(code=2)
        try:
            typer.echo(render_focus(s, focus))
        except ValueError as e:
            typer.echo(f"error: {e}", err=True)
            raise typer.Exit(code=2)
    else:
        typer.echo(f"error: unknown mode {mode!r} (use summary | verbose | focus)", err=True)
        raise typer.Exit(code=2)


@app.command(name="legal-moves")
def legal_moves_cmd(
    state_file: Path = typer.Argument(..., exists=True, dir_okay=False),
    output: Path | None = typer.Option(None, "--output", "-o", help="Write JSON to file instead of stdout."),
) -> None:
    """Enumerate legal actions for the active player."""
    s = _read_state(state_file)
    moves = enumerate_legal_moves(s)
    text = json.dumps(moves, indent=2, sort_keys=True) + "\n"
    if output is None:
        typer.echo(text, nl=False)
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
        typer.echo(f"wrote {output}")


@app.command()
def do(
    state_file: Path = typer.Argument(..., exists=True, dir_okay=False),
    action_file: Path = typer.Argument(..., exists=True, dir_okay=False),
    output: Path | None = typer.Option(None, "--output", "-o", help="Write the post-action state to this path (default: overwrite state_file)."),
) -> None:
    """Execute a submitted action against the state."""
    s = _read_state(state_file)
    action_text = action_file.read_text(encoding="utf-8")
    try:
        action = json.loads(action_text)
    except json.JSONDecodeError as e:
        typer.echo(f"error: action_file is not valid JSON: {e}", err=True)
        raise typer.Exit(code=2)
    try:
        result = apply_action(s, action)
    except IllegalAction as e:
        typer.echo(f"illegal_action: {e}", err=True)
        raise typer.Exit(code=2)
    target = output if output is not None else state_file
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(s.model_dump_json(indent=2) + "\n", encoding="utf-8")
    typer.echo(f"OK: {json.dumps(result, sort_keys=True)}")


@app.command()
def pending(
    state_file: Path = typer.Argument(..., exists=True, dir_okay=False),
) -> None:
    """Show pending sub-decisions and which side owes a response."""
    s = _read_state(state_file)
    if not s.pending_decisions:
        typer.echo("no pending decisions")
        return
    for i, pd in enumerate(s.pending_decisions):
        typer.echo(f"#{i + 1} {pd.kind} (owed by {pd.owed_by})")
        if pd.note:
            typer.echo(f"   {pd.note}")
        if pd.context:
            typer.echo(f"   context: {json.dumps(pd.context, sort_keys=True)}")


@app.command()
def history(
    state_file: Path = typer.Argument(..., exists=True, dir_okay=False),
    last: int = typer.Option(10, "--last", "-n", help="Number of recent entries to show."),
) -> None:
    """Show the last N actions executed against the state."""
    s = _read_state(state_file)
    if not s.history:
        typer.echo("no history yet")
        return
    entries = s.history[-last:] if last > 0 else s.history
    for h in entries:
        typer.echo(
            f"#{h.sequence} ({h.actor}): action={h.action} dice={h.dice} result={h.result}"
        )


@app.command()
def save(
    state_file: Path = typer.Argument(..., exists=True, dir_okay=False),
    output: Path = typer.Option(..., "--output", "-o", help="Path to write the saved copy."),
) -> None:
    """Save (round-trip) state to another path. Validates while loading."""
    s = _read_state(state_file)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(s.model_dump_json(indent=2) + "\n", encoding="utf-8")
    typer.echo(f"wrote {output}")


@app.command()
def load(
    state_file: Path = typer.Argument(..., exists=True, dir_okay=False),
) -> None:
    """Validate a state file by parsing it. Echoes a one-line summary."""
    s = _read_state(state_file)
    typer.echo(
        f"OK: scenario={s.meta.scenario_id} box={s.meta.box} phase={s.meta.phase} "
        f"step={s.meta.levy_step} active={s.meta.active_player} "
        f"lords={len(s.lords)} pending={len(s.pending_decisions)}"
    )


def _read_state(path: Path) -> GameState:
    text = path.read_text(encoding="utf-8")
    return GameState.model_validate_json(text)


if __name__ == "__main__":
    app()
