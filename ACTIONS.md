# Actions

The harness accepts and executes actions submitted as JSON dicts. Each
action has the envelope:

```json
{ "type": "<action_type>", "side": "teutonic" | "russian" | "system", "args": { ... } }
```

The dispatcher (`nevsky.actions.apply_action`) validates the action,
mutates state in place, appends a `HistoryEntry`, and returns a result
dict. Illegal actions raise `IllegalAction` (with a `code` attribute);
the state is not mutated when this happens.

Phase 2 (Levy phase) actions are listed below. Phase 3 will add
Campaign actions.

## Step transitions

- **`advance_step`** — mark the current side's segment of the current
  Levy step finished. T-then-R order per Sequence of Play 2.2.4. When
  both T and R have called `advance_step`, the harness advances to the
  next Levy step (`arts_of_war` -> `pay` -> `disband` -> `muster` ->
  `call_to_arms` -> `done`).

## 3.1 Arts of War

- **`aow_shuffle`** — shuffle own AoW deck (3.1.1). Pools `deck` +
  `discard` and applies the seeded RNG. Cards in `holds`,
  `capabilities_in_play`, `removed`, `this_levy_events`,
  `this_campaign_events`, and `pending_draw` are excluded per 3.1.1.
- **`aow_draw`** — draw 2 cards into `pending_draw` (3.1.2 / 3.1.3).
  Refuses if `pending_draw` is non-empty.
- **`aow_implement_card`** — implement the next card in `pending_draw`.
  - First Levy of scenario (`first_levy_done=False`): implement bottom
    half (Capability) per 3.1.2. `args.lord_id` required for
    this-lord scope; max 2 per Lord; no duplicates by capability name
    (3.4.4).
  - Subsequent Levies (`first_levy_done=True`): implement top half
    (Event) per 3.1.3. Hold events go to `holds`; this-Levy events
    go to `this_levy_events`; this-Campaign events go to
    `this_campaign_events`; immediate events resolve and discard.
  - No-Event / No-Capability cards: removed from play permanently
    per 3.1.3 (2E). Crusade-on-Novgorod scenario retains them via
    the `keep_no_event_cards` special rule.
- **`aow_discard_this_levy`** — 3.5.3, discard own this-Levy events.

## 3.2 Pay

- **`pay_with_coin`** — `args.from = "lord:<id>" | "veche"`,
  `target_lord`, `units`. Veche source is Russian-only; cannot reach
  a Besieged Lord (3.2.1). Lord source can pay own Service or a
  co-located Lord's Service (3.2.1). Besieged Lord's Service can be
  shifted only by his own Coin or a co-besieged Lord's Coin.
- **`pay_with_loot`** — `args.from_lord`, `target_lord`, `units`.
  Loot may only be spent at a Friendly Locale (3.2.2). Sieges
  excluded.

## 3.3 Disband

- **`disband_resolve`** — process all Lords on the active side whose
  Service marker is at-or-left-of the Levy marker.
  - Service marker LEFT of Levy: 3.3.1 permanent removal. Forces /
    Assets / Vassals returned to pools; this-lord capabilities return
    to side's deck; mat removed.
  - Service marker SAME box as Levy: 3.3.2 at-limit Disband. Cylinder
    placed SERVICE_RATING boxes RIGHT of CURRENT box (during Levy);
    Forces / Assets returned; this-lord capabilities return to deck.

## 3.4 Muster

Each option costs 1 Lordship action. Budget = Lord's Lordship rating.
A newly arrived Lord cannot use Lordship in the same Muster segment.
Besieged Lords cannot Muster.

- **`muster_lord`** — `args.by_lord`, `target_lord`, `seat`. Roll d6;
  success on roll <= target's Fealty rating. Aleksandr is excluded
  (Veche-only via Option B per 3.5.2).
- **`muster_vassal`** — `args.by_lord`, `vassal_id`. Adds Vassal's
  pictured Forces to the Lord's mat. Mongols / Kipchaqs require R10
  Steppe Warriors in play. Summer Crusaders require T11 Crusade.
- **`levy_transport`** — `args.by_lord`, `transport_type`. Adds 1
  Boat / Cart / Sled / Ship. Ship requires `ships_authorized` on
  the Lord's mat. Max 8 of any type per Lord.
- **`levy_capability`** — `args.by_lord`, `card_id`,
  `lord_id` (this-lord scope). Tucks under target Lord's mat
  (this-lord) or at side's board edge (side-wide). Max 2 this-lord
  capabilities per Lord; no duplicates by capability name.

