# Dogfood Launcher And P0 Shell Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Start the local iPhone dogfood stack from one terminal and make the existing Path/Profile P0 shells match the approved mobile design without inventing P1 data or actions.

**Architecture:** A parent Bash supervisor will reuse the existing backend, Cloudflare Quick Tunnel, and Expo launchers, start them in dependency order, and stop only the child processes it owns. Path and Profile remain thin Expo Router screens; a small pure profile model owns which rows are actionable so unavailable P1 features cannot accidentally look enabled.

**Tech Stack:** Bash 3.2-compatible shell, pytest, Expo SDK 54, React Native, TypeScript, Expo Router, Vitest.

## Global Constraints

- Keep the current `mobile/ios-p0` branch and do not merge into `master`.
- Do not change backend planning, parser, LLM, migrations, Web, or Telegram. A route-limited dogfood ASGI entry point is allowed only to prevent the public Quick Tunnel from exposing compatibility routes.
- Do not implement Week, Voice, Workout, advanced Path, onboarding, notifications, profile mutations, or fake goal progress.
- Use the approved paper/burgundy palette, system typography, 44 pt touch targets, safe areas, and the three locked root tabs.
- Add no dependency and commit no token, `.env`, or private tunnel URL.

---

### Task 1: Single-terminal dogfood supervisor

**Files:**
- Create: `scripts/dogfood/start.sh`
- Modify: `scripts/dogfood/README.md`
- Test: `tests/test_dogfood_scripts.py`

**Interfaces:**
- Consumes: `scripts/dogfood/start-backend.sh`, `start-tunnel.sh`, `start-mobile.sh`, and `dogfood_read_env_value()` from `lib.sh`.
- Produces: `./scripts/dogfood/start.sh`, which starts FastAPI, waits for local health, starts a Quick Tunnel, waits for tunneled health and `.env.local`, then runs Expo in the foreground; `Ctrl+C` terminates owned backend/tunnel children.

- [ ] **Step 1: Write the failing launcher behavior test**

```python
def test_single_terminal_launcher_help_describes_owned_stack():
    result = subprocess.run(
        [ROOT / "scripts" / "dogfood" / "start.sh", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "одном терминале" in result.stdout
    assert "FastAPI" in result.stdout
    assert "Cloudflare Quick Tunnel" in result.stdout
    assert "Expo" in result.stdout
```

- [ ] **Step 2: Run RED**

Run: `pytest tests/test_dogfood_scripts.py::test_single_terminal_launcher_help_describes_owned_stack -q`

Expected: FAIL because `scripts/dogfood/start.sh` does not exist.

- [ ] **Step 3: Implement the supervisor**

Create an executable Bash script that supports only `--help`, rejects unknown arguments, verifies ports `8000` and `8081` are not already occupied, starts each existing launcher in order, checks child liveness while waiting for health, keeps Expo attached to the terminal, and traps `EXIT`, `INT`, and `TERM` to terminate owned child PIDs.

- [ ] **Step 4: Run GREEN and shell syntax checks**

Run: `pytest tests/test_dogfood_scripts.py -q && bash -n scripts/dogfood/*.sh`

Expected: all dogfood tests pass and every script parses successfully.

- [ ] **Step 5: Update the operator README**

Make `./scripts/dogfood/start.sh` the primary reboot path. Keep the three component commands only as troubleshooting tools and document `Ctrl+C` cleanup.

### Task 2: Truthful Path and Profile P0 shells

**Files:**
- Create: `mobile/src/features/shell/profileModel.ts`
- Create: `mobile/src/features/shell/__tests__/profileModel.test.ts`
- Modify: `mobile/app/(tabs)/path.tsx`
- Modify: `mobile/app/(tabs)/profile.tsx`

**Interfaces:**
- Consumes: `usePlanner()` for `openCapture`, `apiBaseUrl`, Today snapshot/error state; Expo Router for `Today`, `Path`, and `setup` navigation.
- Produces: `buildProfileRows({ apiConfigured, hasAuthoritativeToday, hasTodayError })`, whose only actionable destinations are `/path` and `/setup`; Path's primary CTA opens the existing real Capture flow through Today.

- [ ] **Step 1: Write failing profile-action tests**

```typescript
it('keeps unavailable P1 rows non-actionable', () => {
  const rows = buildProfileRows({
    apiConfigured: true,
    hasAuthoritativeToday: true,
    hasTodayError: false,
  });
  expect(rows.find((row) => row.id === 'routine')?.destination).toBeNull();
  expect(rows.find((row) => row.id === 'notifications')?.destination).toBeNull();
});

it('exposes only the real Path and backend access destinations', () => {
  const rows = buildProfileRows({
    apiConfigured: true,
    hasAuthoritativeToday: true,
    hasTodayError: false,
  });
  expect(rows.filter((row) => row.destination).map((row) => row.destination)).toEqual([
    '/path',
    '/setup',
  ]);
});
```

