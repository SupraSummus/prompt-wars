# Games: a battle's per-direction records

This doc owns why a battle is stored
as a `Battle` header over two per-direction `Game` rows
(`warriors/battles.py`).
Mechanics live in code.

## Why a battle row

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
So the battle holds what the pair shares,
and each game what its direction produced.

## Why `Game` keeps `input_sha256`

Nothing reads it in production;
it is a consistency anchor:
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

## Open decisions

- **`llm` and `scheduled_at` live on both the battle and its games**
  (asserted equal in `resolve_battle`, `warriors/tasks.py`):
  pair-level queries (matchmaking, stats) read the battle's copy,
  game-level processing reads the game's.
  Whether the battle keeps its copy is worth revisiting
  once the ranking registry changes the pair-level queries.
- **`warriors_similarity` is stored once per direction**
  in `GameScore` though it is symmetric per (battle, algorithm);
  its natural home is a per-battle score object,
  and whether one column justifies that object is open.
