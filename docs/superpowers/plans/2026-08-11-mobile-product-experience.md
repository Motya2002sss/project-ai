# Mobile Product Experience Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use frontend-design and test-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the locked iOS-first product journey from Apple sign-in and narrative onboarding through full-day Today, workout/nutrition/learning evidence, voice capture, notifications, and production Profile without redesigning the established paper/burgundy system.

**Architecture:** Mobile stays a thin renderer and capture client over `/api/v2`; domain state and calculations remain server-side. Native capabilities are isolated behind Apple auth, audio, calendar, notification, and purchases adapters so tests use fakes and text-only local mode remains available. Drafts are user-scoped and recoverable; sensitive results are never emitted to analytics.

**Tech Stack:** Expo 54/React Native 0.81/Expo Router/TypeScript, native Expo modules selected with `npx expo install`, FastAPI/SQLAlchemy for activity contracts, Vitest, pytest.

## Global Constraints

- Root tabs are exactly `Сегодня / Календарь / Путь / Профиль` per the expanded master prompt; the AI composer is an action, never a tab or chat.
- Visual tokens remain paper `#F8F9F5`, ink `#1D1F1C`, muted `#73766F`, rule `#D2D4CD`, burgundy `#6B3036`, soft burgundy `#EEE6E6`; system weights are 400/500.
- Minimum touch target is 44×44; safe areas, Dynamic Type, VoiceOver, Reduce Motion, keyboard, and 360/375/390/430 widths are required.
- Ordinary completion is one tap with no forced report or motivational screen.
- Workout/meal/learning facts may be partial; they are never judged, silently corrected, or converted to made-up goal progress.
- Audio is temporary, bounded, deleted after transcription by default, and never logged or analyzed.
- Expo Go is not the release validation target once native Apple/IAP modules are installed; local text mode remains supported.
- The user-owned `.gitignore` change remains untouched.

---

## Task 1: Activity and Result Schema

**Files:**
- Create: `app/models/activity.py`
- Modify: `app/models/__init__.py`
- Create: `migrations/versions/d4c3f2b5a644_activity_evidence.py`
- Test: `tests/test_activity_migration.py`

**Interfaces:**
- Produces `WorkoutExercise`, `WorkoutSet`, `NutritionLog`, `LearningResource`, `LearningSession`, and task/program links.
- Consumes `Evidence`, `Task`, `Program`, `Goal`, and user ownership.

- [ ] **Step 1: Write failing schema tests**

Assert planned/actual workout values are separate, set order is unique, partial completion is representable, nutrition targets/logs do not require invented macro values, learning resources support pages/minutes/exercises/projects, all records cascade with account deletion, and notes are bounded sensitive fields.

- [ ] **Step 2: Confirm failure**

Run: `.venv/bin/pytest -q tests/test_activity_migration.py`
Expected: FAIL on missing activity models.

- [ ] **Step 3: Implement schema and migration**

Migration `d4c3f2b5a644` follows calendar revision `c3b2e1a4f533`. Workout facts use decimal weight and integer reps with optional RPE. Nutrition logs support free-text meal note, adherence, weight observation, and configured targets. Learning sessions support resource/competency, pages/minutes and milestone evidence. No food database or barcode schema is added.

- [ ] **Step 4: Verify migration**

