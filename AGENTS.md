# AGENTS.md

This file is the project-level instruction set for Codex and other coding agents working on AI Life Planner.

## Product Meaning

AI Life Planner is an iOS-first AI daily and life planner. Android comes after the iOS version is validated. The existing Web and Telegram clients are frozen compatibility surfaces, not active product targets.

The product is not a normal todo list and not a command-only Telegram bot. The user writes natural text, and the system turns that text into:

- profile data;
- long-term goals;
- dated tasks;
- realistic daily plans;
- completion status;
- daily summaries.

The main product value is reducing manual planning work. Users should not maintain many fields, dates, priorities, and reschedules by hand.

## Current MVP Status

The repository already contains a working MVP foundation:

- FastAPI app with `/health`;
- PostgreSQL through Docker Compose;
- SQLAlchemy models;
- Alembic migrations;
- frozen Telegram bot through aiogram;
- frozen Web API compatibility foundation;
- frozen Today Web UI in `web/`;
- authenticated Mobile API v1 for local iOS dogfooding;
- mock natural-language parser;
- optional OpenAI/openai-compatible/Ollama parser integration with mock fallback;
- shared message processing service for Telegram text, Web text, and future voice transcripts;
- user profile flow;
- goals flow;
- tasks flow;
- `Task.target_date`;
- today/tomorrow task separation;
- today/tomorrow planning;
- goal task suggestions;
- work/sleep-aware planning;
- deterministic adaptive interval planning with fixed, flexible, and unscheduled tasks;
- conflict/clarification and factual plan diff contracts;
- mark done flow;
- daily summary flow;
- smoke-check script at `scripts/check_mvp.py`;
- parser eval dataset at `tests/fixtures/parser_cases.json`;
- Russian product, roadmap, UAT, and security documentation in the Obsidian vault at `docs/`.

Treat FastAPI, PostgreSQL, the shared message pipeline, and the Planning Engine as the active product core and single source of truth. Preserve the frozen Web and Telegram flows, but do not extend them unless the user explicitly reactivates those surfaces.

## Required Product Context

Before starting a product or architecture task, read:

```text
docs/00 Главная.md
docs/02 Дорожная карта/Сейчас — далее — позже.md
docs/03 Решения/Журнал решений.md
docs/07 Техническая документация/Mobile API Contract v1.md
```

If a task changes product strategy, architecture, or the active roadmap stage, update the corresponding vault documents in the same commit.

Do not require documentation updates for every small CSS adjustment, isolated typo, or other change that does not alter behavior, strategy, architecture, or roadmap state.

## Architecture Rules

- Mobile, bot, and API layers must stay thin.
- Business logic belongs in `app/services/`.
- Database state belongs in SQLAlchemy models and PostgreSQL.
- Schema changes belong in Alembic migrations.
- All clients must use the same backend contract and service layer; mobile must not implement parser, scheduler, or AI planning logic.
- New text input channels must converge on the shared message processing pipeline.
- Final schedule times must be calculated and overlap-checked by deterministic backend code.
- Preserve valid fixed, completed, past, and existing flexible plan positions where possible.
- Future voice/audio input must be converted to text first, then routed through the same parser and services without separate planning logic.
- Important state must not live only inside chat history or LLM messages.
- User-owned reads and writes must filter by user context, usually `user_id`.

## Parser And LLM Rules

The default parser is the mock parser. Real LLM parsing can be enabled through `LLM_PROVIDER=openai`, `LLM_PROVIDER=openai-compatible`, or native `LLM_PROVIDER=ollama`.

Parser or LLM responsibilities:

- parse natural-language messages;
- extract structured tasks, goals, constraints, dates, energy, and user intent;
- generate user-facing explanations when needed.

Backend responsibilities:

- validate parser output;
- decide what can be stored;
- create and update database records;
- build plans;
- check dates and time windows;
- control task statuses.
- calculate availability, select free slots, reject fixed conflicts, and produce factual plan diffs.

LLM integration rules:

- keep the mock parser as fallback;
- keep `LLM_ENABLED=false` as the safe default;
- enforce `LLM_MAX_INPUT_CHARS`, `LLM_MAX_OUTPUT_TOKENS`, and `LLM_TIMEOUT_SECONDS`;
- use native Ollama `/api/chat` for `LLM_PROVIDER=ollama`;
- keep `LLM_OLLAMA_THINK=false` by default for parser calls;
- ask the LLM for structured JSON only;
- validate JSON through Pydantic or equivalent schemas;
- treat LLM output as untrusted input;
- do not let the LLM directly execute commands;
- do not let the LLM directly mutate database state;
- do not send `.env`, tokens, credentials, private URLs, or internal config to the LLM.
- log fallback warnings safely without API keys, Authorization headers, cookies, `.env`, or full database URLs.

## Product Universality

Do not hardcode the product around one person.

Allowed:

- examples in README, docs, tests, and fallback heuristics;
- broad default assumptions when profile data is missing;
- generic heuristics for durations, priorities, and goal task suggestions.

Not allowed:

- assuming every user works 9-18;
- assuming every user sleeps at 23:30;
- assuming all goals are gym, English, or AI projects;
- building flows that only work for one user's personal routine.

The planner must work for finance, study, health, family, creativity, career, personal projects, and other user-defined goals.

## Security Rules

Follow `docs/07 Техническая документация/Базовая безопасность.md`.

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

## Database Rules

- Use Alembic for schema changes.
- Do not call `drop_all()` or `create_all()` in runtime application code.
- Do not delete user data without explicit instruction.
- Do not delete Docker volumes as a shortcut.
- Keep multi-user isolation in mind for Mobile API and all retained compatibility flows.

## Development Constraints

- Do not rewrite the project from scratch.
- Do not change the tech stack without explicit need.
- Do not add dependencies casually.
- Do not develop the frozen Web or Telegram clients unless explicitly requested.
- Do not create Android work before the iOS version is validated.
- Do not move parser, scheduler, confirmation, conflict, or planning logic into a client.
- Do not wire production LLM behavior unless explicitly requested.
- Keep patches focused on the user's request.
- Do not change code when the user asks for documentation-only work.
- If parser, tasks, goals, planning, bot UX, or migrations change, update smoke checks or tests.

## Required Checks Before Commit

Run the relevant checks before committing. For MVP-level changes, run:

```bash
alembic upgrade head
python scripts/check_mvp.py
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

Before committing, inspect:

```bash
git status
git diff --stat
git diff --cached --name-only
git diff --cached
```

Stop before committing if staged changes contain secrets, local artifacts, generated noise, or unrelated edits.

## Commit And Push Rules

- Commit only after checks pass.
- Use the commit message requested by the user when one is provided.
- Push only to the configured intended remote.
- If `origin` is missing or wrong, stop and ask for the correct URL.
- After push, verify that the remote branch points to the new commit.

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
- push is completed when remote is valid;
- remote branch verification confirms the pushed commit.
