# Production Foundations and Auth Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use test-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the local-only mobile identity boundary with production-safe Apple identity verification, rotating device sessions, account lifecycle, and a short narrative onboarding contract while preserving local dogfood mode outside production.

**Architecture:** FastAPI resolves every `/api/v2` request to an internal `User` through an opaque, hashed server session. Apple verification is isolated behind an adapter; onboarding and resource budgets live in PostgreSQL and services, while mobile stores only session credentials in SecureStore and user-scoped caches in AsyncStorage. Existing `/api/v1` and frozen compatibility routes remain unchanged during migration.

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy 2, PostgreSQL, Alembic, PyJWT cryptographic verification, Expo Router, Expo Apple Authentication, Expo SecureStore, Vitest, pytest.

## Global Constraints

- Preserve `GET /api/v1/today` read safety, atomic `DaySnapshot`, factual `PlanDiff`, idempotent mutations, user ownership, timezone-aware scheduling, and deterministic slot selection.
- `MOBILE_DOGFOOD_TOKEN` is permitted only for local/test and must be rejected by production configuration validation.
- Apple identity tokens must be checked for issuer, audience, expiration, signature, subject, nonce, and state; raw tokens must never be logged or persisted.
- Access and refresh credentials stay only in SecureStore on native mobile; all refresh tokens are hashed at rest and rotate on every use with reuse detection.
- Logout, revoke-all, and account deletion clear every user-scoped mobile cache and draft.
- Onboarding uses one narrative, at most one necessary clarification at a time, at most three active goals, and keeps at least 20% unallocated capacity unless the user explicitly selects another policy.
- The user-owned `.gitignore` change must not be modified, staged, or committed.

---

## Current-State Audit

| Capability | Evidence | Coverage | Required action |
|---|---|---:|---|
| Internal user | `app/models/user.py` | Partial | Add stable public UUID and lifecycle fields without changing integer foreign keys. |
| Mobile auth | `app/api/mobile.py:get_mobile_user` | Local only | Add `/api/v2/auth/*` session boundary; keep `/api/v1` dogfood only. |
| Apple verification | Missing | Missing | Add injectable JWKS verifier with issuer/audience/nonce checks. |
| Sessions | Missing | Missing | Store access/refresh hashes, rotation family, device metadata, expiry, revocation. |
| Onboarding | Parser can update profile/goals, no contract | Partial | Add narrative preview/apply workflow and resource budget persistence. |
| Account deletion | Missing | Missing | Add authenticated destructive service with explicit confirmation and cascade tests. |
| Mobile secrets | Dogfood token in SecureStore | Partial | Replace with access/refresh session vault for production. |
| Cache isolation | `mobile/src/storage/cache.ts` uses global keys | Missing | Namespace snapshot, drafts, goals, and calendar caches by public user ID. |

## Task 1: Production Configuration Boundary

**Files:**
- Modify: `app/core/config.py`
- Modify: `.env.example`
- Create: `app/core/runtime.py`
- Test: `tests/test_production_config.py`

**Interfaces:**
- Produces: `validate_runtime_config(settings: Settings) -> None` and `RuntimeMode = Literal["local", "test", "staging", "production"]`.
- Consumes: current `Settings` and application factories.

- [ ] **Step 1: Write failing configuration tests**

```python
def test_production_rejects_debug_and_dogfood_auth():
    settings = Settings(APP_ENV="production", APP_DEBUG=True, MOBILE_DOGFOOD_TOKEN="secret")
    with pytest.raises(RuntimeConfigError) as error:
        validate_runtime_config(settings)
    assert error.value.reasons == ("app_debug_must_be_false", "dogfood_auth_must_be_disabled")

def test_staging_requires_distinct_database_and_apple_audience():
    settings = Settings(APP_ENV="staging", DATABASE_URL="postgresql+psycopg://stage/db", APPLE_CLIENT_ID="dev.ai-life-planner.staging")
    validate_runtime_config(settings)
```

- [ ] **Step 2: Run tests and confirm failure**

Run: `.venv/bin/pytest -q tests/test_production_config.py`
Expected: FAIL because `RuntimeConfigError` and the new settings do not exist.

- [ ] **Step 3: Implement typed production settings and validation**

Add `apple_client_id`, `apple_team_id`, `apple_jwks_url`, access/refresh TTLs, `public_api_url`, `privacy_policy_url`, `terms_url`, `support_url`, and `allow_dogfood_auth`. Validation must aggregate stable machine reasons and must not print secret values.

