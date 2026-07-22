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

`warriors/rating_tests.py::test_get_performance_rating` is flaky:
`get_performance_rating` in `warriors/rating.py` seeds its optimizer
with an unseeded `np.random.uniform` starting position,
so the test intermittently converges to a different optimum
and misses its `pytest.approx(2550.5, abs=0.1)` assertion
(observed failing in a full-suite run, passing in isolation).
Next move: seed the RNG in the test
(e.g. `np.random.seed` in a fixture)
or pass an explicit `rating_guess` so the outcome is deterministic.
