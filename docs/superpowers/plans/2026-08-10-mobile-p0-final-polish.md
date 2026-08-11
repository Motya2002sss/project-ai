# Mobile P0 Final Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring the locked iOS Today P0 vertical slice to dogfood-quality visual and recovery behavior without starting P1 or inventing backend data.

**Architecture:** Keep the existing Expo Router shell, reducer-driven planner lifecycle, and `/api/v1` client intact. Add pure presentation mappers for honest Path/Profile shells, retain server interaction context across retries, and harden the existing one-terminal launcher around observed stale-process and VPN failures.

**Tech Stack:** Expo 54, React Native 0.81, TypeScript 5.9, Vitest 4, Bash, pytest.

## Global Constraints

- Mobile remains a thin client; FastAPI and PostgreSQL remain canonical.
- Final palette, system typography, Today timeline, three-tab navigation, and Capture hierarchy stay unchanged.
- No Week, Voice, Workout, onboarding, general Undo, goal percentages, Profile mutations, Android polish, or fake production data.
- Production flow uses real `/api/v1`; fixtures remain confined to `src/dev/fixtures` and dev routes.
- Preserve the user's unrelated `.gitignore` change.

---

### Task 1: Honest Path presentation

**Files:**
- Create: `mobile/src/features/path/pathModel.ts`
- Create: `mobile/src/features/path/__tests__/pathModel.test.ts`
- Modify: `mobile/app/(tabs)/path.tsx`

**Interfaces:**
- Consumes: `GoalDto[]` from the authoritative cached/server `DaySnapshotDto`.
- Produces: `buildPathModel(goals): { state: 'empty' | 'ready'; goals: Array<{ id: number; title: string }> }`.

- [ ] **Step 1: Write the failing mapper tests**

```ts
expect(buildPathModel([
  { id: 2, title: 'Набрать 6 кг', category: 'health', priority: 'medium', status: 'active' },
  { id: 3, title: 'Архив', category: 'other', priority: 'low', status: 'completed' },
])).toEqual({ state: 'ready', goals: [{ id: 2, title: 'Набрать 6 кг' }] });
expect(buildPathModel([])).toEqual({ state: 'empty', goals: [] });
```

- [ ] **Step 2: Run the focused test and verify RED**

Run: `cd mobile && npm test -- src/features/path/__tests__/pathModel.test.ts`

Expected: FAIL because `pathModel.ts` does not exist.

- [ ] **Step 3: Implement the minimal mapper**

```ts
export function buildPathModel(goals: GoalDto[]): PathModel {
  const activeGoals = goals
    .filter((goal) => goal.status === 'active')
    .map(({ id, title }) => ({ id, title }));
  return { state: activeGoals.length ? 'ready' : 'empty', goals: activeGoals };
}
```

- [ ] **Step 4: Render real goal titles without percentages**

Use `state.today.snapshot?.goals ?? []`, preserve server order, and keep the existing empty Capture action when no active goals exist.

- [ ] **Step 5: Run focused tests and typecheck**

Run: `cd mobile && npm test -- src/features/path/__tests__/pathModel.test.ts && npm run typecheck`

Expected: PASS.

### Task 2: Recoverable interaction sheet

**Files:**
- Modify: `mobile/src/features/planner/plannerReducer.ts`
- Modify: `mobile/src/features/planner/__tests__/plannerReducer.test.ts`
- Modify: `mobile/src/features/capture/CaptureSheet.tsx`
- Modify: `mobile/src/features/interactions/InteractionSheet.tsx`

**Interfaces:**
- Consumes: the current clarification/confirmation/conflict state when an answer starts.
- Produces: `submitting.interaction` and `error.interaction` context used to keep the question visible and safely retry the same request id.

- [ ] **Step 1: Write a failing reducer test**

```ts
const started = plannerReducer(clarificationState, {
  type: 'capture/requestStarted',
  requestId: 'answer-1',
  operation: { kind: 'interaction', interactionId: 'c1', text: 'Разовая задача' },
});
const failed = plannerReducer(started, {
  type: 'capture/requestFailed', requestId: 'answer-1',
  message: 'Не удалось отправить ответ.', retryable: true,
});
expect(failed.capture).toMatchObject({ status: 'error', interaction: clarificationState.capture });
```

- [ ] **Step 2: Run the focused test and verify RED**