- [ ] **Step 4: Run focused and import tests**

Run: `.venv/bin/pytest -q tests/test_production_config.py tests/test_mobile_dogfood_app.py`
Expected: PASS with local defaults preserving current dogfood behavior.

- [ ] **Step 5: Commit**

```bash
git add app/core/config.py app/core/runtime.py .env.example tests/test_production_config.py
git commit -m "Add production runtime configuration boundary"
```

## Task 2: Identity and Session Schema

**Files:**
- Create: `app/models/auth.py`
- Modify: `app/models/user.py`
- Modify: `app/models/__init__.py`
- Create: `migrations/versions/a1f0c9e2d311_production_auth.py`
- Test: `tests/test_auth_migration.py`

**Interfaces:**
- Produces: `AuthIdentity`, `AppSession`, `User.public_id`, and unique `(provider, subject)` identity mapping.
- Consumes: current `users.id` as the internal ownership key.

- [ ] **Step 1: Add a failing migration metadata test**

```python
def test_auth_schema_has_user_owned_unique_and_hashed_credentials():
    assert set(AuthIdentity.__table__.c) >= {"user_id", "provider", "subject", "created_at"}
    assert set(AppSession.__table__.c) >= {"user_id", "access_token_hash", "refresh_token_hash", "family_id", "expires_at", "revoked_at"}
    assert "refresh_token" not in AppSession.__table__.c
```

- [ ] **Step 2: Confirm the schema test fails**

Run: `.venv/bin/pytest -q tests/test_auth_migration.py`
Expected: FAIL on missing models.

- [ ] **Step 3: Add non-destructive models and migration**

The migration adds `users.public_id UUID`, backfills every existing user using PostgreSQL `gen_random_uuid()` or application-safe UUID values in the disposable migration test, marks it unique/non-null, and creates `auth_identities` and `app_sessions` with cascade deletes and indexes on user, expiry, family, and hashes. Store optional Apple email/name only on `User`; repeated null Apple claims never overwrite them.

- [ ] **Step 4: Verify upgrade from current head**

Run: `.venv/bin/pytest -q tests/test_auth_migration.py && .venv/bin/alembic upgrade head`
Expected: PASS and Alembic at `a1f0c9e2d311`.

- [ ] **Step 5: Commit**

```bash
git add app/models/auth.py app/models/user.py app/models/__init__.py migrations/versions/a1f0c9e2d311_production_auth.py tests/test_auth_migration.py
git commit -m "Add production identities and sessions"
```

## Task 3: Apple Verification and Rotating Sessions

**Files:**
- Create: `app/auth/apple.py`
- Create: `app/auth/tokens.py`
- Create: `app/services/auth_service.py`
- Create: `app/schemas/auth.py`
- Test: `tests/test_auth_service.py`
- Modify: `requirements.txt`

**Interfaces:**
- Produces: `AppleIdentity(subject, email, name)`, `AppleTokenVerifier.verify(identity_token, raw_nonce)`, `SessionPair(access_token, refresh_token, access_expires_at, refresh_expires_at)`, `sign_in_with_apple()`, `rotate_session()`, `revoke_session()`, and `revoke_all_sessions()`.
- Consumes: `AuthIdentity`, `AppSession`, and runtime Apple configuration.

- [ ] **Step 1: Write failing auth service tests**

Cover valid Apple claims, wrong issuer/audience, expired token, nonce mismatch, name/email preservation, refresh rotation, previous refresh reuse revoking the whole family, current-device logout, and multiple independent devices. Tests use a generated test RSA key and an injected JWKS response; no Apple network call occurs.

- [ ] **Step 2: Confirm tests fail**

Run: `.venv/bin/pytest -q tests/test_auth_service.py`
Expected: FAIL on missing verifier and session service.

- [ ] **Step 3: Implement minimal cryptographic and opaque-token services**

Use `PyJWT[crypto]==2.10.1` for RS256 verification. Generate 32-byte URL-safe opaque tokens, persist only `sha256(token)` digests, compare digests through indexed lookup, rotate refresh tokens transactionally, and mark `reuse_detected_at` plus revoke the family when an already-rotated token is presented.

- [ ] **Step 4: Run auth and isolation tests**

