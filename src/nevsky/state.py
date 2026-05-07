"""Pydantic models for the Nevsky game state.

Phase 1: full state representation. Sub-models cover Lords (with current
Forces, Assets, Vassals, This-Lord Capabilities), Locales (with markers),
Calendar (16 boxes with cylinders, Service markers, Levy/Campaign marker,
Victory markers), Veche, Decks (per-side AoW deck/discard/removed/holds/
in-play Capabilities/Plan), Legate, pending decisions, action history.

Static data (Lord ratings/starting forces/seats, Locale type/territory/
seaports, Way graph, AoW card metadata) lives in src/nevsky/data/static
JSON files and is looked up by id; only mutable state lives here.

Schema notes:
  - `meta.seed` (RNG seed) lives in state per BRIEF determinism req.
  - `calendar.off_left` / `off_right` track cylinders past the ends
    (rules 2.2.3 explicitly handles these positions).
  - `veche` enforces 8/8 caps via field constraints (rules 1.4.2).
  - `pending_decisions` queue per BRIEF `pending` interface req.
  - Pleskau-only enemy-Lord-removed VP counter is a Calendar-level
    field so it does not need scenario-conditional modeling later.
  - Force types and Asset types are enumerated as Literal types so
    pydantic validates dict keys; typo'd unit/asset names fail loudly.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Side = Literal["teutonic", "russian"]
ForceType = Literal[
    "knights",
    "sergeants",
    "men_at_arms",
    "militia",
    "light_horse",
    "asiatic_horse",
    "serfs",
]
AssetType = Literal[
    "coin",
    "provender",
    "loot",
    "boat",
    "cart",
    "sled",
    "ship",
]
LordState = Literal["ready", "mustered", "disbanded", "removed"]


class Meta(BaseModel):
    """Game metadata: scenario, edition, schema version, RNG state, turn pointer."""

    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    scenario_display_name: str
    edition: Literal["2"] = "2"
    schema_version: str
    seed: int
    sequence: int = 0
    box: int = Field(ge=1, le=16, description="Current 40-Days box; advances at end of Campaign.")
    phase: Literal["levy", "campaign"] = "levy"
    active_player: Side | None = None
    span_start_box: int = Field(ge=1, le=16)
    span_end_box: int = Field(ge=1, le=16)
    aggressor: Literal["teutonic", "russian", "both"]
    special_rules: dict[str, Any] = Field(default_factory=dict)


class CalendarBox(BaseModel):
    """One of the 16 40-Days boxes."""

    model_config = ConfigDict(extra="forbid")

    box: int = Field(ge=1, le=16)
    cylinders: list[str] = Field(default_factory=list)
    service_markers: list[str] = Field(default_factory=list)
    vassal_service_markers: list[str] = Field(default_factory=list)
    has_levy_campaign_marker: bool = False
    levy_campaign_face: Literal["levy", "campaign"] | None = None
    russian_victory_marker: bool = False
    teutonic_victory_marker: bool = False


class Calendar(BaseModel):
    """The 16-box Calendar plus off-end overflow positions (rules 2.2.3)."""

    model_config = ConfigDict(extra="forbid")

    boxes: list[CalendarBox] = Field(default_factory=list)
    off_left: list[str] = Field(default_factory=list, description="Cylinders past the left edge.")
    off_right: list[str] = Field(default_factory=list, description="Cylinders past the right edge.")
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


class VassalState(BaseModel):
    """Per-Vassal mutable state.

    `ready` reflects the Vassal Service marker face (CoA up = ready, CoA
    down = unready). `mustered` is true once the Vassal's Forces have
    been deployed onto the Lord's mat via Muster Vassal action (3.4.2);
    when mustered, the Vassal's Forces are merged into the parent Lord's
    `forces` dict.

    `on_calendar` and `calendar_box` cover the Advanced Vassal Service
    optional rule (3.4.2) where a Vassal's Service marker is placed on
    the Calendar instead of staying on the Lord's mat. For Phase 1 this
    is captured but unused; Phase 2 wires up Levy Vassal mechanics.
    """

    model_config = ConfigDict(extra="forbid")

    vassal_id: str
    ready: bool = True
    mustered: bool = False
    on_calendar: bool = False
    calendar_box: int | None = Field(default=None, ge=1, le=16)


class Lord(BaseModel):
    """Lord state. Static data (ratings, seats, starting forces) is in
    data/static/lords.json and looked up by lord_id; only mutable state
    lives here.

    `forces` is the Lord's CURRENT force composition: starting forces
    plus any Mustered Vassal forces, minus combat losses. Force counts
    are integers per type; rules treat ½-counts as a marker side, but
    the harness tracks integers and emits ½ Hits during combat
    resolution rather than storing fractional units (Phase 3).

    `assets` carries Coin / Provender / Loot plus Transport sub-types
    (Boat, Cart, Sled, Ship). Whether Ships are allowed for the Lord is
    determined by static data (`ships_authorized`); the loader rejects
    Ship counts > 0 for Lords who lack the authorization.
    """

    model_config = ConfigDict(extra="forbid")

    lord_id: str
    side: Side
    location: str | None = Field(
        default=None,
        description="Locale id where this Lord is on the map; None if not mustered.",
    )
    state: LordState = "ready"
    moved_fought: bool = False
    forces: dict[ForceType, int] = Field(default_factory=dict)
    assets: dict[AssetType, int] = Field(default_factory=dict)
    vassals: dict[str, VassalState] = Field(default_factory=dict)
    this_lord_capabilities: list[str] = Field(default_factory=list)

    @field_validator("forces", "assets")
    @classmethod
    def _nonneg(cls, v: dict[str, int]) -> dict[str, int]:
        for k, n in v.items():
            if n < 0:
                raise ValueError(f"negative count for {k!r}: {n}")
        return v


class Locale(BaseModel):
    """Locale state. Static data (type, territory, seats, seaport, VP)
    is in data/static/locales.json and looked up by locale_id.

    Conquered counts can stack: a fully Conquered City carries 2
    markers (matching its 2-VP value); fully Conquered Novgorod carries
    3. Markers are added per Conquest event and stay until removed.

    `walls_plus_one` (R18 Stone Kremlin) is restricted at validation
    time to Russian Forts, Cities, and Novgorod (Phase 2 enforces; the
    pydantic field is just a bool).
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


class SideDeck(BaseModel):
    """One side's Arts of War deck state.

    `deck` is the face-down draw pile (shuffled at start of each Levy).
    `discard` is the face-up pile that returns to deck on shuffle except
    for `removed` cards. `capabilities_in_play` are side-wide
    capabilities under the player's board edge (this-lord capabilities
    live on the Lord's mat in `Lord.this_lord_capabilities`).
    `holds` are face-down Hold-event cards in the player's hand. `plan`
    is the Command-card stack for the current Campaign (entries are
    Command card identifiers; Phase 1 leaves this empty).
    """

    model_config = ConfigDict(extra="forbid")

    deck: list[str] = Field(default_factory=list)
    discard: list[str] = Field(default_factory=list)
    removed: list[str] = Field(default_factory=list)
    capabilities_in_play: list[str] = Field(default_factory=list)
    holds: list[str] = Field(default_factory=list)
    plan: list[str] = Field(default_factory=list)


class Decks(BaseModel):
    """Per-side card state."""

    model_config = ConfigDict(extra="forbid")

    teutonic: SideDeck = Field(default_factory=SideDeck)
    russian: SideDeck = Field(default_factory=SideDeck)


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
    note: str | None = None


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
