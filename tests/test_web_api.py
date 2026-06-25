from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

import app.models  # noqa: F401
from app.core.config import settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app


@pytest.fixture()
def client(tmp_path: Path, monkeypatch) -> Generator[TestClient, None, None]:
    monkeypatch.setattr(settings, "llm_enabled", False)
    monkeypatch.setattr(settings, "llm_provider", "mock")
    monkeypatch.setattr(settings, "llm_api_key", None)

    database_path = tmp_path / "api-test.db"
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )
    TestingSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
        bind=engine,
    )

    Base.metadata.create_all(bind=engine)

    def override_get_db() -> Generator[Session, None, None]:
        db = TestingSessionLocal()
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


def test_post_message_adds_task(client: TestClient):
    response = client.post(
        "/api/message",
        json={
            "user_external_id": "web-user-1",
            "source": "web_text",
            "text": "Сегодня хочу разобрать документы",
        },
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["user_external_id"] == "web-user-1"
    assert payload["source"] == "web_text"
    assert payload["intent"] == "add_tasks"
    assert payload["affected_tasks"][0]["title"] == "разобрать документы"
    assert payload["plan_summary"]["date"] == payload["affected_tasks"][0]["target_date"]
    assert "Принял" in payload["reply_text"]


def test_tasks_are_isolated_by_user(client: TestClient):
    client.post(
        "/api/message",
        json={
            "user_external_id": "user-a",
            "source": "web_text",
            "text": "Сегодня хочу оплатить счета",
        },
    )
    client.post(
        "/api/message",
        json={
            "user_external_id": "user-b",
            "source": "web_text",
            "text": "Сегодня хочу купить продукты",
        },
    )

    user_a_tasks = client.get("/api/tasks/user-a").json()
    user_b_tasks = client.get("/api/tasks/user-b").json()

    assert [task["title"] for task in user_a_tasks] == ["оплатить счета"]
    assert [task["title"] for task in user_b_tasks] == ["купить продукты"]


def test_done_endpoint_updates_task_and_keeps_user_isolation(client: TestClient):
    user_a_response = client.post(
        "/api/message",
        json={
            "user_external_id": "done-user-a",
            "source": "web_text",
            "text": "Сегодня хочу оплатить счета",
        },
    )
    user_b_response = client.post(
        "/api/message",
        json={
            "user_external_id": "done-user-b",
            "source": "web_text",
            "text": "Сегодня хочу купить продукты",
        },
    )

    user_a_task_id = user_a_response.json()["affected_tasks"][0]["id"]
    user_b_task_id = user_b_response.json()["affected_tasks"][0]["id"]

    forbidden_response = client.post(
        f"/api/tasks/{user_b_task_id}/done",
        json={"user_external_id": "done-user-a"},
    )
    done_response = client.post(
        f"/api/tasks/{user_a_task_id}/done",
        json={"user_external_id": "done-user-a"},
    )

    assert forbidden_response.status_code == 404
    assert done_response.status_code == 200
    assert done_response.json()["status"] == "done"

    user_a_tasks = client.get("/api/tasks/done-user-a").json()
    user_b_tasks = client.get("/api/tasks/done-user-b").json()
    user_a_plan = client.get("/api/plan/done-user-a?date=today").json()

    assert [(task["title"], task["status"]) for task in user_a_tasks] == [
        ("оплатить счета", "done")
    ]
    assert [(task["title"], task["status"]) for task in user_b_tasks] == [
        ("купить продукты", "planned")
    ]
    assert all(item["task_id"] != user_a_task_id for item in user_a_plan["items"])


def test_get_goals_returns_user_goals(client: TestClient):
    client.post(
        "/api/message",
        json={
            "user_external_id": "goal-user",
            "source": "web_text",
            "text": "Моя цель: накопить резерв, научиться рисовать",
        },
    )

    response = client.get("/api/goals/goal-user")

    assert response.status_code == 200
    titles = [goal["title"] for goal in response.json()]

    assert "накопить резерв" in titles
    assert "научиться рисовать" in titles


def test_get_plan_today_returns_plan_for_user_tasks(client: TestClient):
    client.post(
        "/api/message",
        json={
            "user_external_id": "plan-user",
            "source": "web_text",
            "text": "Сегодня хочу подготовиться к экзамену",
        },
    )

    response = client.get("/api/plan/plan-user?date=today")

    assert response.status_code == 200
    payload = response.json()

    assert payload["status"] in {"draft", "overloaded"}
    assert any(item["title"] == "подготовиться к экзамену" for item in payload["items"])


def test_profile_endpoint_returns_isolated_profile(client: TestClient):
    client.post(
        "/api/message",
        json={
            "user_external_id": "profile-a",
            "source": "web_text",
            "text": "Мой график с 9 до 18, хочу спать в 23:30",
        },
    )

    profile_a = client.get("/api/profile/profile-a").json()
    profile_b = client.get("/api/profile/profile-b").json()

    assert profile_a["user_external_id"] == "profile-a"
    assert profile_a["work_start_time"] == "09:00:00"
    assert profile_a["work_end_time"] == "18:00:00"
    assert profile_a["sleep_time"] == "23:30:00"
    assert profile_b["user_external_id"] == "profile-b"
    assert profile_b["work_start_time"] is None
    assert profile_b["work_end_time"] is None
    assert profile_b["sleep_time"] is None


def test_message_accepts_voice_transcript_source_without_real_llm(client: TestClient):
    response = client.post(
        "/api/message",
        json={
            "user_external_id": "voice-user",
            "source": "telegram_voice_transcript",
            "text": "Завтра хочу позаниматься математикой",
        },
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["source"] == "telegram_voice_transcript"
    assert payload["intent"] == "add_tasks"
    assert payload["parsed"]["date"] == "tomorrow"
