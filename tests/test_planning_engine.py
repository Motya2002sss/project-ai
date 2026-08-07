from collections.abc import Generator
from datetime import date, datetime, time, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

import app.models  # noqa: F401
import app.services.planning_service as planning_service
import app.services.time_service as time_service
from app.core.config import settings
from app.db.base import Base
from app.llm.schemas import ParsedUserMessage
from app.models.day_plan import DayPlan
from app.models.task import Task
from app.models.user import User
from app.services.message_service import process_user_message
from app.services.message_policy import normalize_task_title
from app.services.planning_service import (
    TimeInterval,
    assert_plan_has_no_overlaps,
    build_day_plan_result,
    choose_best_slot,
    find_available_slots,
    format_plan_date,
)


UTC = timezone.utc
TEST_DATE = date(2026, 8, 3)
TEST_NOW = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("raw_title", "expected"),
    [
        ("Сегодня в 22:00 теннис на 30 минут", "Теннис"),
        ("Теннис минут", "Теннис"),
        ("Час тишины", "Час тишины"),
        ("Сегодня хочу проверить бюджет на 60 минут", "Проверить бюджет"),
        ("Планирую подготовиться к экзамену", "Подготовиться к экзамену"),
    ],
)
def test_task_title_removes_only_scheduling_metadata(raw_title: str, expected: str):
    assert normalize_task_title(raw_title) == expected


def test_plan_date_label_uses_user_timezone(db: Session):
    user = create_user(db)

    assert format_plan_date(TEST_DATE, user=user) == "сегодня"
    assert format_plan_date(TEST_DATE + timedelta(days=1), user=user) == "завтра"


def dt(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 8, 3, hour, minute, tzinfo=UTC)


@pytest.fixture()
def db(tmp_path, monkeypatch) -> Generator[Session, None, None]:
    monkeypatch.setattr(settings, "llm_enabled", False)
    monkeypatch.setattr(settings, "llm_provider", "mock")
    monkeypatch.setattr(planning_service, "get_user_now", lambda user, now=None: now or TEST_NOW)
    monkeypatch.setattr(time_service, "get_user_now", lambda user, now=None: now or TEST_NOW)

    engine = create_engine(f"sqlite:///{tmp_path / 'planning.db'}")
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)

    with SessionLocal() as session:
        yield session

    Base.metadata.drop_all(engine)


def create_user(db: Session, external_id: str = "planning-user", **values) -> User:
    user = User(external_id=external_id, timezone="UTC", **values)
    db.add(user)
    db.flush()
    return user


def create_task(db: Session, user: User, title: str, **values) -> Task:
    task = Task(
        user_id=user.id,
        title=title,
        priority=values.pop("priority", "medium"),
        estimated_minutes=values.pop("estimated_minutes", 60),
        target_date=TEST_DATE,
        scheduling_type=values.pop("scheduling_type", "flexible"),
        status="planned",
        **values,
    )
    db.add(task)
    db.flush()
    return task


def test_find_one_available_slot():
    slots = find_available_slots(
        dt(9),
        dt(12),
        [TimeInterval(dt(9), dt(10))],
        60,
    )

    assert slots == [TimeInterval(dt(10), dt(12))]
    assert choose_best_slot(slots, 60) == TimeInterval(dt(10), dt(11))


def test_find_multiple_available_slots():
    slots = find_available_slots(
        dt(9),
        dt(15),
        [TimeInterval(dt(10), dt(11)), TimeInterval(dt(12), dt(13))],
        60,
    )

    assert [(slot.start, slot.end) for slot in slots] == [
        (dt(9), dt(10)),
        (dt(11), dt(12)),
        (dt(13), dt(15)),
    ]


def test_window_shorter_than_duration_is_rejected():
    slots = find_available_slots(
        dt(9),
        dt(12),
        [TimeInterval(dt(10), dt(11))],
        90,
    )

    assert slots == []


def test_fixed_interval_is_removed_from_availability():
    slots = find_available_slots(
        dt(9),
        dt(12),
        [TimeInterval(dt(10), dt(11), "fixed event")],
        60,
    )

    assert choose_best_slot(slots, 60) == TimeInterval(dt(9), dt(10))


