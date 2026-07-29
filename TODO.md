# TODO

A running registry of open technical debt —
things worth improving but outside the scope
of whatever is currently being worked on.
Spot a rough edge while working on something else —
a sketchy pattern, a dead branch, drifted duplication, a missing test?
Log it here instead of fixing it inline (scope creep)
or burying a `# TODO` in code (invisible outside that file).
Glance at this file before starting new work;
it doubles as a map of where the rough edges are.

Registry, not changelog:
when an entry is resolved — or turns out to be wrong or outdated —
delete it in the same commit.
Never strike it through or mark it "done";
git history is the changelog.
The file only ever contains open items.

One paragraph per entry, separated by blank lines —
no bullets, no numbering, no headings.
Adding or removing an entry then yields a clean, minimal diff
that doesn't reflow its neighbors.
Write each entry concretely enough that someone can pick it up cold,
and name a concrete next move — what the fix would actually look like.
"Verify someday" is a hope, not a next move.

Belongs here: refactors, dead code, inconsistencies,
missing tests, sketchy patterns.
Does not: game-design ideas and open design questions —
those live in `CONCEPT.md` or `docs/`, next to their rationale.
Nor work that lives outside the tree —
GitHub settings, hosting config, third-party dashboards;
an entry belongs here only if a commit to this repo can resolve it,
because nothing else can ever close it.
Prefer behavior-preserving noticings;
when an entry implies a behavior change, say so,
since it will need sign-off.

---

`CONCEPT.md` restates the battle mechanics implemented in `warriors/` —
the prompt-concatenation flow, the LCS scoring steps,
and the normalization formula —
against the "docs must not repeat what the code already says" rule
in `AGENTS.md`
(adopted after the doc was written,
so this is expected backlog, not a violation).
The copies have already drifted:
the doc presents LCS as the only scoring,
while `warriors/score.py` has a second `EMBEDDINGS` algorithm
selectable per arena (`Arena.score_algorithm`).
Next move: keep the concept-level narrative
("make the LLM reproduce your text while ignoring the opponent's")
and move the mechanical detail into docstrings at the source,
leaving the doc pointing at `warriors/battles.py`
and `warriors/score.py` by name.

`warriors/cross_arena.py` is dead code and no longer matches the schema:
`ensure_warrior_on_all_arenas` has no callers,
and it passes `WarriorArena.objects.get_or_create` fields
(`body_sha_256`, `body`, `created_at`, …)
that moved to `Warrior` in migrations 0030–0034,
so calling it would raise.
Its role is filled implicitly by `transfer_rating` in `warriors/tasks.py`
(see docs/data-model.md).
Next move: delete the module and its test file `cross_arena_tests.py`.

`get_performance_rating` in `warriors/rating.py` returns
start-position-dependent results even where the loss is convex:
with `gtol=1e-6` and the loss gradient scaled by `log(10)/400/n`,
L-BFGS-B terminates up to ~0.2 rating points away from the optimum,
and the unseeded random starting position decides where in that band
each call lands (measured spread ±0.22 over 2000 runs
on the `rating_tests.py` fixture data).
Tightening `gtol` to `1e-8` shrinks the spread below 0.01
at the cost of a few more optimizer iterations (verified empirically);
that changes the ratings the site computes,
so it needs sign-off as a behavior change.
Doing it would also let the widened tolerance
in `rating_tests.py::test_get_performance_rating` tighten back.

`Battle.rating_transferred_at` is a dead column:
nothing writes or reads it —
only a "not used anymore" comment in `warriors/battles.py`
and a passthrough entry in `BattleViewpoint.map_field_name`
keep it in the code.
Next move: drop the field, the comment, and the mapping entry,
same shape as the `lcs_len_*` column removal;
implies a schema migration but no behavior change.

`Game.input_sha256` stays as a consistency anchor
("Where the design lands" in `docs/game-migration.md`),
which makes the 34 game rows with a blank sha worth filling.
They are blank because their battle has no sha either,
so `backfill_game_input_sha256` has nothing to copy,
and `verify_games` cannot see them —
blank on both sides compares equal.
The fill waits for step 4 to drop the battle columns:
filling only the game side of a live mirror
reads as a `conflicting input_sha256` finding.
Next move: once the columns are gone,
a repair command that recomputes the sha from the warrior bodies
(the way the root-level `backfill_sha.py` derives it)
onto blank game rows.
`backfill_game_input_sha256` goes at step 4
with the columns it copies from.

The token-limit branch in `resolve_battle_openai`
(`warriors/llms/openai.py`) reads `response.text` and `response.model_version`;
openai's `ChatCompletion` has neither,
so the branch raises `AttributeError`
instead of returning the `'error'` result it means to
whenever the model spends its whole budget on reasoning.
It is a copy of the equivalent branch in `call_gemini`
(`warriors/llms/google.py`), typo in the shared comment included,
where both attributes do exist.
Only a `real_world` test reaches `resolve_battle_openai`,
so nothing exercises the branch.
Next move: return the `result` and `response.model` values
the success path a few lines down already uses,
and cover it with a `respx`-mocked test for `finish_reason == 'length'`,
shaped like the token-limit tests in `warriors/llms/google_tests.py`.

`warriors/embeddings.py` uses the `voyageai` SDK for a single `embed()` call,
and since voyageai 0.5.0 that SDK requires
`langchain-text-splitters`, `tokenizers`, and `pillow` —
so installing it drags in langchain-core, langsmith, and huggingface-hub
to send one HTTP request.
`embedding_explorer/voyage.py` shows the alternative:
the same endpoint called directly with `requests`.
Next move: fold the `voyage-3` request into that module's shape,
drop `voyageai` from `pyproject.toml`,
and map a 429 response to the `RetryMeLater` that
`voyageai.error.RateLimitError` currently triggers —
that exception is the only thing the SDK contributes here.

`verify_games` skips a direction the battle has not resolved,
which leaves `llm` and `scheduled_at` unchecked
on exactly the rows `resolve_battle`'s asserts act on:
those two are set when the pair is created, not at resolution,
so an unresolved direction can hold a drifted copy
and the audit will not say so.
Next move: split the comparison —
the creation-time fields (`llm`, `scheduled_at`, the warrior pair)
on every direction,
the resolution fields only once the battle has resolved it.
The skip exists because `attempts` climbs while a direction retries,
and that is a resolution field.

Five one-off scripts sit at the repo root —
`backfill_sha.py`, `create_game_score.py`, `set_game_score.py`,
`gemini_redo_max_tokens.py`, `moderation_experiment.py` —
imported by hand in a shell, outside any app,
untested and unreachable from `manage.py`.
They rot invisibly:
`backfill_sha.py` cites a `verify_ordering.py` that is not in the tree,
and it writes `Battle.input_sha256_*` without the matching game rows —
the blanks `backfill_game_input_sha256` exists to fill.
Next move: for each, decide between
a management command next to `warriors/management/commands/verify_games.py`
if the operation is still worth running,
and deletion if it was a one-time fix —
git keeps whichever ones get deleted.
For `backfill_sha.py` the decision is settled:
its recompute-from-bodies logic moves into
the game-row sha repair command (see the `input_sha256` entry),
and the script goes.
