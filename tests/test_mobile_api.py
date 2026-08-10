from collections.abc import Generator
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

import app.models  # noqa: F401
import app.services.message_service as message_service
import app.services.planning_service as planning_service
from app.core.config import settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.day_plan import DayPlan
from app.schemas.api import MessageResponse
from app.services.idempotency_service import ReceiptReservation
from app.services.mobile_service import message_to_mobile_response


TEST_TOKEN = "test-mobile-dogfood-token"
AUTH_HEADERS = {"Authorization": f"Bearer {TEST_TOKEN}"}


@pytest.fixture()
def client(tmp_path: Path, monkeypatch) -> Generator[TestClient, None, None]:
    monkeypatch.setattr(settings, "llm_enabled", False)
    monkeypatch.setattr(settings, "llm_provider", "mock")
    monkeypatch.setattr(settings, "llm_api_key", None)

    if hasattr(settings, "mobile_dogfood_token"):
        monkeypatch.setattr(settings, "mobile_dogfood_token", TEST_TOKEN)

    database_path = tmp_path / "mobile-api-test.db"
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )
    testing_session_local = sessionmaker(
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
        bind=engine,
    )
    Base.metadata.create_all(bind=engine)

    def override_get_db() -> Generator[Session, None, None]:
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def db_session(client: TestClient) -> Generator[Session, None, None]:
    dependency = app.dependency_overrides[get_db]()
    db = next(dependency)

    try:
        yield db
    finally:
        dependency.close()


def test_mobile_api_requires_bearer_token(client: TestClient):
    response = client.get("/api/v1/today")

    assert response.status_code == 401


def test_mobile_api_rejects_wrong_bearer_token(client: TestClient):
    response = client.get(
        "/api/v1/today",
        headers={"Authorization": "Bearer wrong"},
    )

    assert response.status_code == 401


def test_mobile_api_reports_missing_server_token(client: TestClient, monkeypatch):
    if hasattr(settings, "mobile_dogfood_token"):
        monkeypatch.setattr(settings, "mobile_dogfood_token", None)

    response = client.get("/api/v1/today", headers=AUTH_HEADERS)

    assert response.status_code == 503


def test_mobile_today_returns_complete_snapshot(client: TestClient):
    response = client.get("/api/v1/today", headers=AUTH_HEADERS)

    assert response.status_code == 200
    payload = response.json()
    assert {
        "date",
        "focus_text",
        "progress",
        "scheduled_items",
        "unscheduled_items",
        "completed_items",
        "current_item",
        "day_context",
        "plan_version",
    } <= payload.keys()
    assert payload["progress"] == {"done": 0, "total": 0}
    assert payload["completed_items"] == []
    assert payload["current_item"] is None


def test_mobile_today_read_does_not_persist_empty_plan(
    client: TestClient,
    db_session: Session,
):
    response = client.get("/api/v1/today", headers=AUTH_HEADERS)

    assert response.status_code == 200
    assert response.json()["plan"]["id"] == 0
    assert response.json()["plan_version"] == 0
    assert db_session.query(DayPlan).count() == 0


