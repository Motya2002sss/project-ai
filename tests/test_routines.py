from collections.abc import Generator
from datetime import date, datetime, time, timedelta, timezone
from time import perf_counter

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

import app.models  # noqa: F401
import app.services.planning_service as planning_service
import app.services.time_service as time_service
from app.core.config import settings
from app.db.base import Base
from app.models.routine import Routine
from app.models.interaction import PendingInteraction
from app.models.task import Task
from app.models.user import User
from app.services.message_service import process_user_message
from app.services.planning_service import assert_plan_has_no_overlaps, build_day_plan_result
from app.services.routine_service import create_routine, materialize_routine_occurrences


TEST_DATE = date(2026, 8, 3)  # Monday
TEST_NOW = datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc)


@pytest.fixture()
def db(tmp_path, monkeypatch) -> Generator[Session, None, None]:
    monkeypatch.setattr(settings, "llm_enabled", False)
    monkeypatch.setattr(settings, "llm_provider", "mock")
    monkeypatch.setattr(planning_service, "get_user_now", lambda user, now=None: now or TEST_NOW)
    monkeypatch.setattr(time_service, "get_user_now", lambda user, now=None: now or TEST_NOW)

    engine = create_engine(f"sqlite:///{tmp_path / 'routines.db'}")
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)

    with SessionLocal() as session:
        yield session

    Base.metadata.drop_all(engine)


def create_user(db: Session, external_id: str = "routine-user") -> User:
    user = User(external_id=external_id, timezone="UTC")
    db.add(user)
    db.flush()
    return user


def test_daily_routine_materialization_is_idempotent(db: Session):
    user = create_user(db)
    result = create_routine(
        db,
        user,
        title="Записывать БЖУ",
        cadence="daily",
        preferred_window="evening",
        estimated_minutes=10,
        start_date=TEST_DATE,
    )

    assert result.created is True
    assert len(result.occurrences) == 1

    materialize_routine_occurrences(db, user, TEST_DATE)
    build_day_plan_result(db, user, plan_date=TEST_DATE, now=TEST_NOW)

    occurrences = db.query(Task).filter(Task.routine_id == result.routine.id).all()
    assert len(occurrences) == 1
    assert occurrences[0].occurrence_date == TEST_DATE


def test_completed_occurrence_is_not_recreated(db: Session):
    user = create_user(db)
    result = create_routine(
        db,
        user,
        title="Принять лекарство",
        cadence="daily",
        preferred_window="morning",
        start_date=TEST_DATE,
    )
    occurrence = result.occurrences[0]
    occurrence.status = "done"
    db.commit()

    materialize_routine_occurrences(db, user, TEST_DATE)

    occurrences = db.query(Task).filter(Task.routine_id == result.routine.id).all()
    assert len(occurrences) == 1
    assert occurrences[0].status == "done"


def test_inactive_and_weekday_routines_respect_schedule(db: Session):
    user = create_user(db)
    inactive = create_routine(
        db,
        user,
        title="Вечерняя запись",
        cadence="daily",
        start_date=TEST_DATE,
    ).routine
    inactive.active = False
    weekday = create_routine(
        db,
        user,
        title="Учить английский",
        cadence="weekdays",
        start_date=TEST_DATE,
    ).routine
    db.commit()

    saturday = date(2026, 8, 8)
    materialize_routine_occurrences(db, user, saturday)

    assert not db.query(Task).filter(Task.routine_id == inactive.id, Task.target_date == saturday).all()
    assert not db.query(Task).filter(Task.routine_id == weekday.id, Task.target_date == saturday).all()


def test_bju_clarification_confirmation_and_routine_apply(db: Session):
    first = process_user_message(
        db,
        "bju-routine-user",
        "добавь бжу чтобы я считал",
        "web_text",
        request_id="bju-1",
    )
    assert first.status == "clarification_required"
    assert db.query(Task).count() == 0

    second = process_user_message(
        db,
        "bju-routine-user",
        "ежедневно вечером",
        "web_text",
        request_id="bju-2",
        interaction_id=first.clarification.id,
    )
    assert second.status == "confirmation_required"
    assert db.query(Routine).count() == 0

    applied = process_user_message(
        db,
        "bju-routine-user",
        "применить",
        "web_text",
        request_id="bju-3",
        interaction_id=second.confirmation.id,
        option_id="apply",
    )

    assert applied.status == "applied"
    assert applied.plan_diff.created_routine_ids
    assert len(applied.affected_routines) == 1
    assert applied.affected_routines[0].cadence == "daily"
    assert len(applied.day_snapshot.tasks) == 1
    assert applied.day_snapshot.tasks[0].routine_id == applied.affected_routines[0].id

    build_day_plan_result(
        db,
        db.query(User).filter(User.external_id == "bju-routine-user").one(),
        plan_date=TEST_DATE,
        now=TEST_NOW,
    )
    assert db.query(Task).count() == 1


