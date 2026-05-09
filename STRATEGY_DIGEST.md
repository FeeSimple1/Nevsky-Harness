# Nevsky Strategy Digest

**Status: ADVISORY ONLY.** The LLM consumer playing through this
harness MAY consult this document. The harness does not load it,
parse it, or enforce any of it. The LLM is free to disagree with
any section, ignore the document entirely, or play from first
principles. Per `BRIEF.md` "No Agent in the Harness", this digest
is suggestions a consumer can use if they agree — not directives.

When suggestions conflict with the rules of play, the rules govern.
When suggestions conflict between sources, the LLM weighs them.

## Sources

- `reference/Nevsky_Strategy.txt` — primary strategy reference
  distilled from the GMT Playbook, Volko Ruhnke design notes, and
  Volko's InsideGMT articles. Authoritative on tactical advice; this
  digest summarises and updates it with smoke-driver findings.
- `reference/Nevsky_Arts_of_War_Reference.txt` — designer-clarified
  Tips paragraphs for each Capability and Event. Read when picking
  Capabilities or playing Hold events.
- Statistical smoke results from rounds 13, 22 of this project
  (`SMOKE_TEST_FINDINGS.md`).
- Strategic discussions captured during development (esp. Russian
  early-defense framing and the played-case-vs-worst-case
  reconciliation).


# 1. Core Priors That Govern Every Decision

## 1.1 The Calendar is the real opponent

Every Lord's Service marker is a doomsday clock. Work backward from
each Lord's Disband box and ask: what do I get out of him before he
goes home? A Lord who Disbands in a Friendly Locale with Coin or Loot
to spare was wasted; a Lord who Disbands at the end of a successful
Sack was used correctly.

## 1.2 Logistics dictate geography

Forces and Assets exist on Lord mats; what you can do with them
exists on the map. The bridge is Transport, which only works in
certain Seasons:

- **Sleds**: Winter only, all Ways.
- **Carts**: Summer only, Trackways only.
- **Boats**: Rasputitsa and Summer, Waterways only.
- **Ships**: Rasputitsa and Summer, Seaports only (and Novgorod for
  Russians).

Rasputitsa is most restrictive: no Trackway transport at all.

## 1.3 Provender is the currency of movement

A Lord with 1-6 units consumes 1 Provender per Campaign at Feed; 7+
consumes 2. The seventh Vassal you Levied "for the muscle" is a
permanent supply tax. Levy only the units you need for the mission
ahead.

## 1.4 The Friendly Locale Test

End every Campaign asking, of each Lord: where will he be standing,
and is it Friendly to him? Friendly = his side's home territory or a
Stronghold his side has Conquered. Lords need Friendly ground to
Muster, Pay with Loot, or Forage outside Summer. Russian Veche Coin
is the great exception — it shifts any non-Besieged Russian Lord's
Service from afar.

## 1.5 Pay > Disband

Loot is easier to obtain than Coin (especially for Teutons), so plan
campaigns ending with Lords in Friendly Locales holding Loot. Coin
travels between co-located Lords (including via Sharing); Veche Coin
travels anywhere.

## 1.6 Ravage is not free anymore (2E)

Ravage costs TWO actions if an Unbesieged enemy Lord is adjacent.
Force the defender to leave first, or accompany your raider with a
screening Lord.

## 1.7 Ravage decays (2E)

At end of each Rasputitsa (turns 8 and 16), the side whose territory
was Ravaged removes Ravaged markers down to half (round up). Ravage
VP earned in the first half-year erodes if you don't keep ravaging.
Ravage is tempo, not a savings account.

## 1.8 Storm is capped per Lord (2E)

Storm Melee is capped at 6 Hits per Lord per Round. A single super-
Lord can't one-shot a City. Think in terms of multiple Lords for big
walls, or sieges + waiting.

## 1.9 "No" cards are gone forever when drawn as Events (2E)

Each side has three "No Event/No Capability" cards. Drawing one as
an Event removes it from play. The Event deck thins; late-game
Events are richer than early-game. Pleskau removes them at start;
the full Crusade scenario keeps them.


# 2. Combat Math (from Smoke)

## 2.1 Battle defender bias

Balanced parity, equal counts, no Capabilities:

| Lords | Defender win % | Avg rounds |
|------:|---------------:|-----------:|
|   1v1 |          ~84% |       ~2.5 |
|   2v2 |          ~89% |       ~2.8 |
|   3v3 |          ~91% |       ~3.0 |
|   4v4 |          ~96% |       ~4.0 |

The bias grows with Lord count because per-step Hit volume scales:
the defender's first-strike removes a larger share of attacker's
next-step output. Treat the 96% number as the conditional probability
that "if a fair 4v4 Battle is fought, defender wins" — not as the
probability you should fight.

