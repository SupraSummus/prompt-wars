# Battle result display: symmetric in games, symmetric in algorithms

This doc owns why the battle result presentation is shaped as it is:
`BattleDetailView` and the warrior's battle list (`warriors/views.py`),
`templates/warriors/battle_detail.html`
and the game partial beside it.

The data treats two sets as peers —
the games of a battle, and the scoring algorithms —
and the page says so.
Privileging one member of either
asserts something no game supports,
and the display that stops asserting it
is also the display that stops caring
how many games and how many algorithms exist.

## Symmetric in games

The grounded argument is not a hypothetical third game
but the pair itself:
the two games resolve independently,
so for a while a battle has one resolved game and one pending.
A display that is per game takes that in stride —
each block branches on its own game's `resolved_at` —
where one built out of two named slots
reads the state off the battle instead, once per slot.
That difference is the whole argument in miniature:
addressing a game by its own warriors, rather than by a slot name,
is what makes the partial-resolution case ordinary.
The battle page reaches that by looping over the battle's games;
the list reaches it by asking each cell's game row directly
("The battle lists keep a score column per game", under "Decisions"),
and both stop asking the battle.

That the count could exceed two is a bonus rather than the case:
nothing in the domain fixes it at two,
and reruns after a model version change,
or a matchup replayed against a second LLM,
would each want a row of their own.
Neither exists, and nothing here argues for them.

## Symmetric in scoring algorithms

Every resolved game is scored by every algorithm:
`resolve_battle` (`warriors/tasks.py`) writes an LCS score
and an embeddings score unconditionally,
so the storage is symmetric and the display follows it.

An unqualified default would have no owner.
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

So the display loops over the algorithms
the way it loops over the games.
The test is mechanical:
a third member of `ScoreAlgorithm` reaches the battle page
without a template edit.
The alternative, a hand-written block per algorithm,
drifts between blocks that nothing forces to agree.

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
Warrior similarity is per battle and per algorithm —
it compares the two prompts and no result —
so it sits beside that algorithm's matrix
instead of being repeated in every game block.
The cooperation score built from it does not follow it up there:
it weighs how much of each prompt survived into *one* result,
so the two games earn different numbers
and each stays in its own block.

Each game then gets its own block:
the result text, and its scores by algorithm and by warrior.

For a cell to be addressable at all,
a game's score has to be askable *for a named warrior*,
rather than as a positional `score`
with the other side derived as the remainder.
`GameScore.score_for` is that question.
The alternative is a facade that rewrites field names
so that "1" means "the warrior this page is about":
that makes "which warrior is 1" a property of the read path
rather than a key,
gives the same game more than one spelling,
and leaves a lookup free to take the wrong one.

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
(`Battle.warrior_performance`),
and no expectation is defined for a wider battle.

## Decisions

**A warrior's score is named once, and rating calls it.**
Two definitions, in dependency order:
a score row's value *for a named warrior* —
the row's fields are already in game order and the row names its game,
so it is a choice between the two of them —
and, on the battle,
a warrior's score under an algorithm:
the mean over the battle's games,
undefined until every game is resolved.
`GameScore.score_for` and `Battle.warrior_score` are those two names,
and `WarriorArena.update_rating` calls the second
rather than keeping its own copy.
The rejected alternative — a display-only computation —
leaves two spellings of one number free to drift,
which is the failure this migration exists to remove;
it would also have given the viewpoint machinery something to port
instead of something to delete.
This is the mechanism the other three decisions rest on:
the summary matrix's cells, the list's score columns,
and rating are all one call.

**The battle lists keep a score column per game.**
A battle page has room for every game and every algorithm;
a list row has room for neither,
and the warrior-arena list is arena-scoped,
so it has an owner to ask for an algorithm —
the one place where naming one is legitimate.
Its per-order score columns stay:
prompt order is the variable playing both directions controls for,
and a warrior's history is read for exactly that asymmetry,
so the columns report data
the way "what stays asymmetric, deliberately" describes.
What changes is how a cell finds its number —
by the game whose first warrior is this row's warrior,
each cell branching on that game's own `resolved_at` —
so no cell names a direction or reads a battle column.
The rejected alternative —
collapsing to the warrior's battle score
and leaving per-game detail to the battle page —
buys a row whose numbers are all battle-level
at the price of the one signal the list is scanned for.
The accepted cost is a column count fixed at two:
a battle with a third game would need this decision reopened,
and nothing proposes one.

**A battle score is pending until every game resolves.**
Rating requires it —
`BattleQuerySet.resolved()` admits a battle
only once every game of it is resolved —
and display follows,
so the number a reader sees is the number rating fits against.
The rejected alternative,
a partial mean with a count of games in it,
invites comparing a one-game mean with a two-game mean
as though they measured the same thing.
Partial resolution stays ordinary one level down:
each game block shows its own score as it lands.
The two definitions coincide by intent, then, rather than by accident.

**A game's anchor is its id.**
An anchor here is an inbound target, not a label:
the warrior's battle list links each score cell
straight at the game it reports.
With N games the stable name is the game's own id,
and the cell building the link already holds the game row,
where a direction string would name a slot again.
The accepted cost is that fragment links made
when the anchors were direction strings —
bookmarks and pasted URLs, no longer anything in the tree —
land at the top of the right battle page;
the battle URL itself is unchanged.

**A warrior keeps its side and color.**
The battle's canonical order gives each warrior a side of the page and a color,
and every block reads its warriors in that order:
the summary rows, the versus header,
and the scores inside each game block.
A reader's eye then follows one warrior down the page,
and the two game blocks, side by side, compare at a glance.
Prompt order stays visible in each game block's header,
where it is a fact about that game,
instead of being the order of the score rows.
The rejected alternative, score rows in prompt order,
puts a warrior on opposite sides of two adjacent game blocks,
and the colors then contradict the positions.

**Color and graphics only repeat the text.**
The page targets WCAG 2.2 AA,
so nothing on it is told by color or shape alone:
every colored dot or bar sits beside a name and a number,
the bars are hidden from screen readers,
and highlighted text is underlined as well as tinted.
Explanations of the numbers are visible text, not tooltips,
which keyboard and touch users cannot reach.
