# AI Life Planner

AI Life Planner is an iOS-first AI daily and life planner. FastAPI, PostgreSQL, and the Planning Engine are the single product brain. Android follows iOS validation; the existing Web and Telegram clients remain in the repository as frozen compatibility surfaces.

Canonical product statement: **iOS-first. Android later. Web/Telegram frozen. Backend is the single product brain.**

The product is not a plain todo list and not a command-only Telegram bot. The user writes normal human text about their schedule, energy, goals, tasks, and day results. The system turns that text into persistent profile data, long-term goals, dated tasks, a realistic day plan, and daily progress.

Core principle:

- parser or LLM extracts structure from natural language;
- backend validates, stores, plans, and controls state;
- important product state lives in PostgreSQL, not only in chat messages.

## Current MVP Status

The MVP already includes the shared backend core, authenticated Mobile API v1, database persistence, migrations, tests, and frozen compatibility clients.

Implemented:

- FastAPI app with `/health`;
- PostgreSQL through Docker Compose;
- SQLAlchemy database models;
- Alembic migrations;
- frozen Telegram bot through aiogram;
- mock natural-language parser;
- optional OpenAI/openai-compatible/Ollama LLM parser;
- automatic fallback to mock parser when LLM is unavailable or invalid;
- shared message processing service for iOS text, frozen compatibility text, and future voice transcripts;
- authenticated Mobile API v1 for iOS dogfooding;
- frozen FastAPI Web compatibility API;
- frozen Today Web UI in `web/`;
- user profile storage;
- long-term goals;
- tasks;
- `Task.target_date`;
- task operations: create, update, cancel, and complete;
- fixed, flexible, and unscheduled task types;
- fixed times, preferred day windows, earliest start, latest end, deadline, and duration constraints;
- today/tomorrow task separation;
- today/tomorrow planning;
- goal task suggestions;
- deterministic work/sleep/current-time-aware interval planning;
- configurable buffer after work;
- priority and estimated duration handling;
- 15-minute free-slot search with a no-overlap invariant;
- minimal-disruption rebuilds that preserve valid existing slots;
- honest unscheduled reasons and clarification for unresolved conflicts;
- factual plan diff returned by the shared message pipeline;
- atomic `DaySnapshot` returned by message processing, without a post-submit GET waterfall;
- persistent clarification, confirmation, and fixed-conflict interactions shared by every channel;
- request idempotency and plan version checks for safe retries and stale proposals;
- limited routines with `daily`, `weekdays`, and `selected_weekdays` cadence and lazy idempotent occurrences;
- completed tasks retained in their original timeline position as day history;
- mark done flow;
- daily summary flow;
- smoke-check script at `scripts/check_mvp.py`;
- product, UAT, and security documentation in `docs/`.

Not ready yet:

- production LLM provider selection and ongoing prompt tuning;
- the native iOS client itself;
- TestFlight multi-user authentication;
- production deployment;
- Week, Path, Profile mutation, Voice/STT, and general Undo mobile contracts;
- advanced recurrence editing, exceptions, and calendar synchronization.

FastAPI currently provides `/health`, frozen `/api` Web compatibility endpoints, and an authenticated `/api/v1` contract for the first iOS vertical slice. Every channel converges on the same parser, service, and planner layers.

Planning is split deliberately: the parser or LLM extracts operations and constraints, while the backend calculates timezone-aware availability, resolves user-owned tasks, prevents overlaps, persists changes atomically, and produces the factual diff. The LLM never chooses or writes the final schedule directly.

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
├── docs/                 # Russian Obsidian project vault
│   ├── 00 Главная.md
│   ├── 02 Дорожная карта/
│   ├── 05 Тестирование продукта/
│   └── 07 Техническая документация/
├── migrations/           # Alembic migrations
├── scripts/
│   └── check_mvp.py
├── tests/
├── web/                  # minimal Vite/React Today screen
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

MOBILE_DOGFOOD_TOKEN=<local-secret>
MOBILE_DOGFOOD_USER_EXTERNAL_ID=mobile:dogfood

PLAN_START_BUFFER_MINUTES=30
DEFAULT_PLAN_START_TIME=18:30
MESSAGE_REQUEST_TIMEOUT_SECONDS=15
MESSAGE_SLOW_NOTICE_SECONDS=5
INTERACTION_TTL_MINUTES=30
IDEMPOTENCY_TTL_HOURS=24

LLM_ENABLED=false
LLM_PROVIDER=mock
LLM_BASE_URL=
LLM_API_KEY=
LLM_MODEL=
LLM_TIMEOUT_SECONDS=12
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
LLM_TIMEOUT_SECONDS=12
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
LLM_TIMEOUT_SECONDS=12
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
LLM_TIMEOUT_SECONDS=12
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

### 6. Use Mobile API v1

Mobile API v1 is the active client contract for local iOS dogfooding. Configure `MOBILE_DOGFOOD_TOKEN` in `.env`, send it as a bearer token, and never send a user id from the client.

```text
GET   /api/v1/today
POST  /api/v1/capture
POST  /api/v1/interactions/{interaction_id}/responses
PATCH /api/v1/tasks/{task_id}/status
```

Capture example:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/capture \
  -H "Authorization: Bearer $MOBILE_DOGFOOD_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "request_id": "ios-capture-1",
    "text": "Сегодня задержусь на работе до 20"
  }'
