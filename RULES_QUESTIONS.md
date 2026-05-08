# Open Questions

Format per BRIEF: ID, Context, Consultation log (5 steps), What is
ambiguous, Options, Affects, Blocking?

When resolved, MOVE the entry to RULES_DECISIONS.md with the user's
adjudication, citation, and commit hash.

---

## Q-004 — T12 Ordensburgen: which Strongholds are Commanderies? (1.3.1)

**Context.**
The Teutonic Capability T12 Ordensburgen grants Teutonic Lords extra
Seats at every Commandery, plus +1 Command when a Lord starts a
Command card at one. Per Rules of Play 1.3.1, "Commanderies are
Strongholds with the Order symbol on the map." Per the Misc Reference
file: "Strongholds with the Order symbol serve as EXTRA Seats for the
relevant Teutonic Lords while T12 Ordensburgen Capability is in play."
The full list of Commanderies is identified by an Order seat symbol on
the printed map (see Playbook page 5: "small black-cross-on-white Seat
symbols, not to be confused with Teutonic master Andreas's larger,
more ornate symbols at Riga and Wenden").

**Consultation log.**
1. *Rules of Play 2E (page 3, page 36 example).* Wenden is named
   explicitly: "Wenden would be two Seats each for Andreas and Rudolf"
   (Playbook page 36, T12).
2. *Playbook (page 8).* The example play references "the OrdenSBurGen
   Commanderies at Fellin and Adsel or Leal" — confirming Fellin
   (Castle), Adsel (Castle), and Leal (Bishopric) as Commanderies.
3. *Playbook (page 6).* "Heinrich is able to Muster at Fellin (instead
   of Leal) only because that Stronghold counts as a Seat for Heinrich
   via the OrdenSBurGen card" — Fellin confirmed.
4. *Background book (page 35).* "the commanderies of the Teutonic
   Order" but no enumeration.
5. *Reference files / 2E Changes / Map Reference.* No enumeration.
   Map symbols are the source of truth. Without the physical map, the
   set is incomplete: Wesenberg, Odenpah (Castles); Reval, Riga,
   Dorpat (Bishoprics) MAY also bear the Order symbol, but textual
   sources do not confirm them.

**What is ambiguous.**
The complete set of Commanderies. Confirmed by text: Wenden, Fellin,
Adsel, Leal. Possible additional Commanderies (per the rules' "all
Strongholds with the Order symbol"): Wesenberg, Odenpah, Reval,
Dorpat. The current implementation flags only the four confirmed ones.

**Options.**

a. *Use only confirmed (current).* Wenden, Fellin, Adsel, Leal flagged
   `commandery: true`. Others remain false until the map is consulted.
b. *Expand by territory.* Flag every Teutonic-territory Stronghold
   that is a Castle or a Bishopric AND is owned by the Order (not a
   civilian Bishop's seat). Risky without map verification.
c. *Match by primary seat.* Flag every Locale that appears as a
   primary Seat for any Teutonic Order Lord (Andreas, Hermann, Rudolf,
   Heinrich) — but this conflates Coat-of-Arms seats with Order seat
   symbols, which the rules say are different (Playbook page 5).

**Affects.**
- `src/nevsky/data/static/locales.json` (`commandery` flag)
- `src/nevsky/actions.py::_seats_of` (T12 extra-Seat enumeration)
- `src/nevsky/campaign.py::effective_command_rating`
  (Ordensburgen +1 detection)

**Blocking?**
No. Option (a) is conservative and can be expanded once the map's
Order seat symbols are read off. Players using the harness for the
Crusade/Watland scenarios will see the +1 trigger at Wenden, Fellin,
Adsel, Leal exactly. If the canonical map adds more Commanderies, an
edit to locales.json suffices.

