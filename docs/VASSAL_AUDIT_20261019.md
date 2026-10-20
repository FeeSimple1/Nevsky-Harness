# Nevsky Vassal component audit — 19 October 2026

Base: `b0084f1` on `main`. Target: Nevsky **second edition**, as required by
`BRIEF.md`. The Vassal comparison found three component-data defects and an
associated loss of player choice in the LLM interface. All are corrected.

## Sources and authority

- [Vassal module listing](https://vassalengine.org/library/projects/Nevsky).
- [Nevsky 2.1 module](https://obj.vassalengine.org/images/e/e2/Nevsky_2.1.vmod),
  published 28 April 2022; 93,335,849 bytes; SHA-256
  `efe44cf19d75e528b3270ceae1a125ef8880f2c94559ecd2ef37d8b99e0c4c57`.
  The download matched the listing's checksum. Inspected `buildFile.xml`,
  the component images and player aids, and all six bundled scenario saves.
- [GMT second-edition product/resources page](https://www.gmtgames.com/p-1009-nevsky-teutons-and-rus-in-collision-1240-1242-2nd-edition.aspx).
- Repository `reference/Nevsky_Second_Edition_Changes.txt`, dated 7 June 2023,
  and the relevant Lords, Map, Scenario, and Strongholds references.
- Repository `sources/NevskyRules_Second_Edition.pdf`, especially 1.5.2,
  2.1.2, 3.4.1–3.4.2 and scenario setups. The printed mat determines initial
  Forces/Assets; each Transport (any) piece is a player choice.
- Repository `sources/Nevsky_PLAYBOOK-FINAL.pdf`, p. 3, corroborates Domash's
  four starting Transport with a mixed three-Sled/one-Ship example. This is
  an example, not an independent override of the rules.

The module predates second edition. It is a component cross-check, not a
rules-enforcing reference engine. The Vassal listing explicitly warns that
players must enforce the rules. Module 2.1's change list addresses hidden-card
rollovers, not second-edition rules. Printed artwork, module automation, and
second-edition changes were considered separately.

## Confirmed corrections

| Item | Before | Correct value / behavior | Evidence and impact |
| --- | --- | --- | --- |
| Domash's initial Assets | 1 Transport, 1 Provender | **4 Transport, 4 Provender** | `images/Mat_R_Domash.png`, Russian Lords aid, and `Mat Domash` creates Provender Marker 4. Restores his logistics at setup and later Muster. |
| Gavrilo's initial Transport | 1 | **2**, independently chosen | `images/Mat_R_Gavrilo.png` and Russian Lords aid. Applies at setup and later Muster. |
| Mstislavich Partisans' Service | 2 | **1** | `images/Teuton Vassal Yaroslav-Mstislavich Partisans.png`, Teutonic Lords aid, and `Service Yaroslav 1` prototype. Corrects advanced Vassal Service placement; still supplies two Militia. |
| Transport choices in LLM play | Missing from `legal_moves`; both startup wrappers silently confirmed all choices | Every pending slot has confirm/override actions during Levy. Startup preserves choices unless `confirm_transports=True` is requested. | Exposed while checking the corrected Transport quantities through the public action interface. All four allowed types remain selectable, including mixed loads. |

The three numeric errors were also present in `reference/Nevsky_Lords.txt`.
That transcription is corrected alongside JSON so future changes cannot
reintroduce the same errors by copying the reference. None of these numeric
differences appears in the second-edition change list; the printed mats/counter
and aids agree. This is a transcription correction, not a new rules ruling.

The existing Q-001 default-and-override policy remains: proceeding with a
normal Levy action accepts non-hotspot defaults. The initial helper display
now offers the player the choices first. Explicit bulk acceptance remains
available. The default table uses four Sleds for Domash's winter starts and
two Carts for Gavrilo's listed summer starts. Each can be changed separately.

Newly created games and future Musters use the corrected quantities. Existing
saved positions are **not** retroactively credited with assets: it would be
unsafe to infer how much they have already spent or lost. Old replay outcomes
that depend on these starting resources may therefore differ in fresh games.

## Comparison coverage

| Area | Checked | Result |
| --- | --- | --- |
| Map inventory | All 53 named Locales, their printed types, eight seaports and four Commanderies | No missing map locations; documentation incorrectly said 51. Corrected the totals to 7 Danish, 17 Livonian, 29 Russian. |
| Ways | 51 Trackways and 34 Waterway adjacencies, visually traced against the module map; shared lake/river junctions interpreted using rule 1.3.1 and the Map reference | No graph correction identified. The module itself does not supply a legal movement graph. |
| Lords | All 12 printed ratings, starting Forces, fixed Assets, Transport quantities and Seats | Corrections above; Hermann/Knud second-edition adjustments retained. |
| Vassals | All 34 printed vassal entries, forces and Service ratings compared to Lords data | Partisans Service corrected. Several module automation values disagree with its own artwork; see below. |
| Cards | 36 numbered AoW identities and event/capability pairings, six blanks; 42 Command cards (three of each Lord and three Passes per side) | Inventory and pairings agree. This is not an exhaustive independent verification of every event resolver. |
| Scenario setup | All six bundled saves: cylinders, Lord Service markers, conquest/ravage/castle markers, Veche and starting VP | Matches after the documented edition changes below. The module has no Quickstart setup to verify. |
| Second-edition strongholds | Castle/Bishopric garrison reductions against Changes Summary | Harness already correct. Corrected misleading metadata claiming Commanderies were not Strongholds; runtime already uses their Castle/Bishopric types. |

### Scenario differences that must remain

- **Pleskau:** second edition removes all blank AoW cards before play.
- **Watland:** Vassal has Vladislav on Calendar box 4; second edition starts him
  Mustered at Ladoga, Service box 6. Retain the updated victory requirement.
- **Return of the Prince:** Vassal places Gavrilo in box 13; second edition
  places him in box 9.
- **Nicolle variant:** checked its separate setup; no additional position
  discrepancy identified.
- **Peipus:** positions and markers agree; printed starting-asset corrections
  still apply to the Lords as above.
- **Crusade on Novgorod:** Vassal places Andreas in box 1; second edition uses
  box 3 and explicitly retains blank AoW cards.

Hermann and Knud each replace one initial Men-at-Arms with Militia in second
edition; Knud also gains one Coin. These are already correct in the harness.
The 2022 aid's restriction on who may Muster Andrey is also obsolete.

### Module automation discrepancies not imported

The module is not internally consistent. Examples from `buildFile.xml`:

- `Service Knud 3` is the Estonian Auxiliaries counter but creates a Knight and
  Men-at-Arms; its artwork/aid show Light Horse and Militia. Harness is correct.
- `Service Aleksandr 4` and `Service Aleksandr 5` encode Service 4, whereas the
  Rostov/Yaroslavl printed aid specifies 3. Harness is correct.
- `Service Andrey 3` encodes Service 3 for Suzdal; the printed aid specifies
  4. Harness is correct.
- `Stats Aleksandr` contains a Fealty value even though the printed Lord has
  none and only the Veche may Muster him. Harness correctly uses no Fealty.
- Rudolf's two different vassal prototypes reuse `VassalID=Rudolf2`; the
  harness's distinct IDs are retained.

## Reproduction and validation

Download the pinned module separately; it and its artwork are not added to
the repository. Run the repeatable machine-readable subset with:

```sh
PYTHONPATH=src python scripts/audit_vassal_components.py /path/Nevsky_2.1.vmod
PYTHONPATH=src python -m pytest tests/test_vassal_component_audit.py -q
PYTHONPATH=src python -m pytest -q
```

`reports/vassal_20261019/component_checks.json` records the module hash,
inventory counts and zero unexplained differences for the automated subset:
locale identifiers, card counts/IDs, all Lord Service/Lordship/Command ratings,
starting Forces and fixed Assets after explicit second-edition adjustments.
The visual and scenario checks above are not misrepresented as automated tests.

The baseline full suite passed **1,884 tests** before edits. New regressions
exercise corrected Assets at setup and Muster, all allowed choices for each
new slot, mixed transport overrides, advanced/basic vassal behavior and both
interactive startup APIs. Existing helper fixtures that intentionally begin
after setup now explicitly request `confirm_transports=True`.

The Crusade replay fixture now contains **1,743 actions**. The only added action
is an explicit Russian `end_card` after Hermann's box-2 Avoid to Lettgallia:
Gavrilo's corrected second Transport reduces the preceding March cost, leaving
one Command unused. The replay keeps the same winner and score (Teutonic 1,
Russian 0.5), all 87 save/reload round trips, and the original terminal-state
and card-conservation assertions. No recorded action was removed or bypassed.

Final validation: **1,900 tests passed**, including the complete corrected
Crusade replay, the Return of the Prince interface replay, and the bounded
randomized action/invariant checks. The pinned Vassal comparison completed
with **zero unexplained differences** in its documented automated subset.
