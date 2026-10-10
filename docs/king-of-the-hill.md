# King of the Hill: a daily boss anyone can attack

Why King of the Hill is shaped as it is, what it leaves out, and how to launch it.
The game's rules are constants in `hill/rules.py`;
the owner's switches are the fields of `Hill` (`hill/models.py`).

## What it is for

The hill shows one public boss prompt a day, numbered "Hill #N",
and anyone may attack it with a prompt of their own.
An attack is one battle against the boss, in both prompt orders,
and its result arrives in about a minute.
At the daily handover, the best attack that beat the boss by a margin becomes the next boss.

It serves the retention and shareable-artifact priorities of `docs/strategy.md`:
a fast first result, a reason to come back the next day,
and a share text (`hill.display.share_text`) that holds only numbers, so it is safe to post anywhere.
It is judged by whether attackers come back in later rounds ("How it is judged").

## The hill and the ladder

A hill battle is an ordinary battle, created unrated and without an arena (`Battle.create`).
The ladder's goals play and score it,
and every ladder query skips it (`BattleQuerySet.rated`; see `docs/data-model.md`).
Rating them would push the boss's `games_played` up with every attack,
and matchmaking backs off exponentially in that number (`get_next_battle_delay`);
the rating fan-out in `transfer_rating` would also enroll every attacker in matchmaking.
The battle page (`BattleDetailView`) shows no unrated battle to anyone;
otherwise the ladder author of a boss could open the attacker's side of a sealed hill battle.

The hill ranks by LCS alone:
the embeddings algorithm decides each game winner-take-all, waits on Voyage
and can't be marked in a reply, and what survived is what the hill shows.

## The crown rule

`hill.handover.decide_successor` picks who holds the hill after a round.

An attack takes the hill only by beating the boss by a margin (`hill.rules.beats_boss`),
because when little of either prompt survives,
the score swings across half on noise.
Otherwise the boss holds for a term at most (`HILL_MAX_REIGN_ROUNDS`),
so a strong boss doesn't sit on the home page through a quiet week.
At the end of a term, the best attack of the reign inherits the hill
even though it lost its battle,
and the boss card says it inherited.
With no eligible attack in the reign, the house boss that served longest ago steps in (`next_house_boss`),
so no single counter-prompt owns the fallback;
with no house boss either, the boss holds on.
The term counts rounds of one text, not of one player, because identities are free.

The crown goes to the best of everything a player sends.
The model runs at temperature 0 (`Hill.llm`), so a battle mostly replays,
and the luck is in the variants: several real edits are several rolls.
The margin and the per-player cap bound it.

## What an attack must be

`hill.attack.submit_attack` runs the checks; these are their reasons.

**Not a copy of a recent boss** (`hill.attack._copy_refusal`).
It is measured by `hill.similarity.copied_share`,
not by the battle's `warriors_similarity`, which padding dilutes.

**Not someone else's text.**
A text that already exists is refused unless this player attacked with it before (`_warrior_refusal`),
so nobody consents to publishing a text they didn't write.
So a ladder author can't bring their own prompt:
anonymous ladder ownership looks the same as having discovered the text.

**A repeat is not a new attack.**
The same text, or one that differs only in spacing, case or punctuation,
leads its player back to their earlier attack in the round, for free (`_repeated_attempt`).

## Traffic regimes

**Nobody attacks.**
The boss holds until its term ends, then a house boss steps in, if the owner seeded one.
Under an owner or house boss the hill page has no battle to show,
so a visitor's first attack is the first battle they see.

**A normal day.**
The battle starts when the attack is accepted,
and the prompt's moderation runs beside it (`hill.tasks.moderate_attempt`),
because moderation in front would add its latency and outages to every first result.
A prompt flagged meanwhile is never shown or crowned,
but its battle is paid for.

**A spike.**
`Hill.max_pending` caps the attacks in battle at once;
past it, the form refuses and keeps the player's text (`hill.attack.admission_refusal`),
so every admitted attack gets its result in about a minute.
`Hill.daily_attempt_limit` is a flat cap on a round's battles, and so on the day's spend.
Attack goals run ahead of ladder goals (the `deadline` in `Battle.create`),
so the ladder waits while the round's budget keeps attacks coming;
it is asynchronous, and nobody watches its queue by the minute.

**One person, many sessions.**
A player is a random key in the session (`hill/identity.py`),
so a new private window is a new player with a fresh cap, for the price of one captcha.
The round's budget bounds what they all spend,
and the standings keep one row per player (`hill.rules.standings`).
One person with many sessions can hold several rows and get several rolls at the crown;
at this scale, that is accepted.

**Degenerate bosses.**
Against a boss that forces a degenerate reply, a two-character echo can win a battle,
so an attack can't take the hill if too little of it survived
or a reply is too repetitive (`hill.rules.crown_block`).

**Failures.**
`hill.status.attempt_status` says which failures count against the player;
a void one is refunded to the player, but not to the round's budget (`hill.rules.budget_used`).
The clock never voids an attack that has a battle:
its goals keep running and costing money, so it keeps its place under `Hill.max_pending`.

