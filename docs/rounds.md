# Rounds: fixed-cadence mass battles

A proposal, not shipped code:
run battles in synchronized rounds at a fixed interval —
daily, say — alongside or eventually instead of
the continuous trickle.
Players lock in warriors before a submission deadline,
the round resolves as one mass job,
and results are revealed at a fixed hour.

## What a shared clock buys

The strongest effect is not volume but simultaneity.
Under the continuous trickle,
every player lives in a private asynchronous stream;
no two players share a "now".
A round creates one:
today's results are a single object everyone saw,
a natural cadence for the digest email
(`docs/strategy.md`, retention priority),
a discussion object,
and a unit of history —
metas rise and die in numbered rounds,
which gives the living system
the memory and narrator it lacks
(see the living-system strength in `docs/design-tensions.md`).
This is the mechanism behind daily-puzzle games:
scarcity plus synchronization.
A deadline drives action
in a way an always-open door does not,
and a fixed reveal hour makes results an event to anticipate.

## What it does not buy

Per-battle unexpectedness does not increase:
same prompts, same models, same mechanic.
What increases is correlated reading —
twenty outputs from the same night
make the weird one stand out.
But a daily pile is exactly as unreadable
as a trickle of the same size;
the round needs an editor.
Rounds are the cadence;
the novelty-surfacing direction in `docs/design-tensions.md`
is the editor;
each is weak without the other.

## Hard requirement: keep the fast lane

The minute-scale first-battle loop is deliberate
(`get_next_battle_delay` in `warriors/random_matchmaking.py`
front-loads a fresh warrior's first games)
and it serves the one funnel stage that works:
anonymous drive-by visitors create warriors
because they see them fight immediately.
"Come back tomorrow at 18:00" loses those players.
So rounds must not replace instant battles for fresh warriors:
keep immediate exhibition or placement matches
(synchronous API, unrated or lightly rated),
and make the round the rated league.
The split doubles as a claim-flow prompt —
"your warrior enters tonight's round;
leave an email to get the results" —
and it is the same seam the cost analysis wants
(see the LLM pricing levers in `docs/strategy.md`:
fresh warriors on the synchronous path,
the scheduled mass on batch pricing,
with the fixed reveal hour hiding
the batch APIs' variable turnaround entirely).

## Shape and participation

Massive should mean simultaneous, not numerous:
Swiss-style pairing with a few opponents
per participating warrior per round
keeps cost linear and tunable.
The exponential backoff schedule translates naturally —
veterans fight every 2^k rounds —
or participation can require periodic re-confirmation,
which doubles as a retention touchpoint
and prunes dead warriors.
One global reveal hour has timezone politics;
choose it for where the game's communities live,
and accept the fixed hour as part of the ritual.

## De-risking path

Add, don't replace:
a nightly opted-in league round with a morning round report,
built on the batch pipeline,
while the trickle continues unchanged.
If the round page and the digest show a pulse,
dial the trickle down toward exhibition-only.
Every step is reversible,
and the batch infrastructure is shared
with the status quo either way.
