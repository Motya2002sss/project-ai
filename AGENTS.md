# AGENTS.md

This file is the project-level instruction set for Codex and other coding agents working on AI Life Planner.

## Product Meaning

AI Life Planner is a commercial-minded AI life planner MVP.

It is not a normal todo list and not a command-only Telegram bot. The user writes natural text, and the system turns it into:

- profile data;
- long-term goals;
- dated tasks;
- realistic day plans;
- completion status;
- daily summaries.

The product should reduce manual planning work. Users should not maintain dozens of fields by hand.

## Current MVP

The project already contains:

- FastAPI app with `/health`;
- PostgreSQL via Docker Compose;
- SQLAlchemy models;
- Alembic migrations;
- Telegram bot via aiogram;
- mock natural-language parser;
- user profile flow;
- goals flow;
- tasks flow;
- `Task.target_date`;
- today/tomorrow planning;
- goal task suggestions;
- work/sleep-aware planning;
- mark done;
- daily summary;
- smoke-check script at `scripts/check_mvp.py`;
- product and security docs in `docs/`.

Do not treat this repository as an empty starter project. Telegram bot, services, models, tasks, goals, planning, migrations, and smoke checks are already part of the MVP.

## Architecture Rules

- Bot and API layers must be thin.
- Business logic belongs in `app/services/`.
- Database state belongs in SQLAlchemy models and PostgreSQL.
- Schema changes belong in Alembic migrations.
- Parser or future LLM extracts structured meaning from text.
- Backend validates input, stores data, builds plans, checks dates, controls statuses, and decides what is persisted.
- Important state must not live only inside chat history or LLM messages.
- Telegram bot and future Web API must use the same service layer.

## LLM Rules

The current default is the mock parser.

When real LLM support is added:

- keep mock parser as fallback;
- ask the LLM for structured JSON only;
- validate JSON through Pydantic;
- do not let the LLM directly execute commands;
- do not let the LLM directly mutate database state;
- do not send secrets, `.env`, tokens, credentials, or internal config to the LLM;
- treat LLM output as untrusted input that backend services must validate.

## Product Universality

Do not hardcode the product around one user.

Allowed:

- examples in README, docs, tests, and mock fallback heuristics;
- broad fallback heuristics for task duration or goal suggestions.

Not allowed:

- assuming every user works 9-18;
- assuming every user sleeps at 23:30;
- assuming all goals are gym, English, or AI projects;
- building flows that only work for one user's personal routine.

## Security Rules

Follow `docs/SECURITY_BASELINE.md`.

Never commit:

- `.env`;
- `.env.*`, except `.env.example`;
- Telegram tokens;
- OpenAI or other LLM API keys;
- real database passwords;
- private URLs with embedded credentials;
- cookies;
- session tokens;
- logs with secrets.

Do not log secrets, raw `.env`, full database URLs with passwords, Authorization headers, cookies, or API keys.

## Database And Multi-User Rules

- User-owned queries must filter by user context, usually `user_id`.
- Telegram users must only access their own profile, goals, tasks, and plans.
- Do not delete user data without explicit instruction.
- Do not delete Docker volumes as a shortcut.
- Do not run `drop_all()` or `create_all()` in runtime application code.
- Use Alembic for schema changes.

## Development Constraints

- Do not rewrite the project from scratch.
- Do not change the tech stack without explicit need.
- Do not add dependencies casually.
- Do not start Web UI work unless explicitly requested.
- Do not wire production LLM behavior unless explicitly requested.
- Keep patches focused.
- If parser, tasks, goals, planning, bot UX, or migrations change, update smoke checks or tests.
- Preserve existing MVP flows: profile, goals, tasks, today/tomorrow, planning, daily summary, Telegram UX, FastAPI import, and Alembic migrations.

## Required Checks Before Commit

Run:

```bash
alembic upgrade head
python scripts/check_mvp.py
python - <<'PY'
from app.bot.main import dp
from app.main import app
print("bot and app import ok")
PY
git status
git diff --stat
git diff --cached --name-only
git diff --cached
```

Run tests when available:

```bash
pytest
```

Before committing, verify staged diff does not contain secrets or local artifacts.

## Commit And Push Rules

- Commit only after checks pass.
- Use clear commit messages.
- Push only to the configured intended remote.
- If `origin` is missing or wrong, stop and ask for the correct URL.

## Definition Of Done

A task is complete only when:

- requested documentation or behavior is updated;
- code changes, if any, are minimal and scoped;
- MVP smoke-check passes;
- Alembic reaches head;
- bot/app import check passes;
- tests pass when available;
- no secrets are staged;
- docs are updated when behavior or setup changes;
- commit is created when requested;
- push is completed when remote is valid.
