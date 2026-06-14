# AI Life Planner

AI Life Planner is a Telegram-first MVP for an AI life planner.

It is not a plain todo list and not a command-only Telegram bot. The core idea is that a user writes normal human text, and the backend turns it into durable profile data, long-term goals, dated tasks, a realistic plan for the day, and end-of-day progress.

The current product direction is:

- parser or future LLM extracts structure from natural language;
- backend validates, stores, schedules, and controls task state;
- important state is stored in PostgreSQL, not only in chat history.

## Current MVP Status

The MVP already works as a Telegram-based planner with a FastAPI backend foundation.

Implemented:

- FastAPI app with `/health`;
- PostgreSQL via Docker Compose;
- SQLAlchemy models;
- Alembic migrations;
- Telegram bot via aiogram;
- mock natural-language parser;
- user profile storage;
- goals;
- tasks;
- `Task.target_date`;
- today/tomorrow task separation;
- goal-based task suggestions;
- work/sleep-aware planning;
- configurable buffer after work;
- task priority and estimated duration handling;
- overflow tasks marked as not scheduled;
- mark task done;
- daily summary;
- smoke-check script at `scripts/check_mvp.py`;
- product, UAT, and security docs in `docs/`.

Not ready yet:

- real LLM parser for production use;
- Web UI;
- production authentication;
- production deployment;
- full FastAPI product API for Web UI.

FastAPI currently exposes `/health`. The main MVP user flow is in the Telegram bot and shared service layer.

## Project Structure

```text
ai-life-planner/
├── app/
│   ├── api/              # FastAPI routers
│   ├── bot/              # Telegram bot
│   ├── core/             # settings
│   ├── db/               # SQLAlchemy engine/session/base
│   ├── llm/              # mock parser, prompts, parser schemas
│   ├── models/           # SQLAlchemy models
│   └── services/         # business logic
├── docs/
│   ├── PRODUCT_SPEC.md
│   ├── SECURITY_BASELINE.md
│   └── UAT_SCENARIOS.md
├── migrations/           # Alembic migrations
├── scripts/
│   └── check_mvp.py
├── tests/
├── docker-compose.yml
├── requirements.txt
├── .env.example
├── AGENTS.md
└── README.md
```

## Environment

Create local env file:

```bash
cp .env.example .env
```

Windows CMD:

```cmd
copy .env.example .env
```

Important variables:

```text
APP_NAME=AI Life Planner
APP_ENV=local
APP_DEBUG=true

POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=ai_life_planner
POSTGRES_USER=ai_life_planner
POSTGRES_PASSWORD=<local-password>

DATABASE_URL=postgresql+psycopg://<user>:<password>@localhost:5432/<database>

TELEGRAM_BOT_TOKEN=

PLAN_START_BUFFER_MINUTES=30
DEFAULT_PLAN_START_TIME=18:30

LLM_PROVIDER=mock
LLM_BASE_URL=
LLM_API_KEY=
LLM_MODEL=
```

For local Telegram usage, set `TELEGRAM_BOT_TOKEN` in `.env`.

Do not commit `.env`, real tokens, real API keys, cookies, or private credentials. See [docs/SECURITY_BASELINE.md](docs/SECURITY_BASELINE.md).

## Local Setup

### 1. Create And Activate Virtual Environment

```bash
python -m venv .venv
```

PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Windows CMD:

```cmd
.venv\Scripts\activate
```

Linux/macOS/WSL:

```bash
source .venv/bin/activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Start PostgreSQL

```bash
docker compose up -d postgres
```

Check:

```bash
docker compose ps
```

### 4. Apply Migrations

```bash
alembic upgrade head
```

This creates and updates the database schema, including `tasks.target_date` for today/tomorrow planning.

### 5. Run FastAPI

```bash
uvicorn app.main:app --reload
```

Health check:

```text
http://127.0.0.1:8000/health
```

Expected response:

```json
{
  "status": "ok",
  "service": "ai-life-planner"
}
```

### 6. Run Telegram Bot

Set `TELEGRAM_BOT_TOKEN` in `.env`, then run:

```bash
python -m app.bot.main
```

Example natural-language messages:

```text
Мой график с 10 до 19, хочу спать в 00:30
Моя цель: накопить 500000 рублей, научиться рисовать, сделать мобильное приложение
Что сделать для целей?
Сегодня хочу разобрать документы
Завтра хочу позаниматься математикой
Покажи план завтра
Итог дня: документы сделал, математику не сделал
Я задержался до 20
```

Useful bot commands:

```text
/start
/tasks
/plan
/done <task_id>
/clear
```

## Smoke Checks

Run the MVP smoke-check:

```bash
python scripts/check_mvp.py
```

Expected:

```text
mvp check ok
```

Import check:

```bash
python - <<'PY'
from app.bot.main import dp
from app.main import app
print("bot and app import ok")
PY
```

Tests:

```bash
pytest
```

## Documentation

- [Product spec](docs/PRODUCT_SPEC.md)
- [Security baseline](docs/SECURITY_BASELINE.md)
- [Manual UAT scenarios](docs/UAT_SCENARIOS.md)
- [Codex/project instructions](AGENTS.md)

## Security Rules

- Never commit `.env`.
- Never commit Telegram tokens, LLM keys, database passwords, cookies, or session tokens.
- Keep `.env.example` safe and placeholder-only.
- Do not log secrets or full database URLs with passwords.
- User-owned data must be filtered by user context.
- Schema changes must go through Alembic.
- Do not delete Docker volumes or user data as a shortcut.

## Development Principles

- Telegram bot and future API should stay thin.
- Business logic belongs in `app/services/`.
- Parser or LLM extracts structure; backend validates and stores.
- Keep the MVP universal; do not hardcode it around one user's schedule, tasks, or goals.
- Keep the mock parser as fallback when real LLM support is added.
