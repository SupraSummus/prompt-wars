# Product strategy

This doc owns the direction-level decisions for Prompt Wars:
what the project is optimizing for,
which bets are worth making, in what order,
and which alternatives are rejected and why.
Mechanics live in code (`warriors/`);
philosophy lives in `docs/parallels.md`;
this doc is about where effort goes.

## The economic frame: survival is cheap, growth is a choice

The project's total burn is on the order of €80/month
(observed 2026-07: ~€50 Scalingo, ~€23 Gemini, ~€9 OpenAI, pennies for Voyage),
and the identified cost levers below bring it to roughly €40/month
without changing how the game plays.
At that level the game runs indefinitely as a self-playing system.

The consequence, and the central decision of this doc:
**development is not an obligation imposed by running costs.**
Keeping the lights on is a fixed, bounded hobby fee;
every feature is built because we want the game to grow,
not because the project bleeds without it.

Where the money actually goes, in order:

1. **Fixed compute, lightly loaded.**
   Two always-on containers serve a workload of roughly one battle
   every three minutes
   (the scheduler runs inside the worker process —
   see the `worker` command in `warriors/management/commands/`
   and `Procfile`).
   Lever: smaller container sizes
   (the constraint is process memory, not load —
   downsize per-container and watch the metrics).
2. **Reasoning tokens — an expense, but a deliberate one.**
   Battle resolution pays for model thinking that never appears in output:
   the Gemini thinking budget in `warriors/llms/google.py`
   and the gpt-5-mini reasoning effort in `warriors/llms/openai.py`.
   These are billed as output tokens and dominate both token bills;
   the visible battle text itself costs single-digit euros per month.
   This spend is not waste:
   a thinking referee is harder to hijack,
   and resistance to manipulation is the game's difficulty setting
   (see the data–instruction separation theme in `docs/parallels.md`).
   The thinking budget is a game-design dial that happens to cost money,
   priced at roughly €15–20/month for a smarter adversary.
   Levers that leave the referee untouched: discounted pricing tiers.
   OpenAI's flex service tier
   (in beta — verify model coverage before relying on it)
   halves the price of the same synchronous call —
   nearly free to adopt
   (one request parameter plus capacity-retry handling
   of the kind `warriors/tasks.py` already does).
   Batch APIs (Google and OpenAI, also half price)
   fit most of the workload —
   battles are async and retry-tolerant —
   but not the fresh-warrior window:
   a new warrior's first games arrive within minutes by design
   (`get_next_battle_delay` in `warriors/random_matchmaking.py`),
   while batch turnaround is best-effort within 24 hours.
   Gemini has no flex equivalent,
   so its half-price path needs either an eligibility split
   (batch only the battles between warriors past the fast window)
   or the rounds redesign (`docs/rounds.md`),
   which turns the scheduled mass into the canonical batch workload.
3. **Everything else is noise.**
   Visible input/output tokens across ~30k LLM calls per month
   cost less than a coffee.

## The product situation: acquisition works, retention is the open question

Observed baseline (2026-07):
roughly 450 battles/day,
~90 warriors created per month — almost all by anonymous visitors,
one or two signups per month,
and 30-day active accounts in the low single digits.

Two readings of the same data:

- **Acquisition works when fed.**
  Traffic spikes align with posts in AI communities
  (OpenAI forum, r/PromptEngineering, Google AI forum —
  see the press list in `README.md`).
  Dozens of strangers per month try the game without being asked to.
- **The funnel has no bottom — as far as the database can see.**
  Anonymous try-ers almost never become accounts,
  and accounts almost never return.
  A known blind spot:
  anonymous players are invisible to account-based metrics,
  so anonymous return visits and battle-watching via secret URLs
  are not counted — retention may be understated.
  Cheap instrumentation (even router-log analysis)
  should confirm or correct this picture
  before heavy investment in the funnel.

The unexploited asset:
battles happen while players are away.
The game continuously generates the reason to come back —
your warrior fought, its rating moved, it produced a notable output —
and tells nobody.
Retention is not a missing feature to invent;
it is a signal the system already emits and currently discards.

## Direction and priority order

1. **Cost levers first** (container sizes, flex and batch pricing) —
   the ones that leave gameplay untouched.
   Container sizing and flex are hours of work;
   batching is a small project
   constrained by the fresh-warrior window (see above).
   Together they halve the burn and remove the anxiety
   that distorts every other decision.
2. **Close the retention loop for players we already get.**
   Start by instrumenting what account data cannot show:
   how many distinct humans visit and whether anonymous players return.
   Anonymous-to-account claim flow
   ("leave an email to keep your warriors"),
   then a periodic digest email built from battle activity.
   Success metrics are blunt at this scale:
   signups per month and 30-day actives.
3. **A recurring shareable artifact, as a habit rather than a feature.**
   A periodic "meta report" — top warriors, upsets, strategy shifts,
   generated mostly from battle data —
   posted to the communities that already know the game.
   Battle permalinks with proper link previews make each post land better.
4. **The dataset as downside protection.**
   Hundreds of thousands of adversarial prompt battles
   across multiple providers and two scoring algorithms
   are a publishable research asset
   (compare TensorTrust's dataset paper, linked in `README.md`).
   This pays out even if the game never grows:
   the project's floor is "interesting dataset plus writeup",
   not "abandoned side project".

Nothing else lands until signups and 30-day actives move.
In particular the side apps (`stories`, `labirynth`, `guessing`)
stay frozen:
new content for players who don't come back compounds nothing.

## Rejected alternatives

- **Bring-your-own-API-key.**
  Premised on token costs being the main burn; they are not.
  Adds onboarding friction exactly at the weakest funnel step.
  Reconsider only if token costs grow by an order of magnitude.
- **Migrating off Scalingo to a VPS.**
  Saves some tens of euros per month
  at the price of owning backups, deploys, and postgres upgrades.
  Bad trade for a one-person hobby project;
  the managed platform is what makes near-zero-maintenance possible.
- **Zeroing the thinking/reasoning budgets to save tokens.**
  Tempting because these tokens dominate the LLM bills,
  wrong because they buy referee intelligence:
  a non-thinking referee is easier to hijack,
  which favors degenerate strategies and shallows the core mechanic.
  It also devalues the dataset —
  adversarial battles against reasoning models
  are what makes the corpus research-relevant.
  Token savings come from batch APIs instead,
  which cut price without touching behavior.
  Tuning the budgets as a game-design decision remains fair game;
  doing it as a cost measure is rejected.
- **New game modes or arenas before retention exists.**
  Widens the surface area for the same handful of players.
  The constraint is the funnel, not the content.
- **Monetization (supporter tiers, paid arenas).**
  There is nobody to monetize;
  revisit when retention metrics show a community
  that might want to keep the lights on.
