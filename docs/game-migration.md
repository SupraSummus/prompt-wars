# Game migration: making the per-direction game the canonical record

This doc owns the plan for the `DBGame`-direction migration
named in the "Target shape" section of `docs/data-model.md`:
retiring `Battle`'s paired directional columns
in favor of the per-direction `DBGame` row
(`warriors/battles.py`, table `warriors_game`),
which then takes the plain name `Game`.
Current mechanics live in code;
this doc is about the order of the moves and why that order.

## Where the design lands

**`Battle` survives as a matchup header.**
The pair of games is a real domain object, not an artifact:
a battle's score averages its games
(`Battle.warrior_score`),
the matchmaking cooldown and opponent-exclusion queries
operate on the warrior *pair*
(`BattleQuerySet.with_warrior_arena`, `recent`),
`ArenaStats.battle_count` counts pairs,
and the battle page URL (`battle_detail`) is public and stable.
The rejected alternative — no battle row, games pairing implicitly
by (llm, warriors, scheduled_at) —
makes every one of those consumers reconstruct the pair
from a coincidence of column values,
and the triple is not guaranteed unique.
So the endpoint is the classic normalization:
`Battle` keeps identity, llm, scheduled time,
and the canonically-ordered warrior pair;
`Game` carries everything per-direction
(result text unit, finish reason, llm version,
resolution time, attempts, its processing goal)
plus a foreign key to its battle.

**Direction becomes derivable, not stored.**
A game's warriors are in prompt order,
so comparing `game.warrior_1_id` with `battle.warrior_1_id`
recovers the direction;
uniqueness is (battle, warrior_1).
`GameScore` keys on (game, algorithm)
rather than (battle, direction, algorithm) —
its similarity fields are already in game order,
so no values moved.

**Deliberate duplication stays.**
`llm` and `scheduled_at` live on both `Battle` and `Game`
(asserted equal in `resolve_battle`, `warriors/tasks.py`):
pair-level queries (matchmaking, stats) read the battle's copy,
game-level processing reads the game's.
Collapsing the duplication is possible after the dust settles
but is not part of this migration.

**`Game` keeps `input_sha256`.**
Nothing reads it in production;
it stays as a consistency anchor:
a future audit can recompute the sha from the warrior bodies
and compare,
catching a drifted body
or a resolution recorded against different inputs.
The rejected alternative — dropping it as derivable —
misses that derivability is what makes the check possible:
a value that is only ever recomputed
can never disagree with anything.
The battle's directional pair carries no extra information
and drops with the other paired columns.
The blank game rows (tracked in `TODO.md`)
become worth filling by that same recomputation —
but only once those columns are gone:
filling one side of a live mirror
reads as a `verify_games` finding,
and filling both sides writes columns that are about to drop.

## Steps

Each step ships independently
and is old-code-compatible for one release:
a writer starts writing a field at least one release
before any reader depends on it,
and a column is dropped at least one release
after the last reader leaves —
so the readers having moved is not yet licence to drop.

Every step rests on one invariant:
a battle direction always has its game row,
and the two agree while both copies exist.
`Battle.create_from_warriors` writes battle and both games
in one transaction,
`resolve_battle` loads the row unconditionally
by the unique (battle, warrior_1),
and the test factory creates both rows with every battle.

The game row is what `resolve_battle` writes;
the battle's directional columns are its mirror
(`mirror_to_battle`, `warriors/battles.py`).
Nothing reads them any more —
rating, the battle page, and the battle lists
all ask the game rows and the (game, algorithm) score rows —
so what is left holding them is the mirror that writes them
and the audit that compares them,
which is the state that reduces dropping them to a code change,
as it did for `lcs_len_*`.

Checking that invariant and repairing it stay apart.
The `verify_games` audit writes nothing
and reports by category rather than by row
(its docstring says why).
Each repair is its own command, named for what it repairs,
deleted once a production run leaves nothing to do:
`backfill_game_input_sha256` for `backfill_sha.py`
having written the battle's sha and not the game's.
A finding nothing explains is a bug to chase, not data to copy over.

### 1. Drop the directional columns

Not while `verify_games` still reports a finding:
after this the game row is the only copy,
so anything it lacks is lost here.

Delete the paired columns from `Battle`
(`input_sha256_*`, `text_unit_*`, `finish_reason_*`,
`llm_version_*`, `resolved_at_*`, `attempts_*`),
the `mirror_to_battle` calls in `resolve_battle`,
and the facade machinery that mapped suffixed names.
The command goes with the columns —
it compares game rows against columns that no longer exist,
and `mirrored_game_fields` has nothing left to map.
`BattleFactory`'s game hook mirrors through that same function,
so it builds its two rows directly from then on.
Same shape as the `lcs_len_*` removal.
The dead `rating_transferred_at` column
(tracked in `TODO.md`) rides along.

`GameScore.battle` and `GameScore.direction` drop here too.
They carry no key any more —
the uniqueness and the lookup sit on (game, algorithm) —
and `direction`'s last reader goes in this same step:
the audit's own re-derivation of the score link, with the command.
`battle` has one live reader to move first:
every page prefetches score rows as `game_scores__game`
and `Battle.score_object` picks out of that list,
so the read path becomes `games__scores`,
and `GameScore.score_for` — which asks its own `game`
for the warrior order — is reached from the game that holds it.

### 2. Rename

With the in-memory `Game` facade gone with the columns,
the name is free:
`DBGame` becomes `Game`.
The table is already `warriors_game`,
so the migration is state-only — no DDL.
This closes the "rename to Game" TODO in `warriors/battles.py`.

## Interaction with the arena decoupling

`docs/data-model.md` sequences a broader migration
(dropping `Battle.arena`, the ranking registry,
re-keying the matchmaking clock).
This plan is one of its independently-shippable tracks
and orders only its own steps;
dropping `Battle.arena` can land any time,
and the ranking-registry work is untouched by it —
rating reads a different *representation* of the same signal,
not a different signal.

## Open decisions

- **How long the battle header keeps `llm`/`scheduled_at`**
  once the ranking registry lands and pair-level queries
  are revisited; until then the duplication is deliberate.
- **`warriors_similarity` is stored once per direction**
  in `GameScore` though it is symmetric per (battle, algorithm);
  correct home is a per-battle score object,
  which is not worth introducing during this migration.