## Privacy and consent

`docs/twitter-for-prompts.md` sets the constraint:
publication is an act, opted into while writing, and moderated before it happens.

An attack's text, its typed names and its battle's replies
are shown only in the browser session that sent it,
except for the attack that takes the hill (`hill.rules.is_public`),
as the consent checkbox on every attack says.
Everyone else sees numbers:
"Attacker #k" in the standings, a score behind an attack's link,
and a share text and link previews without words (`hill.display`).
The boss's typed names and its crowning battle's replies are moderated when it is crowned
(`hill.tasks.moderate_crowned_attempt`), and shown only if they pass.

A takedown is the moderation flag,
set with the "Take down" action in the Warrior admin (`WarriorAdmin.take_down`).
It hides the text, its names and the replies that echo it (`Round.boss_shown`)
from everyone but a player looking at their own attacks,
and ends the boss's term at the next handover (`hill.handover.term_over`).
It works the same for attack, owner and house bosses,
and it takes the warrior off the ladder too.
Requests come through the contact the data policy names.

The hill doesn't use the ladder's `public_battle_results`:
that flag belongs to a warrior and stays set,
so it would publish every ladder battle the boss ever fought.

Share presses, and the new players a share text's link brings,
are counted per round without recording who (`RoundTally`);
the player's own session keeps which rounds it was counted in, so a press counts once a round.

The hill stores no IP address,
but the captcha sends the visitor's to Google, as the data policy says (`llm_wars/data_policy_view.py`).

## Rejected alternatives

- **Handing the hill to the best attack every round.**
  The boss would usually have lost its battle, and its share text would announce a defeat.
  Inheritance does this only at the end of a term, as the price of rotation.
- **Winning both prompt orders.**
  The model's bias toward one position would decide the crown.
- **A confirmation rematch, or a final between the best attacks.**
  At temperature 0 a rematch mostly replays the lucky battle: more calls, nothing confirmed.
- **Ending a reign early when most attacks fail.**
  Fresh sessions are free, so a few deliberate failures could end any reign and pick its inheritor.
- **Revealing every attack, or every battle's replies.**
  It would publish texts their authors never agreed to publish,
  and on a busy day it would be the unmoderated feed `docs/twitter-for-prompts.md` rules out.
- **Generated boss names.**
  The ladder's generated names are never moderated,
  and a boss's name is on the home page.
  Hill warriors keep blank names, which also keeps sealed texts out of `generate_warrior_name`'s samples.
- **IP-based caps.**
  More personal data, and a block on everyone behind a carrier's shared address,
  for a cost the round's budget bounds anyway.
- **Several hills, one per LLM.**
  They would split a handful of daily attackers, when the point is one shared object.
- **A setting for every rule.**
  The win score and the term shouldn't change in the middle of a reign,
  and each setting costs a column, a validator and a parameter passed through the code.
  `Hill` holds only what the owner must change without a deploy.
- **Other ways to tell hill battles apart.**
  A hill-only `LLM` value would make an LLM name a pool, not a model (`docs/data-model.md`);
  an anti-join against hill attempts would bring the hill's table into the ladder's rating job;
  an `Arena` row would get the ladder's rating fan-out and matchmaking queue.

## Deliberately not built

Each with what would bring it back.

- **Reports and auto-hide**, which must never decide succession,
  or a few fresh sessions could dethrone any boss.
  Trigger: a takedown that waits on the owner too long.
- **Families, and a reveal of the top attacks.**
  A reveal needs consent wording that covers it, and applies only to attacks sent under it.
  Trigger: one person's sessions crowding the standings, or a round page that needs more than the winner.
- **A house sparring command**, so the hill page shows a battle before anyone attacks.
  Trigger: launch-day visitors leaving without attacking.
- **A budget released over the round**, instead of a flat cap.
  Trigger: a round's budget running out while a post's traffic keeps arriving.
- **Alerts for a spent budget or a full queue.**
  Trigger: a spike that ran into either unnoticed.
- **A fast lane of worker threads**, so the ladder moves under a hill load.
  Trigger: ladder battles visibly stalling during a spike.
- **Email and a claim flow for winners.**
  Trigger: the claim flow of the retention priority (`docs/strategy.md`), which this would share.
- **An image for link previews.**
  Trigger: shared links that bring little traffic.
- **Cross-device identity.**
  It must be a POST that merges two identities after a confirmation page,
  never a link that switches identity on a GET:
  that is login CSRF, and the link's sender would read the victim's sealed attacks.
  Trigger: players asking to continue on a second device.
- **A prompt crossing between hill and ladder**, in either direction.
  Each direction needs its own review of discovery and of what the other side's battles expose.
  Trigger: players asking for it.

## Open questions

- Whether `HILL_WIN_SCORE`, `HILL_MAX_REIGN_ROUNDS`, `HILL_BOSS_COPY_THRESHOLD` and the crown gates are right:
  they come from reasoning and a few measurements, not from real rounds.
- Whether the model is deterministic in practice; if not, the rematch is worth another look.
- Whether reigns settle into bosses nobody can beat, despite the gates and the term.
- Whether the share text travels.