## 2.2 Composition flips the bias

- **Knight-heavy attacker vs balanced defender**: ~64% attacker win
  at 1v1. Knights (Melee 2, Armor 1-4) are the single biggest
  counter-lever.
- **Light-horse-heavy attacker**: defender wins 100%. All-mounted
  light cavalry is the worst attack composition.
- **Balanced attacker vs militia-heavy defender**: ~100% attacker.
  Militia (Unarmored, no default Archery) is poor defense.
- **Balanced vs Asiatic-heavy defender**: ~92-100% attacker. All-
  archery defense doesn't break a melee push.

## 2.3 Lord-count dominates composition when outnumbered

2v1 = ~99% for the bigger side regardless of composition. Don't
fight outnumbered if you can refuse the engagement.

## 2.4 Storm bias

- Lord-defended Stronghold: 96-100% defender win.
- Garrison-only, 1 siege marker (2 rounds): ~50% defender — coin
  flip.
- Garrison-only, 3 siege markers (4 rounds, full siege): ~20%
  defender — attacker grinds the garrison.

By Stronghold (averaged): Bishopric (walls 4 + 3-unit garrison
including 1 Knight) > Castle > City/Novgorod > Fort.

## 2.5 Reconciliation: worst-case vs played-case

The 96% defender bias measures the engine's mechanical answer when a
Battle is forced on equal terms. The rules' release valves — Avoid
Battle (4.3.4), Withdraw (4.3.4), Concede (4.4.2 NEW ROUND), Forced
March refusal — exist precisely so equal-terms engagement is rare.
Played reality is filtered by attacker selection: an attacker who
sees 96% defender win against him chooses not to engage. The 96%
number is the worst-case outcome of a bad attacker decision; the
strategic question is how often that decision arises.

## 2.6 Storm preview interpretation

`vp_forecast` for `cmd_storm` returns expected VP delta = win_prob ×
stronghold_vp. Useful comparator for a single Lord's actions: Storm
expected VP vs Ravage's deterministic +0.5 VP vs other options.


# 3. Russian Strategic Identity: Battle-Avoidant, Not Defensive

The Russian default play is to refuse engagement, not to accept
disadvantageous Battles defensively.

## 3.1 Convert Battle into Siege

Avoid Battle (4.3.4) and Withdraw into Stronghold (4.3.4) are the
rules' tools to refuse a fight. Withdrawing into a Stronghold turns
a threatened Battle into a Siege the attacker has to maintain for
multiple turns. The attacker's Service clock is the lever.

## 3.2 Stone Kremlin (R18)

Walls +1 marker on Fort/City/Novgorod takes Walls 1-3 → 1-4. Pskov
(City) walls 3 → 4 narrows the gap with Bishopric defense. Stack on
Domash to fortify Novgorod / Pskov / Ladoga over multiple turns.

## 3.3 Russian raid economics

R12/R14 Raiders let Russian Light Horse and Asiatic Horse Ravage
adjacent Locales but **take no Loot**. Per the Arts of War Reference
Tips: this Capability "may be used for multiple actions on a single
Command card and allows Ravage of Locales adjacent by land or water
to gain Provender but no Loot." Russian raiding is a VP-denial +
Provender extraction tool, not Coin enrichment.

T2 Teutonic Raiders, by contrast, allows Loot acquisition (once per
Command card).

The asymmetry matters: Russian raids hurt the Teutons via VP and
Supply disruption (Ravaged Locales reduce Forage capacity, 4.6
needs Provender per Way) but don't fill Russian Coin coffers. Black
Sea Trade (R8) and Lodya (R16) are the Russian Coin engines.


# 4. Late-Game Russian Counterattack

Aleksandr arrives via Veche (3.5.2; never by Lord Levy). Andrey
arrives by normal Muster.

## 4.1 Aleksandr's force pile

Static data: 3 Knights + 2 Men-at-Arms starting; 5 Vassals
(Pereyaslavl, Rostov, Yaroslavl + 2 Mongol contingents). Service
rating 6 — longest in the game.

With Druzhina (R5/R6) granting +1 Command when Knights are present,
Aleksandr runs at command 4. Steppe Warriors (R10) gates the Mongol
Vassals; Mongol Asiatic Horse adds 0.5 Archery per unit.

## 4.2 Andrey is parallel

Command 2, lordship 3, service 5. 3 Knights + 2 MaA + 4 Vassals.

## 4.3 Timing window

Crusade-on-Novgorod schedules Aleksandr at calendar box 5 — after
the Teutons have ~4 boxes of operating window. The design assumes
Teutons must score VP early, before Russian counterattack force is
online.


