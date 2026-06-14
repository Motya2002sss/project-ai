# AI Life Planner

AI Life Planner is a Telegram-first MVP for an AI daily and life planner.

The product is not a plain todo list and not a command-only Telegram bot. The user writes normal human text about their schedule, energy, goals, tasks, and day results. The system turns that text into persistent profile data, long-term goals, dated tasks, a realistic day plan, and daily progress.

Core principle:

- parser or future LLM extracts structure from natural language;
- backend validates, stores, plans, and controls state;
- important product state lives in PostgreSQL, not only in chat messages.

## Current MVP Status

The MVP already includes a working Telegram bot flow, shared business services, database persistence, migrations, and smoke checks.

Implemented:

- FastAPI app with `/health`;
- PostgreSQL through Docker Compose;
- SQLAlchemy database models;
- Alembic migrations;
- Telegram bot through aiogram;
- mock natural-language parser;
- user profile storage;
- long-term goals;
- tasks;
- `Task.target_date`;
- today/tomorrow task separation;
- today/tomorrow planning;
- goal task suggestions;
- work/sleep-aware planning;
- configurable buffer after work;
- priority and estimated duration handling;
- overflow tasks marked as not scheduled;
- mark done flow;
- daily summary flow;
- smoke-check script at `scripts/check_mvp.py`;
- product, UAT, and security documentation in `docs/`.

Not ready yet:

- real LLM parser for production-quality natural language understanding;
- Web UI;
- production authentication;
- production deployment;
- full FastAPI product API for a future Web UI.

FastAPI currently provides the backend foundation and `/health`. The primary MVP interface is Telegram, and the bot uses the same service layer that future API endpoints should use.

## Project Structure

```text
ai-life-planner/
├── app/
│   ├── api/              # FastAPI routers
│   ├── bot/              # Telegram bot entry point and handlers
│   ├── core/             # settings and configuration
│   ├── db/               # SQLAlchemy engine, session, base
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

## Environment Variables

Create a local `.env` file from the example:

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

Never commit `.env`, real tokens, real API keys, cookies, passwords, or private credentials. Keep `.env.example` safe and placeholder-only.

## Local Setup

### 1. Create And Activate A Virtual Environment

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

Check the container:

```bash
docker compose ps
```

### 4. Apply Alembic Migrations

```bash
alembic upgrade head
```

This applies the current schema, including `tasks.target_date` for separating today and tomorrow tasks.

### 5. Run FastAPI

```bash
uvicorn app.main:app --reload
```

Health endpoint:

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

## Checks

Run the MVP smoke check:

```bash
python scripts/check_mvp.py
```

Expected output:

```text
mvp check ok
```

Run the bot/app import check:

```bash
python - <<'PY'
from app.bot.main import dp
from app.main import app
print("bot and app import ok")
PY
```

Run tests when available:

```bash
pytest
```

## Documentation

- [Product spec](docs/PRODUCT_SPEC.md)
- [Security baseline](docs/SECURITY_BASELINE.md)
- [Manual UAT scenarios](docs/UAT_SCENARIOS.md)
- [Codex/project instructions](AGENTS.md)

## Security Notes

- Do not commit `.env`.
- Do not commit Telegram tokens, LLM keys, database passwords, cookies, or session tokens.
- Do not log secrets or full database URLs with passwords.
- User-owned data must be filtered by user context.
- Schema changes must go through Alembic.
- Do not delete Docker volumes or user data as a shortcut.
- See [docs/SECURITY_BASELINE.md](docs/SECURITY_BASELINE.md) before adding auth, LLM calls, logging, or deployment configuration.

## Development Principles

- Telegram bot and future API endpoints should stay thin.
- Business logic belongs in `app/services/`.
- Parser or LLM extracts structured meaning; backend validates and stores.
- The planner must stay universal and must not be hardcoded around one user's schedule, goals, or tasks.
- Keep the mock parser as a fallback when real LLM support is added.
