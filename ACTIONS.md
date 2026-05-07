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
