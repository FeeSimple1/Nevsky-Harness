"""Pydantic models for the Nevsky game state.

Phase 0: top-level skeleton only. Sub-models are stubs --- Phase 1 fills in
Lord, Locale, Forces, Assets, etc., once the scenario loader is wired up.

Schema choices documented inline:
  - `meta.seed` (RNG seed) lives in state per BRIEF.md determinism requirement.
  - `calendar.off_left` / `off_right` track marker positions past either
    end of the Calendar (rules 2.2.3 explicitly handles this case).
  - `veche` enforces 8/8 caps via field constraints (rules 1.4.2 Wastage).
  - `pending_decisions` queue per BRIEF.md `pending` interface requirement.
  - Pleskau-only enemy-Lord-removed VP counter is a top-level Calendar
    field so it does not need to be modeled scenario-conditionally later.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Side = Literal["teutonic", "russian"]


class Meta(BaseModel):
    """Game metadata: scenario, edition, schema version, RNG state, turn pointer."""

    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    edition: Literal["2"] = "2"
    schema_version: str
    seed: int
    sequence: int = 0
    box: int = Field(ge=1, le=16)
    phase: Literal["levy", "campaign"] = "levy"
    active_player: Side | None = None


class CalendarBox(BaseModel):
    """One of the 16 40-Days boxes."""

    model_config = ConfigDict(extra="forbid")

    box: int = Field(ge=1, le=16)
    cylinders: list[str] = Field(default_factory=list)
    service_markers: list[str] = Field(default_factory=list)
    has_levy_campaign_marker: bool = False
    levy_campaign_face: Literal["levy", "campaign"] | None = None
    russian_victory_marker: bool = False
    teutonic_victory_marker: bool = False


class Calendar(BaseModel):
    """The 16-box Calendar plus off-end overflow positions (rules 2.2.3)."""

    model_config = ConfigDict(extra="forbid")

    boxes: list[CalendarBox] = Field(default_factory=list)
    off_left: list[str] = Field(default_factory=list)
    off_right: list[str] = Field(default_factory=list)
    russian_vp: float = 0.0
    teutonic_vp: float = 0.0
    pleskau_lords_removed_russian: int = 0
    pleskau_lords_removed_teutonic: int = 0


class Veche(BaseModel):
    """Novgorod Veche box. Caps enforced (rules 1.4.2)."""

    model_config = ConfigDict(extra="forbid")

    coin: int = Field(ge=0, le=8, default=0)
    vp_markers: int = Field(ge=0, le=8, default=0)
    novgorod_conquered: bool = False


class Lord(BaseModel):
    """Lord mat. Phase 1 fills in forces, assets, vassals, capabilities."""

    model_config = ConfigDict(extra="forbid")

    lord_id: str
    side: Side
    location: str | None = None
    state: Literal["ready", "mustered", "disbanded", "removed"] = "ready"
    moved_fought: bool = False
    placeholder: dict[str, Any] = Field(default_factory=dict)


class Locale(BaseModel):
    """Locale on the map.

    Walls+1 is permitted only on Russian Forts, Cities, and Novgorod
    (R18 Stone Kremlin). Validation deferred to Phase 1.
    """

    model_config = ConfigDict(extra="forbid")

    locale_id: str
    russian_conquered: int = Field(ge=0, default=0)
    teutonic_conquered: int = Field(ge=0, default=0)
    russian_ravaged: bool = False
    teutonic_ravaged: bool = False
    russian_castle: bool = False
    teutonic_castle: bool = False
    walls_plus_one: bool = False
    siege_markers: int = Field(ge=0, le=4, default=0)


class Decks(BaseModel):
    """Per-side card state. Phase 1 fills in card identifiers."""

    model_config = ConfigDict(extra="forbid")

    teutonic_deck: list[str] = Field(default_factory=list)
    russian_deck: list[str] = Field(default_factory=list)
    teutonic_discard: list[str] = Field(default_factory=list)
    russian_discard: list[str] = Field(default_factory=list)
    teutonic_removed: list[str] = Field(default_factory=list)
    russian_removed: list[str] = Field(default_factory=list)
    teutonic_capabilities_in_play: list[str] = Field(default_factory=list)
    russian_capabilities_in_play: list[str] = Field(default_factory=list)
    teutonic_holds: list[str] = Field(default_factory=list)
    russian_holds: list[str] = Field(default_factory=list)
    teutonic_plan: list[str] = Field(default_factory=list)
    russian_plan: list[str] = Field(default_factory=list)


class Legate(BaseModel):
    """Papal Legate state (rules 1.4.1, 3.5.1, 4.2)."""

    model_config = ConfigDict(extra="forbid")

    william_of_modena_in_play: bool = False
    location: Literal["card", "locale"] = "card"
    locale_id: str | None = None


class PendingDecision(BaseModel):
    """A sub-decision the harness is waiting on."""

    model_config = ConfigDict(extra="forbid")

    kind: str
    owed_by: Side
    context: dict[str, Any] = Field(default_factory=dict)


class HistoryEntry(BaseModel):
    """An action executed against the state."""

    model_config = ConfigDict(extra="forbid")

    sequence: int
    actor: Literal["teutonic", "russian", "system"]
    action: dict[str, Any]
    dice: list[dict[str, Any]] = Field(default_factory=list)
    result: dict[str, Any] = Field(default_factory=dict)


class GameState(BaseModel):
    """Top-level game state. Single source of truth, persisted as JSON."""

    model_config = ConfigDict(extra="forbid")

    meta: Meta
    calendar: Calendar
    veche: Veche
    lords: dict[str, Lord] = Field(default_factory=dict)
    locales: dict[str, Locale] = Field(default_factory=dict)
    decks: Decks = Field(default_factory=Decks)
    legate: Legate = Field(default_factory=Legate)
    pending_decisions: list[PendingDecision] = Field(default_factory=list)
    history: list[HistoryEntry] = Field(default_factory=list)
