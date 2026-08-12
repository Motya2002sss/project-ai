from datetime import date, datetime, time, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import event, func, select

from app.models.auth import AppSession
from app.models.calendar import CalendarBusyBlock, TemporaryLifeMode
from app.models.day_plan import DayPlan
from app.models.evidence import MetricObservation
from app.models.goal import Goal
from app.models.plan_item import PlanItem
from app.models.program import GoalMilestone, Program, WeeklyCommitment
from app.models.task import Task
from app.models.user import User
from tests.test_api_v2_auth import api, bearer, begin_apple_sign_in


UTC = timezone.utc


def _owner(factory, public_id: str) -> User:
    with factory() as db:
        return db.scalar(select(User).where(User.public_id == UUID(public_id)))


def _seed_day(factory, user_id: int) -> None:
    with factory() as db:
        task = Task(
            user_id=user_id,
            title="Очень длинная русская строка задачи, которая остаётся фактом сервера",
            target_date=date(2026, 8, 12),
            status="planned",
            scheduling_type="fixed",
            fixed_start=time(10),
            fixed_end=time(11),
            estimated_minutes=60,
        )
        plan = DayPlan(
            user_id=user_id,
            date=date(2026, 8, 12),
            summary="Главное — спокойный следующий шаг",
            status="ready",
            version=4,
        )
        db.add_all([task, plan])
        db.flush()
        plan.items.extend(
            [
                PlanItem(
                    task_id=None,
                    title="Сон",
                    item_type="sleep",
                    status="planned",
                    start_time=time(0),
                    end_time=time(8),
                ),
                PlanItem(
                    task_id=task.id,
                    title=task.title,
                    item_type="task",
                    status="planned",
                    start_time=time(10),
                    end_time=time(11),
                ),
                PlanItem(
                    task_id=None,
                    title="Восстановление",
                    item_type="recovery",
                    status="planned",
                    start_time=time(12),
                    end_time=time(13),
                ),
            ]
        )
        db.add(
            CalendarBusyBlock(
                user_id=user_id,
                device_id="private-iphone",
                provider="apple",
                calendar_external_id="private-calendar",
                external_id="secret-event",
                occurrence_external_id="secret-occurrence",
                occurrence_start=datetime(2026, 8, 12, 8, 30, tzinfo=UTC),
                occurrence_end=datetime(2026, 8, 12, 9, 30, tzinfo=UTC),
                device_timezone="UTC",
                source_revision="secret-revision",
                last_seen_client_revision=1,
            )
        )
        db.commit()


