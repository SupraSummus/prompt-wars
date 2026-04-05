# Running tests in Claude Code web environment

The web environment has Python 3.11 as the default, but the project requires
Python 3.13. PostgreSQL 16 is available but needs to be started manually.

## Setup

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

## Running tests

```bash
cd /home/user/prompt-wars
poetry run python -m pytest embedding_explorer/tests.py -v
```

## Linting

```bash
cd /home/user/prompt-wars
poetry run flake8 embedding_explorer/
poetry run pylint --load-plugins pylint_django --errors-only --disable=E0401,F5110 embedding_explorer/
```
