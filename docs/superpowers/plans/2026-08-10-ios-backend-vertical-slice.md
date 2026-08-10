# iOS Backend Vertical Slice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose the existing AI Life Planner backend as a secure, atomic mobile API for the first iOS dogfooding vertical slice.

**Architecture:** A new `/api/v1` router authenticates one local dogfood identity with a server-configured bearer token and delegates all interpretation, clarification, confirmation, planning, and persistence to the existing service layer. Mobile mutations return a factual diff and a complete `DaySnapshot`; no parser or scheduler logic moves into the client or the API layer.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy, PostgreSQL, Alembic, pytest.

## Global Constraints

- iOS-first. Android later. Web/Telegram frozen. Backend is the single product brain.
- Do not create a mobile UI, React Native project, STT implementation, calendar API, or fake goal progress.
- Preserve the existing Web and Telegram code paths without extending their product scope.
- Do not duplicate parser, scheduler, clarification, confirmation, conflict, or planning logic.
- Stop before commit and show the API contract, changed files, migrations, tests, and Mobile Agent handoff.

---

## File Structure

- Create `app/api/mobile.py`: authenticated `/api/v1` HTTP endpoints only.
- Create `app/schemas/mobile.py`: mobile request and atomic response contracts.
- Create `app/services/mobile_service.py`: response projection and task-status mutation orchestration.
- Modify `app/core/config.py`: local dogfood token and server-owned identity settings.
- Modify `app/main.py`: register the mobile router.
- Modify `app/schemas/api.py`: add iOS message source and explicit completed/current snapshot fields.
- Modify `app/services/message_service.py`: derive completed/current items from persisted plan state.
- Create `tests/test_mobile_api.py`: auth, vertical slice, clarification, atomic completion, and isolation coverage.
- Create `docs/07 Техническая документация/Mobile API Contract v1.md`: canonical mobile contract and audit.
- Modify product, roadmap, decision, security, README, and `AGENTS.md` documents to record the iOS-first freeze.

### Task 1: Mobile Contract Tests

**Files:**
- Create: `tests/test_mobile_api.py`

**Interfaces:**
- Consumes: existing `app.main.app`, `app.db.session.get_db`, and SQLAlchemy models.
- Produces: executable expectations for bearer authentication and `/api/v1` contracts.

- [x] **Step 1: Write the failing auth tests**

```python
def test_mobile_api_requires_configured_bearer_token(client):
    assert client.get("/api/v1/today").status_code == 401

def test_mobile_api_rejects_wrong_bearer_token(client):
    response = client.get(
        "/api/v1/today",
        headers={"Authorization": "Bearer wrong"},
    )
    assert response.status_code == 401
```

- [x] **Step 2: Write the failing vertical-slice tests**

```python
def test_mobile_capture_returns_atomic_applied_result(client, auth_headers):
    response = client.post(
        "/api/v1/capture",
        headers=auth_headers,
        json={
            "request_id": "capture-1",
            "text": "Сегодня задержусь на работе до 20",
        },
    )
    payload = response.json()
    assert payload["status"] == "applied"
    assert payload["plan_diff"]["availability_change"]
    assert payload["day_snapshot"]["day_context"]["work_end_time"] == "20:00:00"
```

```python
def test_mobile_clarification_creates_nothing_until_response(client, auth_headers):
    first = client.post(
        "/api/v1/capture",
        headers=auth_headers,
        json={"request_id": "clarify-1", "text": "добавь бжу чтобы я считал"},
    ).json()
    assert first["status"] == "clarification_required"
    assert first["day_snapshot"]["tasks"] == []

    applied = client.post(
        f"/api/v1/interactions/{first['clarification']['id']}/responses",
        headers=auth_headers,
        json={"request_id": "clarify-2", "option_id": "one_time", "text": "разовая задача"},
    ).json()
    assert applied["status"] == "applied"
    assert [task["title"] for task in applied["day_snapshot"]["tasks"]] == ["Записать БЖУ"]
```

```python
def test_mobile_task_status_returns_snapshot_and_diff(client, auth_headers):
    created = client.post(
        "/api/v1/capture",
        headers=auth_headers,
        json={"request_id": "task-1", "text": "Сегодня хочу оплатить счета"},
    ).json()
    task_id = created["day_snapshot"]["tasks"][0]["id"]
    completed = client.patch(
        f"/api/v1/tasks/{task_id}/status",
        headers=auth_headers,
        json={"status": "done"},
    ).json()
    assert completed["task"]["status"] == "done"
    assert completed["plan_diff"]["completed_task_ids"] == [task_id]
    assert completed["day_snapshot"]["completed_items"][0]["task_id"] == task_id
```

- [x] **Step 3: Run tests and verify RED**

Run: `pytest tests/test_mobile_api.py -q`

Expected: failures because `/api/v1` routes do not exist.

### Task 2: Dogfood Authentication Boundary

**Files:**
- Modify: `app/core/config.py`
- Create: `app/api/mobile.py`
- Modify: `.env.example`

**Interfaces:**
- Consumes: `Authorization: Bearer <token>`.
- Produces: `get_mobile_user(db, credentials) -> User`, mapped to the server-owned `mobile_dogfood_user_external_id`.

