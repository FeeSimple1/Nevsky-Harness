Nevsky Harness — Project Specification
Goal
A Python harness for Nevsky: Teutons and Rus in Collision, 1240–1242 (GMT
Games, 2nd Edition 2023). The harness holds full game state, validates and
executes all rules-defined actions, runs Battle and Storm engagements
automatically, rolls all dice, and exposes a structured interface designed
to be consumed by an LLM (Claude or ChatGPT) playing one or both sides.
The user supplies strategic judgment via the LLM. The user adjudicates
rules ambiguities surfaced during development. The harness supplies
everything else: state, rules enforcement, mechanical resolution.
This is a private project. Code quality should be good enough for the user
to maintain, not for external readers.
Authoritative Sources (Priority Order)

1. Nevsky_Second_Edition_Changes.txt — overrides any conflict in older
   sources.
2. The curated reference .txt files in the repo (Lords, Forces,
   Strongholds, Map, Commands, Battle and Storm, Sequence of Play,
   Call to Arms, Calendar and Veche, Scenarios, Miscellaneous Rules,
   Arts of War Reference, Strategy). These are designer-clarified
   distillations and are the FIRST stop for any question about card
   text, capability mechanics, or rule interpretation. The Tips
   sections in particular contain Volko Ruhnke's clarifications that
   resolve most apparent ambiguities without further escalation.
3. NevskyRules_Second_Edition.pdf — Rules of Play, 2nd Edition. Used
   to confirm what's in the .txt references when something is missing
   from them.
4. Nevsky_PLAYBOOK-FINAL.pdf — examples and historical context. NOT a
   rules source; useful only for clarifying examples.

PDFs in the repo's source/ directory ARE readable; treat them as
ordinary inputs. The PDF-restriction language in earlier rounds of
this project was about external/web PDFs, not the in-repo PDFs.

When sources conflict, higher priority wins. For Q-NNN consultation,
the FIRST step is always the relevant .txt reference file's section
(Battle and Storm, Forces, Arts of War Reference, etc.). Skipping that
step is a process bug. The .txt references are not optional starting
material — they are the canonical answers.
Scope of Inquiry — Hard Constraint
This is a software project to encode a board game's rules. It is NOT a
historical research project. The game's setting in 13th-century Baltic
Rus is theme, not subject matter.
Sources you may consult

The repo's reference .txt files.
The repo's PDFs (Rules of Play, Playbook, PAC).
Standard Python documentation, language references, and library docs
needed to write the code.
Files in the repo that the user has placed there.

Sources you may NOT consult without explicit user instruction

Wikipedia, encyclopedias, or any general-knowledge reference on the
historical period, persons, places, battles, or events.
Academic or popular history sources (Nicolle, Christiansen, the
Novgorod Chronicle, etc.) — even when the rulebook references them.
Other GMT board games or board game databases (BoardGameGeek,
Consimworld) for comparative rules interpretation.
Your own pre-existing knowledge of Nevsky or its themes when that
knowledge comes from outside the repo files. If you find yourself
"remembering" something about Nevsky, treat that memory as if it
doesn't exist; consult the repo files instead.
Web searches of any kind related to the game's subject matter.

Why this matters
Proper names and identifiers (Aleksandr, Hermann, Pskov, Druzhina,
Halbbrüder, Luchniki) are tokens used by the rules to identify specific
game pieces with specific game stats. Their historical referents are
irrelevant to the harness. Encoding any historical "fact" as game logic
is a bug, not a feature. Examples of forbidden reasoning:

"Historically Gavrilo died in 1240, so the harness should remove him
in Summer 1240" — WRONG. The Return of the Prince scenario explicitly
has Gavrilo enter at Calendar box 9; the rules override the history.
"The Battle of the Ice happened on Lake Peipus, so Storm at Uzmen
should have ice-related modifiers" — WRONG. The rules specify what
modifiers exist; nothing else.
"Knights historically had heavier armor than Sergeants, so Knights
should have better Protection" — WRONG. The Forces table specifies
Protection ranges; that is the only source.

