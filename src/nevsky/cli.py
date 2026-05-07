"""CLI entry point for the Nevsky harness.

Phase 0: stubs only. Subcommands raise NotImplementedError until their
phase implements them. The 'version' subcommand is functional so the
smoke test has a real CLI surface to hit.
"""

from __future__ import annotations

import typer

from nevsky import SCHEMA_VERSION, __version__

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
    scenario: str = typer.Argument(..., help="Scenario id, e.g. 'pleskau'."),
    output: str = typer.Option(..., "--output", "-o", help="Path to write the new state file."),
) -> None:
    """Initialize a state file from a scenario (Phase 1)."""
    raise NotImplementedError("Phase 1: scenario loader not yet implemented")


@app.command()
def state(
    state_file: str = typer.Argument(..., help="Path to a state JSON file."),
    mode: str = typer.Option("summary", "--mode", "-m", help="summary | verbose | focus"),
) -> None:
    """Render current state (Phase 1)."""
    raise NotImplementedError("Phase 1: state rendering not yet implemented")


@app.command(name="legal-moves")
def legal_moves(
    state_file: str = typer.Argument(..., help="Path to a state JSON file."),
) -> None:
    """Enumerate legal actions for the active player (Phase 2)."""
    raise NotImplementedError("Phase 2: legal-move enumeration not yet implemented")


@app.command()
def do(
    state_file: str = typer.Argument(..., help="Path to a state JSON file."),
    action_file: str = typer.Argument(..., help="Path to an action JSON file."),
) -> None:
    """Execute a submitted action (Phase 2+)."""
    raise NotImplementedError("Phase 2+: action execution not yet implemented")


@app.command()
def pending(
    state_file: str = typer.Argument(..., help="Path to a state JSON file."),
) -> None:
    """Show pending sub-decisions (Phase 2+)."""
    raise NotImplementedError("Phase 2+: pending-decision tracking not yet implemented")


@app.command()
def history(
    state_file: str = typer.Argument(..., help="Path to a state JSON file."),
    last: int = typer.Option(10, "--last", "-n", help="Number of recent entries to show."),
) -> None:
    """Show the last N actions (Phase 1)."""
    raise NotImplementedError("Phase 1: history rendering not yet implemented")


@app.command()
def save(
    state_file: str = typer.Argument(..., help="Path to a state JSON file."),
    output: str = typer.Option(..., "--output", "-o", help="Path to write the saved copy."),
) -> None:
    """Save state to a file (Phase 1)."""
    raise NotImplementedError("Phase 1: explicit save not yet implemented")


@app.command()
def load(
    state_file: str = typer.Argument(..., help="Path to a state JSON file."),
) -> None:
    """Load state from a file (Phase 1)."""
    raise NotImplementedError("Phase 1: explicit load not yet implemented")


if __name__ == "__main__":
    app()
