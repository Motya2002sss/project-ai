from collections.abc import Generator
from datetime import date, datetime, time, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

import app.models  # noqa: F401
import app.services.planning_service as planning_service
import app.services.time_service as time_service
from app.core.config import settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.day_plan import DayPlan
from app.models.plan_item import PlanItem
from app.services.planning_service import FOCUS_TEXT_MAX_LENGTH, build_plan_focus


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


def add_task(client: TestClient, user_external_id: str, text: str) -> dict:
    response = client.post(
        "/api/message",
        json={
            "user_external_id": user_external_id,
            "source": "web_text",
            "text": text,
        },
    )

    assert response.status_code == 200
    return response.json()["affected_tasks"][0]


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
    assert payload["affected_tasks"][0]["title"] == "Разобрать документы"
    assert payload["status"] == "applied"
    assert "reason" not in payload
    assert payload["plan_diff"]["created_task_ids"] == [payload["affected_tasks"][0]["id"]]
    assert payload["plan_summary"]["date"] == payload["affected_tasks"][0]["target_date"]
    assert "Принял" in payload["reply_text"]


def test_fixed_conflict_returns_clarification_without_partial_api_mutation(client: TestClient):
    first = client.post(
        "/api/message",
        json={
            "user_external_id": "api-conflict-user",
            "source": "web_text",
            "text": "Завтра в 19:00 теннис на час",
        },
    )
    second = client.post(
        "/api/message",
        json={
            "user_external_id": "api-conflict-user",
            "source": "web_text",
            "text": "Завтра в 19:00 созвон на час",
        },
    )

    assert first.status_code == 200
    assert second.status_code == 200
    payload = second.json()
    tasks = client.get("/api/tasks/api-conflict-user?date=tomorrow").json()

    assert payload["status"] == "conflict"
    assert payload["needs_clarification"] is True
    assert payload["plan_diff"]["conflict"]
    assert [task["title"] for task in tasks] == ["Теннис"]


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

    assert [task["title"] for task in user_a_tasks] == ["Оплатить счета"]
    assert [task["title"] for task in user_b_tasks] == ["Купить продукты"]


