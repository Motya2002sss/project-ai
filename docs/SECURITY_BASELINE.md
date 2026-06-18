# AI Life Planner Security Baseline

AI Life Planner is intended to become a commercial product. Security, privacy, and data isolation are part of the product baseline, not optional cleanup work.

## Secrets

Never commit:

- `.env` or `.env.*` files, except `.env.example`;
- Telegram bot tokens;
- OpenAI or other LLM API keys;
- database passwords from real environments;
- private URLs with credentials;
- cookies, session tokens, or Authorization headers;
- logs that contain secrets or raw configuration dumps.

Use `.env` for local secrets. Keep `.env.example` limited to safe local placeholders and empty values for real tokens.

Current ignore rules must include:

- `.env`
- `.env.*`
- `!.env.example`
- `.venv/`
- `node_modules/`
- `__pycache__/`
- `.pytest_cache/`
- frontend build outputs such as `dist/` and `build/`
- local database files such as `*.db`, `*.sqlite`, `*.sqlite3`
- logs such as `*.log` and `logs/`

## Logging

Do not log sensitive values:

- Telegram token;
- LLM API key;
- Authorization headers;
- cookies;
- raw `.env`;
- full database URLs with passwords.

If configuration must be printed during debugging, mask sensitive parts, for example:

- `sk-...abcd`
- `postgresql://user:***@host/db`

## Commit And Push Checklist

Before every commit:

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

Stop before committing if staged changes contain `.env`, tokens, real passwords, cookies, private URLs, or generated local artifacts.

Before push:

```bash
git remote -v
git branch --show-current
git push -u origin HEAD
```

Push only when `origin` points to the intended repository.

## FastAPI Baseline

For API work:

- validate request bodies with Pydantic schemas;
- do not trust user input;
- do not return unnecessary internal fields;
- avoid destructive endpoints without explicit confirmation;
- do not use production CORS wildcard settings;
- keep local development CORS restricted to known frontend origins such as `http://localhost:5173` and `http://127.0.0.1:5173`;
- do not add debug endpoints that reveal env, config, tokens, stack traces, or credentials;
- keep user-facing errors understandable without exposing internals.
- keep API endpoints thin and route user requests through services, parser, and planner layers.

## Database Safety

- Schema changes must go through Alembic migrations.
- Dev repair SQL should be idempotent where possible.
- Do not delete user data without explicit instruction.
- Do not delete Docker volumes as a shortcut.
- Do not call `drop_all()` or `create_all()` in runtime application code.
- Destructive operations must be explained before execution.

## Multi-User Data Isolation

Telegram users must only see their own data. Queries for goals, tasks, plans, and destructive actions must filter by the authenticated user context.

Current MVP rule:

- Telegram user is resolved through `get_or_create_user()`.
- Web/API MVP users are resolved through `user_external_id`.
- `user_external_id` is a local MVP identifier and not production authentication.
- The Today Web UI stores this temporary identifier in `localStorage`; do not treat it as proof of identity.
- Task, goal, and plan service queries must include `user_id` filters for user-owned data.
- Production Web API must introduce an explicit auth strategy before exposing user data beyond local development.

## LLM Safety

When an LLM parser is enabled:

- the LLM returns structured JSON only;
- JSON is validated through Pydantic;
- invalid or unsafe output falls back to the mock parser;
- LLM requests must use a bounded timeout and must not block the bot indefinitely;
- LLM requests must enforce input and output limits before provider calls;
- thinking-capable local models should use parser-safe settings such as `LLM_OLLAMA_THINK=false` by default;
- the LLM does not execute commands;
- the LLM is not the source of truth for database writes;
- secrets, `.env`, tokens, credentials, and internal config must not be sent to the LLM;
- prompt injection must not allow users to reveal secrets, change system behavior, or bypass backend validation.
- fallback logs may include provider, model, error class, and sanitized error message only.

## Dependency Safety

- Add dependencies only when there is a clear product or engineering reason.
- Prefer maintained packages with active security support.
- Do not add packages that require external telemetry or secrets without review.
- Keep dependency changes small and explain why they are needed.

## Before Production

Before a production launch:

- add real authentication for Web API users;
- define environment-specific config for local, staging, and production;
- disable debug mode in production;
- configure production-safe CORS;
- add structured logging with secret masking;
- add database backups and migration rollback procedures;
- add rate limits for bot/API entry points;
- review dependency vulnerabilities;
- add monitoring for failed jobs, parser failures, and database errors;
- document incident response for leaked tokens or corrupted user data.
