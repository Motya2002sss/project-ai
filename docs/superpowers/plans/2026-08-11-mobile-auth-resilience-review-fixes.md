# Mobile Auth Resilience Review Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the independent-review P1/P2 findings around mobile startup deadlines, atomic session ownership, auth lifecycle races, and fail-closed planner scope selection.

**Architecture:** Store access token, refresh token, and their authoritative public user UUID in one versioned SecureStore envelope. Bound every startup/storage/token-provider wait, use a monotonic auth epoch plus serialized secure mutations to suppress stale async completion, and make Planner/Path consume only an authenticated or envelope-bound identity. Local dogfood remains an explicit development-only mode.

**Tech Stack:** Expo 54, React Native 0.81, TypeScript 5.9, SecureStore, AsyncStorage, Vitest.

## Global Constraints

- Do not change Today, onboarding, or Path presentation UI.
- Never store access or refresh credentials outside SecureStore.
- Never delete user cache for transient transport or storage failures.
- Clear session-owned cache only after proven revocation, explicit logout, or successful account deletion.
- Do not stage or commit this slice.

---

### Task 1: Bound asynchronous boundaries

**Files:**
- Modify: `mobile/src/api/client.ts`
- Modify: `mobile/src/api/__tests__/client.test.ts`
- Modify: `mobile/src/storage/sessionStorage.ts`
- Modify: `mobile/src/features/auth/__tests__/authReducer.test.ts`

**Interfaces:**
- Produces: `ApiClient.request()` with one total deadline covering token lookup, recovery, transport, and JSON parsing.
- Produces: `SessionVault` operations with an injectable bounded timeout.

- [ ] **Step 1: Write failing tests for never-settling token and storage promises**

```ts
const request = client.request('/api/v2/today').catch((error) => error);
await vi.advanceTimersByTimeAsync(25);
expect(await request).toMatchObject({ kind: 'timeout', retryable: true });

const load = vault.load().catch((error) => error);
await vi.advanceTimersByTimeAsync(25);
expect(await load).toBeInstanceOf(StorageDeadlineError);
```

- [ ] **Step 2: Verify the new tests fail for the missing deadlines**

Run: `npm test -- src/api/__tests__/client.test.ts src/features/auth/__tests__/authReducer.test.ts`

- [ ] **Step 3: Add total deadline races and abort propagation**

```ts
const deadline = new Promise<never>((_resolve, reject) => {
  timeout = setTimeout(() => {
    controller.abort();
    reject(new ApiError('timeout', true));
  }, this.timeoutMs);
});
return Promise.race([operation(), deadline]);
```

- [ ] **Step 4: Verify focused tests pass**

Run: `npm test -- src/api/__tests__/client.test.ts src/features/auth/__tests__/authReducer.test.ts`

### Task 2: Atomic, identity-bound SecureStore envelope

**Files:**
- Modify: `mobile/src/storage/sessionStorage.ts`
- Modify: `mobile/src/features/auth/sessionHydrationPolicy.ts`
- Modify: `mobile/src/features/auth/__tests__/authReducer.test.ts`
- Modify: `docs/07 Техническая документация/Authentication and Account Lifecycle v1.md`

**Interfaces:**
- Produces: `SessionEnvelope = { version: 2; publicUserId: string | null; accessToken: string; refreshToken: string; source: 'current' | 'legacy' }`.
- Produces: `SessionVault.save(publicUserId, credentials)` as one SecureStore write.

- [ ] **Step 1: Write failing atomicity, legacy migration, partial-write, and account-switch tests**

```ts
await vault.save('user-a', { accessToken: 'a', refreshToken: 'ra' });
await vault.save('user-b', { accessToken: 'b', refreshToken: 'rb' });
expect(await vault.load()).toMatchObject({ publicUserId: 'user-b' });
expect(secureStore.values.size).toBe(1);
```

- [ ] **Step 2: Verify the envelope tests fail against split v1 keys**

Run: `npm test -- src/features/auth/__tests__/authReducer.test.ts`

- [ ] **Step 3: Implement one-write envelope and safe unbound legacy loading**