Run: `.venv/bin/pytest -q tests/test_activity_migration.py && .venv/bin/alembic upgrade head`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/models/activity.py app/models/__init__.py migrations/versions/d4c3f2b5a644_activity_evidence.py tests/test_activity_migration.py
git commit -m "Add workout nutrition and learning facts"
```

## Task 2: Activity APIs and Safety Policy

**Files:**
- Create: `app/schemas/activity.py`
- Create: `app/services/activity_service.py`
- Create: `app/services/safety_policy.py`
- Create: `app/api/v2/activities.py`
- Test: `tests/test_activity_api.py`
- Test: `tests/test_safety_policy.py`

**Interfaces:**
- Produces workout snapshot/draft/final mutations, nutrition observations, learning results, and `SafetyDecision(allowed, reason, safe_message)`.
- Consumes authenticated user, Evidence, progress recalculation, and entitlement checks.

- [ ] **Step 1: Write failing activity tests**

Cover workout 80×6/6/6/5 as valid fact, partial sets, draft retry, finish idempotency, ownership, elapsed time, evidence update, nutrition without fabricated numbers, body-weight trend, pages/minutes learning evidence, and completion without a report.

- [ ] **Step 2: Write failing safety tests**

Cover eating-disorder/extreme restriction, medical diagnosis/treatment, unsafe one-rep-max escalation, injury limitations, allergies, and neutral allowed planning. Tests assert typed refusal/advice boundaries and no mutation on rejected requests.

- [ ] **Step 3: Confirm failures**

Run: `.venv/bin/pytest -q tests/test_activity_api.py tests/test_safety_policy.py`
Expected: FAIL.

- [ ] **Step 4: Implement thin routes and factual services**

Keep safety checks deterministic before any LLM provider call or mutation. Program adaptation returns a candidate requiring confirmation; one successful/failed set never auto-increases weight.

- [ ] **Step 5: Run and commit**

Run: `.venv/bin/pytest -q tests/test_activity_api.py tests/test_safety_policy.py tests/test_progress_service.py`
Expected: PASS.

```bash
git add app/schemas/activity.py app/services/activity_service.py app/services/safety_policy.py app/api/v2/activities.py tests/test_activity_api.py tests/test_safety_policy.py
git commit -m "Expose factual activity results"
```

## Task 3: Sign in with Apple and Onboarding Screens

**Files:**
- Create: `mobile/app/sign-in.tsx`
- Create: `mobile/app/onboarding.tsx`
- Create: `mobile/app/onboarding-preview.tsx`
- Create: `mobile/src/integrations/apple/appleAuthAdapter.ts`
- Create: `mobile/src/features/onboarding/onboardingReducer.ts`
- Create: `mobile/src/features/onboarding/OnboardingScreen.tsx`
- Modify: `mobile/app.json`
- Modify: `mobile/package.json`
- Test: `mobile/src/features/onboarding/__tests__/onboardingReducer.test.ts`

**Interfaces:**
- Produces native Apple credential exchange and onboarding preview/apply navigation.
- Consumes AuthProvider and `/api/v2/onboarding`.

- [ ] **Step 1: Write failing state tests**

Cover welcome→Apple sign-in→narrative draft→processing→clarification→resource budget→preview→apply→Today; draft background retention; duplicate submit; back/correction; three-goal cap; offline failure; and no paywall before personalized preview.

- [ ] **Step 2: Confirm failure**

Run: `cd mobile && npm test -- onboardingReducer`
Expected: FAIL.

- [ ] **Step 3: Install native Apple package and implement screens**

Run: `cd mobile && npx expo install expo-apple-authentication`
Use the official Apple control, generated nonce/state, required welcome copy, one narrative surface, resource budget in real hours/days, and first-plan preview. Do not build a carousel or long questionnaire.

- [ ] **Step 4: Run mobile checks**

Run: `cd mobile && npm test && npm run typecheck && npm run lint && npx expo-doctor`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add mobile/app/sign-in.tsx mobile/app/onboarding.tsx mobile/app/onboarding-preview.tsx mobile/src/integrations/apple mobile/src/features/onboarding mobile/app.json mobile/package.json mobile/package-lock.json
git commit -m "Add Apple sign in and narrative onboarding"
```

## Task 4: Full-Day Today and Navigation

**Files:**
- Modify: `mobile/src/api/types.ts`
- Modify: `mobile/src/features/today/models.ts`
- Modify: `mobile/src/features/today/todayMapper.ts`
- Modify: `mobile/src/features/today/TodayScreen.tsx`
- Modify: `mobile/src/features/today/components/Timeline.tsx`
- Modify: `mobile/src/features/today/components/TimelineRow.tsx`
- Modify: `mobile/src/components/AppBottomNavigation.tsx`
- Test: `mobile/src/features/today/__tests__/fullDayMapper.test.ts`

**Interfaces:**
- Produces full-day anchors/fixed/actions/meals/commute/free/recovery/sleep timeline and four-tab shell.
- Consumes authoritative v2 Today/calendar snapshot and task-goal links.

- [ ] **Step 1: Write failing model tests**

Cover first day, normal full day, overloaded, low-energy, workout, learning, all-done, conflict, offline, current marker, past dimming, goal context, weekly summary, long Russian text, and absence of micro-actions unless server supplied.

- [ ] **Step 2: Confirm failure**

Run: `cd mobile && npm test -- fullDayMapper`
Expected: FAIL.

- [ ] **Step 3: Implement authoritative timeline mapping and navigation**

Current item uses soft burgundy and a thin current-time marker; past remains readable, future complete, top progress is a thin line with no dashboard cards. Checkbox remains separate from task content and does not open a result screen.

