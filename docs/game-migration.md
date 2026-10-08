# Game migration: making the per-direction game the canonical record

This doc owns the plan for the `DBGame`-direction migration
named in the "Target shape" section of `docs/data-model.md`:
the per-direction `DBGame` row
(`warriors/battles.py`, table `warriors_game`)
is the one record of a battle direction,
and takes the plain name `Game`.
Current mechanics live in code;
this doc is about where the design lands and the moves that get there.

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
`GameScore` keys on (game, algorithm),
its similarity fields in game order.

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
The battle holds no sha of its own:
a pair-level copy would add nothing the two game rows lack.
The blank game rows (tracked in `TODO.md`)
are worth filling by that same recomputation.

## Steps

### Rename

`DBGame` becomes `Game`;
nothing else in the code holds that name.
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
