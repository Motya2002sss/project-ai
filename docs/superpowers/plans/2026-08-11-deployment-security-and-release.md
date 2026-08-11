# Deployment, Security, and Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use test-driven-development, systematic-debugging, requesting-code-review, and verification-before-completion while implementing this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the minimum secure operational layer, staging separation, feature kill switches, support tooling, backup/restore, observability, reproducible deployment, CI, and App Store release configuration required for a locally verified production candidate.

**Architecture:** One production FastAPI image runs as non-root behind TLS/reverse proxy; migrations and backup/restore are explicit jobs. Environment validation separates local/staging/production data and integrations. Server feature flags are cached briefly but authoritative. Observability uses privacy-filtered provider interfaces. Support commands operate on internal/public IDs and expose technical state only. Release artifacts and checklists distinguish local implementation from external Apple/RevenueCat/deployment verification.

**Tech Stack:** Docker/Compose, FastAPI middleware, PostgreSQL `pg_dump/pg_restore`, shellcheck, GitHub Actions, Expo EAS configuration, pytest/Vitest, configurable Sentry/PostHog-compatible adapters without external account creation.

## Global Constraints

- Staging uses a separate database/API/Apple sandbox/RevenueCat Test Store/analytics/error environment/OpenAI budget and contains no production user data.
- Critical AI planning, voice, Apple Calendar write, workout adaptation, nutrition generation, paywall, onboarding, and experimental progress formulas can be disabled server-side without an app release.
- Production has debug/docs/dev fixtures/dogfood auth/Quick Tunnel/default passwords/public PostgreSQL/local API URLs disabled.
- No token, capture text, meal content, workout note, health-like detail, email, raw prompt, or Authorization header enters logs, analytics, error reports, or support bundles.
- Restore over production is impossible without an explicit exact confirmation string and target validation.
- No EAS build, Apple credential creation, App Store configuration, DNS, deployment, external account creation, real purchase, volume deletion, or push occurs without owner permission.
- The user-owned `.gitignore` change remains untouched.

---

## Task 1: Request IDs, Readiness, Security Middleware, and Production Validation

**Files:**
- Create: `app/core/logging.py`
- Create: `app/middleware/request_context.py`
- Create: `app/middleware/security.py`
- Modify: `app/api/health.py`
- Modify: `app/main.py`
- Modify: `app/db/session.py`
- Test: `tests/test_production_runtime.py`
- Test: `tests/test_request_security.py`

**Interfaces:**
- Produces `X-Request-ID`, structured sanitized logs, `/ready`, trusted hosts, secure headers, request-size limit, strict configurable CORS, and startup validation.
- Consumes production runtime settings and database connection.

- [ ] **Step 1: Write failing runtime/security tests**

Cover generated/preserved valid request ID, rejection of control characters, response correlation ID, no stack trace in error, request body limit, trusted host, strict CORS, CSP/security headers, `/ready` database failure, production docs disabled, debug false, and secret redaction.

- [ ] **Step 2: Confirm failure**

Run: `.venv/bin/pytest -q tests/test_production_runtime.py tests/test_request_security.py`
Expected: FAIL.

- [ ] **Step 3: Implement minimal middleware and readiness**

Use JSON logs with event name, level, request ID, route template, status, duration, and safe error class. Configure connection pool size/overflow/timeouts. `/health` is process liveness; `/ready` checks the database with a short timeout and no secret details.

- [ ] **Step 4: Run API regression tests**

Run: `.venv/bin/pytest -q tests/test_production_runtime.py tests/test_request_security.py tests/test_mobile_api.py tests/test_api_v2_auth.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/core/logging.py app/middleware app/api/health.py app/main.py app/db/session.py tests/test_production_runtime.py tests/test_request_security.py
git commit -m "Harden production request handling"
```

## Task 2: Server Feature Flags and Kill Switches