# 5. Teuton Resource Constraint: Provender, Not Coin

Verified starting assets:

| Lord          | Coin | Provender |
|---------------|-----:|----------:|
| Andreas       |    0 |         2 |
| Hermann       |    1 |         1 |
| Heinrich      |    1 |         1 |
| Rudolf        |    0 |         1 |
| Yaroslav      |    0 |         1 |
| Knud & Abel   |    1 |         2 |

Total starting Coin across the roster: 3-4. Total starting Provender:
~8. With 4-6 Mustered Lords, each Feed step costs 4-6 Provender, so
Lords' starting stocks cover 1-2 Campaigns before Forage / Supply /
Levy purchase has to make up the gap. Levy purchase is Coin-gated
and barely affordable.

Forage outside Summer requires a Friendly Stronghold. Russian raids
place Ravaged markers on supply Locales, blocking Forage capacity.

The Teutonic operating window before Wastage thins forces is roughly
2-3 Campaigns. This maps to the historical / scenario timeline:

- 1240 Pleskau-Izborsk
- 1241 Watland (Vod)
- 1242 Peipus

The Strategy reference's "Hermann sitting outside an unconquered
Fort with his Service expiring is the signature Teutonic blunder" is
the exact failure mode.


# 6. The Game-Level Race

Time favours the Russians in raw force terms. Time moderately
favours the Teutons in VP-scoring terms in turns 1-6 (they convert
their head start into Conquests + Ravage VP). The whole game is a
race between Russian force consolidation and Teutonic VP
accumulation.

The harness's tactical findings explain why this race exists: per-
engagement math is decisive enough that whoever has the better
position wins their engagements with very high probability.
Positioning and timing matter more than per-engagement luck. The
strategic levers are Service, Disband, Veche timing, Calendar boxes,
Wastage, and Ravaged markers — all of which are about timing and
position rather than luck.


# 7. Levy Capability Priorities

## 7.1 Teuton high-value Capabilities

- **William of Modena (T13)** — Brings the Legate. Adds a Command
  action when co-located, allows Mustering a Ready Lord without
  Fealty, and provides a free Lord shift during Call to Arms. Worth
  it in nearly every scenario long enough to use him more than once.
- **Treaty of Stensby (T1)** — +1 Command for both Heinrich and
  Knud & Abel. Excellent if either Dane is in play.
- **Ordensburgen (T12)** — Commanderies become extra Seats and
  grant +1 Command when starting at one. Powerful with Andreas
  (Wenden) and any Dorpat-based push.
- **Halbbrueder (T9/T10)** — Sergeants AND Men-at-Arms get Armor +1.
  Pin on Hermann or Andreas if expecting fights.
- **Warrior Monks (T7/T15)** — One Knights re-roll per Archery and
  Melee step. Stack with Halbbrueder on the hammer Lord.
- **Balistarii (T4-T6)** — Lord's MaA gain Archery with -2 enemy
  Armor. The only way Teutons get Battle Archery in the open field.
- **Hillforts of the Sword Brethren (T8)** — Each Feed skips one
  Unbesieged Teutonic Lord in Livonia. Free meals.
- **Cogs (T18)** — Big Sail capacity for the Danes; blocks Russian
  Baltic Sea Trade.

## 7.2 Russian high-value Capabilities

- **Black Sea Trade (R8)** — 1 Coin per Call to Arms unless Lovat
  or Novgorod is Conquered. Take this nearly every game; Coin is
  the Russians' constraint and this directly fixes it.
- **Archbishopric of Novgorod (R15)** — Novgorod becomes a Seat for
  every Russian Lord, +1 Command starting from Novgorod. Stacks
  with the Volkhov-Ladoga waterway spine for Supply.
- **Luchniki (R1/R2)** — Light Horse and Militia get Archery.
  Combined with Streltsy, brutal first-Round Archery before the
  Teutons close.
- **Druzhina (R5/R6)** — +1 Command and Defending Round 1-2 Archery
  not halved. Knights piece on the mat is the only requirement.
- **Steppe Warriors (R10)** — Lets Aleksandr and Andrey muster
  Asiatic Horse. Disbands if discarded; don't drop the card.
- **Stone Kremlin (R18)** — Walls +1 markers. Park on Domash, use
  actions to fortify Novgorod, Pskov, Ladoga over multiple turns.
- **Smerdi (R4)** — Pool of Serfs that re-Muster each campaign,
  even after losses. Cheap arrow-fodder.
- **Lodya (R16)** — Russian Boats count as Ships. Pair with Black
  Sea Trade or hedge against Cogs.
