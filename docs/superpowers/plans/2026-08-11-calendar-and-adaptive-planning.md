# Calendar and Adaptive Planning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use test-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add authoritative Day/Week/Month calendar read models, privacy-preserving Apple busy-block synchronization, temporary life modes, and future-only adaptive replanning with factual versioned changes.

**Architecture:** EventKit remains on-device; the backend stores only user-approved busy intervals and optional external identifiers required for deduplication/write sync. The existing `DayPlan` and deterministic scheduler remain authoritative. Mutations create `PlanChange` audit records with base/result versions and typed reasons; Week/Month are read models over persisted plans, commitments, milestones, deadlines, and busy blocks.

**Tech Stack:** FastAPI, SQLAlchemy/PostgreSQL/Alembic, current planning engine, Expo Calendar native module, React Native, pytest, Vitest.

## Global Constraints

- Fixed events, completed actions, and past intervals are never moved automatically.
- Flexible actions move only within explicit windows, minimum blocks, recovery rules, deadlines, and resource capacity.
- Calendar permission denial does not break planning; read and write permissions are separate.
- Privacy mode sends busy intervals only; calendar titles and notes are excluded unless the user explicitly opts into the narrow required field.
- Sync is idempotent and external changes/deletions do not create duplicates.
- GET endpoints are read-safe and never materialize or replan.
- Every schedule mutation is idempotent, version-checked, transactional, and returns factual `PlanDiff` plus authoritative snapshots.
- The user-owned `.gitignore` change remains untouched.

---

## Current-State Audit

| Capability | Evidence | Coverage | Gap |
|---|---|---:|---|
| Day planning | `app/services/planning_service.py` | Strong P0 | Add reserve, commitment, recovery, temporary mode inputs and future-only change records. |
| Day version | `DayPlan.version` | Partial | No durable PlanChange/undo audit. |
| Week/Month | Missing | Missing | No read models or mobile screens. |
| Calendar busy blocks | Missing | Missing | No import/dedupe/deletion contract. |
| Temporary modes | `DayPlan.energy_level/work override` | Day only | Need dated mode that preserves permanent routine. |
| Apple integration | Missing | Missing | Native permission and privacy adapter required. |

## Task 1: Calendar, Temporary Mode, and PlanChange Schema

**Files:**
- Create: `app/models/calendar.py`
- Create: `app/models/plan_change.py`
- Modify: `app/models/__init__.py`
- Create: `migrations/versions/c3b2e1a4f533_calendar_and_plan_changes.py`
- Test: `tests/test_calendar_migration.py`

**Interfaces:**
- Produces `CalendarBusyBlock`, `TemporaryLifeMode`, `PlanChange`.
- Consumes `User`, `DayPlan`, and optional external calendar identity.

- [ ] **Step 1: Write failing schema tests**

Assert unique `(user_id, provider, external_id, occurrence_start)`, timezone-aware UTC start/end, soft deletion/source revision, indexed date ranges, typed life-mode interval, PlanChange base/result versions, idempotency key, affected dates, structured forward/inverse payloads, expiry, and one-user ownership.

- [ ] **Step 2: Confirm failure**

Run: `.venv/bin/pytest -q tests/test_calendar_migration.py`
Expected: FAIL on missing models.

- [ ] **Step 3: Add non-destructive schema and migration**

Migration `c3b2e1a4f533` follows program revision `b2a1d0f3e422`. Busy blocks store no title/notes in privacy mode. PlanChange payloads contain task/placement identifiers and previous factual values only; never raw capture text. Dangerous downgrade is documented as schema-only and never used against production data.

- [ ] **Step 4: Verify migration**