Run: `.venv/bin/pytest -q tests/test_auth_service.py tests/test_mobile_api.py`
Expected: PASS; legacy v1 dogfood tests remain green.

- [ ] **Step 5: Commit**

```bash
git add app/auth app/services/auth_service.py app/schemas/auth.py requirements.txt tests/test_auth_service.py
git commit -m "Implement Apple identity and rotating sessions"
```

## Task 4: Authenticated API v2 and Account Lifecycle

**Files:**
- Create: `app/api/v2/__init__.py`
- Create: `app/api/v2/auth.py`
- Create: `app/api/v2/account.py`
- Create: `app/api/v2/dependencies.py`
- Modify: `app/main.py`
- Test: `tests/test_api_v2_auth.py`
- Test: `tests/test_account_deletion.py`

**Interfaces:**
- Produces endpoints `POST /api/v2/auth/apple`, `POST /api/v2/auth/refresh`, `POST /api/v2/auth/logout`, `POST /api/v2/auth/revoke-all`, `GET /api/v2/me`, `GET /api/v2/account/export`, `DELETE /api/v2/account`.
- Consumes `sign_in_with_apple`, `rotate_session`, opaque access authentication, and current integer `user_id` ownership.

- [ ] **Step 1: Write failing endpoint and data-map tests**

Tests must prove no client-provided user ID is accepted, missing/expired/revoked tokens return the same safe 401 contract, export returns only the authenticated user's portable data without secrets or internal hashes, deletion requires body `{"confirmation":"DELETE"}`, deletion removes all current user-owned rows, and a second user remains intact.

- [ ] **Step 2: Confirm endpoint tests fail**

Run: `.venv/bin/pytest -q tests/test_api_v2_auth.py tests/test_account_deletion.py`
Expected: FAIL with missing routes.

- [ ] **Step 3: Implement thin routes and service-owned deletion**

Return `request_id` in all errors, never echo bearer credentials, make logout idempotent, and perform account deletion in one transaction after revoking sessions. Apple credential revocation is an injectable best-effort adapter whose failure is recorded as a safe technical event and does not resurrect local data.

- [ ] **Step 4: Run API, ownership, and compatibility tests**

Run: `.venv/bin/pytest -q tests/test_api_v2_auth.py tests/test_account_deletion.py tests/test_mobile_api.py tests/test_web_api.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/api/v2 app/main.py tests/test_api_v2_auth.py tests/test_account_deletion.py
git commit -m "Expose authenticated account lifecycle API"
```

## Task 5: Narrative Onboarding and Resource Budget

**Files:**
- Create: `app/models/onboarding.py`
- Modify: `app/models/__init__.py`
- Create: `migrations/versions/a8e7f6d5c4b3_resource_budget_and_onboarding.py`
- Create: `app/schemas/onboarding.py`
- Create: `app/services/onboarding_service.py`
- Create: `app/api/v2/onboarding.py`
- Test: `tests/test_onboarding_service.py`
- Test: `tests/test_onboarding_api.py`

**Interfaces:**
- Produces `ResourceBudget`, `OnboardingPreview`, `OnboardingStatus`, `preview_onboarding(user, narrative, request_id)`, and `apply_onboarding_preview(user, preview_id, expected_version)`.
- Consumes existing parser, profile/goal services, and later program-generation interface `create_program_candidates()`.

- [ ] **Step 1: Write failing onboarding tests**

Cover one narrative extracting routine and up to three active goal candidates, correction before apply, a single clarification, weekly hours/day windows/minimum-comfortable-maximum minutes, 20% reserve, idempotent preview/apply, stale version conflict, and no mutations from `GET /api/v2/onboarding`.

- [ ] **Step 2: Confirm tests fail**

Run: `.venv/bin/pytest -q tests/test_onboarding_service.py tests/test_onboarding_api.py`
Expected: FAIL on missing resource budget and preview service.

- [ ] **Step 3: Implement preview-first onboarding**

Persist structured summary and budget, not raw narration beyond the explicitly documented short-lived preview retention. Migration `a8e7f6d5c4b3` follows `a1f0c9e2d311`. `POST /preview` returns routine/goal/allocation candidates; `POST /apply` creates profile updates and goals atomically. Allocation minutes must sum to at most configured allocatable capacity.

- [ ] **Step 4: Run onboarding and planner regression tests**

Run: `.venv/bin/pytest -q tests/test_onboarding_service.py tests/test_onboarding_api.py tests/test_planning_engine.py`
Expected: PASS with no change to existing Today semantics.