## 3.5 Call to Arms

- **`legate_arrives`** — `args.bishopric` ∈
  {`riga`, `dorpat`, `leal`, `reval`}. Requires William of Modena
  Capability in play and pawn on the William of Modena card.
- **`legate_move`** — `args.locale_id`. Option 1: move pawn to a
  Friendly Locale. Pawn stays on map; uses up the once-per-segment
  Legate option.
- **`legate_use`** — `args.sub_option` ∈ {`2a`, `2b`, `2c`},
  `target_lord`. Uses the Legate's once-per-segment option.
  - 2a: at Seat of Ready Lord — auto-Muster without Fealty roll.
  - 2b: at Seat of Lord on Calendar — slide cylinder 1 box LEFT.
  - 2c: at Friendly Locale with any Lord — that Lord performs an
    immediate extra Muster using full Lordship.
  After USE, pawn returns to William of Modena card.
- **`legate_skip`** — explicitly do nothing in 3.5.1.
- **`veche_action`** — `args.option` ∈
  {`A`, `B`, `C`, `D`, `sea_trade`, `skip`}.
  - A: SLIDE LEFT (cost 1 VP) — slide one Russian Lord cylinder 2
    boxes LEFT (2E correction; PAC's "1 box" is obsolete).
  - B: AUTO-MUSTER (cost 1 VP) — `args.target_lord`, `seat`. Aleksandr
    can ONLY enter via Option B.
  - C: EXTRA MUSTER (cost 1 VP) — `args.target_lord`. Lord must be at
    a Friendly Locale and not Besieged. Resets the recipient's
    `lordship_used` so a follow-up extra Muster uses full Lordship.
  - D: DECLINE (gain 1 VP) — slide Aleksandr/Andrey cylinders (those
    that are Ready) to 1 box RIGHT of Levy. If both are Ready, both
    must be slid; only one VP marker is gained regardless.
  - `sea_trade`: `args.card_id` ∈ {`R8`, `R9`}. Adds Coin to Veche
    box (R8 = 1 Coin; R9 = 2 Coin in non-Winter). Does NOT consume
    the once-per-segment slot. Blocked when Novgorod / Lovat / Neva
    Conquered as applicable.
  - `skip`: pass.

## System actions

- **`system_setup_complete`** — drop scenario-setup `setup_transport_choice`
  PendingDecisions (Q-001) so Phase 2 Levy mechanics can proceed
  without the Phase 1 residue.

## Phase 3a: Campaign-phase actions

### 4.1 Plan

- **`plan_add_card`** — `args.card` is a Mustered own-side Lord id or
  `"pass"`. Each Lord can appear up to 3 times in a side's Plan
  (matching the 3 Command cards per Lord). Plan size by season:
  Summer 6, Rasputitsa 5, Early/Late Winter 4.
- **`finalize_plan`** — mark this side's Plan complete. When both
  sides finalize, harness advances `campaign_step` to `"command"`.

### 4.2 Activation loop

- **`command_reveal`** — reveal the top Command card of the active
  side. Pass cards / Lord-not-on-map cards auto-pass per 4.2.3.
  Lord cards set `actions_remaining = COMMAND_RATING`.
- **`end_card`** — voluntarily end the active Command card before
  exhausting actions; transitions to 4.8.
- **`fpd_resolve`** — 4.8 Feed/Pay/Disband for the active side. Run
  T then R after each Command card. Auto-feeds MOVED_FOUGHT Lords
  (own provender first, then loot, then sharing from co-located
  own-side Lords); unfed Lords lose 1 box of Service. Then runs the
  4.8.2 at-limit Disband (count from NEXT box during Campaign 2E).
  Then removes MOVED_FOUGHT markers.

### 4.7 Simple Commands

- **`cmd_tax`** — 4.7.4. Active Unbesieged Lord at own Seat; +1 Coin;
  consumes entire card.
- **`cmd_forage`** — 4.7.1. 1 action; +1 Provender. Locale not
  Ravaged; at Friendly Stronghold OR Summer.
- **`cmd_ravage`** — 4.7.2. 1 action default; 2 actions if Unbesieged
  enemy Lord adjacent (2E). Locale must be enemy territory, not
  Conquered, not Friendly to active side, not already Ravaged. Adds
  own-color Ravaged marker (+0.5 VP), +1 Provender, and +1 Loot if
  non-Region.
- **`cmd_pass`** — 4.7.5. Forfeit unused actions; ends card.
- **`cmd_sail`** — 4.7.3. Entire card. Active Unbesieged Lord at a
  Seaport; non-Winter; destination Seaport free of Unbesieged enemy
  Lords. `args.group` co-Sails together; sailing to an Unbesieged
  enemy Stronghold places a Siege marker.

### 4.6 Supply

- **`cmd_supply`** — `args.sources` is a list of
  `{locale_id, route, transport}`. Each entry adds 1 Provender (cap
  8). Validates: source eligibility (own Seat, or Russian Novgorod /
  Teutonic any-Seaport via Ships), Way-type compatibility (Boats =
  Waterways, Carts = Trackways, Sleds = any), seasonality (Carts
  Summer only; Sleds Winter/Rasputitsa; Boats/Ships not Winter),
  route adjacency, no enemy block on intermediate locales (unless
  the enemy is Besieged there). 2E rule: 1 Transport per Provender
  per Way of each Route.

### 4.9 End Campaign

- **`end_campaign_resolve`** — runs T-then-R. Per side: 4.9.1 Grow
  (only end-of-Rasputitsa, halve enemy Ravaged markers rounded UP),
  4.9.4 Wastage (per Lord, discard 1 if any Asset count >1 OR >1
  this-lord-capability), 4.9.5 discard This-Campaign events. After
  R, runs 4.9.2 game-end check (if box >= span_end_box -> game over),
  4.9.3 Plow & Reap (end-of-Summer Carts -> Sleds; end-of-Late-Winter
  Sleds -> Carts; halve rounded UP), advances Calendar marker, flips
  to Levy.

## Phase 3b: March, Approach, Battle

### 4.3 March

- **`cmd_march`** — `args.lord_id`, `args.to` (adjacent locale via a
  Way), `args.group` (optional list of co-Marching own-side Lords).
  Costs 1 Unladen action / 2 Laden actions per Locale. Begin Siege
  if entering Locale of an Unbesieged enemy Stronghold without an
  enemy Lord (4.3.5). If destination has enemy Lord(s), enter Approach
  state via `combat_pending`; defender must respond.
  - Laden definition (4.3.2): any Loot, OR Provender count >
    2 * usable Transport count for the season.

### 4.3.4 Approach response

The defender must choose exactly one of:

- **`avoid_battle`** — `args.to` (adjacent friendly locale free of
  enemy Lord/Stronghold/Conquered marker). Requires every defender
  to be Unladen.
- **`withdraw`** — into a Friendly Stronghold at the Battle Locale.
  Capacity by Stronghold type (Commandery/Fort/Castle 1; City/
  Bishopric 2; Novgorod 3). Places a siege marker.
- **`stand_battle`** — engage in 4.4 Battle. Resolves the battle
  immediately and applies Aftermath.

### 4.4 Battle resolution

Run via `stand_battle`. The harness simulates rounds in initiative
order:

1. Archery — defender, then attacker.
2. Melee Horse — defender, then attacker.
3. Melee Foot — defender, then attacker.

Hits per Strike step are computed from the Forces table
(`src/nevsky/data/static/forces.json`) summed across the side's
participating Lords' active units, rounded up at step end. Hits are
distributed to the opposing Lord's units; each Hit triggers a
Protection roll (Armor / Evade / Unarmored / Serfs=none). Failed
Protection rolls Rout (and remove) the unit.

Battle ends when one side has no active units (or after a stalemate
threshold). Aftermath:

- Loser Lords with zero remaining units are permanently removed
  (1.5.1); their Assets (except Ships) transfer to a winner Lord.
- Other loser Lords Retreat (attackers back to from-locale; defenders
  to a clear neighbor); each rolls 1d6 and shifts Service marker
  LEFT by `ceil(roll/2)` boxes (4.4.3 table). Their Assets (except
  Ships) transfer to a winner Lord.
- All participating Lords are marked MOVED_FOUGHT; the active
  Command card ends and 4.8 Feed/Pay/Disband begins.

Phase 3b deliberately defers Phase 4 capability effects (Walls in
Battle by Event, LUCHNIKI/STRELTSY/BALISTARII archery extensions,
HALBBRUEDER Armor +1, WARRIOR MONKS rerolls, RAIDERS, CONVERTS,
DRUZHINA Command +1, Russian archery special rounding, Pursuit on
Concede, Lieutenants 4.1.3, full Reposition with Flanking).

## Phase 3c: Siege, Storm, Sally

State adds `Lord.in_stronghold` (default False). A Lord is BESIEGED
when `in_stronghold=True` AND the Locale has `siege_markers > 0`.
Lords at the same Locale who are NOT inside the Stronghold are the
besiegers. `withdraw` (4.3.4) sets `in_stronghold=True`.

### 4.5.1 Siege

- **`cmd_siege`** — entire card. `args.lord_id` (active Lord).
  - Surrender check: if no Besieged Lords inside, roll 1d6; if
    roll <= siege_markers, the Stronghold is Conquered (place
    Conquered marker; +VP per Strongholds table; if Novgorod, all
    Veche Coin removed per 1.3.3 -- not awarded as Spoils since
    this is Surrender, not Sack).
  - Siegeworks check: if besieging Lords at locale >= Stronghold
    Capacity, +1 Siege marker (max 4).

### 4.5.2 Storm

- **`cmd_storm`** — entire card. `args.lord_id` (active Lord).
  - Storm rounds run via `battle.resolve_storm`. Single front
    lane (no flanking). Garrison units (per Strongholds table) sit
    alongside defender; Garrison MaA have Archery (-2 target Armor)
    and Melee; Garrison Knights have Melee only.
  - Defender protected by Walls (rolled per Hit, d6 <= walls_max
    absorbs). Attacker protected by Siegeworks (siege_markers as
    Walls range 1..siege_markers).
  - Max 6 Melee Hits per Lord per Round (2E). Archery unlimited.
  - Storm ends when all attackers Rout, all defenders+Garrison
    Rout, OR rounds_completed >= siege_markers (attacker loses).
  - On Sack (defender loses): all Besieged Lords permanently
    removed (1.5.1); Stronghold Conquered (+VP); siege markers
    cleared; Spoils (loot/provender/coin = VP each) awarded to
    attacker[0]. Novgorod special: all Veche Coin to attacker[0].
  - On attacker loss: Storm ends; siege continues; no Spoils.
  - Trade Routes cannot be Stormed (`no_storm` flag).

### 4.5.3 Sally

- **`cmd_sally`** — entire card. `args.lord_id` (Besieged Lord).
  - Sallying side does NOT benefit from Walls or Garrison.
  - Defenders (Besiegers at the same locale) receive Siegeworks
    as Walls. Phase 3c uses the Battle resolver for the engagement
    (Walls/Siegeworks integration is a Phase 3c simplification).
  - Sallying loss: Sallying Lords stay Besieged inside; siege
    markers reduced to 1 (RAID).
  - Sallying win: Besieging Lords retreat (or are removed if no
    forces); siege markers cleared (siege lifted).

## Phase 4a: Combat & Command Capabilities

`src/nevsky/capabilities.py` provides `has_lord_capability(state, lord, name)`,
`has_side_capability(state, side, name)`, and `any_capability(state, lord, name)`
keyed off `cards.json` capability_name.

### Combat-mod capabilities (applied at battle resolution)

- **Halbbrueder** (T9/T10, this-lord): owner's Sergeants and Men-at-Arms
  gain Armor +1 for Rout rolls (4.4.2). Affects Rout, NOT Loss.
- **Warrior Monks** (T7/T15, this-lord): owner may reroll 1 failed
  Knights Armor roll per Strike step (Phase 4a applies per Hit-call as
  approximation; per-step single-reroll budget is a Phase 4 refinement).
- **Luchniki** (R1/R2, this-lord): owner's Light Horse and Militia gain
  Archery (x1/2 each).
- **Streltsy** (R3/R13, this-lord) and **Balistarii** (T4/T5/T6, this-lord):
  owner's Men-at-Arms gain Archery x1/2 with target Armor -2.
- **Trebuchets** (T14, this-lord): if any Unrouted Lord on the storming
  side has it, defender Walls in Storm/Sally are reduced by 1 (min 0).

### Command-rating modifiers (applied at `command_reveal`)

`_effective_command_rating(state, lord)` aggregates these +1 bonuses:

- **Druzhina** (R5/R6, this-lord): +1 if Lord has at least 1 Knights unit.
- **House of Suzdal** (R11, this-lord): +1 while Aleksandr AND Andrey
  are both on the map.
- **Treaty of Stensby** (T1, side-wide): +1 for Heinrich and Knud&Abel
  only.
- **Ordensburgen** (T12, side-wide): +1 if Teutonic Lord starts at
  one of his own primary Seats (Commandery).
- **Archbishopric of Novgorod** (R15, side-wide): +1 if Russian Lord
  starts at Novgorod.

### Capability-driven Commands

- **`cmd_stone_kremlin`** (R18): entire-card action. Active Russian Lord
  with Stone Kremlin tucked may mark his Locale's `walls_plus_one` if
  it is a Russian Fort/City/Novgorod. Walls 1-3 -> Walls 1-4 in Storm.
  Marker is removed if the Stronghold is Sacked. Cap: 4 markers in play.
- **`cmd_stonemasons`** (T17): entire-card action + 6 Provender. Active
  Teutonic Lord with Stonemasons tucked, Unbesieged at a Russian
  Fort/Town in Rus, may build a Teutonic Castle marker (replaces the
  Fort/Town). Removes any Walls +1. Cap: 2 Stonemasons Castles per game
  (tracked via `meta.special_rules.stonemasons_castles_built`).
- **`cmd_muster_serf`** (R4 Smerdi): 1 Command action. Active Russian
  Lord Unbesieged in Rus may Muster 1 Serf. Total Serfs in play across
  all Russian Mustered Lords cannot exceed 6 (Smerdi pool cap).

## Phase 4b: Economy & Movement Capabilities

### Per-card flags

`Lord.first_march_used_this_card` and `Lord.raiders_used_this_card`
are reset at `command_reveal` so per-card capability budgets work.

### Capability hooks

- **Converts** (T3, this-lord): the FIRST March of each Command card
  costs 0 actions when the Marching group includes any Lord with
  Converts AND any Lord with Light Horse. Implementation: cmd_march
  detects this and overrides `cost = 0`.
- **Raiders** (T2 / R12 / R14, this-lord): new action
  `cmd_raiders_ravage` (1 action). Adjacent target Locale; standard
  Ravage eligibility (enemy territory, not Conquered, not Friendly,
  not already Ravaged). T2 (Teutonic): Trackway only, once per card,
  +Loot if non-Region. R12/R14 (Russian): any Way, multiple per card,
  no Loot.
- **Ransom** (T16 / R7, side-wide): `apply_ransom(state, removed_lord,
  killer_side, locale_id)` is called in Battle and Storm Aftermath
  paths when an enemy Lord is permanently removed; if the killer side
  has Ransom in play, +Coin equal to the removed Lord's Service rating
  goes to a friendly Lord present at the same locale.
- **Cogs** (T18, this-lord) / **Lodya** (R16, this-lord):
  `effective_ship_count(state, lord_id)` and
  `effective_boat_count(state, lord_id)` apply doublers. R9 Baltic
  Sea Trade ship comparison uses these. Sail / Supply ship validation
  is left for Phase 4 refinement.
- **Hillforts of the Sword Brethren** (T8, side-wide): `fpd_resolve`
  picks one Unbesieged Teutonic Lord in `crusader_livonia` and skips
  Feed for that Lord (he records `hillforts_skipped: True` in the
  feed log).
- **Veliky Knyaz** (R17, this-lord): `cmd_tax` is replaced with a
  Veliky-Knyaz-aware variant. When the active Lord has the capability,
  Tax adds the standard +1 Coin AND adds 2 of the chosen Transport
  type (`args.transport_type`, default cart) AND restores Mustered
  Forces back up to starting + Mustered Vassal totals. Ship transport
  requires `ships_authorized`.

## Phase 4c: Event triggers

`src/nevsky/events.py` provides resolvers for AoW events.

### State extensions

- `Meta.block_lords_this_levy_t` / `_r`: list of Lord ids forbidden
  to use Lordship or be Mustered this Levy (R11 / R17). Cleared on
  Levy -> Campaign transition.
- `Meta.lordship_bonus`: dict[lord_id, int] of currently active
  Lordship +2 bonuses from Hold events. Used by `_spend_lordship` to
  raise the budget. Cleared on Levy -> Campaign transition.

### Immediate event resolvers (called by `aow_implement_card`)

- T1 Grand Prince favors a son
- T2 Torzhok (Domash assets OR Veche Coin)
- T11 Pope Gregory issues indulgences (+ adds Crusade capability)
- T12 Khan Baty
- T14 Bountiful Harvest (Teutonic): remove Russian Ravaged
- T15 Mindaugas: place Teutonic Ravaged in Rus within 2 of Ostrov
- T18 Swedish Crusade (Vladislav AND Karelians shift)
- R9 Osilian Revolt
- R10 Batu Khan
- R11 Valdemar (this-levy block + shift)
- R12 Mindaugas (Russian): place Russian Ravaged in Livonia within
  2 of Rositten
- R14 Prussian Revolt
- R15 Death of the Pope
- R16 Tempest (with Cogs awareness)
- R17 Dietrich von Grueningen (this-levy block + shift)
- R18 Bountiful Harvest (Russian)

Tier 2 immediate events (battle-context: Bridge / Marsh / Ambush /
Hill / Field Organ / Raven's Rock) and Tier 3 (Vodian Treachery,
Heinrich Sees the Curia) return a deferred placeholder for now.

### Hold events (played via `aow_play_hold`)

- **`aow_play_hold`** — `args.card_id` (must be in side's `holds`),
  plus event-specific args. The card is consumed (moved to discard).
  Phase 4c implements R3 Pogost; other holds return a deferred
  placeholder.
- **`aow_lordship_plus_2`** — `args.card_id`, `args.lord_id`,
  `args.mode` ∈ {`lordship`, `shift`}, plus `args.direction` for
  shift mode. Targets per card:
  - T7 Tverdilo: Hermann or Yaroslav (shift 2 / +2 Lordship).
  - T8 Teutonic Fervor: Rudolf only.
  - T17 Dietrich von Grueningen: Andreas or Rudolf.
  - R8 Prince of Polotsk: any Russian Lord (shift 1 / +2 Lordship).
  - R13 Pelgui: Vladislav or Karelians.
  Card consumed; the Lordship bonus persists in
  `meta.lordship_bonus` until Levy ends.

### Block enforcement

`_spend_lordship` and `muster_lord` reject if the Lord is in the
side's `block_lords_this_levy_*` list (R11 / R17 effect). The block
list is cleared at the Levy -> Campaign transition.

## Activation loop semantics (4.2)

When `command_reveal` reveals a Lord card, that Lord becomes the active
Lord with `actions_remaining = effective_command_rating(state, lord)`.
He retains the activation slot (no T/R alternation) until his card
ends. A card ends when:

- He calls `cmd_pass` (forfeits remaining actions).
- He runs out of actions (the next action attempt fails with
  `lordship_exhausted` / `insufficient_actions`).
- He performs an entire-card action: `cmd_tax`, `cmd_sail`,
  `cmd_siege`, `cmd_storm`, `cmd_sally`, `cmd_stone_kremlin`,
  `cmd_stonemasons`.
- A March triggers an Approach + Battle that resolves to a state where
  the Battle handler ends the card (`cmd_march` always ends the card
  when an Approach occurs).
- He calls `end_card` voluntarily.

After the card ends, the harness sets
`campaign_turn.in_feed_pay_disband = True`. Both sides must call
`fpd_resolve` (T then R) before the next reveal. Once both FPD
resolves, `next_to_reveal` flips to the other side (alternation per
4.2). If the other side's plan is empty but the same side still has
cards, the same side reveals again.

A typical agent loop:

```
while state.meta.campaign_step == "command":
    if state.combat_pending is not None:
        # Approach response (avoid_battle / withdraw / stand_battle).
        ...
    elif state.campaign_turn.in_feed_pay_disband:
        for s in ("teutonic", "russian"):
            if (s == "teutonic" and not state.campaign_turn.fpd_completed_t) \
               or (s == "russian" and not state.campaign_turn.fpd_completed_r):
                do(state, {"type": "fpd_resolve", "side": s, "args": {}})
    elif state.campaign_turn.actions_remaining == 0:
        do(state, {"type": "command_reveal",
                   "side": state.campaign_turn.next_to_reveal, "args": {}})
    else:
        # Active-Lord choice.
        # Inspect legal_moves(state); pick one of the cmd_* options or end_card.
        ...
```

## Spoils recipient (4.4.5)

`stand_battle` and `cmd_storm` accept an optional `args.spoils_recipient`
(a winner-side own-Lord id) to direct Spoils to a specific Lord. The
recipient must be at the Battle Locale and on the winning side; if
not, the harness silently falls back to `winner_lords[0]` (or
`attackers[0]` for Storm).