def test_day_returns_authoritative_persisted_timeline_and_privacy_safe_free_time(api) -> None:
    client, factory = api
    signed_in = begin_apple_sign_in(client, identity_token="valid-identity-token-read-day")
    owner = _owner(factory, signed_in["user"]["public_id"])
    _seed_day(factory, owner.id)

    response = client.get(
        "/api/v2/calendar/day",
        params={"date": "2026-08-12"},
        headers=bearer(signed_in["access_token"]),
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["date"] == "2026-08-12"
    assert payload["timezone"] == "UTC"
    assert payload["materialized"] is True
    assert payload["plan_version"] == 4
    assert [item["kind"] for item in payload["items"]] == ["sleep", "task", "recovery"]
    assert payload["items"][1]["task_id"] is not None
    assert payload["busy_intervals"] == [
        {
            "start_at": "2026-08-12T08:30:00Z",
            "end_at": "2026-08-12T09:30:00Z",
        }
    ]
    assert payload["free_intervals"] == [
        {"start_at": "2026-08-12T08:00:00Z", "end_at": "2026-08-12T08:30:00Z"},
        {"start_at": "2026-08-12T09:30:00Z", "end_at": "2026-08-12T10:00:00Z"},
        {"start_at": "2026-08-12T11:00:00Z", "end_at": "2026-08-12T12:00:00Z"},
        {"start_at": "2026-08-12T13:00:00Z", "end_at": "2026-08-12T23:00:00Z"},
    ]
    serialized = response.text
    assert "private-calendar" not in serialized
    assert "secret-event" not in serialized
    assert "secret-revision" not in serialized
    assert response.headers["etag"] == f'"{payload["cursor"]}"'


def test_unmaterialized_day_is_explicit_and_get_does_not_create_or_version_rows(api) -> None:
    client, factory = api
    signed_in = begin_apple_sign_in(client, identity_token="valid-identity-token-read-empty")
    headers = bearer(signed_in["access_token"])

    with factory() as db:
        before = db.scalar(select(func.count(DayPlan.id)))

    first = client.get("/api/v2/calendar/day?date=2026-08-13", headers=headers)
    second = client.get("/api/v2/calendar/day?date=2026-08-13", headers=headers)

    assert first.status_code == 200
    assert first.json()["materialized"] is False
    assert first.json()["plan_version"] is None
    assert first.json()["items"] == []
    assert first.json()["free_intervals"] == [
        {"start_at": "2026-08-13T06:00:00Z", "end_at": "2026-08-13T23:00:00Z"}
    ]
    assert second.json()["cursor"] == first.json()["cursor"]
    with factory() as db:
        assert db.scalar(select(func.count(DayPlan.id))) == before


def test_calendar_get_does_not_update_session_telemetry(api) -> None:
    client, factory = api
    signed_in = begin_apple_sign_in(client, identity_token="valid-identity-token-read-only-auth")
    headers = bearer(signed_in["access_token"])
    original = datetime(2020, 1, 1, tzinfo=UTC)
    with factory() as db:
        session = db.scalar(select(AppSession))
        session.last_seen_at = original
        db.commit()

    response = client.get("/api/v2/calendar/day?date=2026-08-13", headers=headers)

    assert response.status_code == 200
    with factory() as db:
        saved = db.scalar(select(AppSession))
        observed = saved.last_seen_at
        if observed.tzinfo is None:
            observed = observed.replace(tzinfo=UTC)
        assert observed == original


def test_week_has_exactly_seven_owned_days_and_factual_commitment_load(api) -> None:
    client, factory = api
    signed_in = begin_apple_sign_in(client, identity_token="valid-identity-token-read-week")
    owner = _owner(factory, signed_in["user"]["public_id"])
    with factory() as db:
        goal = Goal(user_id=owner.id, title="Подготовиться к собеседованию", status="active")
        db.add(goal)
        db.flush()
        program = Program(
            user_id=owner.id,
            goal_id=goal.id,
            name="Системная подготовка",
            status="active",
            minimum_minutes_week=60,
            comfortable_minutes_week=120,
            maximum_minutes_week=180,
        )
        db.add(program)
        db.flush()
        commitment = WeeklyCommitment(
            user_id=owner.id,
            goal_id=goal.id,
            program_id=program.id,
            title="Практика архитектуры",
            target_minutes_week=120,
            target_sessions_week=2,
            minimum_block_minutes=30,
            allowed_weekdays=[0, 2],
            splittable=True,
            active=True,
        )
        db.add(commitment)
        db.flush()
        task = Task(
            user_id=owner.id,
            goal_id=goal.id,
            program_id=program.id,
            commitment_id=commitment.id,
            title="Разобрать очереди сообщений",
            target_date=date(2026, 8, 12),
            status="done",
            estimated_minutes=60,
        )
        plan = DayPlan(user_id=owner.id, date=date(2026, 8, 12), status="ready", version=3)
        db.add_all([task, plan])
        db.flush()
        plan.items.append(
            PlanItem(
                task_id=task.id,
                title=task.title,
                item_type="task",
                status="done",
                start_time=time(18),
                end_time=time(19),
            )
        )
        stranger = User(external_id="calendar-read-stranger")
        db.add(stranger)
        db.flush()
        db.add(DayPlan(user_id=stranger.id, date=date(2026, 8, 13), status="ready", version=99))
        db.commit()

    response = client.get(
        "/api/v2/calendar/week?start=2026-08-10",
        headers=bearer(signed_in["access_token"]),
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["start"] == "2026-08-10"
    assert payload["end"] == "2026-08-16"
    assert [day["date"] for day in payload["days"]] == [
        f"2026-08-{day:02d}" for day in range(10, 17)
    ]
    selected = payload["days"][2]
    assert selected["plan_version"] == 3
    assert selected["completed_count"] == 1
    assert selected["items"][0]["title"] == "Разобрать очереди сообщений"
    assert all(day["plan_version"] != 99 for day in payload["days"])
    assert payload["commitment_load"] == [
        {
            "commitment_id": str(commitment.id),
            "title": "Практика архитектуры",
            "target_minutes": 120,
            "target_sessions": 2,
            "scheduled_minutes": 60,
            "scheduled_sessions": 1,
            "completed_minutes": 60,
            "completed_sessions": 1,
            "remaining_minutes": 60,
        }
    ]


def test_month_exposes_only_high_level_facts_without_task_or_sensitive_notes(api) -> None:
    client, factory = api
    signed_in = begin_apple_sign_in(client, identity_token="valid-identity-token-read-month")
    owner = _owner(factory, signed_in["user"]["public_id"])
    with factory() as db:
        goal = Goal(
            user_id=owner.id,
            title="Сдать профессиональный экзамен",
            status="active",
            deadline=date(2026, 8, 28),
        )
        db.add(goal)
        db.flush()
        db.add_all(
            [
                GoalMilestone(
                    user_id=owner.id,
                    goal_id=goal.id,
                    title="Пробный экзамен пройден",
                    position=1,
                    status="completed",
                    completed_at=datetime(2026, 8, 20, 12, tzinfo=UTC),
                ),
                MetricObservation(
                    user_id=owner.id,
                    goal_id=goal.id,
                    request_id="measurement-1",
                    value=Decimal("72.5"),
                    unit="kg",
                    occurred_at=datetime(2026, 8, 18, 7, tzinfo=UTC),
                    source="manual",
                    note="чувствительная заметка не для календаря",
                ),
                TemporaryLifeMode(
                    user_id=owner.id,
                    request_id="trip-1",
                    mode="travel",
                    starts_at=datetime(2026, 8, 22, 6, tzinfo=UTC),
                    ends_at=datetime(2026, 8, 25, 20, tzinfo=UTC),
                    status="active",
                    constraints={"private": "не отдавать"},
                ),
                Task(
                    user_id=owner.id,
                    goal_id=goal.id,
                    title="Мелкая задача не должна попасть в Month",
                    source_text="секретный capture text",
                    target_date=date(2026, 8, 19),
                    status="planned",
                    estimated_minutes=25,
                ),
            ]
        )
        db.commit()

    response = client.get(
        "/api/v2/calendar/month?month=2026-08-01",
        headers=bearer(signed_in["access_token"]),
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["month"] == "2026-08-01"
    assert payload["milestones"][0]["title"] == "Пробный экзамен пройден"
    assert payload["deadlines"][0]["title"] == "Сдать профессиональный экзамен"
    assert payload["life_modes"][0]["mode"] == "travel"
    assert payload["measurements"][0] == {
        "goal_id": str(goal.public_id),
        "occurred_at": "2026-08-18T07:00:00Z",
        "value": "72.5000",
        "unit": "kg",
    }
    serialized = response.text
    assert "Мелкая задача" not in serialized
    assert "capture text" not in serialized
    assert "чувствительная заметка" not in serialized
    assert '"private"' not in serialized


def test_calendar_reads_require_authentication(api) -> None:
    client, _factory = api

    assert client.get("/api/v2/calendar/day?date=2026-08-12").status_code == 401
    assert client.get("/api/v2/calendar/week?start=2026-08-10").status_code == 401
    assert client.get("/api/v2/calendar/month?month=2026-08-01").status_code == 401


def test_dense_week_read_has_bounded_query_count(api) -> None:
    client, factory = api
    signed_in = begin_apple_sign_in(client, identity_token="valid-identity-token-read-bounded")
    owner = _owner(factory, signed_in["user"]["public_id"])
    with factory() as db:
        for offset in range(7):
            plan = DayPlan(
                user_id=owner.id,
                date=date(2026, 8, 10 + offset),
                status="ready",
                version=offset + 1,
            )
            db.add(plan)
            db.flush()
            for item_offset in range(8):
                plan.items.append(
                    PlanItem(
                        task_id=None,
                        title=f"Действие {offset}-{item_offset}",
                        item_type="anchor",
                        status="planned",
                        start_time=time(item_offset + 8),
                        end_time=time(item_offset + 9),
                    )
                )
        db.commit()

    engine = factory.kw["bind"]
    statements = 0

    def count_statement(*_args) -> None:
        nonlocal statements
        statements += 1

    event.listen(engine, "before_cursor_execute", count_statement)
    try:
        response = client.get(
            "/api/v2/calendar/week?start=2026-08-10",
            headers=bearer(signed_in["access_token"]),
        )
    finally:
        event.remove(engine, "before_cursor_execute", count_statement)

    assert response.status_code == 200
    assert len(response.json()["days"]) == 7
    assert statements <= 8


def test_week_and_month_reject_ambiguous_range_boundaries(api) -> None:
    client, _factory = api
    signed_in = begin_apple_sign_in(client, identity_token="valid-identity-token-read-ranges")
    headers = bearer(signed_in["access_token"])

    assert client.get("/api/v2/calendar/week?start=2026-08-11", headers=headers).status_code == 422
    assert client.get("/api/v2/calendar/month?month=2026-08-02", headers=headers).status_code == 422
