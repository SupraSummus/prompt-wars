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
The fill waits for the battle's directional columns to drop:
filling only the game side of a live mirror
reads as a `conflicting input_sha256` finding.
Next move: once the columns are gone,
a repair command that recomputes the sha from the warrior bodies
(the way the root-level `backfill_sha.py` derives it)
onto blank game rows.
`backfill_game_input_sha256` goes with the columns it copies from.

`backfill_game_score_game` is a one-time re-keying,
not an ongoing repair:
it links the `GameScore` rows written before the `game` column existed
to the game row their (battle, direction) pair already names.
Delete it once a production run reports zero still unlinked —
the same condition that lets the column go not-null
in step 1 of `docs/game-migration.md`,
so the two land together.

Every test that builds a `Battle` has to sort the warrior pair first,
because `BattleFactory` passes its two `SubFactory` warriors through
in the order given and the `warrior_ordering` check constraint
demands the smaller id first —
so a bare `BattleFactory()` fails about half the time,
and five call sites
(`warriors/tests/fixtures.py` twice, `batch_create_battles`,
`create_mirrored_battle`, and the rating tests)
repeat the same three-line swap.
Next move: swap the pair in a `_adjust_kwargs` classmethod on the factory
and delete the swaps at the call sites;
behavior-preserving for every test that already sorts.

The `thinking_config` that `call_gemini` sends (`warriors/llms/google.py`)
buys thinking but does not bound it:
`gemini-flash-lite-latest` resolves to a Gemini 3 model,
which treats the budget as a hint and reasons into the low thousands of tokens
whatever number it is given,
while `thinking_budget=0` is rejected outright with a 400.
`max_output_tokens` is the only real cap,
and reasoning shares it with the answer,
so a reasoning-heavy pair of warriors can spend the whole cap thinking
and resolve as an error.
The dial that does work is binary —
sending no `thinking_config` at all stops the thinking
on every prompt measured — which is a change to battle outcomes,
so it needs sign-off, as does trading the budget for `thinking_level`.
Next move: pick one and record the reasoning
in the reasoning-tokens item of `docs/strategy.md`,
which owns why the spend is deliberate.

The three connectors (`warriors/llms/`) each spell out the same policy
in their own provider's dialect:
rate limit to `RateLimitError`, server and transport failures
to `TransientLLMError`, everything else out raw,
and — for the two that reason — a token limit reached with less than
`MAX_WARRIOR_LENGTH` of text downgraded to the `'error'` sentinel.
Nothing names that contract or that sentinel in one place,
so the defenses get audited and repaired one provider at a time;
anthropic has no downgrade at all,
having no reasoning that can run past its cap.
Next move: state the `(text, finish_reason, llm_version)` contract
and the meaning of `'error'` where the shared exceptions live
(`warriors/llms/exceptions.py`),
and give the downgrade one home the connectors call.

`call_llm` (`warriors/llms/openai.py`) talks to the same endpoint as
`resolve_battle_openai` but shares none of its defenses:
no `RateLimitError`/`TransientLLMError` mapping,
so a rate limit or a 502 escapes raw from the `ensure_name_generated` goal
and fails it outright instead of earning the retry
`resolve_battle` gets for the identical condition;
and it hands `message.content` straight to `generated_name.strip()`
in `generate_warrior_name` (`warriors/warriors.py`),
which is `AttributeError` for the null content the schema allows.
Nothing covers the function.
Next move: wrap the call in the same two `except` clauses,
have `ensure_name_generated` return `RetryMeLater` for them,
default the content to `''`,
and cover all three with `respx` mocks next to the battle tests.
This changes behavior — a failed name generation starts retrying — so it needs sign-off.

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

`verify_games` skips a direction whose game row has no `resolved_at`,
which leaves `llm` and `scheduled_at` unchecked
on exactly the rows `resolve_battle`'s asserts act on:
those two are set when the pair is created, not at resolution,
so an unresolved direction can hold a drifted copy
and the audit will not say so.
The same skip hides a battle column
that records a resolution its game row lacks —
the shape the pre-mirror repair left behind.
Next move: split the comparison —
the creation-time fields (`llm`, `scheduled_at`, the warrior pair)
on every direction,
the resolution fields once either side records a resolution.
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
`create_game_score.py` and `set_game_score.py` key `GameScore`
on (battle, direction), which the re-keying in
`docs/game-migration.md` drops out from under them.
Next move: for each, decide between
a management command next to `warriors/management/commands/verify_games.py`
if the operation is still worth running,
and deletion if it was a one-time fix —
git keeps whichever ones get deleted.
For `backfill_sha.py` the decision is settled:
its recompute-from-bodies logic moves into
the game-row sha repair command (see the `input_sha256` entry),
and the script goes.

The arena-wide half of `battle_nav_urls` (`warriors/views.py`)
picks its battles two ways the warrior-scoped half does not.
It joins `arena__llm` where `llm` is a column on the battle itself,
and `Battle.arena` is nullable,
so a battle with no arena drops out of the walk silently.
It also runs the queryset through `for_user`,
which narrows a signed-in visitor to battles of their own warriors:
the same page then offers different neighbours to different people,
and often none at all to someone reading a stranger's battle,
while an anonymous visitor walks everything.
Next move: filter `llm=battle.llm` directly and drop the `for_user` call,
leaving both halves scoped by nothing but what is being browsed.
Both are behavior changes, so they need sign-off.