def test_explicit_weekday_routine_goes_directly_to_confirmation(db: Session):
    proposal = process_user_message(
        db,
        "weekday-routine-user",
        "По будням учить английский вечером",
        "web_text",
        request_id="weekday-routine-1",
    )

    assert proposal.status == "confirmation_required"
    assert "По будням" in proposal.confirmation.summary

    applied = process_user_message(
        db,
        "weekday-routine-user",
        "применить",
        "web_text",
        request_id="weekday-routine-2",
        interaction_id=proposal.confirmation.id,
        option_id="apply",
    )

    assert applied.status == "applied"
    assert applied.affected_routines[0].cadence == "weekdays"


def test_routine_can_collect_exact_time_before_confirmation(db: Session):
    first = process_user_message(
        db,
        "exact-routine-user",
        "добавь бжу чтобы я считал",
        "web_text",
        request_id="exact-1",
    )
    timing = process_user_message(
        db,
        "exact-routine-user",
        "ежедневное напоминание",
        "web_text",
        request_id="exact-2",
        interaction_id=first.clarification.id,
        option_id="routine",
    )
    exact = process_user_message(
        db,
        "exact-routine-user",
        "точное время",
        "web_text",
        request_id="exact-3",
        interaction_id=timing.clarification.id,
        option_id="exact_time",
    )
    proposal = process_user_message(
        db,
        "exact-routine-user",
        "20",
        "web_text",
        request_id="exact-4",
        interaction_id=exact.clarification.id,
    )

    assert proposal.status == "confirmation_required"
    assert "20:00" in proposal.confirmation.summary

    applied = process_user_message(
        db,
        "exact-routine-user",
        "применить",
        "web_text",
        request_id="exact-5",
        interaction_id=proposal.confirmation.id,
        option_id="apply",
    )

    assert applied.status == "applied"
    assert applied.affected_routines[0].fixed_time == time(hour=20)
    assert applied.day_snapshot.tasks[0].scheduling_type == "fixed"


def test_expired_clarification_cannot_mutate_state(db: Session):
    first = process_user_message(
        db,
        "expired-routine-user",
        "добавь бжу чтобы я считал",
        "web_text",
        request_id="expired-1",
    )
    interaction = db.get(PendingInteraction, first.clarification.id)
    interaction.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()

    response = process_user_message(
        db,
        "expired-routine-user",
        "разовая задача",
        "web_text",
        request_id="expired-2",
        interaction_id=first.clarification.id,
        option_id="one_time",
    )

    assert response.status == "no_change"
    assert interaction.status == "expired"
    assert db.query(Task).count() == 0


def test_fixed_routine_occurrence_cannot_overlap_fixed_task(db: Session):
    user = create_user(db, "routine-conflict-user")
    db.add(
        Task(
            user_id=user.id,
            title="Созвон",
            priority="high",
            estimated_minutes=60,
            target_date=TEST_DATE,
            scheduling_type="fixed",
            fixed_start=time(hour=19),
            fixed_end=time(hour=20),
            is_locked=True,
            status="planned",
        )
    )
    db.flush()
    routine = create_routine(
        db,
        user,
        title="Записать итоги дня",
        cadence="daily",
        fixed_time=time(hour=19),
        start_date=TEST_DATE,
        commit=False,
    ).routine

    result = build_day_plan_result(db, user, plan_date=TEST_DATE, now=TEST_NOW)

    assert result.conflicts
    assert any(task_id in result.unscheduled_task_ids for task_id in [task.id for task in routine.occurrences])
    assert_plan_has_no_overlaps(result.day_plan, user)


def test_planning_thirty_tasks_stays_bounded_and_overlap_free(db: Session):
    user = create_user(db, "routine-performance-user")

    for index in range(30):
        db.add(
            Task(
                user_id=user.id,
                title=f"Задача {index + 1}",
                priority="medium",
                estimated_minutes=15,
                target_date=TEST_DATE,
                scheduling_type="flexible",
                status="planned",
            )
        )

    db.flush()
    started = perf_counter()
    result = build_day_plan_result(db, user, plan_date=TEST_DATE, now=TEST_NOW)
    elapsed = perf_counter() - started

    assert elapsed < 5
    assert_plan_has_no_overlaps(result.day_plan, user)