**Files:**
- Create: `app/models/operations.py`
- Modify: `app/models/__init__.py`
- Create: `migrations/versions/f6e5b4d7c866_feature_operations.py`
- Create: `app/services/feature_flag_service.py`
- Create: `app/api/v2/features.py`
- Test: `tests/test_feature_flags.py`

**Interfaces:**
- Produces typed flags `ai_planning`, `voice`, `apple_calendar_write`, `workout_adaptation`, `nutrition_generation`, `paywall`, `new_onboarding`, `experimental_progress_formulas`; `FeatureSnapshot` with version/TTL; admin CLI mutation only.
- Consumes environment and optional entitlement audience.

- [ ] **Step 1: Write failing kill-switch tests**

Cover safe defaults, environment-specific values, percentage/audience rules, version change, cache expiry, disabled feature returning typed `feature_disabled`, expensive operation checking immediately before mutation, and mobile fetching a public safe snapshot without admin metadata.

- [ ] **Step 2: Confirm failure**

Run: `.venv/bin/pytest -q tests/test_feature_flags.py`
Expected: FAIL.

- [ ] **Step 3: Implement database-backed flags and service gates**

Migration `f6e5b4d7c866` follows subscription revision `e5d4a3c6b755`. Seed every critical flag with conservative environment defaults in migration. Routes never accept flag mutations. A dedicated CLI uses exact names/environment and records actor/reason/time; service gates are invoked server-side at mutation boundaries.

- [ ] **Step 4: Run gate regression tests**

Run: `.venv/bin/pytest -q tests/test_feature_flags.py tests/test_transcription_api.py tests/test_activity_api.py tests/test_subscription_api.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/models/operations.py app/models/__init__.py migrations/versions/f6e5b4d7c866_feature_operations.py app/services/feature_flag_service.py app/api/v2/features.py tests/test_feature_flags.py
git commit -m "Add server-side feature kill switches"
```

## Task 3: Privacy-Safe Analytics, Errors, Metrics, and AI Budgets

**Files:**
- Create: `app/observability/events.py`
- Create: `app/observability/providers.py`
- Create: `app/observability/privacy.py`
- Create: `app/services/usage_metering_service.py`
- Create: `mobile/src/observability/analytics.ts`
- Create: `mobile/src/observability/errorReporting.ts`
- Test: `tests/test_observability_privacy.py`
- Test: `mobile/src/observability/__tests__/privacy.test.ts`

**Interfaces:**
- Produces allowlisted product events, privacy scrubber, backend metrics, per-user/provider token/cost budgets, no-op defaults, and environment-separated provider configuration.
- Consumes request ID, public user ID hash, provider timing, and normalized non-sensitive properties.

- [ ] **Step 1: Write failing privacy allowlist tests**

Allow exactly onboarding_started/completed, first_plan_created, today_opened, task_completed, result_recorded, replan_requested/applied, goal_created, milestone_completed, paywall_viewed, trial_started, purchase_completed/cancelled, restore_completed, subscription_expired, weekly_review_opened. Reject/scrub capture text, notes, meals, health values, tokens, email, prompts, Authorization/cookies, database URLs, and unknown properties.

- [ ] **Step 2: Write failing budget/metric tests**

Cover request latency/error rate, LLM latency/fallback/planning/billing/capture metrics; staging/production separation; daily/monthly OpenAI hard budget; per-user quota; cost unknown fail-closed for new AI calls while Today/completion continue; production provider absence/error must return a typed recoverable AI-unavailable result and must never present the mock parser as real AI.

- [ ] **Step 3: Confirm failures**

Run: `.venv/bin/pytest -q tests/test_observability_privacy.py`
Run: `cd mobile && npm test -- privacy`
Expected: FAIL.

- [ ] **Step 4: Implement provider interfaces with no-op defaults**

External PostHog/Sentry-compatible adapters are enabled only by DSN/key plus environment. Never create accounts. Scrub at the API boundary and again inside each provider adapter.

- [ ] **Step 5: Run checks and commit**