```ts
await storage.setItemAsync(sessionEnvelopeKey, JSON.stringify({
  version: 2,
  publicUserId,
  accessToken: credentials.accessToken,
  refreshToken: credentials.refreshToken,
}));
```

- [ ] **Step 4: Verify envelope tests pass and update the lifecycle contract**

Run: `npm test -- src/features/auth/__tests__/authReducer.test.ts`

### Task 3: Serialize auth lifecycle mutations

**Files:**
- Modify: `mobile/src/api/authApi.ts`
- Modify: `mobile/src/api/__tests__/authApi.test.ts`
- Modify: `mobile/src/features/auth/AuthProvider.tsx`

**Interfaces:**
- Produces: `AuthOperationCoordinator.invalidate()`, `currentEpoch()`, and `runIfCurrent(epoch, operation)`.
- Consumes: identity-bound `SessionVault` envelope from Task 2.

- [ ] **Step 1: Write failing race tests for refresh versus logout, deletion, and sign-in**

```ts
const refreshEpoch = coordinator.currentEpoch();
const lateSave = coordinator.runIfCurrent(refreshEpoch, saveRotated);
const logoutEpoch = coordinator.invalidate();
const clear = coordinator.runIfCurrent(logoutEpoch, clearSession);
releaseRefresh();
expect(await lateSave).toMatchObject({ current: false });
await clear;
expect(events.at(-1)).toBe('clear');
```

- [ ] **Step 2: Verify the race tests fail without epoch/serialization**

Run: `npm test -- src/api/__tests__/authApi.test.ts`

- [ ] **Step 3: Gate every credential write and dispatch by the captured epoch**

```ts
const epoch = lifecycle.currentEpoch();
const commit = await lifecycle.runIfCurrent(epoch, () => sessionVault.save(scope, rotated));
if (!commit.current) return null;
dispatch({ type: 'refresh/succeeded', user });
```

Before assigning `userRef.current` or dispatching from startup hydration, check both the React effect `active` flag and the captured auth epoch again so an unmounted or superseded hydration cannot publish identity.

- [ ] **Step 4: Verify focused auth tests pass**

Run: `npm test -- src/api/__tests__/authApi.test.ts src/features/auth/__tests__/authReducer.test.ts`

### Task 4: Fail-closed product scope selection

**Files:**
- Modify: `mobile/src/config/environment.ts`
- Modify: `mobile/.env.example`
- Modify: `scripts/dogfood/lib.sh`
- Modify: `mobile/src/features/planner/plannerAuthPolicy.ts`
- Modify: `mobile/src/features/planner/__tests__/plannerAuthPolicy.test.ts`
- Modify: `mobile/src/features/planner/PlannerProvider.tsx`
- Modify: `mobile/src/features/path/usePathData.ts`
- Modify: `mobile/src/features/path/__tests__/pathDataState.test.ts`

**Interfaces:**
- Produces: `resolvePlannerAccess(authStatus, publicUserId, dogfoodEnabled, dogfoodTokenAvailable)` returning production, dogfood, or locked access.
- Produces: explicit `EXPO_PUBLIC_ENABLE_DOGFOOD=true` local-only flag.

- [ ] **Step 1: Write failing policy tests for production unauthenticated, explicit dogfood, and stale Path scope**

```ts
expect(resolvePlannerAccess('unauthenticated', null, false, false)).toEqual({ kind: 'locked', scope: null });
expect(resolvePlannerAccess('unauthenticated', null, true, true)).toEqual({ kind: 'dogfood', scope: 'dogfood' });
```

- [ ] **Step 2: Verify policy tests fail because Planner currently defaults to dogfood**

Run: `npm test -- src/features/planner/__tests__/plannerAuthPolicy.test.ts src/features/path/__tests__/pathDataState.test.ts`

- [ ] **Step 3: Apply policy before cache, draft, or network work and remove legacy Path scope reads**

```ts
if (access.kind === 'locked' || access.scope === null) return;
```

- [ ] **Step 4: Run the complete verification matrix**

Run: `npm test && npm run typecheck && npm run lint`

- [ ] **Step 5: Inspect scope and whitespace without staging**

Run: `git diff --check && git status --short`
