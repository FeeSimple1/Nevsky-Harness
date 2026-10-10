# Long-campaign fixes — October 10, 2026

Base: `394de473fd886f3f5f898dc2d0dcfb3b517253cb`.
Reproduction source: `playtest/crusade-long-20261010`, report commit
`34617cf46c98df067e7e918b7a39bc75f24e51e1`.

## Changes

- Vodian Treachery rejects an already Teutonic-conquered Fort without
  consuming the Hold or changing state. A first conquest clears the Siege,
  refreshes the Calendar victory marker, and preserves the 17.5-VP cap.
- The owner's legal-action menu exposes Pogost, Vodian Treachery, Heinrich
  Sees the Curia, and all five Lordship-or-shift Holds. Deterministic probes
  validate optional choices without changing the live state or its dice.
  Battle/Storm Holds remain in their existing response channels.
- A shared printed-plus-event Lordship budget controls both expenditure and
  enumeration, including the final two expenditures after a +2 Hold.
- Veche C and Legate 2c expose the granted recipient's immediate extra
  Muster, not other Lords' actions. A Lord who arrived in ordinary Muster
  may spend this grant, but still cannot act in his arrival Muster or in
  Call to Arms without a grant.
- Owner-specific interruption menus expose only that owner's any-time Holds
  during the opponent's activation. Interruptions do not transfer the
  activation. The helper records their actual actor and stops automatic
  advancement at optional interruption windows.

No save-schema change, new game variant, or engine strategy was introduced.

## Using interruption choices

The play helper accepts `nv.show("russian")` and
`nv.apply(index, side="russian")` to inspect/play a Russian interruption
while the activation remains Teutonic (and conversely). Decline an
interruption by applying the ordinary active-side action manually.

The CLI's `briefing`, `actions`, and `apply` commands accept `--side` for the
same purpose. Raw-JSON Hold actions remain supported.

## Regression coverage

`tests/test_long_campaign_fixes_20261010.py` contains 38 cases covering the
eight original saved-position reproductions, both factions' extra Musters,
new-arrival restrictions, all five Lordship Holds, T13 recipients, opposing
Hold interruptions, terminal guards, the helper, and complete replay.

The fixtures omit append-only history but preserve the original board,
Calendar, cards, RNG state, and decision fields. The replay fixtures retain
all 1,322 actions of the first game and all 1,685 actions of the full
16-turn game, including setup. Both replay tests check their recorded
winners, end boxes, and save/reload equality.

Rules basis: the repository's Arts of War, Call to Arms, and Stronghold
references; the pre-existing authoritative action handlers. The repair
restores choices hidden by the menu rather than changing the recorded moves.


## Additional property-test repair

Exercising the newly visible bonus actions exposed stale end-of-Levy
accounting: the bonus was cleared at Campaign entry, but its completed
expenditure was not. The same boundary now clears both, as the state model's
per-Levy counter contract requires. Four additional regressions cover both
factions' boundary transitions and the observed Watland seed 371 and Pleskau
seed 163 failures. Existing property assertions remain unchanged.