- [ ] **Step 5: Commit**

```bash
git add app/models/onboarding.py app/models/__init__.py migrations/versions/a8e7f6d5c4b3_resource_budget_and_onboarding.py app/schemas/onboarding.py app/services/onboarding_service.py app/api/v2/onboarding.py tests/test_onboarding_service.py tests/test_onboarding_api.py
git commit -m "Add narrative onboarding and resource budgets"
```

## Task 6: Mobile Auth State and User-Scoped Storage

**Files:**
- Create: `mobile/src/features/auth/authReducer.ts`
- Create: `mobile/src/features/auth/AuthProvider.tsx`
- Create: `mobile/src/api/authApi.ts`
- Create: `mobile/src/storage/sessionStorage.ts`
- Modify: `mobile/src/storage/cache.ts`
- Modify: `mobile/src/storage/mobileStorage.ts`
- Modify: `mobile/app/_layout.tsx`
- Test: `mobile/src/features/auth/__tests__/authReducer.test.ts`
- Test: `mobile/src/storage/__tests__/userScopedStorage.test.ts`

**Interfaces:**
- Produces `AuthState`, `SessionCredentials`, single-flight refresh, `clearUserData(publicUserId)`, and user-scoped cache keys.
- Consumes `/api/v2/auth/*`; later Sign in with Apple screen supplies the native Apple credential.

- [ ] **Step 1: Write failing mobile state/storage tests**

Tests cover cold launch, authenticated, refreshing, expired, revoked, logout, deletion, two simultaneous 401 responses sharing one refresh request, two users never reading each other's Today/draft cache, and complete cache clearing on logout/delete.

- [ ] **Step 2: Confirm tests fail**

Run: `cd mobile && npm test -- authReducer userScopedStorage`
Expected: FAIL because the auth state and scoped cache do not exist.

- [ ] **Step 3: Implement auth reducer, vault, and scoped cache**

SecureStore keys contain access/refresh credentials only. AsyncStorage keys include `publicUserId`; legacy P0 cache is migrated only into the current dogfood namespace and never into a production session.

- [ ] **Step 4: Run mobile checks**

Run: `cd mobile && npm test && npm run typecheck && npm run lint`
Expected: all checks pass.

- [ ] **Step 5: Commit**

```bash
git add mobile/src/features/auth mobile/src/api/authApi.ts mobile/src/storage/sessionStorage.ts mobile/src/storage/cache.ts mobile/src/storage/mobileStorage.ts mobile/app/_layout.tsx
git commit -m "Add mobile session state and scoped storage"
```

## Task 7: Foundation Verification and Documentation

**Files:**
- Create: `docs/07 Техническая документация/Authentication and Account Lifecycle v1.md`
- Modify: `docs/03 Решения/Журнал решений.md`
- Modify: `docs/02 Дорожная карта/Сейчас — далее — позже.md`
- Modify: `README.md`
- Modify: `mobile/BACKEND_GAPS.md`

**Interfaces:**
- Documents the stable v2 auth contract consumed by every later phase.

- [ ] **Step 1: Document security and account data map**

Document Apple claims, session rotation/reuse, device logout, revoke-all, account deletion cascade, SecureStore/AsyncStorage boundaries, production dogfood rejection, and manual release-build verification.

- [ ] **Step 2: Run full phase verification**

Run: `.venv/bin/alembic upgrade head && .venv/bin/python scripts/check_mvp.py && .venv/bin/pytest`
Expected: every backend test passes.

- [ ] **Step 3: Verify mobile and repository state**

Run: `cd mobile && npm test && npm run typecheck && npm run lint`
Run: `cd .. && git diff --check && git status --short`
Expected: checks pass and `.gitignore` is the only unrelated change.

- [ ] **Step 4: Self-review against auth invariants**

Confirm no raw identity/access/refresh token is persisted in logs or database, every user-owned query includes `user_id`, dogfood auth is impossible under production validation, and cache clearing is complete.

- [ ] **Step 5: Commit documentation only**

```bash
git add 'docs/07 Техническая документация/Authentication and Account Lifecycle v1.md' 'docs/03 Решения/Журнал решений.md' 'docs/02 Дорожная карта/Сейчас — далее — позже.md' README.md mobile/BACKEND_GAPS.md
git commit -m "Document production authentication foundation"
```