Run: `.venv/bin/pytest -q tests/test_observability_privacy.py && cd mobile && npm test && npm run typecheck && npm run lint`
Expected: PASS.

```bash
git add app/observability app/services/usage_metering_service.py tests/test_observability_privacy.py mobile/src/observability
git commit -m "Add privacy-safe observability and AI budgets"
```

## Task 4: Support Endpoint and Internal Support CLI

**Files:**
- Create: `app/models/support.py`
- Create: `migrations/versions/f7a6c5d4e388_support_requests.py`
- Create: `app/services/support_service.py`
- Create: `app/api/v2/support.py`
- Create: `scripts/support.py`
- Create: `mobile/src/features/support/SupportScreen.tsx`
- Create: `mobile/app/support.tsx`
- Test: `tests/test_support_tool.py`
- Test: `mobile/src/features/support/__tests__/supportPayload.test.ts`

**Interfaces:**
- Produces user support request with safe diagnostics and CLI commands `show-user`, `sync-entitlement`, `revoke-sessions`, `delete-account`, `recent-request-ids`.
- Consumes public/internal user ID, auth/subscription/device/app technical state, and request ID ledger.

- [ ] **Step 1: Write failing support privacy/authorization tests**

Support payload includes app version/build, correlation ID, normalized subscription state, device model family/OS version, and allowed diagnostic flags. It rejects tokens, capture text, plans, goal details, meal/workout/health-like content, email, and arbitrary keys. CLI requires internal operator mode, exact user identifier, explicit destructive confirmations, and never prints personal plans.

- [ ] **Step 2: Confirm failure**

Run: `.venv/bin/pytest -q tests/test_support_tool.py`
Run: `cd mobile && npm test -- supportPayload`
Expected: FAIL.

- [ ] **Step 3: Implement support storage, route, UI, and CLI**

Migration `f7a6c5d4e388` follows operations revision `f6e5b4d7c866`. The visible Profile button opens a short subject/message form plus an opt-in diagnostics summary. The CLI outputs compact JSON technical state, calls the same account/session/subscription services, and records operator action/reason without secrets.

- [ ] **Step 4: Run support tests**

Run: `.venv/bin/pytest -q tests/test_support_tool.py tests/test_account_deletion.py tests/test_subscription_reconciliation.py`
Run: `cd mobile && npm test && npm run typecheck && npm run lint`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/models/support.py migrations/versions/f7a6c5d4e388_support_requests.py app/services/support_service.py app/api/v2/support.py scripts/support.py tests/test_support_tool.py mobile/src/features/support mobile/app/support.tsx
git commit -m "Add privacy-safe support operations"
```

## Task 5: Production Docker and Environment Separation

**Files:**
- Create: `Dockerfile`
- Create: `.dockerignore`
- Create: `docker-compose.production.yml`
- Create: `docker-compose.staging.yml`
- Create: `deploy/nginx.conf.template`
- Create: `scripts/migrate.sh`
- Create: `scripts/validate-production-config.py`
- Test: `tests/test_container_contract.py`

**Interfaces:**
- Produces non-root image, migration job, backend service, internal PostgreSQL network, readiness/health checks, graceful shutdown, configurable workers, restart policy, and TLS proxy template.
- Consumes environment-injected secrets and immutable image tag.

- [ ] **Step 1: Write failing static container contract tests**

Assert pinned Python base version, locked requirements install, non-root `USER`, no copied `.env/.git/tests/mobile/node_modules`, healthcheck `/ready`, no Alembic in worker command, no published PostgreSQL in production, separate staging database/network/volume names, no default password, and retained previous image variable for rollback.

- [ ] **Step 2: Confirm failure**

Run: `.venv/bin/pytest -q tests/test_container_contract.py`
Expected: FAIL because production container files do not exist.

- [ ] **Step 3: Implement reproducible image and compose profiles**

Use an exact supported Python slim tag plus recorded digest after verification, install pinned wheels, create UID/GID, use `tini`/Uvicorn graceful timeout, separate migration service, strict internal networks, TLS forwarding headers, and configurable `BACKEND_IMAGE`/`PREVIOUS_BACKEND_IMAGE`.

- [ ] **Step 4: Build and smoke locally**

Run: `docker build -t ai-life-planner-backend:test .`
Run: `docker compose -f docker-compose.yml -f docker-compose.staging.yml config`
Run: `docker compose -f docker-compose.yml -f docker-compose.staging.yml up -d`
Run: `curl --fail http://127.0.0.1:8000/health && curl --fail http://127.0.0.1:8000/ready`
Run: `docker compose -f docker-compose.yml -f docker-compose.staging.yml down`
Expected: image and services healthy; volumes remain intact.

