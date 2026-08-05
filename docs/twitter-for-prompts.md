# Twitter for prompts: what survives the reframe

Reading the game as a microblog —
a player writes what is on their mind,
a model blends it with a stranger's text,
the blend is what the world sees —
describes the existing object accurately:
the input box already collects unprompted writing,
the output already carries both authors,
and the visibility flag discussed in `docs/design-tensions.md`
is already a publish toggle wearing game vocabulary.

The reframe yields three mechanics and a long list of dead ends.
Evidence for every verdict below is in `docs/precedents.md`.

## Dead

**The follow graph, handles, timelines.**
Performance metrics trade away the one unusual asset —
two strangers fused without either performing socially
(`docs/design-tensions.md`).

**An auto-published feed of all outputs.**
Uncurated generated feeds do not retain anyone,
and curation ratios elsewhere run near a few percent.
Novelty ranking is an editor's assistant, never the editor.

**Flipping the existing corpus public.**
Prompt boxes collect personal details
because they do not read as publication.
Prior submissions carry the contract they were made under.

**A second leaderboard axis.**
Ranking machinery aimed at a population
of single-digit monthly actives.
The fusion and novelty signals are worth computing
as inputs to a shortlist, not as a board.

**Directed replies as rated battles.**
An opponent you choose is an opponent you farm;
unrated replies carry no stakes.
Nothing remains between those.

**Preview-and-approve before publishing.**
Filters the corpus toward what authors find flattering
and destroys the surprise that is the product.

**Per-pair caching of blends.**
Infinite Craft's cost lever does not transfer:
repeat pairings are rare here
and nondeterministic fresh output is the point.

**Rewording the compose box on its own.**
"Say what's on your mind" in front of a dominance fitness function
is bait: sincere text loses to emoji cheese and its author leaves.
The wording only becomes honest
downstream of a published stream ranked on fusion rather than dominance.

**Presenting blends as AI content.**
The AI penalty discounts precisely the stranger-to-stranger intimacy
the reframe exists to expose.
Disclose the mechanism, give the byline to the two writers.

## Survives

1. **A weekly human-picked selection.**
   A handful of blends, chosen and sequenced by a person,
   attributed to two anonymous writers.
   No schema change and no new mode:
   the candidate pool is battles the existing visibility flag
   already makes public,
   which is narrow and is the point.
   This is also the shareable artifact
   the meta-report priority in `docs/strategy.md` wants,
   and the report a round would need (`docs/rounds.md`).
2. **One-keystroke spectator reaction.**
   No account, no authored contribution —
   the cheapest taste signal the system has never collected.
3. **Adopt-an-output with parentage recorded at the click.**
   Exact and free where the reconstruction in `docs/lineages.md`
   is neither.

## Non-negotiable constraint

Publication is an act:
opt-in at composition time,
a report path that reaches a human,
moderation before publication rather than after.
Anonymity plus a public feed fails fatally rather than awkwardly.
This is what keeps the surface hobby-sized;
a firehose would not.

## The only test that matters first

Build the selection page.
It is not a new work item:
it is the shareable-artifact priority in `docs/strategy.md`
with an editorial design attached,
which is the honest net effect of this whole reframe —
one existing priority sharpened, and a list of proposals killed.
It fails if picking a decent handful each week is a struggle —
which would mean the corpus is the problem
and every mechanic above it is moot.
Nothing else gets built until that page has readers.

## Open

Is the artifact the blend, or the blend shown beside its two parents?
Is the score visible in the selection at all?

Note that this is the first direction with a variable cost:
posts draw battles, and battles cost tokens
(the fixed-fee frame in `docs/strategy.md` stops applying).
