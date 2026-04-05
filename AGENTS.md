# Running tests in Claude Code web environment

The web environment has Python 3.11 as the default, but the project requires Python 3.13. PostgreSQL 16 is available but needs to be started manually.

## Setup

```bash
# Start PostgreSQL
pg_ctlcluster 16 main start

# Create database and user
sudo -u postgres psql -c "CREATE USER promptwars WITH PASSWORD 'promptwars' SUPERUSER CREATEDB;"
sudo -u postgres psql -c "CREATE DATABASE promptwars OWNER promptwars;"

# Install pgvector extension
apt-get install -y postgresql-16-pgvector

# Create .env
cat > .env << 'EOF'
DATABASE_URL=postgres://promptwars:promptwars@localhost:5432/promptwars
DJANGO_SECRET_KEY=test-secret-key-for-testing-only
DJANGO_DEBUG=True
ALLOWED_HOSTS=*
FORCE_HTTPS=False
VOYAGE_API_KEY=test
GOOGLE_AI_API_KEY=test-dummy-key
EOF

# Create venv with Python 3.13 and install deps
python3.13 -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install poetry
poetry lock
poetry install
```

## Running tests

```bash
. .venv/bin/activate
python -m pytest embedding_explorer/tests.py -v
```

## Linting

```bash
python -m flake8 embedding_explorer/
python -m pylint --load-plugins pylint_django --errors-only --disable=E0401,F5110 embedding_explorer/
```