def test_owner_can_set_planned_task_done_and_keep_day_history(client: TestClient):
    task = add_task(
        client,
        user_external_id="status-owner",
        text="Сегодня хочу оплатить счета",
    )

    response = client.patch(
        f"/api/tasks/{task['id']}/status",
        json={"user_external_id": "status-owner", "status": "done"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "done"

    plan = client.get("/api/plan/status-owner?date=today").json()
    completed_item = next(item for item in plan["items"] if item["task_id"] == task["id"])
    assert completed_item["status"] == "done"


def test_owner_can_return_done_task_to_planned(client: TestClient):
    task = add_task(
        client,
        user_external_id="status-return-owner",
        text="Сегодня хочу разобрать документы",
    )
    client.patch(
        f"/api/tasks/{task['id']}/status",
        json={"user_external_id": "status-return-owner", "status": "done"},
    )

    response = client.patch(
        f"/api/tasks/{task['id']}/status",
        json={"user_external_id": "status-return-owner", "status": "planned"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "planned"

    plan = client.get("/api/plan/status-return-owner?date=today").json()
    assert any(item["task_id"] == task["id"] for item in plan["items"])


def test_user_cannot_change_another_users_task_status(client: TestClient):
    task = add_task(
        client,
        user_external_id="status-user-b",
        text="Сегодня хочу купить продукты",
    )

    response = client.patch(
        f"/api/tasks/{task['id']}/status",
        json={"user_external_id": "status-user-a", "status": "done"},
    )

    assert response.status_code == 404
    tasks = client.get("/api/tasks/status-user-b").json()
    assert tasks[0]["status"] == "planned"


def test_status_endpoint_returns_404_for_missing_task(client: TestClient):
    response = client.patch(
        "/api/tasks/999999/status",
        json={"user_external_id": "missing-task-user", "status": "done"},
    )

    assert response.status_code == 404


def test_status_endpoint_rejects_unsupported_status(client: TestClient):
    task = add_task(
        client,
        user_external_id="invalid-status-owner",
        text="Сегодня хочу написать письмо",
    )

    response = client.patch(
        f"/api/tasks/{task['id']}/status",
        json={"user_external_id": "invalid-status-owner", "status": "cancelled"},
    )

    assert response.status_code == 422
    tasks = client.get("/api/tasks/invalid-status-owner").json()
    assert tasks[0]["status"] == "planned"


def test_status_endpoint_allows_patch_from_local_web_origin(client: TestClient):
    response = client.options(
        "/api/tasks/1/status",
        headers={
            "Origin": "http://127.0.0.1:5173",
            "Access-Control-Request-Method": "PATCH",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert "PATCH" in response.headers["access-control-allow-methods"]


def test_legacy_done_endpoint_still_works(client: TestClient):
    task = add_task(
        client,
        user_external_id="legacy-done-owner",
        text="Сегодня хочу проверить отчёт",
    )

    response = client.post(
        f"/api/tasks/{task['id']}/done",
        json={"user_external_id": "legacy-done-owner"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "done"


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


def test_get_plan_today_returns_plan_for_user_tasks(client: TestClient, monkeypatch):
    stable_now = datetime.combine(date.today(), time(hour=12), tzinfo=timezone.utc)
    monkeypatch.setattr(planning_service, "get_user_now", lambda user, now=None: now or stable_now)
    monkeypatch.setattr(time_service, "get_user_now", lambda user, now=None: now or stable_now)

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
    assert any(item["title"] == "Подготовиться к экзамену" for item in payload["items"])
    assert payload["focus_text"].startswith("Сначала — Подготовиться к экзамену")
    assert len(payload["focus_text"]) <= FOCUS_TEXT_MAX_LENGTH


def test_plan_focus_uses_plan_items_instead_of_raw_summary():
    day_plan = DayPlan(
        user_id=1,
        date=date.today(),
        summary="raw parser output with internal instructions",
        status="draft",
    )
    day_plan.items = [
        PlanItem(
            task_id=1,
            title="позвонить врачу",
            item_type="task",
            status="planned",
        ),
        PlanItem(
            task_id=2,
            title="подготовить документы " * 30,
            item_type="task",
            status="planned",
        ),
    ]

    focus_text = build_plan_focus(day_plan)

    assert focus_text.startswith("Сначала — позвонить врачу")
    assert "raw parser output" not in focus_text
    assert len(focus_text) <= FOCUS_TEXT_MAX_LENGTH


def test_tasks_can_be_filtered_to_today_without_hiding_legacy_list(client: TestClient):
    today_task = add_task(
        client,
        user_external_id="dated-task-user",
        text="Сегодня хочу оплатить интернет",
    )
    tomorrow_response = client.post(
        "/api/message",
        json={
            "user_external_id": "dated-task-user",
            "source": "web_text",
            "text": "Завтра хочу забрать документы",
        },
    )
    assert tomorrow_response.status_code == 200
    tomorrow_task = tomorrow_response.json()["affected_tasks"][0]

    today_tasks = client.get("/api/tasks/dated-task-user?date=today").json()
    all_tasks = client.get("/api/tasks/dated-task-user").json()

    assert [task["id"] for task in today_tasks] == [today_task["id"]]
    assert {task["id"] for task in all_tasks} == {today_task["id"], tomorrow_task["id"]}


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


def test_message_returns_atomic_day_snapshot(client: TestClient):
    response = client.post(
        "/api/message",
        json={
            "user_external_id": "snapshot-user",
            "source": "web_text",
            "request_id": "snapshot-request-1",
            "text": "Сегодня добавь задачу оплатить интернет",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    snapshot = payload["day_snapshot"]

    assert payload["request_id"] == "snapshot-request-1"
    assert snapshot["plan"] == payload["plan_summary"]
    assert snapshot["tasks"] == payload["affected_tasks"]
    assert snapshot["progress"] == {"done": 0, "total": 1}
    snapshot_items = snapshot["scheduled_items"] + snapshot["unscheduled_items"]
    assert [item["task_id"] for item in snapshot_items] == [snapshot["tasks"][0]["id"]]


def test_tomorrow_mutation_keeps_message_snapshot_on_user_today(client: TestClient):
    today = client.get("/api/day/tomorrow-snapshot-user?date=today").json()
    response = client.post(
        "/api/message",
        json={
            "user_external_id": "tomorrow-snapshot-user",
            "request_id": "tomorrow-snapshot-request",
            "text": "Завтра хочу позаниматься математикой",
        },
    ).json()

    assert response["affected_tasks"][0]["target_date"] != today["date"]
    assert response["plan_summary"]["date"] == response["affected_tasks"][0]["target_date"]
    assert response["day_snapshot"]["date"] == today["date"]
    assert response["day_snapshot"]["tasks"] == []


def test_ambiguous_tracking_request_uses_persistent_clarification(client: TestClient):
    first = client.post(
        "/api/message",
        json={
            "user_external_id": "tracking-user",
            "source": "web_text",
            "request_id": "tracking-request-1",
            "text": "добавь бжу чтобы я считал",
        },
    )

    assert first.status_code == 200
    first_payload = first.json()
    clarification = first_payload["clarification"]

    assert first_payload["status"] == "clarification_required"
    assert first_payload["day_snapshot"]["tasks"] == []
    assert {option["id"] for option in clarification["options"]} == {
        "routine",
        "one_time",
        "capability",
    }

    second = client.post(
        "/api/message",
        json={
            "user_external_id": "tracking-user",
            "source": "web_text",
            "request_id": "tracking-request-2",
            "interaction_id": clarification["id"],
            "option_id": "one_time",
            "text": "разовая задача",
        },
    )
    payload = second.json()

    assert payload["status"] == "applied"
    assert [task["title"] for task in payload["day_snapshot"]["tasks"]] == ["Записать БЖУ"]
    item = payload["day_snapshot"]["unscheduled_items"][0]
    assert item["start_time"] is None
    assert item["unscheduled_reason"] == "missing_duration"


def test_capability_request_does_not_create_task(client: TestClient):
    response = client.post(
        "/api/message",
        json={
            "user_external_id": "capability-user",
            "source": "web_text",
            "request_id": "capability-request-1",
            "text": "Сделай отдельный трекер питания",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "unsupported_capability"
    assert payload["day_snapshot"]["tasks"] == []


def test_clarification_is_user_scoped(client: TestClient):
    first = client.post(
        "/api/message",
        json={
            "user_external_id": "clarification-owner",
            "request_id": "owner-request-1",
            "text": "добавь бжу чтобы я считал",
        },
    ).json()

    response = client.post(
        "/api/message",
        json={
            "user_external_id": "clarification-other-user",
            "request_id": "other-request-1",
            "interaction_id": first["clarification"]["id"],
            "option_id": "one_time",
            "text": "разовая задача",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "no_change"
    assert client.get("/api/tasks/clarification-other-user").json() == []


def test_message_request_id_is_idempotent(client: TestClient):
    body = {
        "user_external_id": "idempotent-user",
        "source": "web_text",
        "request_id": "same-request-id",
        "text": "Сегодня хочу позвонить врачу",
    }

    first = client.post("/api/message", json=body)
    second = client.post("/api/message", json=body)

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json() == first.json()
    assert len(client.get("/api/tasks/idempotent-user?date=today").json()) == 1


def test_conflict_context_accepts_a_different_fixed_time(client: TestClient):
    client.post(
        "/api/message",
        json={
            "user_external_id": "conflict-context-user",
            "request_id": "conflict-context-1",
            "text": "Завтра в 19:00 теннис на час",
        },
    )
    conflict = client.post(
        "/api/message",
        json={
            "user_external_id": "conflict-context-user",
            "request_id": "conflict-context-2",
            "text": "Завтра в 19:00 созвон на час",
        },
    ).json()

    assert conflict["status"] == "conflict"
    assert {option["id"] for option in conflict["conflict_details"]["options"]} == {
        "choose_time",
        "cancel",
    }

    resolved = client.post(
        "/api/message",
        json={
            "user_external_id": "conflict-context-user",
            "request_id": "conflict-context-3",
            "interaction_id": conflict["conflict_details"]["id"],
            "text": "Поставь в 20:00",
        },
    ).json()

    assert resolved["status"] == "applied"
    assert resolved["day_snapshot"]["scheduled_items"] == []
    starts = [item["start_time"] for item in resolved["plan_summary"]["items"]]
    assert starts == ["19:00:00", "20:00:00"]

    tomorrow = client.get("/api/day/conflict-context-user?date=tomorrow").json()
    assert [item["start_time"] for item in tomorrow["scheduled_items"]] == starts


def test_repeated_day_snapshot_read_keeps_plan_version(client: TestClient):
    client.post(
        "/api/message",
        json={
            "user_external_id": "plan-version-user",
            "request_id": "plan-version-request",
            "text": "Сегодня хочу разобрать почту",
        },
    )

    first = client.get("/api/day/plan-version-user?date=today").json()
    second = client.get("/api/day/plan-version-user?date=today").json()

    assert first["plan_version"] == second["plan_version"]


def test_low_energy_replan_requires_confirmation_before_moving_tasks(client: TestClient):
    user_id = "low-energy-user"

    for index, text in enumerate(
        [
            "Сегодня хочу поделать проект",
            "Сегодня хочу разобрать почту",
            "Сегодня хочу купить продукты",
        ],
        start=1,
    ):
        response = client.post(
            "/api/message",
            json={
                "user_external_id": user_id,
                "request_id": f"low-energy-setup-{index}",
                "text": text,
            },
        )
        assert response.status_code == 200

    proposal = client.post(
        "/api/message",
        json={
            "user_external_id": user_id,
            "request_id": "low-energy-proposal",
            "text": "Сегодня мало сил, добавь ещё 40 минут на проект и оставь только главное.",
        },
    ).json()

    assert proposal["status"] == "confirmation_required"
    assert proposal["confirmation"]
    assert len(proposal["day_snapshot"]["tasks"]) == 3
    project_before = next(task for task in proposal["day_snapshot"]["tasks"] if "проект" in task["title"].lower())
    assert project_before["estimated_minutes"] == 60

    applied = client.post(
        "/api/message",
        json={
            "user_external_id": user_id,
            "request_id": "low-energy-apply",
            "interaction_id": proposal["confirmation"]["id"],
            "option_id": "apply",
            "text": "применить",
        },
    ).json()

    assert applied["status"] == "applied"
    assert applied["day_snapshot"]["day_context"]["energy_level"] == "low"
    assert [task["title"] for task in applied["day_snapshot"]["tasks"]] == ["Поделать проект"]
    assert applied["day_snapshot"]["tasks"][0]["estimated_minutes"] == 100
    tomorrow = client.get(f"/api/tasks/{user_id}?date=tomorrow").json()
    assert {task["title"] for task in tomorrow} == {"Разобрать почту", "Купить продукты"}


def test_low_energy_context_can_be_used_by_follow_up_replan(client: TestClient):
    user_id = "low-energy-follow-up-user"

    for index, text in enumerate(
        ["Сегодня подготовиться к экзамену", "Сегодня разобрать почту"],
        start=1,
    ):
        client.post(
            "/api/message",
            json={
                "user_external_id": user_id,
                "request_id": f"low-energy-follow-up-setup-{index}",
                "text": text,
            },
        )

    context = client.post(
        "/api/message",
        json={
            "user_external_id": user_id,
            "request_id": "low-energy-follow-up-context",
            "text": "Сегодня мало сил",
        },
    ).json()
    proposal = client.post(
        "/api/message",
        json={
            "user_external_id": user_id,
            "request_id": "low-energy-follow-up-proposal",
            "text": "Оставь только главное",
        },
    ).json()

    assert context["day_snapshot"]["day_context"]["energy_level"] == "low"
    assert context["day_snapshot"]["tasks"]
    assert proposal["status"] == "confirmation_required"
    assert len(proposal["day_snapshot"]["tasks"]) == 2


def test_permanent_work_schedule_does_not_create_task(client: TestClient):
    payload = client.post(
        "/api/message",
        json={
            "user_external_id": "work-schedule-user",
            "request_id": "work-schedule-1",
            "text": "Я работаю с 9 до 18",
        },
    ).json()

    assert payload["intent"] == "set_work_schedule"
    assert payload["status"] == "applied"
    assert payload["affected_tasks"] == []
    assert payload["day_snapshot"]["tasks"] == []
    assert payload["profile"]["work_start_time"] == "09:00:00"
    assert payload["profile"]["work_end_time"] == "18:00:00"


def test_work_schedule_is_user_scoped(client: TestClient):
    client.post(
        "/api/message",
        json={"user_external_id": "work-owner", "text": "Я работаю с 9 до 18"},
    )

    owner = client.get("/api/profile/work-owner").json()
    other = client.get("/api/profile/work-other").json()

    assert owner["work_end_time"] == "18:00:00"
    assert other["work_start_time"] is None
    assert other["work_end_time"] is None


def test_repeated_work_schedule_is_no_change_without_duplicates(client: TestClient):
    for request_id in ["schedule-repeat-1", "schedule-repeat-2"]:
        response = client.post(
            "/api/message",
            json={
                "user_external_id": "schedule-repeat-user",
                "request_id": request_id,
                "text": "Я работаю с 9 до 18",
            },
        )

    payload = response.json()
    tasks = client.get("/api/tasks/schedule-repeat-user").json()

    assert payload["status"] == "no_change"
    assert payload["reply_text"].startswith("Рабочее время уже установлено: 09:00–18:00.")
    assert "План менять не пришлось" in payload["reply_text"]
    assert tasks == []


def test_day_work_override_does_not_change_profile(client: TestClient):
    user_id = "day-work-override-user"
    client.post(
        "/api/message",
        json={"user_external_id": user_id, "text": "Я работаю с 9 до 18"},
    )
    payload = client.post(
        "/api/message",
        json={"user_external_id": user_id, "text": "Сегодня работаю с 10 до 20"},
    ).json()
    profile = client.get(f"/api/profile/{user_id}").json()

    assert payload["intent"] == "set_day_availability"
    assert payload["day_snapshot"]["day_context"] == {
        "energy_level": None,
        "budget_limit": None,
        "work_override_mode": "busy",
        "work_start_time": "10:00:00",
        "work_end_time": "20:00:00",
    }
    assert profile["work_start_time"] == "09:00:00"
    assert profile["work_end_time"] == "18:00:00"


def test_ambiguous_work_input_requests_clarification_without_mutation(client: TestClient):
    user_id = "ambiguous-work-user"
    before = client.get(f"/api/day/{user_id}?date=today").json()
    payload = client.post(
        "/api/message",
        json={
            "user_external_id": user_id,
            "request_id": "ambiguous-work-1",
            "text": "Добавь работу с 9 до 18",
        },
    ).json()
    after = client.get(f"/api/day/{user_id}?date=today").json()

    assert payload["status"] == "clarification_required"
    assert (
        payload["clarification"]["question"]
        == "Ты хочешь указать рабочее время с 09:00 до 18:00 или добавить отдельную задачу?"
    )
    assert {option["id"] for option in payload["clarification"]["options"]} == {
        "work_schedule",
        "task",
        "cancel",
    }
    assert payload["affected_tasks"] == []
    assert payload["day_snapshot"]["tasks"] == []
    assert before["plan_version"] == after["plan_version"]
    assert before["tasks"] == after["tasks"] == []


def test_ambiguous_work_input_never_creates_default_hour_task(client: TestClient):
    user_id = "ambiguous-no-hour-user"
    payload = client.post(
        "/api/message",
        json={"user_external_id": user_id, "text": "Внести работу с 9 до 18"},
    ).json()

    assert payload["parsed"]["tasks"] == []
    assert client.get(f"/api/tasks/{user_id}").json() == []
    assert all(item["task_id"] is None for item in payload["day_snapshot"]["plan"]["items"])


def test_empty_day_focus_uses_work_schedule_not_raw_command(client: TestClient):
    payload = client.post(
        "/api/message",
        json={"user_external_id": "work-focus-user", "text": "Я работаю с 9 до 18"},
    ).json()

    assert payload["day_snapshot"]["focus_text"] == "Рабочий день до 18:00. Вечер пока свободен."
    assert "Я работаю" not in payload["day_snapshot"]["focus_text"]


def test_work_schedule_returns_factual_plan_diff(client: TestClient):
    payload = client.post(
        "/api/message",
        json={"user_external_id": "work-diff-user", "text": "Я работаю с 9 до 18"},
    ).json()

    assert payload["plan_diff"]["availability_change"] == "Рабочее время обновлено: 09:00–18:00."
    assert payload["plan_diff"]["created_task_ids"] == []


def test_work_schedule_snapshot_has_no_phantom_task(client: TestClient):
    payload = client.post(
        "/api/message",
        json={"user_external_id": "work-snapshot-user", "text": "Я работаю с 9 до 18"},
    ).json()
    snapshot = payload["day_snapshot"]

    assert snapshot["tasks"] == []
    assert snapshot["scheduled_items"] == []
    assert snapshot["unscheduled_items"] == []
    assert snapshot["progress"] == {"done": 0, "total": 0}


def test_weekday_work_schedule_requires_confirmation(client: TestClient):
    user_id = "weekday-work-user"
    payload = client.post(
        "/api/message",
        json={"user_external_id": user_id, "text": "По будням работаю с 9 до 18"},
    ).json()
    profile = client.get(f"/api/profile/{user_id}").json()

    assert payload["status"] == "confirmation_required"
    assert {option["id"] for option in payload["confirmation"]["options"]} == {"apply", "cancel"}
    assert profile["work_start_time"] is None
    assert profile["work_end_time"] is None


def test_day_off_confirmation_applies_only_to_today(client: TestClient):
    user_id = "day-off-user"
    client.post(
        "/api/message",
        json={"user_external_id": user_id, "text": "Я работаю с 9 до 18"},
    )
    proposal = client.post(
        "/api/message",
        json={"user_external_id": user_id, "text": "Я сегодня не работаю"},
    ).json()
    applied = client.post(
        "/api/message",
        json={
            "user_external_id": user_id,
            "interaction_id": proposal["confirmation"]["id"],
            "option_id": "apply",
            "text": "применить",
        },
    ).json()
    profile = client.get(f"/api/profile/{user_id}").json()

    assert proposal["status"] == "confirmation_required"
    assert applied["status"] == "applied"
    assert applied["day_snapshot"]["day_context"]["work_override_mode"] == "off"
    assert applied["day_snapshot"]["day_context"]["work_end_time"] is None
    assert profile["work_end_time"] == "18:00:00"


def test_explicit_work_task_and_event_still_create_tasks(client: TestClient):
    flexible = client.post(
        "/api/message",
        json={"user_external_id": "explicit-work-user", "text": "Добавь рабочую задачу на час"},
    ).json()
    fixed = client.post(
        "/api/message",
        json={"user_external_id": "explicit-work-event-user", "text": "Завтра в 15:00 рабочий созвон"},
    ).json()

    assert flexible["intent"] == "create_task"
    assert flexible["affected_tasks"][0]["scheduling_type"] == "flexible"
    assert fixed["intent"] == "create_event"
    assert fixed["affected_tasks"][0]["fixed_start"] == "15:00:00"
