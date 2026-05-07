"""Regenerate the committed state schema from the pydantic models.

Usage: python scripts/generate_schema.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from nevsky.state import GameState  # noqa: E402

SCHEMA_OUT = ROOT / "src" / "nevsky" / "data" / "schema" / "state.schema.json"


def main() -> None:
    schema = GameState.model_json_schema()
    SCHEMA_OUT.write_text(
        json.dumps(schema, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {SCHEMA_OUT}")


if __name__ == "__main__":
    main()
