from datetime import datetime, time, timezone
from uuid import UUID

from sqlalchemy import func, select

from app.models.calendar import CalendarBusyBlock, TemporaryLifeMode
from app.models.task import Task
from app.models.user import User
from tests.test_api_v2_auth import api, bearer, begin_apple_sign_in


def test_production_planner_requires_session_authentication(api) -> None:
    client, _factory = api

    assert client.get("/api/v2/today").status_code == 401
    assert client.post(
        "/api/v2/capture",
        json={"request_id": "no-auth", "text": "Добавить задачу"},
    ).status_code == 401
    assert client.patch(
        "/api/v2/tasks/1/status", json={"status": "done"}
    ).status_code == 401
    assert client.post(
        "/api/v2/planning/replan",
        json={
            "request_id": "no-auth-replan",
            "reason": "manual",
            "affected_dates": ["2026-08-11"],
            "base_versions": {"2026-08-11": 0},
        },
    ).status_code == 401


def test_production_capture_is_session_scoped_without_external_identity(api) -> None:
    client, factory = api
    owner = begin_apple_sign_in(
        client, identity_token="valid-identity-token-planner-owner"
    )
    other = begin_apple_sign_in(
        client, identity_token="valid-identity-token-planner-other"
    )
    request = {
        "request_id": "production-capture-1",
        "text": "Сегодня хочу оплатить счета",
    }

    first = client.post(
        "/api/v2/capture",
        headers=bearer(owner["access_token"]),
        json=request,
    )
    retry = client.post(
        "/api/v2/capture",
        headers=bearer(owner["access_token"]),
        json=request,
    )
    hidden = client.get(
        "/api/v2/today", headers=bearer(other["access_token"])
    )

    assert first.status_code == retry.status_code == 200, first.text
    assert retry.json() == first.json()
    assert len(first.json()["day_snapshot"]["tasks"]) == 1
    assert first.json()["day_snapshot"]["week_progress"] == {
        "done": 0,
        "total": 1,
    }
    as_of = datetime.fromisoformat(
        first.json()["day_snapshot"]["as_of"].replace("Z", "+00:00")
    )
    assert as_of.utcoffset() is not None
    assert hidden.status_code == 200
    assert hidden.json()["tasks"] == []
    assert "user_external_id" not in first.text
    with factory() as db:
        users = list(db.scalars(select(User).order_by(User.id)).all())
        assert len(users) == 2
        assert all(user.external_id is None for user in users)
        assert db.scalar(select(func.count(Task.id))) == 1


def test_production_capture_rejects_request_id_reuse_with_different_text(api) -> None:
    client, factory = api
    owner = begin_apple_sign_in(
        client, identity_token="valid-identity-token-planner-idempotency"
    )
    headers = bearer(owner["access_token"])

    first = client.post(
        "/api/v2/capture",
        headers=headers,
        json={"request_id": "capture-reused-key", "text": "Сегодня оплатить счета"},
    )
    conflict = client.post(
        "/api/v2/capture",
        headers=headers,
        json={"request_id": "capture-reused-key", "text": "Сегодня купить продукты"},
    )

    assert first.status_code == 200, first.text
    assert conflict.status_code == 409
    assert conflict.json() == {"detail": "idempotency_conflict"}
    with factory() as db:
        assert db.scalar(select(func.count(Task.id))) == 1


def test_production_capture_respects_persisted_calendar_and_mode_constraints(api) -> None:
    client, factory = api
    owner = begin_apple_sign_in(
        client, identity_token="valid-identity-token-planner-constraints"
    )
    headers = bearer(owner["access_token"])
    today = datetime.now(timezone.utc).date()
    with factory() as db:
        user = db.scalar(
            select(User).where(User.public_id == UUID(owner["user"]["public_id"]))
        )
        assert user is not None
        db.add(
            CalendarBusyBlock(
                user_id=user.id,
                device_id="constraints-iphone",
                provider="apple",
                calendar_external_id="work",
                external_id="busy-morning",
                occurrence_external_id="busy-morning-1",
                occurrence_start=datetime.combine(today, time(6), tzinfo=timezone.utc),
                occurrence_end=datetime.combine(today, time(12), tzinfo=timezone.utc),
                device_timezone="UTC",
                source_revision="1",
                last_seen_client_revision=1,
            )
        )
        db.add(
            TemporaryLifeMode(
                user_id=user.id,
                request_id="constraints-mode",
                mode="recovery",
                starts_at=datetime.combine(today, time(12), tzinfo=timezone.utc),
                ends_at=datetime.combine(today, time(23), tzinfo=timezone.utc),
                status="active",
                constraints={"max_flexible_minutes": 0},
            )
        )
        db.commit()

    response = client.post(
        "/api/v2/capture",
        headers=headers,
        json={
            "request_id": "capture-under-persisted-constraints",
            "text": "Сегодня хочу оплатить счета",
        },
    )

    assert response.status_code == 200, response.text
    snapshot = response.json()["day_snapshot"]
    assert snapshot["scheduled_items"] == []
    assert len(snapshot["unscheduled_items"]) == 1
    assert snapshot["unscheduled_items"][0]["unscheduled_reason"] in {
        "capacity_limit",
        "no_available_slot",
    }


