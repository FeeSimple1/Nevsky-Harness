"""Pydantic models for the Nevsky game state.

Phase 2 expansion: adds Levy phase machinery on top of Phase 1's static
inventory of state. New fields:

  - `meta.levy_step` tracks where we are within the Levy SoP (3.0):
      `arts_of_war` (3.1) -> `pay` (3.2) -> `disband` (3.3) ->
      `muster` (3.4) -> `call_to_arms` (3.5) -> `done`
  - `meta.levy_step_completed_t` / `_r` flag whether each side has
    finished the current Levy step (T-then-R order per SoP 2.2.4).
  - `meta.first_levy_done` tracks whether the scenario's opening Levy
    has been processed (governs Capabilities-on-first-Levy vs Events on
    subsequent Levies, rule 3.1.2 / 3.1.3).
  - `Lord.lordship_used` counts Lordship spent this Muster; Phase 2
    enforces budget = LORDSHIP_RATING (3.4).
  - `Lord.just_arrived_this_levy` flags Lords newly Mustered this
    Levy; they cannot use Lordship in the same Muster segment (3.4
    important note) -- reset at end of Levy.
  - `SideDeck.pending_draw` holds AoW cards drawn but not yet
    implemented (3.1.2 / 3.1.3 step-by-step resolution).
  - `SideDeck.this_levy_events` and `this_campaign_events` hold cards
    revealed for those persistence buckets (3.1.3 / 4.9.5).
  - `Legate.acted_this_call_to_arms` enforces the at-most-one option
    per 3.5.1.
  - `Veche.acted_this_call_to_arms` enforces the at-most-one option
    per 3.5.2.
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
LevyStep = Literal[
    "arts_of_war",
    "pay",
    "disband",
    "muster",
    "call_to_arms",
    "done",
]
CampaignStep = Literal[
    "plan",
    "command",
    "end_campaign",
    "done",
]


class Meta(BaseModel):
    """Game metadata: scenario, edition, schema version, RNG state, turn pointer."""

    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    scenario_display_name: str
    edition: Literal["2"] = "2"
    schema_version: str
    seed: int
    sequence: int = 0
    rng_state: int = 0
    box: int = Field(ge=1, le=16, description="Current 40-Days box; advances at end of Campaign.")
    phase: Literal["levy", "campaign"] = "levy"
    levy_step: LevyStep = "arts_of_war"
    levy_step_completed_t: bool = False
    levy_step_completed_r: bool = False
    first_levy_done: bool = False
    campaign_step: CampaignStep = "plan"
    plan_complete_t: bool = False
    plan_complete_r: bool = False
    end_campaign_completed_t: bool = False
    end_campaign_completed_r: bool = False
    block_lords_this_levy_t: list[str] = Field(default_factory=list)
    block_lords_this_levy_r: list[str] = Field(default_factory=list)
    lordship_bonus: dict[str, int] = Field(default_factory=dict)
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
    acted_this_call_to_arms: bool = False


class CampaignTurn(BaseModel):
    """Per-Command-card resolution state (4.2).

    Tracks the alternating T/R reveal pointer, the currently active
    Command card, the active Lord (None on Pass), the action budget for
    the active Lord, and the per-card 4.8 Feed/Pay/Disband sub-step
    completion flags.
    """

    model_config = ConfigDict(extra="forbid")

    next_to_reveal: Side = "teutonic"
    active_card: str | None = None
    active_lord: str | None = None
    actions_remaining: int = 0
    in_feed_pay_disband: bool = False
    fpd_completed_t: bool = False
    fpd_completed_r: bool = False


class CombatPending(BaseModel):
    """Pending Approach / Battle decision (4.3.4 - 4.4).

    Set by cmd_march when Marching into a Locale containing enemy
    Lord(s). Defender (whose Lords are at the target) chooses one of:
    avoid_battle (Unladen, 4.3.4), withdraw (4.3.4 into a Friendly
    Stronghold), or stand_battle (4.4 begins).
    Cleared after the chosen response resolves.
    """

    model_config = ConfigDict(extra="forbid")

    attacker_side: Side
    attacker_group: list[str] = Field(default_factory=list)
    from_locale: str
    to_locale: str
    way_type: str
    defender_side: Side
    defender_lords: list[str] = Field(default_factory=list)
    pending_response_by: Side
    laden: bool = False


class VassalState(BaseModel):
    """Per-Vassal mutable state.

    `ready` reflects the Vassal Service marker face (CoA up = ready, CoA
    down = unready). `mustered` is true once the Vassal's Forces have
    been deployed onto the Lord's mat via Muster Vassal action (3.4.2);
    when mustered, the Vassal's Forces are merged into the parent Lord's
    `forces` dict.

    `on_calendar` and `calendar_box` cover the Advanced Vassal Service
    optional rule (3.4.2) where a Vassal's Service marker is placed on
    the Calendar instead of staying on the Lord's mat. For Phase 2 this
    is captured but not exercised by any default action; the basic
    Muster Vassal action keeps markers on the mat.
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
    are integers per type; rules treat half-counts as a marker side, but
    the harness tracks integers and emits half Hits during combat
    resolution rather than storing fractional units (Phase 3).

    `assets` carries Coin / Provender / Loot plus Transport sub-types
    (Boat, Cart, Sled, Ship). Whether Ships are allowed for the Lord is
    determined by static data (`ships_authorized`); the loader rejects
    Ship counts > 0 for Lords who lack the authorization.

    `lordship_used` and `just_arrived_this_levy` are Phase 2 fields used
    during Muster (3.4) and reset at end of Levy.
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
    lordship_used: int = 0
    just_arrived_this_levy: bool = False
    in_stronghold: bool = False
    first_march_used_this_card: bool = False
    raiders_used_this_card: bool = False
    lieutenant_of: str | None = None  # Lord this Lord serves under as Lower Lord (4.1.3)
    has_lower_lord: str | None = None  # Lower Lord stacked on this Lord (Marshal/Lieutenant)

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

    `deck` is the face-down draw pile (shuffled at start of each Levy
    via 3.1.1). `discard` is the face-up pile that returns to deck on
    shuffle except for `removed` cards. `capabilities_in_play` are
    side-wide capabilities under the player's board edge (this-lord
    capabilities live on the Lord's mat in `Lord.this_lord_capabilities`).
    `holds` are face-down Hold-event cards in the player's hand.
    `pending_draw` are cards drawn during the current Arts of War step
    that have not yet been implemented (3.1.2 / 3.1.3).
    `this_levy_events` and `this_campaign_events` are persistence
    buckets per 3.1.3.
    `plan` is the Command-card stack for the current Campaign (4.1).
    """

    model_config = ConfigDict(extra="forbid")

    deck: list[str] = Field(default_factory=list)
    discard: list[str] = Field(default_factory=list)
    removed: list[str] = Field(default_factory=list)
    capabilities_in_play: list[str] = Field(default_factory=list)
    holds: list[str] = Field(default_factory=list)
    pending_draw: list[str] = Field(default_factory=list)
    this_levy_events: list[str] = Field(default_factory=list)
    this_campaign_events: list[str] = Field(default_factory=list)
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
    acted_this_call_to_arms: bool = False


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
    campaign_turn: CampaignTurn = Field(default_factory=CampaignTurn)
    combat_pending: CombatPending | None = None
    pending_decisions: list[PendingDecision] = Field(default_factory=list)
    history: list[HistoryEntry] = Field(default_factory=list)
