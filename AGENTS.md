# AGENTS.md

## Project

AI Life Planner is a commercial-minded AI life planner MVP.

It is not a simple todo list and not a command-only Telegram bot. The product value is that a user writes normal human text, and the system turns it into durable profile data, long-term goals, dated tasks, a realistic day plan, task completion updates, and end-of-day summaries.

## Current MVP State

The MVP already includes:

- FastAPI app with `/health`;
- PostgreSQL through Docker Compose;
- SQLAlchemy models and Alembic migrations;
- Telegram bot through aiogram;
- mock natural-language parser;
- user profile storage;
- goals;
- tasks;
- `Task.target_date` for today/tomorrow separation;
- goal task suggestions;
- work/sleep-aware day planning;
- mark done;
- daily summary;
- smoke-check script at `scripts/check_mvp.py`;
- product, UAT, and security documentation in `docs/`.

Do not treat the project as a skeleton-only repository. Telegram bot, services, models, planning, goals, tasks, and migrations are already part of the MVP.

## Product Principles

- Reduce manual planning work.
- Let the user write naturally instead of filling many fields.
- Store important state in PostgreSQL, not in LLM messages or chat history.
- Keep the product universal: do not hardcode the app around one user, one schedule, or one set of goals.
- Examples such as gym, English, AI projects, 9-18, and 23:30 are allowed only as demos, tests, README examples, or fallback heuristics.
- Telegram is the current primary MVP interface.
- FastAPI is the foundation for the future Web UI and API.

## Architecture Rules

- Bot/API layers must stay thin.
- Business logic belongs in `app/services/`.
- Persistence belongs in SQLAlchemy models and database migrations.
- Parser/LLM extracts structured meaning from text.
- Backend validates, stores, schedules, controls statuses, and decides what is persisted.
- LLM must not directly execute commands, mutate state, or become the source of truth.
- If a real LLM is enabled, keep the mock parser as fallback and validate LLM JSON through Pydantic.
- Keep Telegram bot and future Web UI on the same service layer.

## Security Baseline

Follow `docs/SECURITY_BASELINE.md`.

Never commit:

- `.env` or `.env.*`, except `.env.example`;
- Telegram tokens;
- OpenAI/LLM keys;
- real database passwords;
- private URLs with credentials;
- cookies or session tokens;
- logs containing secrets.

Do not log secrets, full database URLs with passwords, raw `.env`, Authorization headers, or cookies.

Before committing, inspect staged files and staged diff. Stop if secrets or local artifacts are staged.

## Database Rules

- Schema changes must go through Alembic migrations.
- Do not delete data without explicit instruction.
- Do not delete Docker volumes as a shortcut.
- Do not call `drop_all()` or `create_all()` in runtime app code.
- Multi-user data must be isolated by user context. User-owned queries must filter by `user_id`.

## Development Constraints

- Do not rewrite the project from scratch.
- Do not change the tech stack without a clear reason.
- Do not add dependencies casually.
- Do not start Web UI work unless explicitly requested.
- Do not connect a production LLM unless explicitly requested.
- Keep changes focused and covered by smoke checks or tests.
- Preserve existing working flows: profile, goals, tasks, today/tomorrow, planning, daily summary, Telegram UX, FastAPI import, and Alembic migrations.

## Required Checks

Run before commit:

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

If the local Windows shell cannot use the project `.venv` because it was created under WSL, use a temporary local check environment rather than modifying `.venv`.

## Definition Of Done

A change is done only when:

- the requested behavior or documentation update is complete;
- existing MVP flows are not broken;
- smoke-check passes;
- Alembic reaches head;
- bot/app imports pass;
- no secrets are staged;
- documentation is updated when behavior or setup changes;
- commit is created when requested;
- push is performed only when `origin` is configured correctly.
