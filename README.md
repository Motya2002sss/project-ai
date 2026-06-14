# AI Life Planner

AI Life Planner is a Telegram-first AI life planner MVP. It is not just a todo list and not just a command bot.

The user writes normal human text, and the system turns it into:

- a remembered user profile;
- long-term goals;
- dated tasks for today or tomorrow;
- a realistic day plan;
- task completion updates;
- end-of-day summaries.

The current MVP uses a mock parser with deterministic fallback heuristics. A real LLM parser is planned later, but the backend already owns persistence, validation, task state, and planning rules.

## What Works Now

- FastAPI app with `/health`.
- PostgreSQL through Docker Compose.
- SQLAlchemy models:
  - `User`
  - `Goal`
  - `Task`
  - `DayPlan`
  - `PlanItem`
- Alembic migrations.
- Telegram bot through aiogram.
- Natural-language mock parser.
- User profile storage:
  - name;
  - timezone;
  - work start/end;
  - sleep time.
- Goals:
  - create from natural language;
  - list active goals;
  - suggest small tasks from goals.
- Tasks:
  - create from natural language;
  - attach to `target_date`;
  - list active tasks;
  - mark done;
  - clear tasks.
- Planning:
  - today/tomorrow separation;
  - priority ordering;
  - estimated duration;
  - work schedule;
  - configurable buffer after work;
  - sleep deadline;
  - low-energy adjustment;
  - overflow tasks marked as not scheduled.
- Daily summary:
  - completed tasks are marked done;
  - skipped tasks remain active;
  - plan is rebuilt.
- Smoke check script: `scripts/check_mvp.py`.

## Not Ready Yet

- Real LLM integration is not production-ready yet. The mock parser remains the default.
- Web UI is not implemented yet.
- Production auth for future Web API is not implemented yet.
- FastAPI currently exposes only `/health`; product flows are available through the Telegram bot and shared services.

## Project Structure

```text
ai-life-planner/
├── app/
│   ├── api/              # FastAPI routers
│   ├── bot/              # Telegram bot entrypoint
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
└── README.md
```

## Environment Variables

Create `.env` from `.env.example`:

```bash
cp .env.example .env
```

On Windows CMD:

```cmd
copy .env.example .env
```

Required/local variables:

```text
APP_NAME=AI Life Planner
APP_ENV=local
APP_DEBUG=true

DATABASE_URL=postgresql+psycopg://<user>:<password>@localhost:5432/<database>

TELEGRAM_BOT_TOKEN=

PLAN_START_BUFFER_MINUTES=30
DEFAULT_PLAN_START_TIME=18:30

LLM_PROVIDER=mock
LLM_BASE_URL=
LLM_API_KEY=
LLM_MODEL=
```

For Telegram bot usage, set `TELEGRAM_BOT_TOKEN` in `.env`.

Do not commit `.env` or real secrets. See [docs/SECURITY_BASELINE.md](docs/SECURITY_BASELINE.md).

## Local Setup

### 1. Create And Activate Venv

```bash
python -m venv .venv
```

Windows PowerShell:

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

Check container status:

```bash
docker compose ps
```

### 4. Apply Alembic Migrations

```bash
alembic upgrade head
```

This creates the core tables and ensures `tasks.target_date` exists for today/tomorrow planning.

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

Make sure `TELEGRAM_BOT_TOKEN` is set in `.env`, then run:

```bash
python -m app.bot.main
```

The bot supports natural-language messages such as:

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

Slash commands also exist for quick checks:

```text
/start
/tasks
/plan
/done <task_id>
/clear
```

## Smoke Checks

Run:

```bash
python scripts/check_mvp.py
```

Expected:

```text
mvp check ok
```

Bot/FastAPI import check:

```bash
python - <<'PY'
from app.bot.main import dp
from app.main import app
print("bot and app import ok")
PY
```

Run tests:

```bash
pytest
```

## Product Docs

- [Product spec](docs/PRODUCT_SPEC.md)
- [Manual UAT scenarios](docs/UAT_SCENARIOS.md)
- [Security baseline](docs/SECURITY_BASELINE.md)

## Development Principles

- LLM/parser extracts structure; backend controls state and planning.
- Important state must be stored in PostgreSQL, not in chat history.
- User-owned data must be filtered by `user_id`.
- Schema changes go through Alembic.
- Do not commit secrets.
- Keep Telegram bot and future Web UI on the same service layer.
