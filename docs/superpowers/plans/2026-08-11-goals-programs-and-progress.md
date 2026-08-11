# Goals, Programs, and Progress Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use test-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn existing goals into explainable paths made of milestones, programs, weekly commitments, evidence, and deterministic progress snapshots without inventing progress from task counts.

**Architecture:** Existing `Goal` remains the aggregate root and receives only fields that define its outcome and strategy. New user-owned tables store milestones, programs, commitments, evidence, observations, and immutable progress snapshots. A pure progress calculator selects a typed strategy (`metric`, `milestone`, or `consistency`); APIs return authoritative read models and mobile renders the vertical burgundy path without local formulas.

**Tech Stack:** SQLAlchemy 2, PostgreSQL, Alembic, FastAPI/Pydantic, deterministic Python services, React Native/TypeScript, Vitest, pytest.

## Global Constraints

- Fact and plan are separate: completing a task may create execution evidence, but never proves a long-term outcome automatically.
- Percentages are exposed only when the goal strategy supplies an explainable denominator.
- LLM may propose program structure or explain a snapshot but may not calculate or persist progress directly.
- At most three active directions; free entitlement limits are enforced server-side by the subscriptions phase.
- All records and reads are user-owned, timezone-aware, versioned where mutable, and account-deletion safe.
- Existing Goal/Task/Routine entities are extended rather than replaced.
- The user-owned `.gitignore` change remains untouched.

---

## Current-State Audit

| Capability | Evidence | Coverage | Gap |
|---|---|---:|---|
| Goal storage | `app/models/goal.py` | Partial | No baseline, target, strategy, intensity, allocation, version, or public ID. |
| Goal-task relation | `Task.goal_id` | Partial | Snapshot does not expose the canonical relation. |
| Milestones/programs | Missing | Missing | No durable path structure. |
| Evidence/results | Daily summary changes status only | Missing | Partial/factual metrics are not stored. |
| Progress | `DaySnapshot.progress` counts day tasks | Daily only | No weekly/outcome progress or forecast confidence. |
| Path mobile | `mobile/src/features/path/pathModel.ts` | Honest shell | Must consume authoritative progress; no client percentages. |

## Task 1: Goal Outcome and Program Schema

**Files:**
- Modify: `app/models/goal.py`
- Modify: `app/models/task.py`
- Create: `app/models/program.py`
- Create: `app/models/evidence.py`
- Modify: `app/models/__init__.py`
- Create: `migrations/versions/b2a1d0f3e422_goals_programs_progress.py`
- Test: `tests/test_goal_program_migration.py`

**Interfaces:**
- Produces `GoalMilestone`, `Program`, `ProgramPhase`, `WeeklyCommitment`, `Evidence`, `MetricObservation`, `GoalProgressSnapshot`.
- Consumes `Goal`, `Task`, and `User` ownership.

- [ ] **Step 1: Write failing schema tests**

Assert foreign keys/cascade policy, uniqueness of milestone order per goal and program phase order, indexes on `(user_id, occurred_at)`, immutable progress payload fields, and absence of raw percentage columns on `Task`.

- [ ] **Step 2: Confirm failure**

Run: `.venv/bin/pytest -q tests/test_goal_program_migration.py`
Expected: FAIL on missing models.

- [ ] **Step 3: Implement models and non-destructive migration**

Migration `b2a1d0f3e422` follows onboarding revision `a8e7f6d5c4b3`. Extend Goal with `public_id`, `life_area`, `outcome_type`, decimal `baseline_value/current_value/target_value`, `metric_unit`, `deadline`, `intensity`, `allocation_minutes_week`, `version`, and timestamps. Add canonical `Task.program_id` and `Task.commitment_id` links in the same migration. Program tables store min/comfortable/max weekly load and adaptation rules as validated JSON. Evidence stores typed factual quantities plus optional bounded note; progress snapshots store computed components, formula version, forecast date, and confidence.

- [ ] **Step 4: Verify upgrade and metadata**

Run: `.venv/bin/pytest -q tests/test_goal_program_migration.py && .venv/bin/alembic upgrade head`
Expected: PASS and existing goals retained with null outcome fields.

- [ ] **Step 5: Commit**

```bash
git add app/models/goal.py app/models/task.py app/models/program.py app/models/evidence.py app/models/__init__.py migrations/versions/b2a1d0f3e422_goals_programs_progress.py tests/test_goal_program_migration.py
git commit -m "Add goal programs and evidence schema"
```

## Task 2: Deterministic Progress Strategies

**Files:**
- Create: `app/services/progress_service.py`
- Create: `app/schemas/progress.py`
- Test: `tests/test_progress_service.py`

