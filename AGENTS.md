# AGENTS.md

Agent-facing project doc.
`CLAUDE.md` in the repo root is a symlink to this file,
so both names resolve to the same content —
different tools look for different filenames.
Edit either, you edit both.

## Docs must not repeat what the code already says

A doc paragraph that restates code behavior —
a scoring formula, a matchmaking rule, a config default —
is a second copy that goes stale silently,
and the reader can't tell which copy is authoritative.
Split by ownership:

- **Code (comments/docstrings)** owns "what is implemented and how".
  Battle resolution, scoring, and matchmaking live in `warriors/`
  (`battles.py`, `score.py`, `lcs.py`, `random_matchmaking.py`);
  if you're about to write a doc paragraph describing behavior,
  put the one-or-two-sentence rationale in a docstring or comment
  at the source and have the doc point at the file or function by name.
- **Docs (`README.md`, `CONCEPT.md`, `docs/`)** own what code cannot show:
  the game's design goals and philosophy (`docs/parallels.md`),
  decisions and their rationale,
  what is deliberately *not* implemented and why,
  observed player strategies and emergent behavior,
  and planned work and open questions
  (`docs/lineages.md` is a design proposal, not shipped code —
  that's exactly the kind of content that belongs in a doc).

Cross-references go by name:
docs name files, functions, and models;
a code comment whose "why" spans modules
points at a doc section by heading.
When renaming a doc heading or a named item,
grep the other side for references to it.

Don't paste code or values into docs —
formulas, constants, payload shapes.
Link to the item instead;
a pasted copy is guaranteed to drift.

## Docs describe the present; git owns the past

A doc that narrates its own evolution is a changelog,
and git already keeps a better one.
The test for any sentence about the past:
does it change what a reader working on the current system should do?
If it only records that something happened or used to be different, delete it;
if it explains why the present is the way it is,
keep it — phrased as present-tense rationale, not as an event.
A rejected alternative and why it was rejected earns its place
(it stops the next person from re-proposing it);
done markers, "now implemented" status narration,
and dates that only order the doc's own edits are deadweight.
When a decision changes, rewrite the owning section in place —
don't append an amendment that readers must apply mentally.
A word-level tell: temporal adverbs —
"still", "now", "not yet", "no longer" —
anchor a sentence to the moment it was written;
write the plain present instead.

## Tracking debt you notice in passing

When you spot a rough edge while working on something else —
a refactor, a dead branch, drifted duplication, a missing test —
log it in `TODO.md` at the repo root
instead of fixing it now (scope creep)
or burying an inline `# TODO` (invisible outside that file).
Glance at `TODO.md` before starting new work;
its header has the convention.
Game-design ideas and philosophical observations are not debt:
they go to `CONCEPT.md` or `docs/`, next to their rationale.

## Prose uses semantic line breaks

Write natural-language text —
this file, `README.md`, `CONCEPT.md`, `docs/`, commit bodies —
using [semantic line breaks](https://sembr.org):
start a new source line after each sentence,
and after independent clauses set off by a comma,
semicolon, colon, or em dash.
Markdown joins these lines with a space on render,
so the output is unchanged;
what it buys is diffs that land on the clause that changed
rather than reflowing a whole paragraph.
Adopt this lazily:
leave existing prose alone,
but reformat any paragraph you touch as part of the edit.
Don't reflow whole documents just to convert them.

## Git

Commit messages: focus on "why", not "what" — "what" is in the diff.
Keep the subject short: aim for ≤50 characters, hard limit 72.
Prefer a terse imperative over a full sentence;
if it doesn't fit, move detail to the body.

## Running tests in Claude Code web environment

The web environment has Python 3.11 as the default, but the project requires
Python 3.13. PostgreSQL 16 is available but needs to be started manually.

### Setup

```bash
# Start PostgreSQL
pg_ctlcluster 16 main start

# Create database and user
sudo -u postgres psql -c "CREATE USER promptwars WITH PASSWORD 'promptwars' SUPERUSER CREATEDB;"
sudo -u postgres psql -c "CREATE DATABASE promptwars OWNER promptwars;"

# Upgrade pgvector to >= 0.7.0 (system package is 0.6.0, too old)
# Required for HammingDistance on BitField (the <~> operator on bit type).
apt-get install -y postgresql-16-pgvector postgresql-server-dev-16
cd /tmp && git clone --branch v0.8.0 --depth 1 https://github.com/pgvector/pgvector.git
cd /tmp/pgvector && make && make install
pg_ctlcluster 16 main restart

# IMPORTANT: if a test_promptwars database already exists from a previous
# session, DROP IT. It will have the old pgvector 0.6.0 extension baked in
# and HammingDistance queries will fail with "operator does not exist".
sudo -u postgres psql -c "DROP DATABASE IF EXISTS test_promptwars;"

# Create .env
cat > /home/user/prompt-wars/.env << 'EOF'
DATABASE_URL=postgres://promptwars:promptwars@localhost:5432/promptwars
DJANGO_SECRET_KEY=test-secret-key-for-testing-only
DJANGO_DEBUG=True
ALLOWED_HOSTS=*
FORCE_HTTPS=False
VOYAGE_API_KEY=test
GOOGLE_AI_API_KEY=test-dummy-key
EOF

# Install dependencies
cd /home/user/prompt-wars
pip install poetry
poetry install
```

### Running tests

```bash
cd /home/user/prompt-wars
poetry run python -m pytest embedding_explorer/tests.py -v
```

### Linting

```bash
cd /home/user/prompt-wars
poetry run flake8 embedding_explorer/
poetry run pylint --load-plugins pylint_django --errors-only --disable=E0401,F5110 embedding_explorer/
```