- [ ] **Step 5: Commit**

```bash
git add Dockerfile .dockerignore docker-compose.production.yml docker-compose.staging.yml deploy/nginx.conf.template scripts/migrate.sh scripts/validate-production-config.py tests/test_container_contract.py
git commit -m "Add production container deployment"
```

## Task 6: PostgreSQL Backup, Restore Guard, and Drill

**Files:**
- Create: `scripts/backup-postgres.sh`
- Create: `scripts/restore-postgres.sh`
- Create: `scripts/restore-drill.sh`
- Create: `docs/07 Техническая документация/Backup and Recovery Runbook.md`
- Test: `tests/test_backup_scripts.py`

**Interfaces:**
- Produces encrypted backup artifact metadata, retention pruning, guarded restore command, isolated drill database, and measured RTO report.
- Consumes database URLs through environment without printing them.

- [ ] **Step 1: Write failing shell contract tests**

Assert `set -euo pipefail`, private `mktemp -d`, `pg_dump --format=custom`, encryption recipient/key requirement, checksum, retention by explicit backup directory, no broad delete, restore target parsing, refusal for production host/database unless `RESTORE_CONFIRM=RESTORE_<exact-db>`, and drill always creates a new disposable database name.

- [ ] **Step 2: Confirm failure**

Run: `.venv/bin/pytest -q tests/test_backup_scripts.py`
Expected: FAIL.

- [ ] **Step 3: Implement backup/restore scripts and runbook**

Backups use external secret-injected encryption, record schema revision/time/checksum, and prune only validated files older than retention. Restore verifies checksum/decryption, restores to an empty explicitly named database, runs migrations/readiness, measures seconds, and never drops a database.

- [ ] **Step 4: Execute an isolated local restore drill**

Run: `BACKUP_ENV=staging ./scripts/backup-postgres.sh`
Run: `RESTORE_ENV=drill ./scripts/restore-drill.sh <encrypted-backup>`
Expected: restored disposable database passes `/ready` and smoke checks; report contains measured recovery time. Do not target production and do not delete volumes.

- [ ] **Step 5: Commit**

```bash
git add scripts/backup-postgres.sh scripts/restore-postgres.sh scripts/restore-drill.sh 'docs/07 Техническая документация/Backup and Recovery Runbook.md' tests/test_backup_scripts.py
git commit -m "Add guarded backup and restore drill"
```

## Task 7: Clean Developer Scripts

**Files:**
- Modify: `scripts/dogfood/*.sh`
- Modify: `scripts/dogfood/README.md`
- Modify: `tests/test_dogfood_scripts.py`

**Interfaces:**
- Preserves exact supervisor ownership and project-root collision protection while standardizing output.

- [ ] **Step 1: Add failing output/help tests**

Require English `[backend] starting`, `[backend] ready`, `[mobile] starting`, concise `--help`, `error: port 8000 is already in use`, predictable exit codes, no conversational tutorial in runtime output, no broad `pkill`, no secret output, and unchanged exact PID/start/command/root ownership checks.

- [ ] **Step 2: Confirm failure**

Run: `.venv/bin/pytest -q tests/test_dogfood_scripts.py`
Expected: existing mixed-language strings fail new assertions.