Run: `cd mobile && npm test -- src/features/planner/__tests__/plannerReducer.test.ts`

Expected: FAIL because interaction context is discarded.

- [ ] **Step 3: Retain context in reducer states**

Add a named `InteractionCaptureState` union, store it in interaction answer `submitting`, preserve it in `requestFailed`, and preserve it again when retry starts.

- [ ] **Step 4: Keep the same sheet visible while busy/error**

Render `InteractionSheet` for direct, submitting, and retryable-error contexts. Disable options/free text while busy and show `Повторить` inside the same sheet after a retryable error.

- [ ] **Step 5: Run focused tests and typecheck**

Run: `cd mobile && npm test -- src/features/planner/__tests__/plannerReducer.test.ts && npm run typecheck`

Expected: PASS.

### Task 3: Locked visual shell polish

**Files:**
- Modify: `mobile/src/features/today/TodayScreen.tsx`
- Modify: `mobile/app/(tabs)/path.tsx`
- Modify: `mobile/app/(tabs)/profile.tsx`
- Modify: `mobile/src/components/AppBottomNavigation.tsx`

**Interfaces:**
- Consumes: existing semantic theme tokens only.
- Produces: consistent screen gutters, lower thumb-zone composition, honest Profile placeholder, and readable long Russian strings at supported widths.

- [ ] **Step 1: Make the single P0 Capture control fill the available row**

Keep the label `Что изменилось?`, `44×44` minimum target, current burgundy accent, and no microphone placeholder before Voice exists.

- [ ] **Step 2: Replace technical Profile identity copy**

Use a neutral unavailable-profile placeholder; retain only actionable Path and backend-access rows, and keep P1 rows visibly unavailable.

- [ ] **Step 3: Align Path/Profile vertical rhythm with Today**

Use the same title top inset, rules, 22/16 pt gutters, 400/500 weights, and no new decorative cards or shadows.

- [ ] **Step 4: Run lint/typecheck**

Run: `cd mobile && npm run typecheck && npm run lint`

Expected: PASS.

### Task 4: One-terminal dogfood recovery

**Files:**
- Modify: `scripts/dogfood/start.sh`
- Modify: `scripts/dogfood/README.md`
- Modify: `tests/test_dogfood_scripts.py`

**Interfaces:**
- Consumes: macOS process state, exact project supervisor PID, and active network-service status.
- Produces: a safe early VPN diagnostic and recoverable project-owned supervisor state without killing arbitrary port owners.

- [ ] **Step 1: Add failing launcher tests**

Run the copied launcher with a fake connected VPN result and assert it exits before backend start with an `AmneziaWG/VPN` instruction. Run it with a validated stale project supervisor marker and assert the stale process is cleaned before new startup.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `.venv/bin/pytest tests/test_dogfood_scripts.py -q`

Expected: new tests FAIL against current launcher.

- [ ] **Step 3: Add minimal diagnostics/recovery**

Detect connected macOS VPN before starting Quick Tunnel, with `DOGFOOD_ALLOW_VPN=1` as an explicit override. Track only the exact project-owned supervisor so a later launch can clean a stopped/orphaned previous run; never kill an arbitrary PID discovered only from port `8000`.

- [ ] **Step 4: Verify scripts**

Run: `.venv/bin/pytest tests/test_dogfood_scripts.py -q && bash -n scripts/dogfood/*.sh`

Expected: PASS.

### Task 5: Visual and full verification

**Files:**
- Modify only files identified by visual defects from the previous tasks.

**Interfaces:**
- Consumes: dev-only scenario routes.
- Produces: visual QA evidence; production networking remains real.

- [ ] **Step 1: Capture canonical states at `390×844`**

Check Today normal, processing, diff, clarification, confirmation, conflict, all-done, offline, Path, Profile, and Task Details.

- [ ] **Step 2: Check width boundaries**

Repeat normal Today plus long Russian strings at `375×812` and `430×932`; confirm no horizontal overflow, clipped action, or hidden tab/capture control.

- [ ] **Step 3: Run all mobile and root checks**

Run:

```bash
cd mobile && npm test && npm run typecheck && npm run lint
cd .. && .venv/bin/pytest -q
git diff --check
```

Expected: all commands exit `0`.

- [ ] **Step 4: Review the final diff and preserve unrelated changes**

Confirm `.gitignore` remains unstaged and no `.env`, tokens, generated screenshots, or dev-server artifacts are included.