**Interfaces:**
- Produces `calculate_metric_progress`, `calculate_milestone_progress`, `calculate_consistency_progress`, `recalculate_goal_progress(db, user, goal, as_of)`, and `ProgressResult`.
- Consumes goal outcome fields, milestones, commitments, and evidence.

- [ ] **Step 1: Write failing formula tests**

Cover metric direction 72→78 and 90→80, missing baseline, target reached, milestone criteria/weights, unweighted milestone fallback, weekly minutes/sessions, partial evidence, rolling consistency, missed work without punishment, pace, forecast, and low/medium/high confidence thresholds. Assert that arbitrary completed-task counts never create outcome percentage.

- [ ] **Step 2: Confirm failure**

Run: `.venv/bin/pytest -q tests/test_progress_service.py`
Expected: FAIL because calculators do not exist.

- [ ] **Step 3: Implement pure decimal-safe formulas**

`metric`: `(current-baseline)/(target-baseline)` clamped only for display. `milestone`: completed criterion weights divided by defined total, or completed count divided by milestone count when every milestone is equivalently weighted. `consistency`: completed factual units divided by planned commitment units for the bounded rolling window. Return `percentage=None` and a typed `insufficient_data` reason when the denominator is not defensible.

- [ ] **Step 4: Run formula and timezone tests**

Run: `.venv/bin/pytest -q tests/test_progress_service.py tests/test_planning_engine.py -k 'progress or timezone or plan_date'`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/progress_service.py app/schemas/progress.py tests/test_progress_service.py
git commit -m "Calculate explainable goal progress"
```

## Task 3: Evidence and Milestone Mutations

**Files:**
- Create: `app/services/evidence_service.py`
- Create: `app/services/program_service.py`
- Create: `app/schemas/goals.py`
- Create: `app/api/v2/goals.py`
- Test: `tests/test_goal_api.py`
- Test: `tests/test_evidence_service.py`

**Interfaces:**
- Produces goal CRUD/pause/resume, milestone confirmation, evidence creation, observation creation, program preview/apply, and optimistic version checks.
- Consumes authenticated user and progress recalculation.

- [ ] **Step 1: Write failing ownership/idempotency tests**

Cover create/update/pause/resume, maximum three active goals, idempotency key reuse, stale goal version, milestone order, partial evidence, metric observation, another user's opaque 404, and progress recalculation in the same transaction.

- [ ] **Step 2: Confirm failure**

Run: `.venv/bin/pytest -q tests/test_goal_api.py tests/test_evidence_service.py`
Expected: FAIL on missing service/routes.

- [ ] **Step 3: Implement service-owned mutations**

Use request receipts for mutation idempotency, validate program load against the resource budget, require confirmation for deadline/program/intensity changes, and return the updated goal plus authoritative progress snapshot. Notes are never logged or emitted in analytics.

- [ ] **Step 4: Run API and isolation tests**

Run: `.venv/bin/pytest -q tests/test_goal_api.py tests/test_evidence_service.py tests/test_account_deletion.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/evidence_service.py app/services/program_service.py app/schemas/goals.py app/api/v2/goals.py tests/test_goal_api.py tests/test_evidence_service.py
git commit -m "Add goal program and evidence API"
```

## Task 4: Weekly Commitment Materialization

**Files:**
- Modify: `app/services/planning_service.py`
- Modify: `app/services/routine_service.py`
- Test: `tests/test_weekly_commitments.py`

**Interfaces:**
- Produces `materialize_weekly_commitments(db, user, week_start)` and canonical links `Task.program_id`, `Task.commitment_id`.
- Consumes active commitments, program phases, resource budget, existing fixed/flexible planning.

- [ ] **Step 1: Write failing commitment tests**

Cover allowed weekdays, preferred window, minimum block, splittable/unsplittable, recovery gap, idempotent materialization, reserve capacity, fixed-event protection, and no generation beyond the nearest detailed week.

- [ ] **Step 2: Confirm failure**

Run: `.venv/bin/pytest -q tests/test_weekly_commitments.py`
Expected: FAIL on missing materializer and links.

- [ ] **Step 3: Implement candidate-to-task materialization**

Create only the current/next detailed week, preserve existing factual/completed actions, retain canonical commitment identity, and let the existing deterministic scheduler choose placements. Unsatisfied load remains an explicit commitment shortfall, never fake completion.

- [ ] **Step 4: Run planning regression tests**

Run: `.venv/bin/pytest -q tests/test_weekly_commitments.py tests/test_planning_engine.py tests/test_routines.py`
Expected: PASS and no overlap regression.

- [ ] **Step 5: Commit**

```bash
git add app/services/planning_service.py app/services/routine_service.py tests/test_weekly_commitments.py
git commit -m "Materialize weekly goal commitments"
```

## Task 5: Path and Goal Detail Read Models

**Files:**
- Create: `app/services/path_service.py`
- Modify: `app/api/v2/goals.py`
- Create: `tests/test_path_api.py`
- Create: `docs/07 Техническая документация/Mobile API Contract v2.md`

**Interfaces:**
- Produces `GET /api/v2/path`, `GET /api/v2/goals/{public_id}`, paginated `GET /api/v2/goals/{public_id}/evidence`.
- Consumes programs, commitments, milestones, latest progress snapshots.

- [ ] **Step 1: Write failing atomic read-model tests**

Assert at most three active goals in server order, current phase, next step, recent evidence summary without sensitive notes, explicit formula explanation, nullable percentage, forecast confidence, pagination cursor, and bounded query count.

- [ ] **Step 2: Confirm failure**

Run: `.venv/bin/pytest -q tests/test_path_api.py`
Expected: FAIL on missing endpoints.

- [ ] **Step 3: Implement eager-loaded authoritative path model**

Use select-in/eager loading to avoid N+1. Machine fields remain typed; presentation copy is optional and never controls behavior. Document v2 beside preserved v1, including compatibility and pagination.

- [ ] **Step 4: Run path/API tests**

Run: `.venv/bin/pytest -q tests/test_path_api.py tests/test_mobile_api.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/path_service.py app/api/v2/goals.py tests/test_path_api.py 'docs/07 Техническая документация/Mobile API Contract v2.md'
git commit -m "Expose authoritative goal paths"
```

## Task 6: Mobile Path and Goal Details

**Files:**
- Create: `mobile/src/api/pathApi.ts`
- Create: `mobile/src/features/path/pathTypes.ts`
- Modify: `mobile/src/features/path/pathModel.ts`
- Modify: `mobile/app/(tabs)/path.tsx`
- Create: `mobile/app/goal/[id].tsx`
- Create: `mobile/src/features/path/GoalDetailsScreen.tsx`
- Test: `mobile/src/features/path/__tests__/pathModelV2.test.ts`

**Interfaces:**
- Produces mobile path state for metric/milestone/consistency/insufficient-data goals.
- Consumes only `/api/v2/path` and goal detail read models.

- [ ] **Step 1: Write failing mapping tests**

Cover nullable percentage, formula label, milestones, current phase, next step, recent evidence, long Russian text, empty state, cached state, loading/error, and no percentage derived from tasks.

- [ ] **Step 2: Confirm failure**

Run: `cd mobile && npm test -- pathModelV2`
Expected: FAIL because v2 mapper is missing.

- [ ] **Step 3: Implement restrained vertical path UI**

Use the locked paper/burgundy visual system, one vertical line, system weights 400/500, no dashboard cards, and Reduce Motion-aware 300–500ms progress transition. Goal Details exposes pause/edit and «Разобрать с AI», while server confirmation controls risky changes.

- [ ] **Step 4: Run mobile checks**

Run: `cd mobile && npm test && npm run typecheck && npm run lint`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add mobile/src/api/pathApi.ts mobile/src/features/path mobile/app/\(tabs\)/path.tsx mobile/app/goal
git commit -m "Render authoritative goal paths"
```