```

Capture and interaction responses contain one status, one factual `plan_diff`, and one consistent `day_snapshot`. Task status mutations return the changed task, diff, and rebuilt snapshot in the same response. See [Mobile API Contract v1](docs/07%20Техническая%20документация/Mobile%20API%20Contract%20v1.md).

The bearer token is deliberately limited to one local dogfood identity. It is not TestFlight or production authentication.

### 6.1 Production identity foundation (API v2)

The production-safe boundary is implemented locally under `/api/v2`: Apple identity-token verification, one-use state/nonce challenges, hashed rotating device sessions, authenticated account export/deletion, and preview-first onboarding. Client-supplied user identity is rejected.

Native mobile stores access/refresh credentials in SecureStore and namespaces cache/drafts by the authenticated public user UUID. The legacy v1 cache can migrate only into the local `dogfood` namespace.

This foundation has automated local coverage, but is not yet a public login: real Apple release credentials, authorization-code exchange/revocation, staging and TestFlight verification remain required. See [Authentication and Account Lifecycle v1](docs/07%20Техническая%20документация/Authentication%20and%20Account%20Lifecycle%20v1.md).

### 7. Frozen Web API Foundation

The MVP API is intentionally small. It powers the local Today Web UI and prepares the backend for future voice input without adding production auth yet.

Supported input sources:

```text
web_text
telegram_text
telegram_voice_transcript
```

Future voice flow should be:

```text
voice/audio -> speech-to-text -> text -> /api/message -> process_user_message -> parser -> services -> planner
```

Message endpoint:

```bash
curl -X POST http://127.0.0.1:8000/api/message \
  -H "Content-Type: application/json" \
  -d '{
    "user_external_id": "local-user-1",
    "source": "web_text",
    "text": "Сегодня хочу разобрать документы"
  }'
```

`MessageResponse` uses explicit states: `applied`, `clarification_required`, `confirmation_required`, `conflict`, `no_change`, `unsupported_capability`, and `failed`. It includes a backend-calculated `plan_diff` and a consistent `day_snapshot` with plan, tasks, goals, routines, progress, day context, and plan version. Clarifications and confirmations carry a user-scoped interaction ID and expiry. Fixed-time conflicts and unconfirmed routines do not partially mutate the plan.

Read endpoints:

```text
GET /api/profile/{user_external_id}
GET /api/goals/{user_external_id}
GET /api/tasks/{user_external_id}
GET /api/day/{user_external_id}?date=today
GET /api/plan/{user_external_id}?date=today
GET /api/plan/{user_external_id}?date=tomorrow
PATCH /api/tasks/{task_id}/status
POST /api/tasks/{task_id}/done
```

`user_external_id` is a temporary MVP identifier for local/API experiments. It is not production authentication and must not be treated as a secure user identity in public deployments.

The status endpoint accepts only `planned` or `done`. It filters the task by both its ID and the temporary user identity before changing state:

```bash
curl -X PATCH http://127.0.0.1:8000/api/tasks/1/status \
  -H "Content-Type: application/json" \
  -d '{"user_external_id": "web-demo-user", "status": "planned"}'
```

`POST /api/tasks/{task_id}/done` remains available for backward compatibility.

FastAPI allows local CORS only for Vite dev origins:

```text
http://localhost:5173
http://127.0.0.1:5173
```

### 8. Run The Frozen Today Web UI

The retained Web UI is frozen. It remains useful for compatibility checks but is not an active product surface.

Start the backend first:

```bash
uvicorn app.main:app --reload
```

Then run the frontend:

```bash
cd web
npm install
npm run dev
```

Open:

```text
http://127.0.0.1:5173
```

Optional API override:

```bash
VITE_API_BASE_URL=http://127.0.0.1:8000 npm run dev
```

The Web UI stores `User ID` in `localStorage` and defaults to `web-demo-user`. This is a temporary local MVP identity, not production authentication.

Production auth, payments, deployment, a full calendar, and a full multi-screen Web UI are not implemented.

### 9. Run The Frozen Telegram Bot

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

Build the Web UI:

```bash
cd web
npm run build
```

## Документация проекта

Главная точка входа в русскоязычный Obsidian vault:

- [00 Главная](docs/00%20Главная.md)
- [Текущая дорожная карта](docs/02%20Дорожная%20карта/Сейчас%20—%20далее%20—%20позже.md)
- [Mobile API Contract v1](docs/07%20Техническая%20документация/Mobile%20API%20Contract%20v1.md)
- [Authentication and Account Lifecycle v1](docs/07%20Техническая%20документация/Authentication%20and%20Account%20Lifecycle%20v1.md)

## Security Notes

- Do not commit `.env`.
- Do not commit Telegram tokens, LLM keys, database passwords, cookies, or session tokens.
- Do not log secrets or full database URLs with passwords.
- User-owned data must be filtered by user context.
- Schema changes must go through Alembic.
- Do not delete Docker volumes or user data as a shortcut.
- See [Базовая безопасность](docs/07%20Техническая%20документация/Базовая%20безопасность.md) before adding auth, LLM calls, logging, or deployment configuration.

## Development Principles

- Mobile and compatibility endpoints must stay thin.
- Mobile stores only cache and drafts; backend owns all product state and calculations.
- Business logic belongs in `app/services/`.
- Parser or LLM extracts structured meaning; backend validates and stores.
- LLM output is untrusted input; deterministic backend code calculates all displayed times and rejects overlaps.
- The planner must stay universal and must not be hardcoded around one user's schedule, goals, or tasks.
- Mock/deterministic parsing is allowed only in local/test. Staging/production AI failures must be typed and recoverable, never presented as successful real AI work.