Run: `.venv/bin/pytest -q tests/test_calendar_migration.py && .venv/bin/alembic upgrade head`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/models/calendar.py app/models/plan_change.py app/models/__init__.py migrations/versions/c3b2e1a4f533_calendar_and_plan_changes.py tests/test_calendar_migration.py
git commit -m "Add calendar and plan change schema"
```

## Task 2: Idempotent Busy-Block Synchronization

**Files:**
- Create: `app/schemas/calendar.py`
- Create: `app/services/calendar_service.py`
- Create: `app/api/v2/calendar.py`
- Test: `tests/test_calendar_sync.py`

**Interfaces:**
- Produces `sync_busy_blocks(user, sync_batch, expected_version)`, `CalendarSyncResult`, `GET /api/v2/calendar/sync-state`, `PUT /api/v2/calendar/busy-blocks`.
- Consumes authenticated user and client-generated stable external occurrence IDs.

- [ ] **Step 1: Write failing sync tests**

Cover first import, exact retry, updated time, remote deletion, overlapping blocks, two calendars with same event ID, another user's same event ID, bounded date window, invalid timezone/order, and repeated sync without copies.

- [ ] **Step 2: Confirm failure**

Run: `.venv/bin/pytest -q tests/test_calendar_sync.py`
Expected: FAIL on missing service.

- [ ] **Step 3: Implement transactional upsert/tombstone sync**

Require batch idempotency key and monotonically increasing client sync revision. Normalize UTC only after validating the device timezone, restrict sync horizon, reject titles/notes in privacy payloads, and return changed affected dates for explicit replanning.

- [ ] **Step 4: Run isolation tests**

Run: `.venv/bin/pytest -q tests/test_calendar_sync.py tests/test_account_deletion.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/schemas/calendar.py app/services/calendar_service.py app/api/v2/calendar.py tests/test_calendar_sync.py
git commit -m "Synchronize privacy-safe calendar blocks"
```

## Task 3: Future-Only Adaptive Replanning and Undo

**Files:**
- Create: `app/services/plan_change_service.py`
- Modify: `app/services/planning_service.py`
- Modify: `app/services/message_service.py`
- Create: `app/api/v2/planning.py`
- Test: `tests/test_adaptive_replanning.py`
- Test: `tests/test_plan_change_undo.py`

**Interfaces:**
- Produces `apply_replan(user, request_id, base_versions, affected_dates, reason)`, `undo_plan_change(user, change_id, request_id, expected_version)`, and atomic multi-day result.
- Consumes current deterministic planner, calendar blocks, commitments, and temporary modes.

- [ ] **Step 1: Write failing replanning invariant tests**

Cover fixed/past/completed preservation, flexible future movement, preferred windows/deadlines/recovery, two affected days, stale base version, duplicate request, factual moved/unscheduled diffs, no partial commit on overlap, and temporary modes normal/workload/recovery/sick/travel/vacation/low_sleep/focus_sprint.

- [ ] **Step 2: Write failing undo tests**

Cover owned latest change, expired change, already-undone change, intervening version conflict, exact retry, and restoration of placements without rewriting completion/evidence.

- [ ] **Step 3: Confirm failures**

Run: `.venv/bin/pytest -q tests/test_adaptive_replanning.py tests/test_plan_change_undo.py`
Expected: FAIL on missing PlanChange service.

- [ ] **Step 4: Implement atomic explicit mutation boundary**

Snapshot only affected future placements, acquire user/date plan locks in deterministic order, calculate candidate plans, validate all no-overlap invariants, then persist every plan and one PlanChange in a single transaction. Undo applies stored inverse placement data only when current versions match.

- [ ] **Step 5: Run regression and commit**

Run: `.venv/bin/pytest -q tests/test_adaptive_replanning.py tests/test_plan_change_undo.py tests/test_planning_engine.py tests/test_mobile_api.py`
Expected: PASS.

```bash
git add app/services/plan_change_service.py app/services/planning_service.py app/services/message_service.py app/api/v2/planning.py tests/test_adaptive_replanning.py tests/test_plan_change_undo.py
git commit -m "Version adaptive planning changes"
```

## Task 4: Day, Week, and Month Read Models

**Files:**
- Create: `app/services/calendar_read_service.py`
- Modify: `app/api/v2/calendar.py`
- Test: `tests/test_calendar_read_api.py`

**Interfaces:**
- Produces `GET /api/v2/calendar/day`, `/week`, and `/month` with opaque ETag/version cursors.
- Consumes persisted `DayPlan`, busy blocks, commitments, milestones, deadlines, and temporary modes.

- [ ] **Step 1: Write failing read-safety tests**

Assert Day includes anchors/fixed/planner/free/recovery/sleep when persisted; Week contains seven summaries and commitment load; Month contains milestones/deadlines/trips/control measurements/tension summary but no tiny tasks; repeated reads do not create rows or increment versions; query count is bounded.

- [ ] **Step 2: Confirm failure**

Run: `.venv/bin/pytest -q tests/test_calendar_read_api.py`
Expected: FAIL on missing read endpoints.

- [ ] **Step 3: Implement eager-loaded read models**

Return explicit absence for unmaterialized days instead of mutating on GET. Compute free intervals from persisted blocks only. Include server timezone and UTC instants where cross-midnight interpretation matters.

- [ ] **Step 4: Run read and P0 safety tests**

Run: `.venv/bin/pytest -q tests/test_calendar_read_api.py tests/test_mobile_api.py -k 'today or calendar or read'`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/calendar_read_service.py app/api/v2/calendar.py tests/test_calendar_read_api.py
git commit -m "Expose Day Week and Month read models"
```

## Task 5: Mobile Calendar Models and Screens