## Task 7: Phase Verification and Product Docs

**Files:**
- Modify: `docs/01 Продукт/Спецификация продукта.md`
- Modify: `docs/02 Дорожная карта/Этапы проекта.md`
- Modify: `docs/03 Решения/Журнал решений.md`
- Modify: `mobile/BACKEND_GAPS.md`

- [ ] **Step 1: Document formula versions and evidence privacy**

Record metric/milestone/consistency semantics, forecast confidence, program materialization horizon, and why task counts are not outcome progress.

- [ ] **Step 2: Run backend phase checks**

Run: `.venv/bin/alembic upgrade head && .venv/bin/python scripts/check_mvp.py && .venv/bin/pytest`
Expected: all backend tests pass.

- [ ] **Step 3: Run mobile and diff checks**

Run: `cd mobile && npm test && npm run typecheck && npm run lint`
Run: `cd .. && git diff --check`
Expected: all pass.

- [ ] **Step 4: Self-review**

Trace each displayed progress value to stored evidence and a formula version; confirm every query is user-scoped and no health-like note enters analytics/logs.

- [ ] **Step 5: Commit documentation**

```bash
git add 'docs/01 Продукт/Спецификация продукта.md' 'docs/02 Дорожная карта/Этапы проекта.md' 'docs/03 Решения/Журнал решений.md' mobile/BACKEND_GAPS.md
git commit -m "Document programs and honest progress"
```