- [ ] **Step 3: Refine scripts without weakening safety**

Move troubleshooting to README, retain safe cleanup traps and runtime namespaces, and keep token-in-curl-config behavior.

- [ ] **Step 4: Run script checks**

Run: `.venv/bin/pytest -q tests/test_dogfood_scripts.py`
Run: `bash -n scripts/*.sh scripts/dogfood/*.sh`
Run: `shellcheck scripts/*.sh scripts/dogfood/*.sh`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/dogfood tests/test_dogfood_scripts.py
git commit -m "Standardize safe developer scripts"
```

## Task 8: Mobile Release Configuration and Versioning

**Files:**
- Modify: `mobile/app.json`
- Create: `mobile/app.config.ts`
- Create: `mobile/eas.json`
- Create: `mobile/src/config/release.ts`
- Create: `scripts/check-mobile-version.py`
- Create: `docs/07 Техническая документация/iOS Build and Release Runbook.md`
- Test: `tests/test_mobile_release_config.py`

**Interfaces:**
- Produces development/preview/production profiles, semantic app version, monotonically increasing iOS build number, bundle IDs, Apple/IAP capabilities, permission copy, deep link, URLs, production API, source-map policy, and dev-route exclusion.
- Consumes owner-supplied Apple/EAS credentials only during manual external build.

- [ ] **Step 1: Write failing release config tests**

Assert distinct bundle IDs/API URLs/environments, production no localhost/tunnel/dev routes, Sign in with Apple and IAP capability, calendar/microphone/notification copy, scheme, privacy/terms/support URLs, semantic version, numeric build, and build number greater than recorded previous release.

- [ ] **Step 2: Confirm failure**

Run: `.venv/bin/pytest -q tests/test_mobile_release_config.py`
Expected: FAIL.

- [ ] **Step 3: Implement deterministic config profiles**

Production identifiers use owner-configurable environment values with safe example defaults that cannot accidentally ship. EAS profiles define local development client, internal preview/TestFlight candidate, and production submission; no cloud build is invoked.

- [ ] **Step 4: Run config/export checks**

Run: `cd mobile && npm test && npm run typecheck && npm run lint && npx expo-doctor && npx expo export --platform web`
Run: `cd .. && .venv/bin/pytest -q tests/test_mobile_release_config.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add mobile/app.json mobile/app.config.ts mobile/eas.json mobile/src/config/release.ts scripts/check-mobile-version.py 'docs/07 Техническая документация/iOS Build and Release Runbook.md' tests/test_mobile_release_config.py
git commit -m "Configure iOS release profiles"
```

## Task 9: CI and Supply-Chain Checks

**Files:**
- Create: `.github/workflows/ci.yml`
- Create: `pyproject.toml`
- Create: `scripts/scan-secrets.sh`
- Test: `tests/test_ci_contract.py`

**Interfaces:**
- Produces backend/mobile/infrastructure CI jobs with no real secrets.

- [ ] **Step 1: Write failing workflow contract tests**

Require pinned action major revisions, least permissions, Python/Node setup, backend import/lint/format/migration/pytest/production-config/Docker build, mobile `npm ci`/test/typecheck/lint/expo-doctor/export, ShellCheck, compose config, secret scan, generated-artifact check, and no Apple/RevenueCat/OpenAI production values.

- [ ] **Step 2: Confirm failure**

Run: `.venv/bin/pytest -q tests/test_ci_contract.py`
Expected: FAIL.

- [ ] **Step 3: Implement workflow and local equivalents**

Use fake Apple JWKS, RevenueCat Test Store fixtures, fake transcription and mock LLM. Configure Ruff for current code without a repository-wide rewrite; apply only agreed checks.

- [ ] **Step 4: Run every local CI command**

Run backend/mobile/infrastructure/script commands exactly as declared in workflow and fix discrepancies before commit.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/ci.yml pyproject.toml scripts/scan-secrets.sh tests/test_ci_contract.py
git commit -m "Add production candidate CI"
```

