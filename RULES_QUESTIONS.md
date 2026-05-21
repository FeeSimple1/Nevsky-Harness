# Open Questions

Format per BRIEF: ID, Context, Consultation log (5 steps), What is
ambiguous, Options, Affects, Blocking?

When resolved, MOVE the entry to RULES_DECISIONS.md with the user's
adjudication, citation, and commit hash.

## Q-009 — Does Feed (4.8.1) apply to Lords who only took a *stationary* Command (Tax, Forage, Ravage, Supply, Muster Serf, Stone Kremlin, Stonemasons), or only to Lords who Marched/Fought/Sailed?

**Context.** During the Crusade seed-1 LLM self-play (box 2), Russian gavrilo (9-unit Pskov garrison) took a *Tax* command and Russian vladislav (7-unit reserve) took *Muster-Serf* commands. At end-of-card FPD each was required to Feed (units>=7 -> 2 Provender), had 0 Provender, was marked **Unfed**, and had his Service marker shifted 1 box LEFT (4.8.1 unfed penalty) -> reached the Levy marker -> Disband risk. The harness sets `lord.moved_fought = True` in the handlers for Tax, Forage, Ravage, Supply, Muster-Serf, Stone Kremlin, Stonemasons (campaign.py), and `_enter_feed_pay_disband` Feeds every MOVED_FOUGHT Lord.

**Consultation log.**
1. `reference/Nevsky Miscellaneous Rules Reference.txt` L451-457: "Moved/Fought markers: placed on a Lord cylinder when the Lord conducts **March, Avoid Battle, Battle, Siege, Storm, or Sail**." This list EXCLUDES Tax/Forage/Ravage/Supply/Muster.
2. Same file L571 (glossary): "Feed — Eat after **Marched/Fought** (4.8.1)."
3. `reference/Nevsky_Commands.txt` L21 (Moved/Fought marker): "Tracks Lords that **acted on the current Command card**; required for Feed at end of card." This is BROADER — any command action.
4. `reference/Nevsky_Sequence_of_Play.txt` 4.8.1: "applies_to: Lords marked MOVED_FOUGHT (any side)." Gates Feed on the marker but doesn't itself say which actions set it.
5. No existing test asserts that Tax/Forage/etc. SET moved_fought; tests set the flag manually. So the current behavior is not a locked/intentional decision.

**What is ambiguous.** Whether a Lord who takes only a stationary Command (Tax, Forage, Ravage, Supply, Muster-Serf, Stone Kremlin, Stonemasons) must Feed. Misc Rules L451/L571 imply NO (marker only for March/Avoid/Battle/Siege/Storm/Sail); Commands.txt L21 implies YES (any acted Lord). The two authoritative summaries conflict; the Rules of Play 2E 4.8.1 / marker definition should settle it.

**Options.**
- (A) Feed only Lords who Marched/Avoided/Fought/Sieged/Stormed/Sailed (Misc Rules reading). Tax/Forage/Ravage/Supply/Muster/StoneKremlin/Stonemasons do NOT set moved_fought and do NOT Feed. (Foraging then feeding the same stack is near self-defeating, which weakly supports this.)
- (B) Keep current harness behavior: any Lord who took a Command this card Feeds (Commands.txt reading).

**Affects.** Feed economy and Unfed/Disband cascades for large stacks; whether a stationary Taxing/Foraging garrison consumes Provender each card. Materially changes survivability of bulked garrisons (e.g., Pskov) and the value of Forage. Touches `_h_cmd_tax/_forage/_ravage/_supply/_muster_serf/_stone_kremlin/_stonemasons` and `_enter_feed_pay_disband`.

**Blocking?** No — playthrough continues under the current harness behavior (B) pending adjudication. If the user rules (A), this becomes a numbered fix round (remove moved_fought from the stationary handlers) with regression tests.
