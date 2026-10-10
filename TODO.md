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

`Battle.warrior_performance` (`warriors/battles.py`)
runs both warriors' playstyles through `normalize_playstyle_len`,
which pads an empty playstyle with random values,
and a warrior not yet rated has an empty one.
So the Performance column of the warrior's battle list
shows a different number on every page load
whenever either warrior in the row is unrated.
Next move: have the read path pad with zeros,
or show no performance until both warriors are rated.
Either changes the numbers shown, so it needs sign-off.

The leaderboard, recent-battles and upcoming-battles tables
(`templates/warriors/`) sit bare in the page,
so a table wider than the screen widens the whole page;
the leaderboard does at 320px.
The warrior's battle list shows the fix:
the `overflow-auto` region around its table,
labelled by the heading above it.
Next move: wrap all three the same way
and screenshot each at 320px.

Two first attacks sent at once without a hill session cookie
(two tabs, or a browser without JavaScript to disable the button)
run as two players (`hill.identity.get_identity`):
one is accepted, and if the browser keeps the other's cookie,
the player can neither see their attempt nor send the text again.
Next move, once a player reports it:
carry a signed key in the form for a visitor without one, and have `get_identity` adopt it.

No LLM client sets a timeout sized to its call site.
The Gemini client (`warriors/llms/google.py`) has none:
google-genai passes `timeout=None` unless `HttpOptions.timeout` is set, in milliseconds.
The OpenAI and Anthropic clients run on their SDKs' 600-second timeout and two retries of their own.
One hung call pins a worker thread (`--threads` in `Procfile`), hill battles included,
and the SDK retries run before `_run_llm`'s backoff sees a rate limit.
Next move: give each call site a timeout a little above its slowest normal call
(`GoalProgress.time_taken` in production),
in the shape of `moderation_client` in `hill/tasks.py`;
a Gemini timeout maps to `TransientLLMError` and takes the existing retry path.
Dropping SDK retries changes battle timing, so it needs sign-off.

`do_moderation` (`warriors/tasks.py`) catches nothing around its moderation call,
so a rate limit, a 5xx or a dropped connection fails the goal,
and once django_goals gives up, `moderation_passed` stays None for good:
nothing schedules it again,
and a warrior without a verdict is never `battleworthy`.
It also asserts `moderation_date is None`,
so `hill_crown --warrior` or the admin's take-down action (`WarriorAdmin.take_down`)
on a ladder warrior whose `do_moderation` is still queued records a verdict first
and makes that goal fail:
the warrior never gets its generated name or its embedding.
Next move: move `moderation_client`, `TRANSIENT_MODERATION_ERRORS` and `moderate`
from `hill/tasks.py` to `warriors/llms/openai.py`,
and `record_warrior_moderation` next to `Warrior`, as the one writer of its verdict;
have `do_moderation` use both and answer transient errors with `RetryMeLater`;
add a repair command that re-schedules moderation for warriors whose goal gave up with no verdict,
and log here the condition for deleting it.
Retrying instead of giving up changes ladder behavior,
so it needs sign-off.

A Voyage embedding that fails on anything but a rate limit is lost for good:
`_ensure_voyage_3_embedding` (`warriors/embeddings.py`) retries only `voyageai.error.RateLimitError`,
and `schedule_voyage_3_embedding` never schedules again once a goal is set, given up or not.
Every EMBEDDINGS `GameScore` waiting on the embedding stays empty,
and the resolve goal waiting on that score never reaches `AllDone`;
King of the Hill reads scores before goal states because of this (`hill.status.attempt_status`).
The client also has no timeout, so a hung call holds a worker thread.
Next move: answer the SDK's server, connection and timeout errors with the same `RetryMeLater`,
pass the client a `timeout`,
have `schedule_voyage_3_embedding` schedule afresh when the existing goal gave up,
and re-schedule the stuck rows with a repair command,
deleted once no EMBEDDINGS `GameScore` waits on a given-up goal.
Retrying a 5xx is a behavior change, so it needs sign-off.

