# Gameplay data model: one battle stream, rankings over it

This doc owns the design-level reading of the gameplay data model:
which concern each model carries,
why the ladder is one pool of battles across models,
and why rankings are code rather than rows.
Mechanics live in code (`warriors/`);
this doc is about what the schema should mean.

## Four concerns

Gameplay decomposes into four independent axes:

1. **Which LLM performs the battle** —
   drawn per ladder battle from `LADDER_LLMS` (`warriors/battles.py`)
   and recorded on `Battle` and `Game`.
2. **Warrior–result similarity** —
   `GameScore` rows keyed by (game, algorithm),
   with `ScoreAlgorithm` an enum (`warriors/score.py`).
   Every game gets a score row for every algorithm
   (see `resolve_battle` in `warriors/tasks.py`).
3. **Winner computation** —
   pure code deriving a score from the similarities,
   per algorithm (`GameScore.score` in `warriors/score.py`).
4. **Leaderboard rating** —
   mELO state on `WarriorRating`, keyed by (warrior, ranking)
   (`warriors/rating_models.py`).

Each is an enum or code;
no database row encodes a combination of them.

Not every battle in the stream feeds the ladder.
Unrated battles, King of the Hill's, are played and scored,
but the ladder never reads them;
`BattleQuerySet.rated` draws the line.

## The ladder is one pool across models

A ladder battle goes to one model, drawn at random,
and a warrior's rating reads every battle it fought,
whichever model answered (`BattleQuerySet.with_warrior`).
The matchmaking cooldown is per pair, across models, too.
So a prompt is measured by how it does over the draw,
not on the one model it was tuned for,
and the set of models is a dial on cost per battle,
not on how many battles are fought.

`LLM` names a model, never a pool:
the draw is what pools battles,
so a value that meant "the hill's battles" or "this ranking's battles"
would be a second, hidden pooling mechanism.

Battles fought before the draw were pinned to one model each,
so a long-lived warrior's history leans on that model.
They count as if drawn;
`update_rating` keeps only the most recent battle with each opponent,
so fresh drawn battles displace them without special handling.

Rejected alternatives:

- **Every battle resolved by every model.**
  It multiplies the cost of a battle by the number of models
  for a signal the draw gives on average,
  and makes adding a model a decision about volume.
- **A model set per leaderboard.**
  Leaderboards with different sets could not share a battle,
  which splits the pool back into per-model ladders.

## Rankings in code

A leaderboard is a *view* over the battle stream,
not a place where warriors live.
`Ranking` (`warriors/rankings.py`) lists them,
each reading the stream through a score algorithm,
and every one ranks every battle:
`transfer_rating` refits both warriors in each.

Adding a ranking takes code anyway —
a new algorithm, or new parameters for one —
so a database row naming the combination
would buy only a way to configure one nobody reviewed,
such as two rows with the same algorithm:
two rating states converging over the same battles.
The cost is that a ranking cannot be switched on or off without a deploy.

The rankings are peers.
Each battle pairs warriors by their rating in a ranking drawn for it
(`schedule_battle`, `schedule_battle_top`),
so every ranking gets battles between warriors it rates alike.
Players see them side by side:
each has its leaderboard (`/leaderboard/<ranking>/`),
and a warrior's page shows its rating in all of them,
its battle list read through the one asked for.
`LEADING_RANKING` is only where a page showing one ranking opens.

## One clock per warrior

The matchmaking clock is `Warrior.next_battle_schedule`:
one per warrior, whatever the number of rankings,
so adding a ranking never multiplies battles.
Its pace comes from the warrior's battle count (`create_battle`);
`WarriorRating.games_played` is a different number,
the opponents a rating's last fit read,
and matchmaking does not read it.

A warrior with no clock is off the ladder:
a King of the Hill attacker plays only the hill,
and submitting a text through the prompt form puts it on.
Going on the ladder starts the clock and gives a rating in every ranking at once (`enter_ladder`),
the one place either happens,
so the rest of the code reads ratings and never creates them.
A ranking added later needs its rows backfilled for the warriors already there,
and a `refit_ratings` run to fit them.

## Arena-era URLs

Links of the forms `warrior-arena/<id>/` and `arena/<id>/…`
circulate outside the site,
each naming a page of a per-arena warrior or of an arena.
`LegacyWarriorArena` keeps every warrior-arena id and the warrior it names,
so each leads to the warrior's page;
an arena URL redirects to the page that serves every ranking.