What to do when the rules reference history
The Rules of Play and Playbook contain historical commentary, design
notes, and flavor text. Read them only for the game-mechanical content
they contain. Ignore the historical claims. If a Design Note says "Once
rivers froze, sleds became versatile" alongside a rule about Sleds being
usable on all Ways in Winter, the rule is the input; the design
rationale is not.
What to do if you think you need historical context to resolve an ambiguity
You don't. If a rule is ambiguous, the resolution path is the
consultation chain (below), then the user. Historical "what actually
happened" is never an input. If you find yourself reaching for context
outside the repo to formulate or resolve a question, that is itself a
signal the question needs to go to the user. Do not fill in the gap
from general knowledge.
Names and identifiers
You may and should use proper names from the game (Lords, Vassals,
Locales, Capabilities, Strongholds) for state tracking, code
identifiers, file names, comments, and user-facing displays. Use them
exactly as the rules use them. Do not annotate them with historical
context, do not gloss them, do not transliterate alternates ("Aleksandr"
not "Alexander"; "Pleskau" in the scenario name even though the place
is called "Pskov" in the rules — they are game tokens, use them as
written).
Rules Accuracy Trumps Simplification — HARD CONSTRAINT
Where the rules are clear, the harness MUST implement them faithfully.
Simplifications, approximations, "Phase N+ deferrals", and
convenience shortcuts are NOT acceptable when the rules are explicit
about a behavior.

The only acceptable reasons to depart from the rules are:
  1. The rules are ambiguous (-> follow the Ambiguity Policy / Q-NNN
     consultation chain below).
  2. The user has explicitly adjudicated a deviation (recorded in
     RULES_DECISIONS.md as [HOUSE RULE]).

Reasons that are NOT acceptable:
  - "Easier to implement this way."
  - "Phase N is just a stub; Phase N+1 will fix it."
  - "Most games won't hit this case."
  - "The simplification is conservative / lenient."

When implementing a feature, if the chosen approach diverges from the
rules in any measurable way, the divergence MUST be either:
  a. Fixed in the same PR before merge.
  b. Logged as a Q-NNN in RULES_QUESTIONS.md and surfaced to the user
     before merge.

Code comments that say "simplified", "approximated", "deferred", or
similar are flags for audit. Each must trace to either a Q-NNN, a
[HOUSE RULE] decision, or a future-phase commitment with an explicit
issue tracking it.

Ambiguity Policy
The harness encodes rules deterministically. Every rule encoded in code
must trace to a source. The user is the sole authority on rules
interpretation when sources are silent or unclear.
Consultation Chain — REQUIRED before logging any question
When you encounter anything ambiguous, work through this chain in order
and document each step:

1. Curated reference file. Identify the most relevant .txt file
   (Battle and Storm for combat, Commands for Command actions, Arts of
   War Reference for card text and capability mechanics, etc.) and
   read the relevant section IN FULL. The Tips paragraphs in the Arts
   of War Reference are designer-clarified text and resolve most
   apparent ambiguity about card mechanics on their own. If the answer
   is in the .txt reference, the consultation ends here and the
   question does not need to be logged.
2. Rules of Play, primary section. Find the rule section number cited
   in the reference file and read the full section in the PDF, plus any
   sub-sections.
3. Rules of Play, related sections. Use the Key Terms index (page 24)
   to locate any cross-referenced sections. Read those too.
4. Playbook examples. Search the Playbook for worked examples that
   might illustrate the case. Examples are not rules but they often
   resolve apparent ambiguity.
5. Second Edition Changes. Check whether the case is addressed by an
   erratum or 2E modification.

Only after all five steps have been performed and documented should you
log a question. If the consultation resolves the question, encode the
answer with a citation comment in the code and proceed.

Common process error: invoking the PDF-access concern as a reason to
skip the .txt references. The .txt references are unrestricted in-repo
files and contain designer-clarified answers for most card-text and
capability-mechanics questions. Read them first.
Question Format — REQUIRED fields
Append questions to RULES_QUESTIONS.md. Each entry must contain:

Question ID — Q-NNN, sequential.
Context — what you were implementing when the question arose.
Consultation log — what you checked at each of the five steps
above, including section numbers and quoted text. Confirm explicitly
that no external/historical sources were consulted. If a step was
skipped, explain why.
What is ambiguous — specifically what the rules do not
determine.
Options — at least two concrete possibilities, each with a brief
argument from the rules text for why a reader might choose it.
Affects — files, functions, tests, or scenarios that depend on
the answer.
Blocking? — whether other work can proceed without an answer.