def test_two_fixed_events_do_not_overlap(db: Session):
    user = create_user(db)
    create_task(
        db,
        user,
        "Теннис",
        scheduling_type="fixed",
        fixed_start=time(19),
        fixed_end=time(20),
        is_locked=True,
    )
    create_task(
        db,
        user,
        "Созвон",
        scheduling_type="fixed",
        fixed_start=time(20),
        fixed_end=time(21),
        is_locked=True,
    )

    result = build_day_plan_result(db, user, plan_date=TEST_DATE, now=TEST_NOW)

    assert result.conflicts == []
    assert_plan_has_no_overlaps(result.day_plan, user)


def test_conflicting_fixed_events_return_conflict_without_overlap(db: Session):
    user = create_user(db)
    create_task(
        db,
        user,
        "Теннис",
        scheduling_type="fixed",
        fixed_start=time(19),
        fixed_end=time(20),
        is_locked=True,
    )
    second = create_task(
        db,
        user,
        "Созвон",
        scheduling_type="fixed",
        fixed_start=time(19),
        fixed_end=time(20),
        is_locked=True,
    )

    result = build_day_plan_result(db, user, plan_date=TEST_DATE, now=TEST_NOW)

    assert [conflict.task_id for conflict in result.conflicts] == [second.id]
    assert second.id in result.unscheduled_task_ids
    assert_plan_has_no_overlaps(result.day_plan, user)


def test_preferred_morning_limits_slot_search():
    morning = TimeInterval(dt(6), dt(12), "morning")
    slots = find_available_slots(dt(6), dt(23), [], 60, preferred_window=morning)

    assert choose_best_slot(slots, 60) == TimeInterval(dt(6), dt(7))


def test_preferred_evening_limits_slot_search():
    evening = TimeInterval(dt(17), dt(23), "evening")
    slots = find_available_slots(dt(6), dt(23), [], 60, preferred_window=evening)

    assert choose_best_slot(slots, 60) == TimeInterval(dt(17), dt(18))


def test_preferred_window_that_passed_stays_unscheduled(db: Session):
    user = create_user(db)
    task = create_task(db, user, "Сходить в зал", preferred_window="morning")
    evening_now = datetime(2026, 8, 3, 18, 0, tzinfo=UTC)

    result = build_day_plan_result(db, user, plan_date=TEST_DATE, now=evening_now)
    item = next(item for item in result.day_plan.items if item.task_id == task.id)

    assert item.status == "not_scheduled"
    assert item.unscheduled_reason == "preferred_window_passed"


def test_earliest_start_is_respected():
    slots = find_available_slots(dt(9), dt(18), [], 60, earliest_start=dt(14))

    assert choose_best_slot(slots, 60) == TimeInterval(dt(14), dt(15))


def test_latest_end_is_respected():
    slots = find_available_slots(
        dt(9),
        dt(18),
        [TimeInterval(dt(9), dt(11, 30))],
        60,
        latest_end=dt(12),
    )

    assert slots == []


def test_sleep_boundary_leaves_task_unscheduled(db: Session):
    user = create_user(
        db,
        work_start_time=time(9),
        work_end_time=time(21),
        sleep_time=time(22),
    )
    task = create_task(db, user, "Большая задача", estimated_minutes=90)

    result = build_day_plan_result(db, user, plan_date=TEST_DATE, now=TEST_NOW)

    assert task.id in result.unscheduled_task_ids


def test_work_boundary_and_buffer_are_busy(db: Session):
    user = create_user(
        db,
        work_start_time=time(9),
        work_end_time=time(18),
        sleep_time=time(23),
    )
    task = create_task(db, user, "Личная задача")

    result = build_day_plan_result(db, user, plan_date=TEST_DATE, now=TEST_NOW)
    item = next(item for item in result.day_plan.items if item.task_id == task.id)

    assert item.start_time == time(18, settings.plan_start_buffer_minutes)