- [x] **Step 1: Add safe settings**

```python
mobile_dogfood_token: str | None = None
mobile_dogfood_user_external_id: str = "mobile:dogfood"
```

- [x] **Step 2: Implement strict bearer verification**

Use `HTTPBearer(auto_error=False)` and `secrets.compare_digest`. Return `401` for missing/invalid credentials and `503` when the server has no dogfood token configured. Never accept a user id from the mobile request.

- [x] **Step 3: Run auth tests and verify GREEN**

Run: `pytest tests/test_mobile_api.py -q`

Expected: auth tests pass; vertical-slice tests still fail on missing routes/contracts.

### Task 3: Atomic Mobile Capture And Interaction Responses

**Files:**
- Create: `app/schemas/mobile.py`
- Create: `app/services/mobile_service.py`
- Modify: `app/api/mobile.py`
- Modify: `app/main.py`
- Modify: `app/schemas/api.py`

**Interfaces:**
- Produces `MobileCaptureRequest(text: str, request_id: str)`.
- Produces `MobileInteractionResponseRequest(text: str, request_id: str, option_id: str | None)`.
- Produces `MobileActionResponse(request_id, status, reply_text, retryable, plan_diff, clarification, confirmation, conflict, day_snapshot)`.
- Delegates to `process_user_message(..., source="ios_text")` exactly once.

- [x] **Step 1: Add `ios_text` and `ios_voice_transcript` sources**

- [x] **Step 2: Project the internal message response into the mobile contract**

Exclude `user_external_id`, raw parsed payload, and Web/Telegram-specific fields from the mobile response.

- [x] **Step 3: Implement `/capture` and interaction response routes**

The interaction route passes its path id as `interaction_id` into the same message pipeline. Option and free-text answers use the existing persistent interaction context.

- [x] **Step 4: Run capture and clarification tests and verify GREEN**

Run: `pytest tests/test_mobile_api.py -q`

### Task 4: Complete Today Snapshot And Task Mutation

**Files:**
- Modify: `app/schemas/api.py`
- Modify: `app/services/message_service.py`
- Modify: `app/services/mobile_service.py`
- Modify: `app/api/mobile.py`
- Test: `tests/test_mobile_api.py`

**Interfaces:**
- Extends `DaySnapshotResponse` with `completed_items: list[PlanItemResponse]` and `current_item: PlanItemResponse | None`.
- Produces `MobileTaskMutationResponse(task, plan_diff, day_snapshot)`.

- [x] **Step 1: Add failing snapshot semantics test**

The completed list contains persisted done items. `current_item` is only a planned scheduled item whose interval contains current user-local time; it is otherwise `null`.

- [x] **Step 2: Derive fields in `day_snapshot_to_response()`**

Use `get_user_now(user)` and persisted `PlanItem` times. Do not infer current work in the mobile client.

- [x] **Step 3: Implement atomic task status mutation**

Resolve the authenticated user, call `set_task_status(..., commit=False)`, rebuild that task's day, commit, and return task + factual status diff + the rebuilt snapshot. A foreign or missing task returns the same `404`.

- [x] **Step 4: Run completion and isolation tests and verify GREEN**

Run: `pytest tests/test_mobile_api.py -q`

### Task 5: Product And Architecture Documentation

**Files:**
- Modify: `AGENTS.md`
- Modify: `README.md`
- Modify: `docs/00 Главная.md`
- Modify: `docs/01 Продукт/Видение продукта.md`
- Modify: `docs/01 Продукт/Принципы продукта.md`
- Modify: `docs/02 Дорожная карта/Сейчас — далее — позже.md`
- Modify: `docs/03 Решения/Журнал решений.md`
- Modify: `docs/07 Техническая документация/Базовая безопасность.md`
- Create: `docs/07 Техническая документация/Mobile API Contract v1.md`

**Interfaces:**
- Produces the canonical statement: `iOS-first. Android later. Web/Telegram frozen. Backend is the single product brain.`

- [x] **Step 1: Record the product decision and freeze**

- [x] **Step 2: Document implemented P0 endpoints and response examples**

- [x] **Step 3: Document deferred Week, Path, Profile, Voice, Undo, TestFlight auth, latency, and migration gaps without claiming they exist**

### Task 6: Verification And Pre-Commit Handoff

**Files:**
- No new files.

- [x] **Step 1: Run targeted API and isolation tests**

Run: `pytest tests/test_mobile_api.py tests/test_web_api.py -q`

- [x] **Step 2: Apply migrations**

Run: `alembic upgrade head`

- [x] **Step 3: Run repository checks**

Run: `python scripts/check_mvp.py`

Run: `python scripts/eval_parser_cases.py` only if interpretation logic changed.

Run: `python -c "from app.bot.main import dp; from app.main import app; print('bot and app import ok')"`

Run: `pytest -q`

- [x] **Step 4: Inspect the complete diff and stop before commit**

Run: `git status --short`, `git diff --stat`, and `git diff`.

Report the API Contract v1, changed files, migrations, test evidence, residual gaps, and what the Mobile Agent can now implement. Do not commit until the user reviews this checkpoint.
