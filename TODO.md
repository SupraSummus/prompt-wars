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

The `game` foreign key on `GameScore` (`warriors/score.py`)
carries an index nobody reads:
it is a prefix of `unique_game_algorithm`,
which Postgres answers the foreign key's own lookups from,
so every insert and update on the table
writes a second index entry for nothing.
The one bulk measurement of the cost covers two indexes,
this one and the (battle, direction, algorithm) index beside it:
dropping both took a million-row update over this table
from 54s to 40s.
Only this one is left, so the win left to take is part of that.
Next move: set `db_index=False` on the field
and migrate the index away;
behavior-preserving.

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

`moderation_experiment.py` sits at the repo root,
a scratch run against the OpenAI moderation endpoint
imported by hand in a shell, outside any app,
untested and unreachable from `manage.py`.
Next move: delete it, which git keeps,
unless the experiment is worth rerunning,
in which case it becomes a management command
in `warriors/management/commands/`.

The arena walk in `battle_nav_context` (`warriors/views.py`)
picks its battles two ways the warrior walk beside it does not.
It joins `arena__llm` where `llm` is a column on the battle itself,
and `Battle.arena` is nullable,
so a battle with no arena drops out of the walk silently.
It also runs the queryset through `for_user`,
which narrows a signed-in visitor to battles of their own warriors:
the same page then offers different neighbours to different people,
and often none at all to someone reading a stranger's battle,
while an anonymous visitor walks everything.
Now that the arena walk is the one nav every battle page carries,
that is the difference between a page with neighbours and a dead end.
Next move: filter `llm=battle.llm` directly and drop the `for_user` call,
leaving both walks scoped by nothing but what is being browsed.
Both are behavior changes, so they need sign-off.

A score is drawn two ways.
The battle page uses `warriors/partials/score_bar.html`,
a number beside a bar,
whose styles sit in the `head` block of `battle_detail.html`.
The warrior's battle list (`warriorarena_detail.html`)
still uses `score.html`,
a red/green `<meter>` with no visible number,
which also says "good/bad" by color alone.
Next move: move the bar styles and `.pw-sr-only` into `base.html`,
switch the warrior list to `score_bar.html` with a neutral bar color,
and delete `score.html`.
It changes what the list looks like, so it needs sign-off.
