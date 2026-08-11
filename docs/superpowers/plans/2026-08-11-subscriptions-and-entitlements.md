# Subscriptions and Entitlements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use test-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a transparent monthly/annual RevenueCat subscription flow and server-authoritative `pro` entitlement with lifecycle reconciliation, usage limits, restore, and Test Store/sandbox verification hooks.

**Architecture:** RevenueCat/StoreKit owns localized products and transactions; mobile contains a purchases adapter and custom restrained paywall. PostgreSQL stores customer mapping, normalized subscription state, entitlement, billing events, and usage counters. Signed webhook ingestion is fast and idempotent; reconciliation is repeatable. Every expensive server feature asks a central entitlement/feature policy, never trusts a client boolean.

**Tech Stack:** RevenueCat `react-native-purchases`, StoreKit, FastAPI, SQLAlchemy/PostgreSQL/Alembic, HMAC-SHA256 raw-body verification, pytest, Vitest.

## Global Constraints

- iOS digital Pro access uses Apple IAP through RevenueCat, never Stripe or a universal external checkout.
- RevenueCat Customer ID is the internal stable `User.public_id`, never email or Apple subject.
- Product identifiers, offering ID, entitlement ID, public app key, and environment are configuration; prices/trials/discounts come only from StoreKit/RevenueCat.
- Webhook secret and RevenueCat secret API key remain backend-only.
- Free users keep logout, delete account, privacy, terms, restore purchases, and export.
- Machine reason `usage_limit_reached` includes period, remaining, reset_at, and entitlement.
- Sandbox and production billing data never mix.
- No real purchase occurs in automated CI; fakes or RevenueCat Test Store contracts are used.
- The user-owned `.gitignore` change remains untouched.

---

## Task 1: Subscription, Billing, and Usage Schema

**Files:**
- Create: `app/models/subscription.py`
- Modify: `app/models/__init__.py`
- Create: `migrations/versions/e5d4a3c6b755_subscriptions_entitlements.py`
- Test: `tests/test_subscription_migration.py`

**Interfaces:**
- Produces `Subscription`, `BillingEvent`, `UsageCounter` and normalized lifecycle states.
- Consumes `User.public_id` from foundations.

- [ ] **Step 1: Write failing schema tests**

Assert one customer mapping per `(environment, app_user_id)`, unique billing event ID per environment, raw payload digest without raw secret/body persistence, subscription product/period/expiration/grace/revocation fields, indexed active entitlement, and unique usage period counters.

- [ ] **Step 2: Confirm failure**

Run: `.venv/bin/pytest -q tests/test_subscription_migration.py`
Expected: FAIL.

- [ ] **Step 3: Implement schema and migration**

Migration `e5d4a3c6b755` follows device revision `d8c7b6a5f433`. States are `unknown/free/trial/active/grace_period/billing_issue/expired/revoked`; source environment is `test/sandbox/production`. Billing events keep normalized technical metadata and payload digest only. Subscription history required for support is retained according to documented policy without personal plan data.

- [ ] **Step 4: Verify migration**