def test_today_task_is_not_scheduled_in_the_past(db: Session):
    user = create_user(db)
    task = create_task(db, user, "Новая задача")
    now = datetime(2026, 8, 3, 14, 7, tzinfo=UTC)

    result = build_day_plan_result(db, user, plan_date=TEST_DATE, now=now)
    item = next(item for item in result.day_plan.items if item.task_id == task.id)

    assert item.start_time == time(14, 15)


def test_no_available_window_is_explicit():
    slots = find_available_slots(
        dt(9),
        dt(12),
        [TimeInterval(dt(9), dt(12))],
        30,
    )

    assert slots == []
    assert choose_best_slot(slots, 30) is None


def test_existing_flexible_slots_remain_stable(db: Session):
    user = create_user(db)
    first = create_task(db, user, "Первая задача")
    second = create_task(db, user, "Вторая задача")
    initial = build_day_plan_result(db, user, plan_date=TEST_DATE, now=TEST_NOW)
    initial_times = {
        item.task_id: item.start_time
        for item in initial.day_plan.items
        if item.task_id in {first.id, second.id}
    }
    create_task(db, user, "Новая задача", priority="high")

    updated = build_day_plan_result(db, user, plan_date=TEST_DATE, now=TEST_NOW)
    updated_times = {
        item.task_id: item.start_time
        for item in updated.day_plan.items
        if item.task_id in {first.id, second.id}
    }

    assert updated_times == initial_times
    assert_plan_has_no_overlaps(updated.day_plan, user)


def test_natural_language_flexible_task_gets_real_slot(db: Session):
    response = process_user_message(
        db,
        "message-user",
        "Сегодня добавь теннис на час",
        "web_text",
    )

    task = response.affected_tasks[0]
    item = next(item for item in response.plan_summary.items if item.task_id == task.id)

    assert task.scheduling_type == "flexible"
    assert item.start_time is not None
    assert item.end_time is not None
    assert response.plan_diff.created_task_ids == [task.id]


def test_natural_language_fixed_event_uses_exact_time(db: Session):
    response = process_user_message(
        db,
        "fixed-user",
        "Сегодня в 19:00 созвон на час",
        "web_text",
    )

    task = response.affected_tasks[0]
    item = next(item for item in response.plan_summary.items if item.task_id == task.id)

    assert task.scheduling_type == "fixed"
    assert item.start_time == time(19)
    assert item.end_time == time(20)


def test_fixed_conflict_rolls_back_new_task(db: Session):
    process_user_message(db, "conflict-user", "Сегодня в 19:00 теннис на час", "web_text")

    response = process_user_message(
        db,
        "conflict-user",
        "Сегодня в 19:00 созвон на час",
        "web_text",
    )

    tasks = db.query(Task).filter(Task.user_id == 1).all()
    assert response.status == "conflict"
    assert response.needs_clarification is True
    assert [task.title for task in tasks] == ["Теннис"]


def test_morning_task_is_not_scheduled_in_evening(db: Session, monkeypatch):
    evening_now = datetime(2026, 8, 3, 18, 0, tzinfo=UTC)
    monkeypatch.setattr(planning_service, "get_user_now", lambda user, now=None: evening_now)

    response = process_user_message(
        db,
        "morning-user",
        "Утром хочу сходить в зал",
        "web_text",
    )
    item = response.plan_summary.items[0]

    assert item.start_time is None
    assert item.unscheduled_reason == "preferred_window_passed"


def test_recurrence_ambiguity_does_not_create_task(db: Session):
    response = process_user_message(
        db,
        "recurrence-user",
        "Утром хожу в зал",
        "web_text",
    )

    assert response.status == "clarification_required"
    assert db.query(Task).count() == 0