**Files:**
- Create: `mobile/src/api/calendarApi.ts`
- Create: `mobile/src/features/calendar/calendarTypes.ts`
- Create: `mobile/src/features/calendar/calendarModel.ts`
- Create: `mobile/src/features/calendar/CalendarScreen.tsx`
- Create: `mobile/app/calendar.tsx`
- Modify: `mobile/src/features/today/components/TodayHeader.tsx`
- Test: `mobile/src/features/calendar/__tests__/calendarModel.test.ts`

**Interfaces:**
- Produces Day/Week/Month segmented screen nested from Today; Calendar is not a root tab.
- Consumes `/api/v2/calendar/*` and user-scoped cache.

- [ ] **Step 1: Write failing model tests**

Cover seven-day Week, selected day, Month milestone filtering, fixed/flexible/free/recovery/conflict states, long Russian copy, offline cache, loading/error, 360/375/390/430 layout breakpoints, and no drag/drop mutation.

- [ ] **Step 2: Confirm failure**

Run: `cd mobile && npm test -- calendarModel`
Expected: FAIL.

- [ ] **Step 3: Implement calendar screen in locked visual language**

Use one timeline and hairline rules, no dense grid or category rainbow. Capture remains available; applied replan returns to Today. Month shows only high-level events.

- [ ] **Step 4: Run mobile checks**

Run: `cd mobile && npm test && npm run typecheck && npm run lint`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add mobile/src/api/calendarApi.ts mobile/src/features/calendar mobile/app/calendar.tsx mobile/src/features/today/components/TodayHeader.tsx
git commit -m "Add mobile Day Week and Month calendar"
```

## Task 6: Apple Calendar Permission and Sync Adapter

**Files:**
- Create: `mobile/src/integrations/calendar/calendarAdapter.ts`
- Create: `mobile/src/integrations/calendar/expoCalendarAdapter.ts`
- Create: `mobile/src/features/calendar/calendarSyncService.ts`
- Modify: `mobile/app.json`
- Modify: `mobile/package.json`
- Test: `mobile/src/features/calendar/__tests__/calendarSyncService.test.ts`

**Interfaces:**
- Produces `CalendarAdapter.requestReadPermission()`, `readBusyIntervals(range)`, optional `requestWritePermission()`, and `writePlannerEvent()` behind a server flag.
- Consumes native EventKit through the Expo-compatible calendar package selected by `npx expo install`.

- [ ] **Step 1: Write failing adapter contract tests**

Test denied permission, privacy-only mapping, duplicate occurrence IDs, changed/deleted events, no content leakage, explicit write opt-in, write dedupe, and kill-switch disabling writes without a new app release.

- [ ] **Step 2: Confirm failure**

Run: `cd mobile && npm test -- calendarSyncService`
Expected: FAIL.

- [ ] **Step 3: Install SDK-compatible calendar package and implement adapter**

Run: `cd mobile && npx expo install expo-calendar`
Add Russian permission copy explaining busy-time use. Default to read/import only; write APIs are unreachable unless user preference and server feature flag are both true.

- [ ] **Step 4: Run mobile checks**

Run: `cd mobile && npm test && npm run typecheck && npm run lint && npx expo-doctor`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add mobile/src/integrations/calendar mobile/src/features/calendar/calendarSyncService.ts mobile/src/features/calendar/__tests__/calendarSyncService.test.ts mobile/app.json mobile/package.json mobile/package-lock.json
git commit -m "Integrate privacy-safe Apple Calendar sync"
```

## Task 7: Phase Verification and Documentation

**Files:**
- Create: `docs/07 Техническая документация/Calendar Sync and Adaptive Planning v1.md`
- Modify: `docs/03 Решения/Журнал решений.md`
- Modify: `docs/02 Дорожная карта/Этапы проекта.md`
- Modify: `README.md`

- [ ] **Step 1: Document privacy, dedupe, replan, and rollback contracts**

Include permission sequence, busy-only payload, write opt-in, external ID lifecycle, future-only invariant, PlanChange retention, and server kill switch.

- [ ] **Step 2: Run backend verification**

Run: `.venv/bin/alembic upgrade head && .venv/bin/python scripts/check_mvp.py && .venv/bin/pytest`
Expected: all pass.

- [ ] **Step 3: Run mobile and repository verification**

Run: `cd mobile && npm test && npm run typecheck && npm run lint && npx expo-doctor`
Run: `cd .. && git diff --check`
Expected: all pass.

- [ ] **Step 4: Self-review the invariant matrix**

Verify every plan mutation leaves fixed/past/completed facts unchanged and every calendar sync replay is idempotent and user-scoped.

- [ ] **Step 5: Commit docs**

```bash
git add 'docs/07 Техническая документация/Calendar Sync and Adaptive Planning v1.md' 'docs/03 Решения/Журнал решений.md' 'docs/02 Дорожная карта/Этапы проекта.md' README.md
git commit -m "Document adaptive calendar planning"
```