Run: `.venv/bin/pytest -q tests/test_subscription_migration.py && .venv/bin/alembic upgrade head`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/models/subscription.py app/models/__init__.py migrations/versions/e5d4a3c6b755_subscriptions_entitlements.py tests/test_subscription_migration.py
git commit -m "Add subscription and usage schema"
```

## Task 2: Central Entitlement and Usage Policy

**Files:**
- Create: `app/services/entitlement_service.py`
- Create: `app/schemas/entitlements.py`
- Test: `tests/test_entitlement_service.py`

**Interfaces:**
- Produces `EntitlementSnapshot`, `require_capability(user, capability)`, `consume_usage(user, capability, request_id)`, and server-configured free/pro policy.
- Consumes Subscription and UsageCounter.

- [ ] **Step 1: Write failing policy tests**

Cover free one active goal/basic Today/completion/basic progress/7-day history/AI quota; Pro three goals/programs/replanning/Week/Month/Path/history/workout/nutrition/learning/calendar/review/voice/higher AI quota; unknown/failure fail-closed only for expensive features; grace remains entitled; expired/revoked denied; idempotent usage consumption and reset.

- [ ] **Step 2: Confirm failure**

Run: `.venv/bin/pytest -q tests/test_entitlement_service.py`
Expected: FAIL.

- [ ] **Step 3: Implement centralized policy**

Keep limits in typed settings/config and return `CapabilityDecision(allowed, reason, entitlement, remaining, reset_at)`. Do not scatter product checks through routers or presentation copy.

- [ ] **Step 4: Run service tests**

Run: `.venv/bin/pytest -q tests/test_entitlement_service.py tests/test_goal_api.py tests/test_activity_api.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/entitlement_service.py app/schemas/entitlements.py tests/test_entitlement_service.py
git commit -m "Enforce centralized free and Pro policy"
```

## Task 3: Signed RevenueCat Webhook Lifecycle

**Files:**
- Create: `app/services/revenuecat_service.py`
- Create: `app/api/v2/billing.py`
- Modify: `app/core/config.py`
- Test: `tests/test_revenuecat_webhook.py`

**Interfaces:**
- Produces `verify_webhook(raw_body, timestamp, signature)`, `normalize_billing_event`, `apply_billing_event`, and `POST /api/v2/billing/revenuecat/webhook`.
- Consumes raw ASGI request bytes, environment-specific secret, BillingEvent, Subscription.

- [ ] **Step 1: Write failing signature/replay tests**

Cover correct HMAC over `timestamp + "." + raw_body`, malformed/invalid signature, old/future timestamp tolerance, duplicate event, event ID collision across environments, unknown customer, out-of-order expiration/renewal, trial, purchase, renewal, grace, billing issue, expiration, refund, revocation, and constant-time signature comparison.

- [ ] **Step 2: Confirm failure**

Run: `.venv/bin/pytest -q tests/test_revenuecat_webhook.py`
Expected: FAIL.

- [ ] **Step 3: Implement fast idempotent ingestion**

Verify before JSON parsing, persist a unique normalized event, update subscription in one transaction, return 2xx only for accepted/duplicate valid events, and enqueue reconciliation intent through an in-process durable status field rather than adding Redis prematurely.

- [ ] **Step 4: Run webhook tests**

Run: `.venv/bin/pytest -q tests/test_revenuecat_webhook.py tests/test_entitlement_service.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/revenuecat_service.py app/api/v2/billing.py app/core/config.py tests/test_revenuecat_webhook.py
git commit -m "Process signed RevenueCat lifecycle events"
```

## Task 4: Reconciliation and Subscription API

**Files:**
- Create: `app/integrations/revenuecat.py`
- Create: `app/services/subscription_service.py`
- Create: `app/api/v2/subscriptions.py`
- Create: `scripts/reconcile_subscriptions.py`
- Test: `tests/test_subscription_reconciliation.py`
- Test: `tests/test_subscription_api.py`

**Interfaces:**
- Produces RevenueCat adapter, repeatable reconciliation, `GET /api/v2/subscription`, `POST /api/v2/subscription/sync`, and support-triggerable single-user sync.
- Consumes secret backend API key and stable public app user ID.

- [ ] **Step 1: Write failing reconciliation tests**

Cover API timeout, malformed response, sandbox/production mismatch, active/grace/expired/refunded state, repeated sync, webhook/sync race, unknown customer, no secret, and safe logs without headers/body.

- [ ] **Step 2: Confirm failure**

Run: `.venv/bin/pytest -q tests/test_subscription_reconciliation.py tests/test_subscription_api.py`
Expected: FAIL.

- [ ] **Step 3: Implement injectable provider and atomic apply**

Use bounded timeout and no unsafe retry for mutation endpoints. Manual sync is rate-limited/idempotent; the CLI can reconcile all due rows in pages without printing personal data.

- [ ] **Step 4: Run service/API tests**

Run: `.venv/bin/pytest -q tests/test_subscription_reconciliation.py tests/test_subscription_api.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/integrations/revenuecat.py app/services/subscription_service.py app/api/v2/subscriptions.py scripts/reconcile_subscriptions.py tests/test_subscription_reconciliation.py tests/test_subscription_api.py
git commit -m "Reconcile authoritative subscriptions"
```

## Task 5: Mobile Purchases Adapter and State Machine

**Files:**
- Create: `mobile/src/integrations/purchases/purchasesAdapter.ts`
- Create: `mobile/src/integrations/purchases/revenueCatAdapter.ts`
- Create: `mobile/src/features/subscription/subscriptionReducer.ts`
- Create: `mobile/src/features/subscription/SubscriptionProvider.tsx`
- Modify: `mobile/package.json`
- Test: `mobile/src/features/subscription/__tests__/subscriptionReducer.test.ts`
- Test: `mobile/src/integrations/purchases/__tests__/purchasesAdapter.test.ts`

**Interfaces:**
- Produces `loading_offerings/ready/purchasing/purchased/cancelled/pending/failed/restoring/restored/unavailable` purchase state and normalized StoreKit offering models.
- Consumes RevenueCat public key, `User.public_id`, backend entitlement snapshot.

- [ ] **Step 1: Write failing state/adapter tests**

Cover missing native module, Test Store offerings, localized monthly/annual prices, actual eligibility/trial, purchase success/cancel/pending/failure, restore, user login/logout mapping, and backend entitlement overriding stale client customer info.

- [ ] **Step 2: Confirm failure**

Run: `cd mobile && npm test -- subscriptionReducer purchasesAdapter`
Expected: FAIL.

- [ ] **Step 3: Install RevenueCat SDK and implement adapter**

Run: `cd mobile && npm install react-native-purchases`
Configure once per authenticated user, call `logIn(publicUserId)`, never use email/Apple subject, and avoid static native imports in web/text-only test paths through an adapter boundary.

- [ ] **Step 4: Run mobile checks**

Run: `cd mobile && npm test && npm run typecheck && npm run lint && npx expo-doctor`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add mobile/src/integrations/purchases mobile/src/features/subscription mobile/package.json mobile/package-lock.json
git commit -m "Add RevenueCat purchase state"
```