Do not log a question without all seven fields. The discipline of
filling them in resolves a meaningful fraction of would-be questions.
Decision Log
When the user answers a question, MOVE the entry from
RULES_QUESTIONS.md to RULES_DECISIONS.md, appending the user's
adjudication, any rules citation provided, and the commit hash where the
answer is encoded. Decisions are permanent — never delete an entry from
RULES_DECISIONS.md.
If the user marks a decision [HOUSE RULE] (rules silent on the
question), treat it as authoritative and cite it like any other rule.

No Agent in the Harness — Hard Constraint
The harness encodes the rules and exposes state. It MUST NOT make
strategic decisions on the consumer's behalf. The LLM (or human)
consumer applies all strategic judgment. The harness's job is:

  - Maintain authoritative game state.
  - Enforce rules: actions either succeed and mutate state or raise
    IllegalAction with a code.
  - Surface state in forms the consumer can read efficiently
    (render_summary, lord_combat_summary, paths_from, etc.).
  - Enumerate legal moves with their mechanical effects.
  - Compute previews / forecasts on request (vp_forecast,
    battle_preview, storm_preview).

What the harness MUST NOT do:

  - Recommend specific actions ("Use when winrate < 30%").
  - Editorialise about strategic trade-offs ("loses tempo", "Trade
    losses now for...").
  - Pick decisions for the consumer (Reserve advance, Concede,
    Avoid Battle, Withdraw, Plan ordering, Capability picks, etc.).
  - Run an internal agent that selects actions when the consumer
    hasn't.

Test fixtures under `tests/_playthrough_*.py` exercise the engine by
driving the harness with simple heuristic policies. Those scripts
ARE agents (necessarily — to stress-test the engine end-to-end) but
they are NOT part of the shipped harness. They live in the test
suite, are not in `src/nevsky/`, and are excluded from the package.

If a comment, docstring, note field, or helper output in
src/nevsky/ contains language like "Use when...", "should",
"recommend", "prefer", or any other prescription about WHEN to take
an action, that's a bug. The remedy is to replace the prescriptive
text with a description of the rule's mechanical effect and let the
consumer decide.

Architecture Requirements
The user does not require specific implementation choices, but the
harness must satisfy these constraints:

Language: Python 3.11+.
State representation: A single JSON file holds complete game state.
State files are portable across sessions. Loading a state file fully
reconstructs the game.
Determinism: Given a state file and an action, the resulting state
is deterministic except for dice. Dice use a seedable RNG; the seed is
stored in the state file.
Two interfaces:

A library API (Python functions/classes) for programmatic use.
A CLI that wraps the library, suitable for an LLM to call via shell
or for the user to run directly.


No graphical interface.

LLM-Consumer Interface — Required Capabilities
The harness must expose, at minimum:

new — Initialize a state file from a scenario. All six scenarios
plus the Nicolle variant supported.
state — Render current state. Must support:

Summary mode — compact view fitting in ~500 tokens, sufficient
for an LLM to make routine decisions.
Verbose mode — full state.
Focused views — a single Lord's mat, a single Locale, the
Calendar, the Veche, deck composition.


legal-moves — Enumerate all legal actions for a given player in
the current phase. Each move includes its action grammar, costs,
prerequisites met, and a brief description with rule citation.
This is the primary interface an LLM uses to decide what to do.
do — Execute a submitted action. Validates against rules,
updates state, returns a structured result describing what happened
(including dice rolled, hits assigned, markers placed, VP changes).
Errors include rule citations.
pending — When an action triggers a sub-decision (e.g., Approach:
each defender chooses Avoid/Withdraw/Stand), the harness records the
pending decision in the state file. pending returns the current
pending decisions and which player owes a response.
history — Return the last N actions and results, for context.
save / load — Explicit state persistence (in addition to
automatic state file updates).

Action Grammar
Actions are submitted as JSON. The action grammar is part of the
specification and must be documented in ACTIONS.md as it is developed.
Every action type has a schema; the harness rejects malformed actions
with a clear error.
Dice and Mechanical Resolution
The harness rolls all dice. The LLM never rolls. Every roll is logged
in the action result with the context (whose roll, against what target,
what happened). This is non-negotiable: it removes a class of errors and
makes the game auditable.
Two-Sided Play
The harness supports:

LLM plays one side, user plays the other.
LLM plays both sides (alternating activations).
Pure observer mode (state inspection only).

The harness does not need to know which player is the LLM; it just
exposes legal moves and validates submissions per the active player.
Phasing
Each phase is a separate PR. Do not start the next phase until the
previous PR is merged by the user.

Phase 0: Project skeleton, JSON schema for state, scenario data
files, basic CLI structure, test framework. No game logic yet.
Phase 1: State model, scenario loader (all six + Nicolle variant),
state display (summary/verbose/focused), state command.
Phase 2: Levy phase mechanics — Pay, Disband, Muster, Vassal Levy,
Transport Levy, Capability Levy, Veche Call to Arms, Legate Call to
Arms. legal-moves for Levy.
Phase 3a: Simple Commands — Tax, Forage, Ravage, Supply, Sail,
Pass. Feed/Pay/Disband cycle. legal-moves for these.
Phase 3b: March with Approach decision tree, Avoid Battle,
Withdraw, Battle resolution.
Phase 3c: Siege, Storm, Sally, Relief Sally.
Phase 4 (deferred): Per-card Arts of War effects. Until Phase 4,
cards are tracked as data with effect text in a notes field; the
user/LLM applies card effects manually. The harness flags when a card
in play would affect a current action so the user knows to consider
it.

Test Discipline
Every rule encoded in code must have at least one test. The test's
docstring cites the rule section. A rule without a test does not exist
in the harness.
pytest -v should produce a list of every rule the harness claims to
implement, organized by rule section.
End-to-end scenario tests exist for at least one full Levy + Campaign
turn of Pleskau by end of Phase 3a, and at least one full Battle by end
of Phase 3b.
Commit and PR Workflow

Small, focused commits with descriptive messages.
Each commit message references the rule section it implements OR the
question/decision it resolves.
One PR per phase (regular, not draft -- Eric's call, 2026-05-08).
The user reviews and merges PRs. Cowork does not merge to main.
Branch naming: phase-N-short-description.

When to Ping the User
These are the only times you ping the user:

A new question batch is ready in RULES_QUESTIONS.md (don't ping per
question — let questions accumulate to a reasonable batch, then ping).
A phase PR is ready for review.
A test is failing in a way the consultation chain cannot resolve.
A playtest issue logged in PLAYTESTS.md requires interpretation.

Outside these triggers, work autonomously. The user expects long stretches
of no contact.
Out of Scope

AI opponents, strategy advice, or playstyle tuning.
Graphical interface.
Networked / multi-user play.
Sharing or distribution; this is a private project.
Anything not directly serving "run a Nevsky game with state persistence,
rules enforcement, and an LLM-friendly interface."

Engine / Operator Split — Battle decisions
The harness's Battle resolution (resolve_battle) faithfully implements
the 2E three-position Array with Flanking, Reposition, and per-position
Strike resolution (Q-005). Some moments in a Battle require player
judgment that no deterministic rule pins down: which Reserve to advance,
which left/right Lord to slide to center, where to direct Hits when a
Flanker creates ambiguity, and similar.

These choice points flow through a BattleDecisionContext. The engine
generates the legal options at each choice point and asks the context
for a selection. The context resolves the request in one of three
ways, in priority order:
  1. scripted_decisions list (FIFO, consumed in order). Used by tests
     to pin operator choices. A type mismatch raises immediately.
  2. callback (callable). Used by live play; the harness invokes the
     callback with {type, side, options, info} and expects a return
     value present in options.
  3. deterministic fallback ("leftmost"). Used when neither scripted
     nor callback is provided; picks options[0]. Keeps the harness
     usable as a deterministic black box.

Decision types:
  initial_placement_attacker — non-Active Attacker Lord into a slot
  initial_placement_defender — Defender Lord into a slot
  reserve_advance            — which Reserve advances to which slot
  center_fill                — which left/right Lord fills empty center
  flanker_target             — Flanker tie-break when multiple targets
                               are equally close

The full decision trace appears under result["decisions"] for any
Battle, so a reproduced Battle from a state file plus a recorded
scripted_decisions list will replay deterministically.

Tests must use scripted_decisions for any Battle they assert outcomes
on. The leftmost fallback is acceptable only for tests that verify
structural properties (winner exists, positions are valid, etc.) and
not for tests that pin specific Hit counts or Lord-Routs.