- **Raiders (R12/R14)** — A mounted Lord can ravage one adjacent
  unoccupied Locale per Command card. Extends Domash, Karelians,
  Andrey for VP.


# 8. Plan & Activation Tactics

- Plan stack alternates flips T then R. The card flipped LAST knows
  the most. Lords with high Command (3 actions: Aleksandr, Andreas,
  Hermann, Andrey) are good late-stack pivots.
- Forced-moves go FIRST (Lords whose Service is about to run out,
  who must reach a Friendly Locale, or who must sail before
  Rasputitsa).
- Pass cards are not wasted — they let you do nothing while the
  opponent commits.

## 8.1 March-into-Stronghold ends the card (4.3)

Per the rules, Marching into an enemy-territory Stronghold places a
Siege marker AND ends the Command card. Storm therefore comes on a
SEPARATE Command card. Plan accordingly.


# 9. Per-Scenario Priors

## 9.1 Pleskau (1240, 2 turns, Teutons aggressor)

Per Volko: "Hermann should take Izborsk turn 1 by Storm" — but
remember March-into-Stronghold ends the card, so the Storm comes
turn 2. Plan is: turn 1 Hermann marches Dorpat → Ugaunia → Izborsk
(places Siege; card ends), turn 2 Hermann Storms.

Special victory: +1 VP per enemy Lord removed. Watch Vladislav at
Neva — he can ravage Estonia. Knud & Abel at Reval/Narwia deters
him.

## 9.2 Watland (1241, 5 turns, Teutons aggressor)

2E victory override: Teutons need ≥7 VP AND ≥2× Russian. Otherwise
Russians win, no tie.

- Andreas at Fellin drives on Koporye (R-castle: flipping it gives
  +1 T VP and removes the R-castle).
- Knud & Abel sail to Wesenberg / Reval and threaten down the coast.
- Yaroslav at Pskov holds the south.
- Russians: bring Andrey forward (Veche option A: shift cylinder
  left, or Veche B: auto-Muster), build Black Sea Trade, hold
  Novgorod and the Volkhov spine, Vladislav raids Estonia.

## 9.3 Peipus (1242, 4 turns, Russians aggressor)

Don't fixate on Pskov. Yaroslav alone at Pskov disbands box 14 from
short Service if you SIEGE him so he cannot Tax. Pair with Ransom
(R7) for Coin.

Alternative: ravage past Pskov (Izborsk if free, Ostrov, Velikaya
River) and conquer undefended Teutonic Castles before Rasputitsa.
Levy Raiders Capability for ravaging reach. Levy Boats before
Rasputitsa hits because Sleds/Carts become useless. Ships + Lodya
make Baltic Sea Trade work post-Winter. Spend Veche Coin liberally.

## 9.4 Return of the Prince (1241-1242, 8 turns, Russians aggressor)

Aleksandr starts at Novgorod; Andreas at Koporye. The Russians must
reverse Vodian losses and ideally wreck Teutonic VP before time runs
out. Black Sea Trade early. Stone Kremlin on Domash to harden
Novgorod and Ladoga. Plan a winter campaign to retake Koporye while
Sleds are usable.

The starting position is heavily Teutonic-favoured (T 9 - R 3); the
Russian strategic burden is to claw back ~6 VP.

## 9.5 Crusade on Novgorod (1240-1242, 16 turns, both aggressors)

The full game and the one where Disband / re-Muster cycles pay off.
Lords like the Karelians and Rudolf turn over fast — that's fine,
they re-enter. Andreas and Andrey, if they leave, are gone for a
long time; don't let those two be wasted.

"No" cards are NOT removed when drawn here, so the Event deck stays
slow throughout.

Teutons: early campaigns are yours. Pskov in 1240, Watland in 1241.
Stack VP early because Aleksandr is coming.

Russians: tough early. Veche VP, decline princes, Black Sea Trade,
hold Novgorod, then bring Aleksandr forward when Teuton service is
worn and Knight-stacked Russian Battles will dominate.


# 10. How the LLM May Use This Document

This is a digest the LLM may consult when:

- Loading a scenario and forming a high-level plan.
- Picking Capabilities at Levy.
- Deciding whether to Avoid / Withdraw / Stand at a combat-pending.
- Planning a multi-turn campaign for a key Lord.

The LLM may:

- Apply suggestions verbatim.
- Adapt them to the specific board state.
- Disagree with any of them based on play observation.
- Ignore the document and play from first principles.

The harness will not consult this document. Nothing in
`src/nevsky/` parses or loads it. It is a peer document to BRIEF.md
and the reference/ files — useful information for the LLM consumer,
not a runtime dependency of the engine.