## How it is judged

Launch day doesn't answer whether the hill works:
a post brings people (`docs/strategy.md`), and the hill is a bet on them coming back.
So the verdict comes from the weeks after the post's traffic has passed.
`hill_report` prints the hill's counts per round,
and given the launch round, per window: a verdict window, then a confirmation window
(`--help` for its options).
It leaves out each post's round and the days its traffic swells,
and the owner's own attacks, which would flatter the counts;
the owner's identity is on their attacks in the HillAttempt admin.

A player is a browser session (`hill/identity.py`),
so attackers overcount people and returning players undercount them;
the bands allow for that.
Where the report prints k of n without a percentage, the percentage bands don't apply;
judge by the counts.

| # | Signal | Flop | Alive | Banger |
|---|---|---|---|---|
| 1 | Attackers per round, median | < 3, the ladder's human rate | 3–14 | ≥ 15, and the confirmation window keeps 80% of the verdict window's mean |
| 2 | Regulars; next-round return | < 5, no more than the 30-day active accounts; < 10% | 5–19; 10–25% | ≥ 20; ≥ 25% |
| 3 | A 2nd attack; at the cap | < 30% with a 2nd | 30–60% | > 60%, and ≥ 20% at the cap |
| 4 | Pressed Share; new players through a shared link | < 5%, or at most one new player through a link in a window | 5–15%; 10–30% | ≥ 15%; ≥ 30% |

- **Banger:** rows 1 and 2 banger in the verdict window and holding in the confirmation window,
  with rows 3 and 4 at least alive.
- **Alive:** rows 1 and 2 at least alive.
  Rows 3 and 4 then say what to fix:
  few 2nd attacks, the first result doesn't hook;
  shares that bring nobody, the trigger for "An image for link previews";
  no shares, the share step itself.
- **Flop:** row 1 or row 2 a flop, however good launch day looked.

Early warnings don't decide the verdict.
In the first hours, more than 60% of the launch round's attackers sending a 2nd attack is good,
and under 30% bad.
Once the next round closes, 25% of the launch round's new players attacking again in it is good,
and under 10% bad;
it undercounts, since in-app browsers keep their own cookies.
The launch round's own size measures the post more than the game.

The report's tuning line can change `hill/rules.py`, not the verdict.
Beaten twice or less in a window whose median round has 10 or more attackers is too hard;
beaten 12 times or more, or mostly by one of a round's first attacks, is too cheap.
A house fallback means a term ended, by its length or a takedown, with no attack fit to inherit,
and one player holding more than a third of the rounds may be one person's several browsers.

For the project, the lift that counts is regulars:
a month and two months after the post,
twice as many as the accounts that logged in in the 30 days before it ("Launch runbook").
A banger with flat accounts is expected, since the hill has no path to an account;
it is the trigger for "Email and a claim flow for winners", not a mark against the hill.

## Launch runbook

1. **Seed the first boss and the house, soon after deploying:**
   the nav links the hill from the deploy on, to a "closed" page until it is enabled.
   `hill_crown` moderates the prompt, creates the hill switched off if there is none,
   and with `--now` opens a round under it.
   Both seeds are texts the project publishes elsewhere:

       ./manage.py hill_crown --body-file hill/seeds/dawkins.txt --name "Dawkins mutation" --house --now
       ./manage.py hill_crown --body-file hill/seeds/start-stop.txt --name "Start–Stop" --house

2. **Check the switches, then enable.**
   In admin, check the `Hill` row's `llm`, `daily_attempt_limit` and `max_pending`, then tick `enabled`.
3. **Before an announced post, raise the limits.**
   Raise `daily_attempt_limit`; each attack is one battle of two model calls.
   Raise the worker's threads (`--threads` in `Procfile`, a deploy)
   within the database's connection limit, since every running goal holds a connection,
   and raise `max_pending` to what those threads drain in a few minutes.
   Raise the web tier's concurrency (`WEB_CONCURRENCY` on the platform).
   Check that the production reCAPTCHA keys are set, or every captcha passes,
   and that `SENTRY_DSN` is set, since a failed handover decision is logged there (`close_round`).
4. **Post right after a handover**,
   so the first wave's attacks count in the round they were sent,
   and the next handover is the reason to come back.
   The round it opened is the launch round `hill_report` judges from.
   Just before posting, count the accounts that logged in within the last 30 days (`User.last_login`):
   the lift check in "How it is judged" needs that number, and it can't be counted later.
5. **During the post, watch by hand**
   the hill page for its busy and used-up states, and the pending attempts in admin.
   Lowering `max_pending` hands the worker back to the ladder without a deploy.
6. **Take something down** with the "Take down" action in the Warrior admin.
   A boss taken down is hidden at once,
   and its term ends at the next handover.
   To replace it at once, run `hill_crown --now`;
   `--warrior` takes an existing warrior's id,
   and a house boss keeps its names.
7. **Switch it off** by unticking `enabled`.
   The open round stays as it is, and nothing needs migrating back.