def test_complete_cancel_move_and_extend_do_not_create_duplicates(db: Session):
    process_user_message(db, "ops-user", "Сегодня хочу оплатить интернет", "web_text")
    process_user_message(db, "ops-user", "Оплатил интернет", "web_text")
    process_user_message(db, "ops-user", "Оплатил интернет", "web_text")
    process_user_message(db, "ops-user", "Сегодня хочу сходить в зал", "web_text")
    cancel_response = process_user_message(db, "ops-user", "Зал отменяется", "web_text")
    process_user_message(db, "ops-user", "Сегодня хочу поделать проект", "web_text")
    move_response = process_user_message(db, "ops-user", "Проект перенеси на завтра", "web_text")
    extend_response = process_user_message(db, "ops-user", "Добавь ещё 40 минут на проект", "web_text")

    tasks = db.query(Task).order_by(Task.id).all()
    assert len(tasks) == 3
    assert tasks[0].status == "done"
    assert tasks[1].status == "cancelled"
    assert tasks[2].target_date == TEST_DATE + timedelta(days=1)
    assert tasks[2].estimated_minutes == 100
    assert cancel_response.plan_diff.cancelled_task_ids == [tasks[1].id]
    assert move_response.plan_diff.updated_task_ids == [tasks[2].id]
    assert extend_response.plan_diff.updated_task_ids == [tasks[2].id]


def test_multi_action_message_applies_each_clause_without_cross_date_leak(db: Session):
    process_user_message(db, "multi-action-user", "Сегодня хочу сходить в зал", "web_text")
    process_user_message(db, "multi-action-user", "Сегодня хочу поделать проект", "web_text")

    response = process_user_message(
        db,
        "multi-action-user",
        "Зал отменяется, в 19 созвон, проект перенеси на завтра",
        "web_text",
    )
    tasks = db.query(Task).order_by(Task.id).all()
    gym = next(task for task in tasks if task.title == "Сходить в зал")
    project = next(task for task in tasks if task.title == "Поделать проект")
    call = next(task for task in tasks if task.title == "Созвон")

    assert response.status == "applied"
    assert len(tasks) == 3
    assert gym.status == "cancelled"
    assert project.target_date == TEST_DATE + timedelta(days=1)
    assert call.target_date == TEST_DATE
    assert call.fixed_start == time(hour=19)
    assert_plan_has_no_overlaps(
        build_day_plan_result(db, gym.user, plan_date=TEST_DATE, now=TEST_NOW).day_plan,
        gym.user,
    )


def test_personal_task_starts_after_work_buffer(db: Session):
    process_user_message(db, "work-buffer-user", "Я работаю с 9 до 18", "web_text")
    response = process_user_message(
        db,
        "work-buffer-user",
        "Сегодня хочу разобрать документы",
        "web_text",
    )
    item = next(item for item in response.plan_summary.items if item.task_id)

    assert item.start_time == time(18, settings.plan_start_buffer_minutes)


def test_fixed_event_and_flexible_task_do_not_overlap_work_or_each_other(db: Session):
    process_user_message(db, "work-overlap-user", "Я работаю с 9 до 18", "web_text")
    fixed = process_user_message(
        db,
        "work-overlap-user",
        "Сегодня в 19:00 созвон на час",
        "web_text",
    )
    flexible = process_user_message(
        db,
        "work-overlap-user",
        "Сегодня хочу разобрать документы",
        "web_text",
    )
    items = {item.task_id: item for item in flexible.plan_summary.items}

    assert items[fixed.affected_tasks[0].id].start_time == time(19)
    assert items[flexible.affected_tasks[0].id].start_time == time(20)
    day_plan = db.query(DayPlan).one()
    user = db.query(User).filter_by(external_id="work-overlap-user").one()
    assert_plan_has_no_overlaps(day_plan, user)


def test_task_stays_unscheduled_when_work_and_sleep_leave_no_slot(db: Session):
    user = create_user(
        db,
        external_id="work-no-slot-user",
        work_start_time=time(9),
        work_end_time=time(22),
        sleep_time=time(23),
    )
    task = create_task(db, user, "Личная задача", estimated_minutes=60)

    result = build_day_plan_result(db, user, plan_date=TEST_DATE, now=TEST_NOW)
    item = next(item for item in result.day_plan.items if item.task_id == task.id)

    assert item.status == "not_scheduled"
    assert item.unscheduled_reason == "no_available_slot"