def test_mobile_today_refresh_preserves_authoritative_plan(client: TestClient, monkeypatch):
    current_date = datetime.now(timezone.utc).date()
    initial_now = datetime.combine(
        current_date,
        datetime.strptime("07:00", "%H:%M").time(),
        tzinfo=timezone.utc,
    )
    later_now = datetime.combine(
        current_date,
        datetime.strptime("22:00", "%H:%M").time(),
        tzinfo=timezone.utc,
    )
    monkeypatch.setattr(planning_service, "get_user_now", lambda user, now=None: initial_now)

    created = client.post(
        "/api/v1/capture",
        headers=AUTH_HEADERS,
        json={
            "request_id": "today-read-safe-1",
            "text": "Сегодня хочу оплатить счета",
        },
    )

    assert created.status_code == 200
    authoritative = created.json()["day_snapshot"]
    authoritative_placements = [
        (
            item["task_id"],
            item["status"],
            item["start_time"],
            item["end_time"],
        )
        for item in authoritative["plan"]["items"]
    ]
    monkeypatch.setattr(planning_service, "get_user_now", lambda user, now=None: later_now)

    first_refresh = client.get("/api/v1/today", headers=AUTH_HEADERS)
    second_refresh = client.get("/api/v1/today", headers=AUTH_HEADERS)

    assert first_refresh.status_code == second_refresh.status_code == 200

    for refreshed in (first_refresh.json(), second_refresh.json()):
        placements = [
            (
                item["task_id"],
                item["status"],
                item["start_time"],
                item["end_time"],
            )
            for item in refreshed["plan"]["items"]
        ]
        assert refreshed["plan_version"] == authoritative["plan_version"]
        assert placements == authoritative_placements


def test_mobile_retryable_uses_typed_request_in_progress_reason(client: TestClient):
    snapshot = client.get("/api/v1/today", headers=AUTH_HEADERS).json()
    response = MessageResponse(
        request_id="typed-in-progress-1",
        user_external_id="mobile:dogfood",
        source="ios_text",
        intent="show_plan",
        parsed={},
        status="no_change",
        reason="request_in_progress",
        reply_text="Обработка продолжается.",
        day_snapshot=snapshot,
    )

    mobile_response = message_to_mobile_response(response)

    assert mobile_response.retryable is True
    assert mobile_response.reason == "request_in_progress"


