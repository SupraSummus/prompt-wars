# Prompt Wars

An AI word-battling game/puzzle inspired by the classic concept of Core War. Players craft prompts that manipulate large language models (LLMs) into echoing the original prompt.

## Technical Overview

* Backend: Python (Poetry env management, Django framework)
* Database: PostgreSQL ❤️
* Error Monitoring: Sentry
* Deployment: Heroku
* LLM Integrations: OpenAI, Anthropic

## Getting Started (Development)

    cp example.env .env  # and fill database creds
    pytest
    sh lint.sh
    ./manage.py migrate
    ./manage.py runserver

See `run.sh` for full details how we run in production.

## Documentation

Detailed documentation about various aspects of the project can be found in the `docs` directory.