- [ ] **Step 4: Run mobile checks**

Run: `cd mobile && npm test && npm run typecheck && npm run lint`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add mobile/src/api/types.ts mobile/src/features/today mobile/src/components/AppBottomNavigation.tsx
git commit -m "Render the complete authoritative day"
```

## Task 5: Workout, Nutrition, and Learning Mobile Flows

**Files:**
- Create: `mobile/src/api/activityApi.ts`
- Create: `mobile/app/workout/[id].tsx`
- Create: `mobile/src/features/workout/WorkoutDetailsScreen.tsx`
- Create: `mobile/src/features/workout/workoutReducer.ts`
- Create: `mobile/app/nutrition.tsx`
- Create: `mobile/src/features/nutrition/NutritionScreen.tsx`
- Create: `mobile/app/learning/[id].tsx`
- Create: `mobile/src/features/learning/LearningDetailsScreen.tsx`
- Test: `mobile/src/features/workout/__tests__/workoutReducer.test.ts`
- Test: `mobile/src/features/activities/__tests__/activityModels.test.ts`

**Interfaces:**
- Produces user-scoped offline drafts and factual mutation requests for activities.
- Consumes `/api/v2/activities/*` and authoritative progress responses.

- [ ] **Step 1: Write failing state/model tests**

Cover planned versus actual sets, partial completion, 80×5 acceptance, optional RPE/note, offline draft restore, same request ID retry, finish success, rollback; nutrition free-text/adherence/weight; learning pages/minutes/exercises; no emotional post-completion screen.

- [ ] **Step 2: Confirm failure**

Run: `cd mobile && npm test -- workoutReducer activityModels`
Expected: FAIL.

- [ ] **Step 3: Implement restrained activity screens**

Editable set rows are direct controls, not cards. Nutrition stays a compact factual log without invented macros. Learning shows resource, competency and one next action. Every draft is namespaced by user and activity ID.

- [ ] **Step 4: Run checks**

Run: `cd mobile && npm test && npm run typecheck && npm run lint`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add mobile/src/api/activityApi.ts mobile/app/workout mobile/src/features/workout mobile/app/nutrition.tsx mobile/src/features/nutrition mobile/app/learning mobile/src/features/learning mobile/src/features/activities
git commit -m "Add factual workout nutrition and learning flows"
```

## Task 6: Voice Transcription Pipeline

**Files:**
- Create: `app/services/transcription_service.py`
- Create: `app/api/v2/transcriptions.py`
- Create: `app/schemas/transcription.py`
- Modify: `app/core/config.py`
- Test: `tests/test_transcription_api.py`
- Create: `mobile/src/integrations/audio/audioAdapter.ts`
- Create: `mobile/src/features/voice/VoiceCaptureSheet.tsx`
- Create: `mobile/src/features/voice/voiceReducer.ts`
- Modify: `mobile/src/features/planner/PlannerProvider.tsx`
- Modify: `mobile/package.json`
- Test: `mobile/src/features/voice/__tests__/voiceReducer.test.ts`

**Interfaces:**
- Produces bounded audio upload → transcript preview → edited text → existing capture pipeline.
- Consumes configurable transcription provider; text capture remains available when disabled.

- [ ] **Step 1: Write failing backend limits tests**

Cover allowed MIME types, maximum bytes/duration, empty speech, provider timeout, temp deletion on success/failure, no audio/raw transcript logs, disabled provider, and no semantic mutation from transcription alone.

- [ ] **Step 2: Write failing mobile voice tests**

Cover permission denied, listening, no speech, transcribed, edit, cancel/delete, background interruption, Reduce Motion, upload retry, and explicit confirmation before high-risk semantic capture.

- [ ] **Step 3: Confirm failures**

Run: `.venv/bin/pytest -q tests/test_transcription_api.py`
Run: `cd mobile && npm test -- voiceReducer`
Expected: FAIL.

- [ ] **Step 4: Implement provider abstraction and native adapter**

Run: `cd mobile && npx expo install expo-audio`
Use a private `mkstemp` file with guaranteed cleanup. Provider output is Pydantic-validated text; the endpoint returns transcript only. Mobile always shows editable preview before invoking ordinary capture.

- [ ] **Step 5: Run checks and commit**

Run: `.venv/bin/pytest -q tests/test_transcription_api.py && cd mobile && npm test && npm run typecheck && npm run lint`
Expected: PASS.

```bash
git add app/services/transcription_service.py app/api/v2/transcriptions.py app/schemas/transcription.py app/core/config.py tests/test_transcription_api.py mobile/src/integrations/audio mobile/src/features/voice mobile/src/features/planner/PlannerProvider.tsx mobile/package.json mobile/package-lock.json
git commit -m "Add reviewed voice transcription capture"
```

## Task 7: Notifications and Production Profile

**Files:**
- Create: `app/models/device.py`
- Create: `migrations/versions/d8c7b6a5f433_device_registrations.py`
- Create: `app/services/notification_service.py`
- Create: `app/api/v2/devices.py`
- Create: `mobile/src/integrations/notifications/notificationAdapter.ts`
- Create: `mobile/src/features/profile/ProfileScreen.tsx`
- Modify: `mobile/app/(tabs)/profile.tsx`
- Modify: `mobile/app.json`
- Test: `tests/test_notification_service.py`
- Test: `mobile/src/features/shell/__tests__/productionProfileModel.test.ts`

**Interfaces:**
- Produces device registration/preferences, local notification schedule, and production Profile actions.
- Consumes auth/session, calendar plan versions, subscription state, support URLs, and account lifecycle.

- [ ] **Step 1: Write failing notification/profile tests**

Cover permission denial, nearest fixed/action/leave/replan decision/weekly review/measurement only, stale notification removal after replan, multiple devices, logout unregister, and Profile name/masked email/plan/subscription/manage/restore/notifications/calendar/routine/goals/privacy/terms/support/version/logout/delete. Assert no backend URL/token/dev copy/dead control appears in production.

- [ ] **Step 2: Confirm failure**

Run: `.venv/bin/pytest -q tests/test_notification_service.py`
Run: `cd mobile && npm test -- productionProfileModel`
Expected: FAIL.

- [ ] **Step 3: Implement permission-aware scheduling and Profile**

Run: `cd mobile && npx expo install expo-notifications expo-device expo-application`
Migration `d8c7b6a5f433` follows activity revision `d4c3f2b5a644`. Only enabled capabilities render. Delete account requires an explicit destructive confirmation and clears SecureStore/caches after server success.

- [ ] **Step 4: Run checks**

Run: `.venv/bin/pytest -q tests/test_notification_service.py && cd mobile && npm test && npm run typecheck && npm run lint && npx expo-doctor`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/models/device.py migrations/versions/d8c7b6a5f433_device_registrations.py app/services/notification_service.py app/api/v2/devices.py tests/test_notification_service.py mobile/src/integrations/notifications mobile/src/features/profile mobile/app/\(tabs\)/profile.tsx mobile/app.json mobile/package.json mobile/package-lock.json
git commit -m "Add notifications and production profile"
```

## Task 8: Accessibility, Fixtures, and Visual QA

**Files:**
- Create: `mobile/src/dev/fixtures/productionScenarios.ts`
- Modify: `mobile/app/(tabs)/dev/[scenario].tsx`
- Create: `docs/05 Тестирование продукта/Mobile Production Visual QA.md`
- Modify: `mobile/README.md`

- [ ] **Step 1: Add realistic non-production fixture scenarios**

Include first day, normal full day, overloaded, low-energy, workout, learning, all done, partial workout, conflict, offline, no calendar permission, free, trial, active Pro, grace, expired, paywall loading, and purchase failure. Production builds must exclude dev routes and fixtures.

- [ ] **Step 2: Run automated accessibility model tests**

Run: `cd mobile && npm test`
Expected: tests cover accessibility labels, separate checkbox/content actions, Reduce Motion state, and untruncated long copy models.

- [ ] **Step 3: Perform visual QA at required viewports**

Run local web export and inspect 360×800, 375×812, 390×844, and 430×932 plus large text, keyboard, loading, empty, offline, error, and subscription states. Do not commit screenshots.

- [ ] **Step 4: Run phase verification**

Run: `.venv/bin/alembic upgrade head && .venv/bin/pytest`
Run: `cd mobile && npm test && npm run typecheck && npm run lint && npx expo-doctor && npx expo export --platform web`
Run: `cd .. && git diff --check`
Expected: all local checks pass.

- [ ] **Step 5: Commit QA assets/docs**

```bash
git add mobile/src/dev/fixtures/productionScenarios.ts mobile/app/\(tabs\)/dev/\[scenario\].tsx 'docs/05 Тестирование продукта/Mobile Production Visual QA.md' mobile/README.md
git commit -m "Add production mobile QA scenarios"
```
