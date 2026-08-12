---
aliases:
  - Mobile API v2
  - Production iOS API Contract
type: architecture
status: active
area: backend
updated: 2026-08-12
---

# Mobile API Contract v2

> **Production identity boundary for the iOS client. `/api/v1` remains compatible with the local dogfood build.**

## 1. Boundary and authentication

Every `/api/v2` product request uses the server-issued access token obtained after Sign in with Apple:

```http
Authorization: Bearer <access_token>
```

The client never sends `user_id`, `user_external_id`, Apple subject, or another ownership selector. The backend resolves the internal `User` from the hashed session. Missing, expired, reused, or revoked credentials return the same opaque `401` response.

The complete challenge, Apple sign-in, refresh rotation, logout, revoke-all, export, and deletion lifecycle is documented in `Authentication and Account Lifecycle v1.md`.

## 2. Path read model

### `GET /api/v2/path`

Returns at most three active goals in server order: high, medium, low priority, then stable creation order. The endpoint is read-only for goal/program/progress data and never recalculates or creates a progress snapshot.

```json
{
  "goals": [
    {
      "goal": {
        "public_id": "44cf1138-6258-4b5f-b96f-8514bcbb7ed5",
        "title": "Подготовиться к полумарафону",
        "life_area": "body",
        "outcome_type": "consistency",
        "baseline_value": null,
        "current_value": null,
        "target_value": null,
        "metric_unit": null,
        "deadline": "2026-11-01",
        "intensity": "comfortable",
        "allocation_minutes_week": 180,
        "status": "active",
        "version": 2
      },
      "progress": {
        "strategy": "consistency",
        "percentage": "50.0000",
        "components": {
          "planned_minutes": "720",
          "completed_minutes": "360",
          "denominator": "minutes"
        },
        "reason": null,
        "formula_version": "progress-v1",
        "forecast_date": null,
        "confidence": "medium"
      },
      "formula": {
        "strategy": "consistency",
        "label": "Регулярность",
        "explanation": "Фактические минуты относительно запланированных минут."
      },
      "milestones": [],
      "current_program": {
        "id": "f6889c40-a14e-4f73-a26a-cfa48f7609b4",
        "name": "Базовый цикл",
        "status": "active",
        "minimum_minutes_week": 90,
        "comfortable_minutes_week": 180,
        "maximum_minutes_week": 240,
        "version": 1
      },
      "current_phase": {
        "id": "28c2f6e1-ae78-4197-aef1-5fb0c3156da2",
        "title": "Основа",
        "position": 1,
        "status": "active",
        "start_date": "2026-08-01",
        "end_date": "2026-09-01"
      },
      "next_step": {
        "commitment_id": "28d09d72-c3d8-4188-8078-fc7800b89599",
        "title": "Лёгкий бег",
        "target_minutes_week": 120,
        "target_sessions_week": 3,
        "minimum_block_minutes": 30,
        "allowed_weekdays": [1, 3, 5],
        "preferred_window": "evening"
      },
      "recent_evidence": []
    }
  ]
}
```

Rules:

- `progress.percentage` is nullable and is never derived from task count;
- absence of a persisted snapshot returns `percentage=null` and `reason="not_calculated"` without a hidden mutation;
- `formula` explains the persisted strategy and does not control machine behavior;
- only the latest persisted progress snapshot is returned;
- `recent_evidence` contains at most three factual summaries;
- evidence `note`, `attributes`, request id, capture text, and other sensitive payloads are not selected for this read model;
- no N+1 query is allowed as the number of returned goals changes.

## 3. Goal Details

### `GET /api/v2/goals/{public_id}`

Returns the same authoritative `GoalPathResponse` used by Path for one owned goal, including paused or completed goals. A missing goal and another user's goal both return:

```json
{"detail": "Goal not found"}
```

with HTTP `404`.

The response contains ordered milestones, the current active program, current phase, next active weekly commitment, latest progress snapshot, formula explanation, and three recent evidence summaries. It does not create snapshots or program rows.

## 4. Evidence history

### `GET /api/v2/goals/{public_id}/evidence`

Query parameters:

- `limit`: `1…50`, default `20`;
- `cursor`: opaque cursor returned by the previous page.

```json
{
  "items": [
    {
      "id": "6840cf59-a92b-49f7-9121-bb539c611c90",
      "evidence_type": "partial",
      "quantity": "30.0000",
      "unit": "minutes",
      "occurred_at": "2026-08-11T18:30:00Z"
    }
  ],
  "next_cursor": null
}
```

Ordering is newest first by `(occurred_at, id)`. The cursor is an opaque keyset position, not an offset and not an ownership token. Invalid cursors return HTTP `400` with `detail="invalid_cursor"`. Ownership is checked independently on every page.

Notes and arbitrary evidence attributes are intentionally absent. A future explicit sensitive-detail endpoint requires separate product and privacy review.

## 5. Goal and evidence mutations

Existing `/api/v2/goals` mutations remain authoritative:

- create, update, pause, resume, and confirmed deletion;
- program preview and confirmed apply;
- factual evidence and metric observations;
- confirmed milestone completion.

Every mutation is user-scoped, idempotent by request id, and returns the authoritative goal plus recalculated progress. Risky deadline, intensity, program, and deletion changes require explicit confirmation and optimistic version checks.

## 6. Calendar read models

Authenticated calendar reads are available at:

- `GET /api/v2/calendar/day?date=YYYY-MM-DD`;
- `GET /api/v2/calendar/week?start=YYYY-MM-DD`, where `start` is Monday;
- `GET /api/v2/calendar/month?month=YYYY-MM-01`.

Day returns the persisted `DayPlan` and ordered items, privacy-safe busy intervals, and free intervals within the planner horizon (`06:00` through the user's sleep time or `23:00`). An unmaterialized day is explicit (`materialized=false`, `plan_version=null`) and a GET never creates a plan. Week always returns seven owned day summaries plus factual active-commitment load. Month returns only high-level completed milestones, goal deadlines, temporary life modes, control measurements, and aggregate tension; task titles, capture text, calendar identifiers, measurement notes, life-mode constraints, and other sensitive details are excluded.

Each response includes a stable opaque `cursor` and matching `ETag`. Repeated reads do not update plan versions, materialize rows, or update session telemetry. All instants are UTC while `timezone` identifies the user's interpretation zone.

## 7. Compatibility

- `/api/v1` is preserved for the current local dogfood Today/Capture flow;
- `/api/v2` uses production sessions and never accepts the shared dogfood token as identity;
- v1 and v2 models coexist during migration; no existing v1 field is removed or reinterpreted;
- the iOS Path screen must consume `/api/v2/path` and must not derive percentages, forecast, current phase, or next step locally;
- a cached Path response may be shown offline with its cached-state label, but it cannot be presented as a fresh server result.

## 8. Errors

Common responses:

- `400 invalid_cursor` — malformed evidence cursor;
- `401 Invalid authentication credentials` — invalid production session;
- `404 Goal not found` — missing or unowned goal;
- `422` — invalid query bounds or response/request schema;
- `409` — stale mutation version, missing confirmation, active-goal cap, or idempotency conflict.

Error text is presentation-neutral. Client behavior depends on HTTP status and typed `detail`, never on localized copy.