def test_mobile_in_progress_request_exposes_typed_reason(
    client: TestClient,
    monkeypatch,
):
    monkeypatch.setattr(
        message_service,
        "reserve_message_request",
        lambda *args, **kwargs: ReceiptReservation(processing=True),
    )

    response = client.post(
        "/api/v1/capture",
        headers=AUTH_HEADERS,
        json={
            "request_id": "typed-in-progress-2",
            "text": "Сегодня хочу оплатить счета",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "no_change"
    assert response.json()["reason"] == "request_in_progress"
    assert response.json()["retryable"] is True


def test_mobile_capture_cannot_select_user_identity(client: TestClient):
    response = client.post(
        "/api/v1/capture",
        headers=AUTH_HEADERS,
        json={
            "request_id": "identity-1",
            "text": "Сегодня хочу оплатить счета",
            "user_external_id": "somebody-else",
        },
    )

    assert response.status_code == 422


def test_mobile_capture_returns_atomic_availability_result(client: TestClient):
    response = client.post(
        "/api/v1/capture",
        headers=AUTH_HEADERS,
        json={
            "request_id": "availability-1",
            "text": "Сегодня задержусь на работе до 20",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "applied"
    assert payload["plan_diff"]["availability_change"]
    assert payload["day_snapshot"]["day_context"]["work_override_mode"] == "busy"
    assert payload["day_snapshot"]["day_context"]["work_end_time"] == "20:00:00"
    assert "user_external_id" not in payload
    assert "parsed" not in payload


def test_mobile_capture_request_id_is_idempotent(client: TestClient):
    body = {
        "request_id": "same-mobile-request",
        "text": "Сегодня хочу позвонить врачу",
    }

    first = client.post("/api/v1/capture", headers=AUTH_HEADERS, json=body)
    second = client.post("/api/v1/capture", headers=AUTH_HEADERS, json=body)

    assert first.status_code == second.status_code == 200
    assert second.json() == first.json()
    assert len(first.json()["day_snapshot"]["tasks"]) == 1


def test_frozen_api_cannot_read_or_mutate_mobile_identity(client: TestClient):
    created = client.post(
        "/api/v1/capture",
        headers=AUTH_HEADERS,
        json={
            "request_id": "compatibility-bypass-1",
            "text": "Сегодня хочу оплатить счета",
        },
    ).json()
    task_id = created["day_snapshot"]["tasks"][0]["id"]

    read_response = client.get("/api/tasks/mobile:dogfood")
    mutation_response = client.patch(
        f"/api/tasks/{task_id}/status",
        json={"user_external_id": "mobile:dogfood", "status": "done"},
    )
    capture_response = client.post(
        "/api/message",
        json={
            "user_external_id": "mobile:dogfood",
            "request_id": "compatibility-bypass-2",
            "text": "Сегодня хочу купить продукты",
        },
    )

    assert read_response.status_code == 404
    assert mutation_response.status_code == 404
    assert capture_response.status_code == 404
    assert mutation_response.json() == {"detail": "User not found"}


def test_mobile_clarification_creates_nothing_until_response(client: TestClient):
    first = client.post(
        "/api/v1/capture",
        headers=AUTH_HEADERS,
        json={
            "request_id": "clarification-1",
            "text": "добавь бжу чтобы я считал",
        },
    )

    assert first.status_code == 200
    first_payload = first.json()
    clarification = first_payload["clarification"]
    assert first_payload["status"] == "clarification_required"
    assert first_payload["day_snapshot"]["tasks"] == []
    assert clarification["free_text_allowed"] is True
    assert {option["id"] for option in clarification["options"]} == {
        "routine",
        "one_time",
        "capability",
    }

    second = client.post(
        f"/api/v1/interactions/{clarification['id']}/responses",
        headers=AUTH_HEADERS,
        json={
            "request_id": "clarification-2",
            "option_id": "one_time",
            "text": "разовая задача",
        },
    )

    assert second.status_code == 200
    payload = second.json()
    assert payload["status"] == "applied"
    assert [task["title"] for task in payload["day_snapshot"]["tasks"]] == [
        "Записать БЖУ"
    ]


def test_mobile_confirmation_uses_explicit_interaction_response(client: TestClient):
    proposal = client.post(
        "/api/v1/capture",
        headers=AUTH_HEADERS,
        json={
            "request_id": "confirmation-1",
            "text": "По будням работаю с 9 до 18",
        },
    )

    assert proposal.status_code == 200
    proposal_payload = proposal.json()
    confirmation = proposal_payload["confirmation"]
    assert proposal_payload["status"] == "confirmation_required"
    assert {option["id"] for option in confirmation["options"]} == {"apply", "cancel"}

    applied = client.post(
        f"/api/v1/interactions/{confirmation['id']}/responses",
        headers=AUTH_HEADERS,
        json={
            "request_id": "confirmation-2",
            "option_id": "apply",
            "text": "применить",
        },
    )

    assert applied.status_code == 200
    assert applied.json()["status"] == "applied"
    assert applied.json()["day_snapshot"]["day_context"]["work_end_time"] == "18:00:00"


def test_mobile_fixed_conflict_is_structured(client: TestClient):
    first = client.post(
        "/api/v1/capture",
        headers=AUTH_HEADERS,
        json={
            "request_id": "conflict-1",
            "text": "Завтра в 19:00 теннис на час",
        },
    )
    conflict = client.post(
        "/api/v1/capture",
        headers=AUTH_HEADERS,
        json={
            "request_id": "conflict-2",
            "text": "Завтра в 19:00 созвон на час",
        },
    )

    assert first.status_code == conflict.status_code == 200
    payload = conflict.json()
    assert payload["status"] == "conflict"
    assert payload["plan_diff"]["conflict"]
    assert payload["conflict"]["id"]
    assert {option["id"] for option in payload["conflict"]["options"]} == {
        "choose_time",
        "cancel",
    }


def test_mobile_task_status_returns_snapshot_and_factual_diff(client: TestClient):
    created = client.post(
        "/api/v1/capture",
        headers=AUTH_HEADERS,
        json={
            "request_id": "complete-1",
            "text": "Сегодня хочу оплатить счета",
        },
    ).json()
    task_id = created["day_snapshot"]["tasks"][0]["id"]

    response = client.patch(
        f"/api/v1/tasks/{task_id}/status",
        headers=AUTH_HEADERS,
        json={"status": "done"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "applied"
    assert payload["task"]["status"] == "done"
    assert payload["plan_diff"]["completed_task_ids"] == [task_id]
    assert payload["day_snapshot"]["progress"] == {"done": 1, "total": 1}
    assert [item["task_id"] for item in payload["day_snapshot"]["completed_items"]] == [
        task_id
    ]


def test_mobile_task_status_cannot_mutate_another_user(client: TestClient):
    foreign = client.post(
        "/api/message",
        json={
            "user_external_id": "foreign-user",
            "request_id": "foreign-task-1",
            "text": "Сегодня хочу купить продукты",
        },
    ).json()
    task_id = foreign["affected_tasks"][0]["id"]

    response = client.patch(
        f"/api/v1/tasks/{task_id}/status",
        headers=AUTH_HEADERS,
        json={"status": "done"},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Task not found"}


def test_mobile_task_status_cannot_resurrect_cancelled_task(client: TestClient):
    created = client.post(
        "/api/v1/capture",
        headers=AUTH_HEADERS,
        json={
            "request_id": "cancelled-task-1",
            "text": "Сегодня хочу купить продукты",
        },
    ).json()
    task_id = created["day_snapshot"]["tasks"][0]["id"]
    cancelled = client.post(
        "/api/v1/capture",
        headers=AUTH_HEADERS,
        json={
            "request_id": "cancelled-task-2",
            "text": "Купить продукты отменяется",
        },
    )

    assert cancelled.status_code == 200
    assert cancelled.json()["plan_diff"]["cancelled_task_ids"] == [task_id]

    response = client.patch(
        f"/api/v1/tasks/{task_id}/status",
        headers=AUTH_HEADERS,
        json={"status": "planned"},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Task not found"}


def test_mobile_interaction_is_user_scoped(client: TestClient):
    foreign = client.post(
        "/api/message",
        json={
            "user_external_id": "foreign-interaction-user",
            "request_id": "foreign-interaction-1",
            "text": "добавь бжу чтобы я считал",
        },
    ).json()

    response = client.post(
        f"/api/v1/interactions/{foreign['clarification']['id']}/responses",
        headers=AUTH_HEADERS,
        json={
            "request_id": "foreign-interaction-2",
            "option_id": "one_time",
            "text": "разовая задача",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "no_change"
    assert response.json()["day_snapshot"]["tasks"] == []


def test_mobile_today_identifies_current_item_from_backend(
    client: TestClient,
    monkeypatch,
):
    current_date = datetime.now(timezone.utc).date()
    planning_now = datetime.combine(
        current_date,
        datetime.strptime("11:00", "%H:%M").time(),
        tzinfo=timezone.utc,
    )
    snapshot_now = datetime.combine(
        current_date,
        datetime.strptime("12:30", "%H:%M").time(),
        tzinfo=timezone.utc,
    )
    monkeypatch.setattr(planning_service, "get_user_now", lambda user, now=None: planning_now)
    monkeypatch.setattr(
        message_service,
        "get_user_now",
        lambda user, now=None: snapshot_now,
        raising=False,
    )

    created = client.post(
        "/api/v1/capture",
        headers=AUTH_HEADERS,
        json={
            "request_id": "current-item-1",
            "text": "Сегодня в 12:00 тестовый созвон на час",
        },
    )

    assert created.status_code == 200
    snapshot = client.get("/api/v1/today", headers=AUTH_HEADERS).json()
    assert snapshot["current_item"]["title"] == "Тестовый созвон"
    assert snapshot["current_item"]["start_time"] == "12:00:00"
    assert snapshot["current_item"]["end_time"] == "13:00:00"