## Task 6: Transparent Custom Paywall

**Files:**
- Create: `mobile/app/paywall.tsx`
- Create: `mobile/src/features/subscription/PaywallScreen.tsx`
- Create: `mobile/src/features/subscription/paywallModel.ts`
- Modify: `mobile/src/features/profile/ProfileScreen.tsx`
- Test: `mobile/src/features/subscription/__tests__/paywallModel.test.ts`

**Interfaces:**
- Produces custom paywall based entirely on actual offering/eligibility and backend entitlement.
- Consumes SubscriptionProvider and privacy/terms/manage URLs.

- [ ] **Step 1: Write failing paywall model tests**

Cover loading/unavailable, monthly/annual labels, localized price/period, eligible/noneligible trial, renewal date text, no fake discount, no default deceptive selection, restore/manage/privacy/terms/close, purchase states, Dynamic Type and long Russian strings.

- [ ] **Step 2: Confirm failure**

Run: `cd mobile && npm test -- paywallModel`
Expected: FAIL.

- [ ] **Step 3: Implement restrained paywall**

Use required copy «Каждый день ведёт к цели», real benefits, a clear purchase action naming period/price, visible auto-renewal and next charge, Restore, Manage, Privacy, Terms, and close when free tier is enabled. No countdown, gradients, hidden renewal, or hardcoded price.

- [ ] **Step 4: Run mobile checks**

Run: `cd mobile && npm test && npm run typecheck && npm run lint`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add mobile/app/paywall.tsx mobile/src/features/subscription/PaywallScreen.tsx mobile/src/features/subscription/paywallModel.ts mobile/src/features/profile/ProfileScreen.tsx
git commit -m "Add transparent subscription paywall"
```

## Task 7: Billing Verification and Documentation

**Files:**
- Create: `docs/07 Техническая документация/Subscriptions and RevenueCat v1.md`
- Create: `docs/05 Тестирование продукта/Subscription Sandbox Checklist.md`
- Modify: `docs/03 Решения/Журнал решений.md`
- Modify: `README.md`
- Modify: `mobile/README.md`

- [ ] **Step 1: Document IDs, states, environment separation, and manual tests**

Document monthly/annual/`pro` configuration, webhook signature, reconciliation, Test Store, Apple sandbox monthly/annual, Restore, expiration/grace/billing issue/refund/revocation, manage subscription, and owner credential fields without real values.

- [ ] **Step 2: Run backend phase verification**

Run: `.venv/bin/alembic upgrade head && .venv/bin/pytest`
Expected: all pass.

- [ ] **Step 3: Run mobile phase verification**

Run: `cd mobile && npm test && npm run typecheck && npm run lint && npx expo-doctor`
Expected: all pass without real billing credentials.

- [ ] **Step 4: Self-review billing boundaries**

Confirm prices/trials are provider values, client booleans cannot unlock server features, Test Store cannot update production rows, and privacy/delete/restore remain reachable for free/expired users.

- [ ] **Step 5: Commit docs**

```bash
git add 'docs/07 Техническая документация/Subscriptions and RevenueCat v1.md' 'docs/05 Тестирование продукта/Subscription Sandbox Checklist.md' 'docs/03 Решения/Журнал решений.md' README.md mobile/README.md
git commit -m "Document subscription release checks"
```