- [ ] **Step 2: Run RED**

Run: `cd mobile && npm test -- src/features/shell/__tests__/profileModel.test.ts`

Expected: FAIL because `profileModel.ts` does not exist.

- [ ] **Step 3: Implement the minimal profile model**

Return four approved rows: `Мой распорядок` and `Уведомления` with `destination: null`; `Цели и планы` with `/path`; `Данные и доступ` with `/setup`. Derive the access detail as `Настроить backend`, `Проверить подключение`, or `Backend подключён` without exposing the Quick Tunnel URL on the Profile screen.

- [ ] **Step 4: Run GREEN**

Run: `cd mobile && npm test -- src/features/shell/__tests__/profileModel.test.ts`

Expected: the new tests pass.

- [ ] **Step 5: Build the approved P0 screen states**

Path shows one calm, non-card empty invitation and a 44 pt `Рассказать о цели` action. The action calls `openCapture()` and returns to Today, where the existing real Capture sheet appears. Profile shows a small neutral local identity mark, the four approved rows, arrows only on the two real destinations, and quiet `Позже` labels for unavailable P1 rows. Both screens use a scrollable safe-area surface and the existing semantic tokens.

- [ ] **Step 6: Verify mobile checks**

Run: `cd mobile && npm test && npm run typecheck && npm run lint`

Expected: all tests, TypeScript, and Expo lint pass.

### Task 3: Visual and repository verification

**Files:**
- Verify only; no new production files.

**Interfaces:**
- Consumes: Expo Web at `http://127.0.0.1:8081/` and the in-app browser viewport control.
- Produces: evidence that Today, Path, Profile, setup navigation, and long Russian copy fit `390×844` without horizontal overflow.

- [ ] **Step 1: Reload Expo and inspect Path/Profile at 390×844**

Check the DOM, screenshots, 44 pt actions, bottom safe region, disabled P1 presentation, and that the Cloudflare URL is no longer the main Profile content.

- [ ] **Step 2: Verify the Path capture handoff**

Tap `Рассказать о цели`; verify navigation to Today and the real Capture sheet, without fixtures or local intent interpretation.

- [ ] **Step 3: Review the final diff and Git state**

Run: `git diff --check`, `git status --short --branch`, and inspect only the scoped files. Preserve unrelated worktree changes and do not merge into `master`.

### Task 4: Security review follow-up

**Files:**
- Create: `app/mobile_dogfood.py`
- Create: `tests/test_mobile_dogfood_app.py`
- Modify: `scripts/dogfood/start-backend.sh`
- Modify: `scripts/dogfood/start-tunnel.sh`
- Modify: `scripts/dogfood/check.sh`
- Modify: `scripts/dogfood/lib.sh`
- Test: `tests/test_dogfood_scripts.py`

**Interfaces:**
- Consumes: the existing `/health` and authenticated `/api/v1` routers.
- Produces: a dedicated ASGI app that returns `404` for compatibility `/api`, `/docs`, and `/openapi.json`; PID-aware tunnel health waiting; file-backed bearer configuration for `curl`; deterministic supervisor subprocess coverage.

- [ ] **Step 1: Prove the current tunnel surface is too broad**

Write `test_mobile_dogfood_surface_exposes_only_health_and_authenticated_v1` and run it before `app/mobile_dogfood.py` exists. Expected: collection fails because the restricted entry point is missing.

- [ ] **Step 2: Add the restricted ASGI entry point**

Include only `health_router` and `mobile_router`, disable docs/redoc/openapi, and make `start-backend.sh` launch `app.mobile_dogfood:app`.

- [ ] **Step 3: Add PID-aware tunnel waiting through RED→GREEN**

Test a child exiting with status `7` during health polling. Implement `dogfood_wait_for_health_while_process_alive()` and propagate the child status without exhausting retries.

- [ ] **Step 4: Keep the bearer secret out of process argv through RED→GREEN**

Run a copied real `check.sh` against fake curl, assert the token never appears in argv and each request has `--max-time`, then write a mode-0600 temporary curl config and pass only its path.

- [ ] **Step 5: Add supervisor subprocess coverage and mutation-check cleanup**

Run the copied launcher with fake backend/tunnel/mobile children, assert dependency order and owned cleanup, and prove the test fails when PID registration is removed.

- [ ] **Step 6: Bind readiness to the owned tunnel**

Seed `mobile/.env.local` with a healthy stale URL and delay the owned tunnel. Verify RED when Expo starts early, then pass a per-launch temporary readiness file to `start-tunnel.sh` and wait for the URL written by that owned child instead of reading stale configuration.
