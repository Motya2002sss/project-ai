# Mobile backend gaps

## Optional Task Details context

**Status:** non-blocking for Today P0; the unavailable sections are omitted.

**Existing contract:** `DaySnapshot.tasks[]` supplies the task title, timing,
duration, scheduling type, and status. It does not expose a task-to-goal link or
an execution plan.

**Missing data:** canonical linked-goal identity/title and ordered execution
steps for one task. The mobile client must not derive either from titles or
other snapshot fields.

**Minimal future contract:** an authenticated task-details read returning the
canonical `task`, optional `linked_goal: { id, title } | null`, and optional
ordered `execution_steps: [{ id, title, status, order }]`. Until such a contract
exists, Task Details intentionally shows only the fields already supplied by
`DaySnapshot`.

## Production auth completion

**Locally available:** `/api/v2` Apple identity-token verification, rotating
sessions, `/me`, export/delete and onboarding preview/apply.

**Still required before TestFlight/App Store:** authorization-code exchange,
encrypted storage of the revocable Apple credential, Apple revoke call during
account deletion, release entitlement verification and native release-build
testing. A locally injected JWKS test is not external Apple verification.

## Authoritative v2 Today

Production sessions cannot call the dogfood-only `/api/v1` planner routes.
Mobile auth state and user-scoped storage therefore must not be wired to the
existing planner transport until authenticated v2 Today/capture/task mutation
routes return the same authoritative `DaySnapshot` and factual `PlanDiff`.

## Onboarding generation quality

The local v2 contract safely previews, versions and applies routine fields,
three goal candidates and a resource budget. Program/milestone generation and
production AI-unavailable behavior remain separate planned slices. The mobile
client must not label deterministic local extraction as completed production AI.
