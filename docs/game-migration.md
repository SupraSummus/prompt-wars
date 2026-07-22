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
a battle's score averages the two directions
(`BattleViewpoint.score`),
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
`GameScore` re-keys from (battle, direction, algorithm)
to (game, algorithm) —
its similarity fields are already in game order,
so no values move.

**Deliberate duplication stays.**
`llm` and `scheduled_at` live on both `Battle` and `Game`
(asserted equal in `resolve_battle`, `warriors/tasks.py`):
pair-level queries (matchmaking, stats) read the battle's copy,
game-level processing reads the game's.
Collapsing the duplication is possible after the dust settles
but is not part of this migration.

## Steps

Each step ships independently
and is old-code-compatible for one release:
a writer starts writing a field at least one release
before any reader depends on it,
and a column is dropped at least one release
after the last reader leaves.
While a dual-write holds,
rolling back a reader flip is a code revert with no data repair.

### 1. Link games to their battle

Add a nullable `battle` foreign key to `DBGame`,
written in `Battle.create_from_warriors`;
backfill historical rows by the (llm, warriors, scheduled_at) match
the backfill script already uses —
the same triple rejected above as a pairing *key*,
acceptable for a one-time match because
enforcing not-null and unique (battle, warrior_1) right after
surfaces any ambiguous rows for manual resolution.
This replaces implicit pairing with an explicit one
*before* anything starts reading game rows,
and lets `resolve_battle` locate its game by battle and direction
rather than only via `processed_goal`.

### 2. Verify the shadow copy and make it mandatory

A management command walks every battle direction
and compares all mirrored fields against the game row —
the per-request assertions in `resolve_battle`, made exhaustive —
creating any missing rows
(this absorbs and replaces the root-level `tmp.py` scratch script,
which gets deleted).
With the table verified complete,
`resolve_battle` stops tolerating a missing game row:
the `DBGame.DoesNotExist` branch goes away
(test factories already create game rows alongside battles).

### 3. Invert write authority

`resolve_battle` and `_run_llm` currently treat
the `Game` facade over `Battle` as primary
and mirror results into the game row.
Flip it: the game row is the object the resolution task
loads, mutates, and saves,
and the battle's directional columns become the mirror.
The facade's attribute names already match the game row's fields,
so the resolver body barely changes —
only which object is authoritative and which is the copy.
After this step the directional columns are write-only,
the same state the `lcs_len_*` columns were in before removal.

### 4. Re-key GameScore

Add a nullable `game` foreign key to `GameScore`,
dual-written in `get_or_create_game_score` (`warriors/score.py`);
backfill from (battle, direction);
move the uniqueness to (game, algorithm).
`_ensure_score` then reads the game row directly —
warriors, result text unit, finish reason —
instead of constructing the battle facade.
`direction` and `battle` drop from `GameScore`
once nothing selects by them.

### 5. Cut the remaining readers over

In order of blast radius:

- **Rating** (`WarriorArena.update_rating`,
  `warriors/rating_models.py`):
  iterate battles as today,
  but hydrate each viewpoint from the battle's two game rows
  and their (game, algorithm) scores,
  instead of the directional columns and direction-keyed scores.
  The score-averaging semantics are unchanged.
- **Views and templates**:
  `BattleDetailView`, `RecentBattlesView`,
  and the warrior-detail battle list keep their battle-level shape,
  prefetching games and scores through the battle.
  Templates already think in per-direction games
  (`templates/warriors/partials/game.html`),
  so a thin viewpoint wrapper over (battle, game, game)
  preserves the template contract
  while `BattleViewpoint`'s string-rewriting field maps disappear.
- **Matchmaking and stats**: no change —
  cooldown, opponent exclusion, and `battle_count`
  are pair-level and stay on `Battle`.

### 6. Drop the directional columns

Delete the paired columns from `Battle`
(`input_sha256_*`, `text_unit_*`, `finish_reason_*`,
`llm_version_*`, `resolved_at_*`, `attempts_*`),
the step-3 mirror writes,
and the facade machinery that mapped suffixed names.
Same shape as the `lcs_len_*` removal.
The dead `rating_transferred_at` column
(tracked in `TODO.md`) rides along.

### 7. Rename

With the in-memory `Game` facade deleted in step 6,
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
rating reads change *representation* here (step 5),
not which signal feeds them.

## Open decisions

- **How long the battle header keeps `llm`/`scheduled_at`**
  once the ranking registry lands and pair-level queries
  are revisited; until then the duplication is deliberate.
- **`warriors_similarity` is stored once per direction**
  in `GameScore` though it is symmetric per (battle, algorithm);
  correct home is a per-battle score object,
  which is not worth introducing during this migration.
