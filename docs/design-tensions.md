# Design tensions and directions

This doc owns a design-level reading of the game:
what it does well,
where the mechanics work against its own appeal,
and the candidate directions that follow.
Mechanics live in code (`warriors/`);
effort priorities live in `docs/strategy.md`;
the fixed-cadence rounds proposal has its own doc,
`docs/rounds.md`.

## Strengths

**Anonymous intimacy.**
A player's thought is fused with a stranger's thought
by a third mind — the LLM as mediator —
without either player performing socially.
It is talking to strangers with the awkwardness removed.
Two limits:
the game offers exactly one relationship to the stranger (combat),
and the fusion happens while players are away
and is shown to nobody
(the discarded retention signal in `docs/strategy.md`
is this same gap seen from the funnel side).

**Emergent gems.**
Battle outputs are sometimes funny or genuinely surprising,
and watching nondeterministic paths unfold is a real pleasure —
but most outputs are boring,
and the gems are buried in the pile.
This is a curation gap, not a generation gap:
every output gets an embedding,
so novelty is measurable
as distance from the cloud of prior outputs,
yet nothing ranks or surfaces it.
The only related control, `Warrior.public_battle_results`,
is a visibility flag, not a taste signal;
nobody can mark an output as good.

**A living system.**
The universe of submitted prompts grows
and becomes more diverse —
in span, not in uniformity of distribution.
But the system has no memory and no narrator:
no map of prompt space,
no lineage records
(`docs/lineages.md` is the unimplemented proposal),
no visible history of meta shifts.
A living world that cannot be observed
reads as a static leaderboard.

## The central tension: dominance selects against delight

A perfect score means the output is the winning prompt verbatim.
The documented meta strategies (`CONCEPT.md`)
are all ways of making the output maximally boring:
a lone rare emoji, a canned refusal, a one-line protocol response.
The interesting outputs — real fusions of two prompts —
come from balanced mid-ladder battles,
precisely the ones the rating system treats as unremarkable draws.
The fitness function breeds interestingness out of the population.

The open redesign question:
what does a score look like that rewards
surviving *interestingly* rather than replicating sterilely?
`cooperation_score` in `warriors/score.py`
measures the fusion-quality axis
(see its docstring),
is displayed as an experimental table row,
and feeds no mechanic.

## Further weaknesses

Zero-sum is the only verb:
everything a player can do is attack.
The core loop is illegible to newcomers:
LCS, normalization, two directions, and two scoring algorithms
stand between a first-time player and the first "aha",
and a first loss to an emoji-cheese warrior teaches nothing.
Players have no stakes in battles they didn't initiate:
matches fire on a schedule against strangers nobody chose,
with no way even to watch a rival.

## Directions, ranked by leverage

1. **Novelty surfacing.**
   Rank outputs by embedding distance from the existing corpus;
   surface a feed of notable battles.
   This attacks the buried-gems problem
   with data the system pays for anyway,
   and provides the content engine
   for the digest email and the shareable meta-report
   in `docs/strategy.md`.
2. **Adopt-an-output.**
   One click turns a battle result into a warrior.
   This makes the competition-creation duality
   in `docs/parallels.md` a playable verb,
   and makes lineage explicit at creation time —
   removing the need for the fuzzy-matching reconstruction
   that `docs/lineages.md` proposes.
   Adoption count is also a fame metric that rewards generativity:
   "my warrior's children are everywhere"
   points the opposite way from sterile dominance.
3. **A second leaderboard axis.**
   Keep the dominance rating untouched;
   add a parallel ranking fed by output novelty and adoption counts.
   Embedding-based novelty is much harder to goodhart
   than an LLM interestingness judge,
   which players would hijack immediately
   (the data–instruction separation theme in `docs/parallels.md`).
4. **A cooperative mode.**
   Two strangers' prompts scored on fusion quality
   (`cooperation_score`) instead of dominance —
   the stranger-mixing strength as a duet rather than a duel.
   Deliberately parked:
   `docs/strategy.md` rejects new game modes
   before retention exists,
   and that reasoning holds here.

The through-line is a single move:
stop discarding selection signals the system emits.
Novelty (embeddings),
lineage (players copy-paste battle results by hand),
and cooperation (scored but hidden)
all exist with no surface and no consequence.