Pasting a King of the Hill text into the ladder's `/create/` form
is a discovery like any other (`WarriorCreateForm.save`, `warriors/create_view.py`):
the paster gets ladder access to the warrior, as a session grant or a `WarriorUserPermission`,
and a `WarriorArena` enrolls it in matchmaking.
Boss texts are public,
so anyone can put any boss on the ladder,
and a logged-in paster who ticks `public_battle_results`
publishes the model's replies in its ladder battles (`update_public_battle_results`);
a guess at a sealed attack's text is told whether it exists.
Hill battles stay unreadable either way:
they are unrated,
so no ladder page lists or opens them.
Next move: in `WarriorCreateForm.clean`,
read the hash with `cleaned_data.get` (`clean_body` may have failed),
and refuse a text whose Warrior is a hill boss, a house boss or has a `HillAttempt`,
unless the requester already holds a grant for it,
checked without `Warrior.is_user_authorized`'s cache (next entry),
with copy that doesn't say whether the text is public;
test that a refusal creates no `WarriorArena` and no grant.
It changes what the ladder accepts,
so it needs sign-off.

`Warrior.is_user_authorized` (`warriors/warriors.py`) sits behind a process-wide `lru_cache`
keyed by the warrior and the user,
and model instances hash by primary key,
so an answer outlives the request that computed it:
a user who opens a warrior, then discovers it through `/create/`,
reads as unauthorized in that process until the entry is evicted
(reproduced: a fresh instance answers False after a `WarriorUserPermission` is created).
Next move: drop the `lru_cache`,
and if the warrior and battle pages' query counts suffer,
memoize on the instance in a dict keyed by user id,
which lives no longer than the request.
It changes who reads as authorized,
so it needs sign-off.

An anonymous GET of `/challenge/<id>/` (`ChallengeWarriorView`, `warriors/views.py`) is a 500:
`ChallengeWarriorForm` filters its choices by `warrior__users=self.user`,
and rendering them with `AnonymousUser` raises `ValidationError`
("“AnonymousUser” is not a valid UUID").
The link shows only for signed-in users, but nothing stops the request.
Next move: `LoginRequiredMixin` on the view,
with a test that an anonymous visitor is sent to log in.

`RECAPTCHA_PUBLIC_KEY` and `RECAPTCHA_PRIVATE_KEY` default to Google's published test keys
(`llm_wars/settings.py`), which pass every captcha,
and the `django_recaptcha` system check that would flag them is silenced.
A production environment missing either variable
therefore runs with no captcha and says nothing:
the ladder's create form and King of the Hill's first attack in a round
let every robot through.
Next move: fall back to the test keys only when an explicit setting asks for them,
set in `example.env`, which development and CI copy,
and silence the check only then,
so a deploy without keys fails the system checks `migrate` runs at `postdeploy`.
Failing a deploy that lacks the keys is a behavior change, so it needs sign-off.

The hill tells an outage from a bad reply by counting retries:
`hill.status._ran_out_of_retries` reads `finish_reason == 'error'` with `game.attempts > MAX_TRANSIENT_RETRIES`,
because `_run_llm` (`warriors/tasks.py`) stores the same 'error' for both.
If `_run_llm`'s retry comparison changes, outages silently become charged failures,
and the hill tests build games with `attempts=` directly, so they would not notice.
Next move: have `_run_llm` store a distinct finish reason when it gives up,
check that in `hill.status`, and keep `MAX_TRANSIENT_RETRIES` private to `warriors.tasks`.
It changes the Finish chip on ladder battle pages, so it needs sign-off.

`embedding_explorer` imports `requests` (`models.py`, `voyage.py`),
which `pyproject.toml` doesn't list:
it is installed only because `google-genai` and `voyageai` depend on it,
so dropping or replacing either would break the import at startup.
Next move: add `requests = "*"` to `pyproject.toml` and run `poetry lock`,
which leaves the locked versions as they are.

Saving "Make the model's replies public" on a prompt's all-arenas page (`warriors/warrior_view.py`) is a 404:
the form posts a `Warrior` id to `warrior_set_public_battle_results` (`warriors/views.py`),
which looks the permission up by a `WarriorArena` id;
its only test posts a `WarriorArena` id.
The checkbox is also written out by hand there and in `warriorarena_detail.html`,
while `PublicBattleResutsForm` (sic) only validates.
Next move: key the endpoint by `Warrior` id,
render the checkbox from that form in one partial used by both pages,
and test a post from the all-arenas page.
Changing what the URL takes changes behavior, so it needs sign-off.

`Game.result` and `Game.result_marked_for` (`warriors/battles.py`) hold what CONCEPT.md "Vocabulary" calls the reply,
and the `result`, `marked_result` and `result_visible` keys
that `game_block` (`warriors/views.py`) and `hill.display.battle_view` hand to templates
are named after them.
`result` is a property, so renaming needs no migration.
Next move: rename them to `reply`, `reply_marked_for` and so on,
then drop `Game.result` from the code's own names in the Vocabulary section.
