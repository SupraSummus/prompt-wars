# Prompt Wars

An AI word-battling game/puzzle inspired by the classic concept of Core War. Players craft prompts that manipulate large language models (LLMs) into echoing the original prompt.

## Technical Overview

* Backend: Python (Poetry env management, Django framework)
* Database: PostgreSQL ❤️
* Error Monitoring: Sentry
* Deployment: Scalingo
* LLM Integrations: OpenAI, Anthropic, Google Gemini

## Getting Started (Development)

    cp example.env .env  # and fill database creds
    pytest
    sh lint.sh
    ./manage.py migrate
    ./manage.py runserver

See `Procfile` for full details how we run in production.

## Documentation

- [CONCEPT.md](CONCEPT.md)
- [philosophical stuff](docs/parallels.md)

# Any press is good press

- https://community.openai.com/t/prompt-wars-an-ai-powered-language-battleground/669544
- https://www.reddit.com/r/PromptEngineering/comments/1hqppcf/fun_promptengineering_game_i_found_online/
- https://thecyberwire.com/podcasts/the-faik-files/29/notes
