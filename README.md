# AI Life Planner

AI Life Planner is a Telegram-first MVP for an AI daily and life planner.

The product is not a plain todo list and not a command-only Telegram bot. The user writes normal human text about their schedule, energy, goals, tasks, and day results. The system turns that text into persistent profile data, long-term goals, dated tasks, a realistic day plan, and daily progress.

Core principle:

- parser or LLM extracts structure from natural language;
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
- optional OpenAI/openai-compatible/Ollama LLM parser;
- automatic fallback to mock parser when LLM is unavailable or invalid;
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

- production-quality LLM evaluation and prompt tuning;
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

LLM_ENABLED=false
LLM_PROVIDER=mock
LLM_BASE_URL=
LLM_API_KEY=
LLM_MODEL=
LLM_TIMEOUT_SECONDS=30
LLM_MAX_INPUT_CHARS=1500
LLM_MAX_OUTPUT_TOKENS=250
LLM_OLLAMA_THINK=false
LLM_EVAL_STRICT=false
```

For local Telegram usage, set `TELEGRAM_BOT_TOKEN` in `.env`.

Never commit `.env`, real tokens, real API keys, cookies, passwords, or private credentials. Keep `.env.example` safe and placeholder-only.

## LLM Parser

The default parser is local and deterministic:

```text
LLM_ENABLED=false
LLM_PROVIDER=mock
```

To enable OpenAI:

```text
LLM_ENABLED=true
LLM_PROVIDER=openai
LLM_API_KEY=<your-local-key>
LLM_MODEL=gpt-4o-mini
LLM_TIMEOUT_SECONDS=30
LLM_MAX_INPUT_CHARS=1500
LLM_MAX_OUTPUT_TOKENS=250
```

To use an OpenAI-compatible endpoint:

```text
LLM_ENABLED=true
LLM_PROVIDER=openai-compatible
LLM_BASE_URL=https://your-openai-compatible-endpoint/v1
LLM_API_KEY=<your-local-key>
LLM_MODEL=<model-name>
LLM_TIMEOUT_SECONDS=30
LLM_MAX_INPUT_CHARS=1500
LLM_MAX_OUTPUT_TOKENS=250
```

OpenAI-compatible means an API that implements `/v1/chat/completions`. Some local providers expose that shape, but native Ollama should use `LLM_PROVIDER=ollama`.

Native Ollama uses `{LLM_BASE_URL}/api/chat` and reads `response["message"]["content"]`:

```env
LLM_ENABLED=true
LLM_PROVIDER=ollama
LLM_BASE_URL=http://localhost:11434
LLM_MODEL=<local-model-name>
LLM_API_KEY=ollama
LLM_TIMEOUT_SECONDS=30
LLM_MAX_INPUT_CHARS=1500
LLM_MAX_OUTPUT_TOKENS=250
LLM_OLLAMA_THINK=false
```

The LLM must return JSON that validates as `ParsedUserMessage`. If `LLM_ENABLED=false`, the API key is missing, the provider is `mock`, input is too long, the request times out, the provider returns invalid JSON, or Pydantic validation fails, the system falls back to the mock parser. Telegram users should receive a normal planner response rather than a technical LLM error.

For thinking-capable local models, keep `LLM_OLLAMA_THINK=false` for parser calls unless you are explicitly evaluating that behavior. The parser needs clean JSON, not reasoning text.

The LLM only extracts structure. Database writes, task status changes, plan building, and persistence stay in backend services.

Parser evaluation cases live in `tests/fixtures/parser_cases.json`. Tests run these cases against the mock parser without making real LLM calls. Local models are useful for development and comparison, but they are not required for production.

Run the parser eval dataset against the currently configured parser/provider:

```bash
python scripts/eval_parser_cases.py
```

Strict LLM eval fails a case when LLM is enabled but the parser fell back to mock:

```bash
python scripts/eval_parser_cases.py --strict-llm
```

You can also set `LLM_EVAL_STRICT=true`. The eval summary prints total cases, passed, failed, fallback count, provider, and model.

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
