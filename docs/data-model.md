# Gameplay data model: what arenas couple, and the direction out

This doc owns the design-level reading of the gameplay data model:
which concern each model actually carries,
where the arena concept couples independent concerns,
and the proposed target shape.
Mechanics live in code (`warriors/`);
this doc is about what the schema should mean.

## Four concerns, mostly separated already

Gameplay decomposes into four independent axes:

1. **Which LLM performs the battle** —
   the `LLM` enum on `Battle` and `DBGame` (`warriors/battles.py`).
2. **Warrior–result similarity** —
   `GameScore` rows keyed by (battle, direction, algorithm),
   with `ScoreAlgorithm` an enum (`warriors/score.py`).
   Every game gets a score row for every algorithm,
   regardless of any arena's configuration
   (see `resolve_battle` in `warriors/tasks.py`).
3. **Winner computation** —
   pure code deriving a score from the similarities,
   per algorithm (`GameScoreViewpoint.score` in `warriors/score.py`).
4. **Leaderboard rating** —
   mELO state on `WarriorArena` (`warriors/rating_models.py`).

The first three are already enum-keyed or code-level:
no DB object encodes a combination of them.
Battles are keyed by LLM, not by arena —
`Battle.arena` exists but is nullable and vestigial;
every gameplay query goes through `llm`
(`BattleQuerySet.with_warrior_arena`, matchmaking cooldown,
`ArenaStats.battle_count`),
and `DBGame`, the newer model, has no arena at all.
Only the fourth concern hangs off a DB combination object:
`Arena` binds (llm, score_algorithm) as a row,
and `WarriorArena` keys rating state by it.

## The one bag of warriors already exists — implicitly

`Warrior` is global:
body, moderation, ownership, and embedding
live on the shared object,
and `WarriorArena` is a thin per-arena shell
(rating state, `games_played`, `next_battle_schedule`,
plus delegating properties).

Cross-arena spread happens automatically within an LLM:
`transfer_rating` (`warriors/tasks.py`) fans a battle's result
out to every arena with the same llm,
lazily creating `WarriorArena` rows via
`get_or_create_warrior_arenas`,
battle-eligible in that arena immediately.
So "submit once, play everywhere" is the de facto behavior
for arenas sharing an LLM —
but as a side effect of rating transfer,
not as a stated rule,
and with quirks that follow from the accident:

- **Duplicate matchmaking clocks.**
  Each same-llm arena keeps an independent
  `next_battle_schedule` for the same warrior,
  all feeding one shared battle pool,
  so a warrior's battle frequency scales with
  how many arenas share its LLM.
- **Veterans jump the queue once.**
  A lazily created row is battle-eligible immediately,
  so an old warrior crossing into another arena
  gets one out-of-cadence battle
  before `create_battle` recomputes `games_played`
  from the llm-wide count and restores its cadence.
- **Nonsense configurations are expressible.**
  Two arenas with identical (llm, score_algorithm)
  are two independent rating states
  converging over the same battle set.

The explicit version of cross-arena submission,
`ensure_warrior_on_all_arenas` (`warriors/cross_arena.py`),
is unreferenced and incompatible with the schema —
evidence the implicit mechanism displaced it
without the model being restated.

## What Arena actually earns its keep for

Presentation and operations, not gameplay:
a name and description,
a `Site` binding for domain-based routing
(`ArenaViewMixin` in `warriors/views.py`),
and the `listed`/`enabled` toggles.
Those are CMS concerns;
the only gameplay decision an arena makes
is which similarity signal feeds the rating
(`update_rating` reads `arena.score_algorithm`).

## Target shape

A leaderboard is a *view* over the battle stream,
not a place where warriors live.
The schema should say so:

- **Warrior** stays the global unit of submission —
  one bag, entered once.
- **The battle stream is keyed by LLM** (already true);
  `Battle.arena` gets dropped,
  and the `DBGame`-direction migration
  makes the per-direction game the canonical record
  (plan: `docs/game-migration.md`).
- **Ranking configuration moves to code**:
  a registry mapping a ranking key (enum)
  to (llm, score_algorithm, mELO parameters).
  Combinations become code review material,
  not runtime rows;
  nonsense configurations become unrepresentable.
- **Per-warrior rating state is keyed by (warrior, ranking key)** —
  the successor of `WarriorArena`,
  stripped to rating fields and `games_played`.
- **The matchmaking clock is keyed by (warrior, llm)** —
  one clock per battle pool,
  so adding a ranking never multiplies battles.
- **Arena survives, if at all, as pure presentation**:
  a page (or DB row, for deploy-free `enabled`/`listed` flips)
  that binds name, description, and site to a ranking key,
  carrying no gameplay state.

## The one genuine open decision: which LLMs does a warrior enter?

Today the arena a player submits through
selects the LLM pool the warrior battles in
(spread to other pools happens only via same-llm arenas).
With one bag and rankings-as-views,
the natural rule is "a submission enters every battle pool" —
but that multiplies battle volume by the number of LLMs,
which is a cost decision, not a schema decision
(see the economic frame in `docs/strategy.md`).
Options, in increasing cost:
keep per-LLM enrollment as an explicit player choice;
enroll everywhere but with per-LLM cadence dialed down;
enroll everywhere at full cadence.
The rounds proposal (`docs/rounds.md`) cuts across this:
under fixed-cadence rounds,
per-round participation is the enrollment mechanism anyway.

## Migration is incremental

Each step is independently shippable:
deleting the dead `warriors/cross_arena.py` module;
keying the matchmaking clock by (warrior, llm);
introducing the ranking registry
and pointing `update_rating` at it instead of `arena.score_algorithm`;
backfilling and dropping `Battle.arena`;
reducing `Arena` to presentation.
Nothing requires a big-bang rewrite,
because battles, scores, and winner computation
are already keyed the right way.