def test_production_clarification_continues_for_same_session(api) -> None:
    client, _factory = api
    owner = begin_apple_sign_in(
        client, identity_token="valid-identity-token-planner-clarification"
    )
    headers = bearer(owner["access_token"])

    first = client.post(
        "/api/v2/capture",
        headers=headers,
        json={
            "request_id": "production-clarification-1",
            "text": "добавь бжу чтобы я считал",
        },
    )

    assert first.status_code == 200, first.text
    clarification = first.json()["clarification"]
    assert first.json()["status"] == "clarification_required"
    assert first.json()["day_snapshot"]["tasks"] == []

    second = client.post(
        f"/api/v2/interactions/{clarification['id']}/responses",
        headers=headers,
        json={
            "request_id": "production-clarification-2",
            "option_id": "one_time",
            "text": "разовая задача",
        },
    )

    assert second.status_code == 200, second.text
    assert second.json()["status"] == "applied"
    assert [
        item["title"] for item in second.json()["day_snapshot"]["tasks"]
    ] == ["Записать БЖУ"]


def test_production_task_mutation_returns_authoritative_owned_snapshot(api) -> None:
    client, factory = api
    owner = begin_apple_sign_in(
        client, identity_token="valid-identity-token-planner-task-owner"
    )
    other = begin_apple_sign_in(
        client, identity_token="valid-identity-token-planner-task-other"
    )
    created = client.post(
        "/api/v2/capture",
        headers=bearer(owner["access_token"]),
        json={
            "request_id": "production-task-1",
            "text": "Сегодня хочу оплатить счета",
        },
    )
    assert created.status_code == 200, created.text
    task_id = created.json()["day_snapshot"]["tasks"][0]["id"]
    base_version = created.json()["day_snapshot"]["plan_version"]
    owner_payload = {
        "status": "done",
        "request_id": "production-task-status-1",
        "expected_plan_version": base_version,
    }

    hidden = client.patch(
        f"/api/v2/tasks/{task_id}/status",
        headers=bearer(other["access_token"]),
        json={
            "status": "done",
            "request_id": "production-task-hidden",
            "expected_plan_version": base_version,
        },
    )
    applied = client.patch(
        f"/api/v2/tasks/{task_id}/status",
        headers=bearer(owner["access_token"]),
        json=owner_payload,
    )
    replayed = client.patch(
        f"/api/v2/tasks/{task_id}/status",
        headers=bearer(owner["access_token"]),
        json=owner_payload,
    )
    reused_key = client.patch(
        f"/api/v2/tasks/{task_id}/status",
        headers=bearer(owner["access_token"]),
        json={**owner_payload, "status": "planned"},
    )
    stale_reopen = client.patch(
        f"/api/v2/tasks/{task_id}/status",
        headers=bearer(owner["access_token"]),
        json={
            "status": "planned",
            "request_id": "production-task-stale-reopen",
            "expected_plan_version": base_version,
        },
    )

    assert hidden.status_code == 404
    assert hidden.json() == {"detail": "Task not found"}
    assert applied.status_code == 200, applied.text
    assert replayed.json() == applied.json()
    assert reused_key.status_code == 409
    assert reused_key.json() == {"detail": "idempotency_conflict"}
    assert stale_reopen.status_code == 409
    assert stale_reopen.json() == {"detail": "stale_plan_version"}
    assert applied.json()["task"]["status"] == "done"
    assert applied.json()["day_snapshot"]["progress"] == {"done": 1, "total": 1}
    assert applied.json()["day_snapshot"]["week_progress"] == {
        "done": 1,
        "total": 1,
    }
    with factory() as db:
        owner_user = db.scalar(
            select(User).where(
                User.public_id == UUID(owner["user"]["public_id"])
            )
        )
        assert owner_user is not None
        assert db.scalar(
            select(Task.status).where(
                Task.id == task_id,
                Task.user_id == owner_user.id,
            )
        ) == "done"


def test_production_task_mutation_requires_idempotency_and_version(api) -> None:
    client, _factory = api
    owner = begin_apple_sign_in(
        client, identity_token="valid-identity-token-planner-task-contract"
    )

    response = client.patch(
        "/api/v2/tasks/1/status",
        headers=bearer(owner["access_token"]),
        json={"status": "done"},
    )

    assert response.status_code == 422