## Task 10: Privacy, Legal, App Store, Release, and Beta Gates

**Files:**
- Create: `docs/08 Release/Privacy Policy Template.md`
- Create: `docs/08 Release/Terms Template.md`
- Create: `docs/08 Release/Data Inventory and Retention.md`
- Create: `docs/08 Release/App Store Metadata.md`
- Create: `docs/08 Release/App Privacy Questionnaire.md`
- Create: `docs/08 Release/App Review Notes.md`
- Create: `docs/08 Release/Beta Acceptance Gate.md`
- Create: `docs/08 Release/Release and Rollback Runbook.md`
- Create: `docs/08 Release/Launch Status.md`
- Create: `CHANGELOG.md`
- Create: `mobile/assets/icon.png`
- Create: `mobile/assets/adaptive-icon.png`
- Create: `mobile/assets/splash-icon.png`
- Create: `mobile/assets/app-store/README.md`
- Modify: `README.md`
- Modify: `docs/00 Главная.md`
- Modify: `docs/02 Дорожная карта/Сейчас — далее — позже.md`
- Modify: `docs/02 Дорожная карта/Этапы проекта.md`
- Modify: `docs/03 Решения/Журнал решений.md`

**Interfaces:**
- Produces owner-ready external checklist and status taxonomy `locally implemented / staging verified / TestFlight verified / App Store configured / publicly released`.

- [ ] **Step 1: Write legal/privacy templates and data inventory**

List purpose, fields, processor, retention, deletion/export, LLM training prohibition without consent, sensitive routine/goal/nutrition/fitness handling, and owner/lawyer review disclaimer. Include published URL gates. Generate a restrained original app icon and launch asset in the locked paper/burgundy visual language, verify required pixel dimensions and contrast, and document the exact iPhone screenshot scenes/sizes; do not fabricate App Store upload/configuration status.

- [ ] **Step 2: Prepare App Store metadata and assets checklist**

Include icon, launch screen, iPhone screenshots, subtitle, description, keywords, support/marketing/privacy URLs, age rating, privacy questionnaire, review notes, Sign in with Apple steps, subscription screenshots, restore/manage terms, and account deletion instructions. Do not mark an item configured without external evidence.

- [ ] **Step 3: Define release/rollback and beta stage gates**

Record semantic version/build strategy, changelog, migration compatibility, retained previous image, staged rollout, production smoke/monitoring, rollback command, and stages owner dogfood → internal TestFlight → 5–10 invited → 20–50 external → submission → staged public. Require no P0/P1 data loss/cross-user exposure, Apple release sign-in, monthly/annual/restore/lifecycle, logout/delete, backup restore, crash-free metric, AI limits, and support channel.

- [ ] **Step 4: Run final local production-candidate verification**

Run all commands from master prompt: Alembic, smoke, full pytest, mobile npm ci/test/typecheck/lint/expo-doctor/export, Docker build/compose/up/health/ready/down, ShellCheck, dependency audit, secret scan, disposable migration/restore drill, and production-config startup. Record exact outputs only for commands actually executed.

- [ ] **Step 5: Final review and scoped commit**

Run requesting-code-review against the complete branch, fix every Critical/Important finding, rerun affected and full checks, inspect `git diff -- . ':(exclude).gitignore'`, then commit only owned release documents:

```bash
git add 'docs/08 Release' CHANGELOG.md mobile/assets/icon.png mobile/assets/adaptive-icon.png mobile/assets/splash-icon.png mobile/assets/app-store/README.md README.md 'docs/00 Главная.md' 'docs/02 Дорожная карта/Сейчас — далее — позже.md' 'docs/02 Дорожная карта/Этапы проекта.md' 'docs/03 Решения/Журнал решений.md'
git commit -m "Document production candidate release gates"
```

The final report must not claim staging, TestFlight, App Store, backup drill, or public release verification unless that exact external/local drill was completed and evidenced.
