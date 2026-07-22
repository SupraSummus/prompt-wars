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

`Battle.rating_transferred_at` is a dead column:
nothing writes or reads it —
only a "not used anymore" comment in `warriors/battles.py`
and a passthrough entry in `BattleViewpoint.map_field_name`
keep it in the code.
Next move: drop the field, the comment, and the mapping entry,
same shape as the `lcs_len_*` column removal;
implies a schema migration but no behavior change.
