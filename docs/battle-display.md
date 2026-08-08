# Battle result display: symmetric in games, symmetric in algorithms

A proposal, not shipped code.
It owns the target shape of the battle result presentation
for the reader cut-over in `docs/game-migration.md`,
where the templates change anyway.

The present display privileges one member
of each of two sets the data treats as peers:
one game of the two, and one scoring algorithm of the two.
Neither privilege comes from the game;
both come from how the values were once stored and once computed.
The display that stops asserting them
is also the display that stops caring
how many games and how many algorithms exist.

## Symmetric in games

The battle page has two named slots
(`battle_detail.html` renders `game_1_2` and `game_2_1`
under fixed headings and fixed anchors),
and the accessors that feed them are named for directions.

The grounded argument is not a hypothetical third game
but the pair itself:
the two games resolve independently,
so for a while a battle has one resolved game and one pending.
Where the display is already per game
it takes that in stride —
the game partial branches on its own game's `resolved_at` —
and where the pair is named,
`warriorarena_detail.html` spells the state out per direction
three times in one table row.
The difference is the whole argument in miniature:
looping is what makes the partial-resolution case ordinary.

That the count could exceed two is a bonus rather than the case:
nothing in the domain fixes it at two,
and reruns after a model version change,
or a matchup replayed against a second LLM,
would each want a row where today there is a named slot.
Neither exists, and this proposal does not argue for them.

## Symmetric in scoring algorithms

Every resolved game is scored by every algorithm:
`resolve_battle` (`warriors/tasks.py`) writes an LCS score
and an embeddings score unconditionally.
The storage is symmetric; the display is not.
LCS supplies the page's unqualified numbers —
the meters, the preserved ratios, the battle score —
while embeddings is reached through a special-cased property
(`Game.embedding_scoring`, which builds a second facade
with the algorithm name written into it)
and rendered under an "experimental" heading.
`BattleViewpoint` carries a `score_algorithm` defaulting to LCS,
so `BattleDetailView`, which names no algorithm, gets LCS by omission.

That default has no owner.
Which algorithm is authoritative is a property of a *ranking*,
not of a battle:
today `Arena.score_algorithm`,
and under the target shape in `docs/data-model.md`
part of the ranking registry key,
so several rankings can read one battle through different algorithms.
The battle page belongs to no arena and no ranking —
it is the record of what happened —
which leaves it no basis for calling one column the score
and the other experimental.

The display should loop over the algorithms
the way it loops over the games.
The test is mechanical:
a third member of `ScoreAlgorithm` should reach the battle page
without a template edit.
Today each algorithm is a hand-written block,
and hand-written per-algorithm blocks drift —
`TODO.md` carries the instance.

Symmetric does not mean identical.
LCS can mark the surviving subsequence inside the result text
and an embedding similarity has nothing to mark,
so algorithm-specific extras hang off their own algorithm's block.
What goes away is one algorithm's numbers standing unqualified
while the others are guests.
Where a number does feed a ranking,
that is an annotation on it, not a reason to structure the page around it.

## The shape

Three axes — game, algorithm, warrior — and a page renders two at a time.

The battle summary is a matrix per algorithm,
reached by looping over algorithms rather than naming any:
a row per warrior, a column per game,
each cell that warrior's score in that game,
and a margin column holding the mean, which is the battle score.
Every column sums to one, the margin column included,
so a reader can check the arithmetic by eye —
the practical test of a symmetric presentation.
Warrior similarity and the cooperation score built from it
are per battle and per algorithm, not per game,
so they sit beside that algorithm's matrix
instead of being repeated in every game block.

Each game then gets its own block:
the result text, and its scores by algorithm and by warrior.

For a cell to be addressable at all,
a game's score has to be askable *for a named warrior*,
rather than as a positional `score`
with the other side derived as the remainder.
That is mechanism in service of the two symmetries,
with a payoff of its own:
the viewpoint machinery
(`BattleViewpoint`'s field rewriting, the in-memory `Game` facade)
exists to make "1" mean "the warrior this page is about",
and per-warrior addressing retires all of it.
Rewriting is also what makes "which warrior is 1"
a property of the read path rather than a key,
so the same game has more than one spelling
and a lookup can take the wrong one;
`Game.score_object` says why its lookup is keyed on the game.

## What stays asymmetric, deliberately

Prompt order inside a game is the variable
that playing both directions controls for,
so it stays visible per game.
The battle's canonical warrior order stays too —
pair identity, matchmaking exclusion,
and the uniqueness constraint all key off it.
Symmetry here means an order or an algorithm choice
is data the page reports,
not structure baked into slot names, field names, and defaults.
Performance stays pairwise:
it is a score minus a rating-model expectation for two warriors
(`BattleViewpoint.performance`),
and no expectation is defined for a wider battle.

## Decisions to settle before coding

- **What the battle lists show.**
  A battle page has room for every game and every algorithm;
  a list row has room for neither.
  The warrior-arena list is arena-scoped,
  so it has an owner to ask for an algorithm —
  the one place where naming one is legitimate.
  Its fixed pair of per-direction score columns is the harder half:
  either keep two columns while every battle has two games,
  or collapse to the warrior's battle score
  and leave per-game detail to the battle page.
- **Battle score with a game missing.**
  Mean over resolved games, or "pending" until all are in?
  Display can reasonably show the partial mean with a count;
  rating must not — its resolved-battle filter
  stays "every game of this battle is resolved"
  (the `BattleQuerySet.resolved()` change
  in step 1 of `docs/game-migration.md`).
  The two coincide by accident, and the split should be deliberate.
- **Anchors.**
  Per-game anchors are direction strings linked from the battle list.
  With N games the stable name is the game's own id,
  and the accepted cost is that old fragment links
  land at the top of the right battle page;
  the battle URL itself is unchanged.
- **Whether a warrior's battle score under an algorithm
  becomes a named thing in code** that rating also calls,
  rather than a display-only computation.
  Rating's averaging semantics are unchanged either way;
  the question is whether one definition serves both.

## Sequencing

Written against the battle's directional columns,
a symmetric renderer has to reconstruct games from suffixed field names —
a second facade beside the one being deleted.
`GameScore` already keys on (game, algorithm)
and is already selected by the game it names,
so a per-warrior lookup has something to sit on.
That makes this the shape of step 1's view and template work
in `docs/game-migration.md`,
not a separate project after it.
