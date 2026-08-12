from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.api.v2.planning import router as planning_router
from app.api.v2.dependencies import get_authenticated_request
from app.db.base import Base
from app.db.session import get_db
from app.models.calendar import CalendarBusyBlock, TemporaryLifeMode
from app.models.day_plan import DayPlan
from app.models.goal import Goal
from app.models.plan_change import PlanChange
from app.models.plan_item import PlanItem
from app.models.program import Program, WeeklyCommitment
from app.models.task import Task
from app.models.user import User
from app.services.plan_change_service import (
    PlanChangeConflict,
    TemporaryModeRequest,
    apply_replan,
)


UTC = timezone.utc
NOW = datetime(2026, 8, 11, 10, 0, tzinfo=UTC)
TODAY = NOW.date()
TOMORROW = TODAY + timedelta(days=1)


@pytest.fixture
def db(tmp_path: Path) -> Generator[Session, None, None]:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'adaptive.db'}")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session


def _user(db: Session, suffix: str = "owner") -> User:
    user = User(external_id=f"adaptive-{suffix}", timezone="UTC")
    db.add(user)
    db.commit()
    return user


def _task(
    db: Session,
    user: User,
    *,
    title: str,
    plan_date: date = TODAY,
    start: time | None,
    end: time | None,
    status: str = "planned",
    scheduling_type: str = "flexible",
    preferred_window: str | None = None,
    deadline: datetime | None = None,
    locked: bool = False,
) -> Task:
    duration = None
    if start is not None and end is not None:
        duration = (end.hour * 60 + end.minute) - (start.hour * 60 + start.minute)
    task = Task(
        user_id=user.id,
        title=title,
        target_date=plan_date,
        status=status,
        scheduling_type=scheduling_type,
        fixed_start=start if scheduling_type == "fixed" else None,
        fixed_end=end if scheduling_type == "fixed" else None,
        preferred_window=preferred_window,
        deadline=deadline,
        estimated_minutes=duration or 60,
        is_locked=locked,
    )
    db.add(task)
    db.flush()
    return task


def _plan(
    db: Session,
    user: User,
    *,
    plan_date: date,
    version: int,
    tasks: list[tuple[Task, time | None, time | None, str]],
) -> DayPlan:
    plan = DayPlan(
        user_id=user.id,
        date=plan_date,
        status="draft",
        version=version,
    )
    db.add(plan)
    db.flush()
    for task, start, end, item_status in tasks:
        plan.items.append(
            PlanItem(
                task_id=task.id,
                title=task.title,
                item_type="task",
                status=item_status,
                start_time=start,
                end_time=end,
                unscheduled_reason=None,
            )
        )
    db.commit()
    return plan


def _busy(
    db: Session,
    user: User,
    *,
    start: datetime,
    end: datetime,
    suffix: str,
) -> CalendarBusyBlock:
    block = CalendarBusyBlock(
        user_id=user.id,
        device_id="iphone",
        provider="apple",
        calendar_external_id="primary",
        external_id=f"event-{suffix}",
        occurrence_external_id=f"occurrence-{suffix}",
        occurrence_start=start,
        occurrence_end=end,
        device_timezone="UTC",
        source_revision="1",
        last_seen_client_revision=1,
    )
    db.add(block)
    db.commit()
    return block


def _item(db: Session, task_id: int) -> PlanItem:
    return db.scalar(select(PlanItem).where(PlanItem.task_id == task_id))


def test_replan_preserves_fixed_past_and_completed_but_moves_future_flexible(
    db: Session,
) -> None:
    user = _user(db)
    past = _task(db, user, title="Утреннее чтение", start=time(7), end=time(8))
    completed = _task(
        db,
        user,
        title="Завтрак",
        start=time(8),
        end=time(9),
        status="done",
    )
    fixed = _task(
        db,
        user,
        title="Врач",
        start=time(12),
        end=time(13),
        scheduling_type="fixed",
    )
    flexible = _task(
        db,
        user,
        title="Разобрать архитектуру",
        start=time(14),
        end=time(15),
        preferred_window="afternoon",
        deadline=datetime(2026, 8, 11, 17, 0, tzinfo=UTC),
    )
    _plan(
        db,
        user,
        plan_date=TODAY,
        version=4,
        tasks=[
            (past, time(7), time(8), "planned"),
            (completed, time(8), time(9), "done"),
            (fixed, time(12), time(13), "planned"),
            (flexible, time(14), time(15), "planned"),
        ],
    )
    _busy(
        db,
        user,
        start=datetime(2026, 8, 11, 14, 0, tzinfo=UTC),
        end=datetime(2026, 8, 11, 15, 0, tzinfo=UTC),
        suffix="new-meeting",
    )

    result = apply_replan(
        db,
        user=user,
        request_id="adaptive-preserve-1",
        base_versions={TODAY: 4},
        affected_dates=[TODAY],
        reason="calendar_sync",
        now=NOW,
    )

    assert result.status == "applied"
    assert result.base_versions == {TODAY.isoformat(): 4}
    assert result.result_versions == {TODAY.isoformat(): 5}
    assert (_item(db, past.id).start_time, _item(db, past.id).end_time) == (
        time(7),
        time(8),
    )
    assert (_item(db, completed.id).start_time, _item(db, completed.id).status) == (
        time(8),
        "done",
    )
    assert (_item(db, fixed.id).start_time, _item(db, fixed.id).end_time) == (
        time(12),
        time(13),
    )
    assert (_item(db, flexible.id).start_time, _item(db, flexible.id).end_time) == (
        time(13),
        time(14),
    )
    assert result.plan_diff["moved"] == [
        {
            "date": TODAY.isoformat(),
            "task_id": flexible.id,
            "old_start": "14:00:00",
            "old_end": "15:00:00",
            "new_start": "13:00:00",
            "new_end": "14:00:00",
        }
    ]


def test_past_fixed_interval_is_preserved_once_instead_of_becoming_unscheduled(
    db: Session,
) -> None:
    user = _user(db, "past-fixed")
    fixed = _task(
        db,
        user,
        title="Утренний приём",
        start=time(8),
        end=time(9),
        scheduling_type="fixed",
    )
    _plan(
        db,
        user,
        plan_date=TODAY,
        version=5,
        tasks=[(fixed, time(8), time(9), "planned")],
    )

    result = apply_replan(
        db,
        user=user,
        request_id="past-fixed-preservation",
        base_versions={TODAY: 5},
        affected_dates=[TODAY],
        reason="manual",
        now=NOW,
    )

    rows = db.scalars(select(PlanItem).where(PlanItem.task_id == fixed.id)).all()
    assert result.status == "no_change"
    assert len(rows) == 1
    assert rows[0].status == "planned"
    assert (rows[0].start_time, rows[0].end_time) == (time(8), time(9))


def test_no_change_replan_does_not_delete_or_insert_placement_rows(
    db: Session,
) -> None:
    user = _user(db, "placement-identity")
    task = _task(db, user, title="Стабильная задача", start=time(16), end=time(17))
    plan = _plan(
        db,
        user,
        plan_date=TODAY,
        version=5,
        tasks=[(task, time(16), time(17), "planned")],
    )
    original = _item(db, task.id)
    original_id = original.id
    statements: list[str] = []
    bind = db.get_bind()

    def capture_statement(
        _connection,
        _cursor,
        statement,
        _parameters,
        _context,
        _executemany,
    ) -> None:
        normalized = " ".join(statement.lower().split())
        if "plan_items" in normalized:
            statements.append(normalized)

    event.listen(bind, "before_cursor_execute", capture_statement)
    try:
        result = apply_replan(
            db,
            user=user,
            request_id="placement-identity-no-change",
            base_versions={TODAY: 5},
            affected_dates=[TODAY],
            reason="manual",
            now=NOW,
        )
    finally:
        event.remove(bind, "before_cursor_execute", capture_statement)

    db.expire_all()
    assert result.status == "no_change"
    assert db.get(DayPlan, plan.id).version == 5
    assert _item(db, task.id).id == original_id
    assert not any(
        statement.startswith("delete from plan_items")
        or statement.startswith("insert into plan_items")
        for statement in statements
    )


def test_fixed_placement_uses_persisted_fact_instead_of_task_field_drift(
    db: Session,
) -> None:
    user = _user(db, "fixed-drift")
    fixed = _task(
        db,
        user,
        title="Зафиксированная встреча",
        start=time(12),
        end=time(13),
        scheduling_type="fixed",
    )
    _plan(
        db,
        user,
        plan_date=TODAY,
        version=4,
        tasks=[(fixed, time(14), time(15), "planned")],
    )

    result = apply_replan(
        db,
        user=user,
        request_id="fixed-placement-drift",
        base_versions={TODAY: 4},
        affected_dates=[TODAY],
        reason="manual",
        now=NOW,
    )

    item = _item(db, fixed.id)
    assert result.status == "no_change"
    assert (item.start_time, item.end_time) == (time(14), time(15))


def test_locked_future_placement_is_preserved_without_fixed_time_fields(
    db: Session,
) -> None:
    user = _user(db, "locked")
    locked = _task(
        db,
        user,
        title="Не переносить",
        start=time(16),
        end=time(17),
        locked=True,
    )
    _plan(
        db,
        user,
        plan_date=TODAY,
        version=4,
        tasks=[(locked, time(16), time(17), "planned")],
    )

    result = apply_replan(
        db,
        user=user,
        request_id="locked-preservation",
        base_versions={TODAY: 4},
        affected_dates=[TODAY],
        reason="manual",
        now=NOW,
    )

    item = _item(db, locked.id)
    assert result.status == "no_change"
    assert item.status == "planned"
    assert (item.start_time, item.end_time) == (time(16), time(17))


def test_future_only_boundary_uses_the_users_local_date(db: Session) -> None:
    user = _user(db, "local-date")
    user.timezone = "America/Los_Angeles"
    local_date = date(2026, 8, 10)
    task = _task(
        db,
        user,
        title="Вечерняя задача",
        plan_date=local_date,
        start=time(20),
        end=time(21),
    )
    _plan(
        db,
        user,
        plan_date=local_date,
        version=2,
        tasks=[(task, time(20), time(21), "planned")],
    )

    result = apply_replan(
        db,
        user=user,
        request_id="local-date-boundary",
        base_versions={local_date: 2},
        affected_dates=[local_date],
        reason="manual",
        now=datetime(2026, 8, 11, 1, 0, tzinfo=UTC),
    )

    assert result.status == "no_change"
    assert result.affected_dates == [local_date.isoformat()]
    assert _item(db, task.id).start_time == time(20)


def test_unknown_non_task_placement_returns_conflict_instead_of_dropping_history(
    db: Session,
) -> None:
    user = _user(db, "non-task")
    task = _task(db, user, title="Будущая задача", start=time(16), end=time(17))
    plan = _plan(
        db,
        user,
        plan_date=TODAY,
        version=3,
        tasks=[(task, time(16), time(17), "planned")],
    )
    plan.items.append(
        PlanItem(
            task_id=None,
            title="Подъём",
            item_type="anchor",
            status="done",
            start_time=time(7),
            end_time=time(7, 15),
        )
    )
    db.commit()

    with pytest.raises(PlanChangeConflict) as conflict:
        apply_replan(
            db,
            user=user,
            request_id="non-task-safe-conflict",
            base_versions={TODAY: 3},
            affected_dates=[TODAY],
            reason="manual",
            now=NOW,
        )

    assert conflict.value.code == "unsupported_non_task_placement"
    db.expire_all()
    assert db.scalar(select(DayPlan).where(DayPlan.id == plan.id)).version == 3
    assert db.scalar(
        select(func.count(PlanItem.id)).where(PlanItem.day_plan_id == plan.id)
    ) == 2


def test_replan_never_places_a_flexible_action_after_its_deadline(
    db: Session,
) -> None:
    user = _user(db, "deadline")
    task = _task(
        db,
        user,
        title="Отправить документы",
        start=time(14),
        end=time(15),
        deadline=datetime(2026, 8, 11, 14, 0, tzinfo=UTC),
    )
    _plan(
        db,
        user,
        plan_date=TODAY,
        version=2,
        tasks=[(task, time(14), time(15), "planned")],
    )
    _busy(
        db,
        user,
        start=datetime(2026, 8, 11, 10, 0, tzinfo=UTC),
        end=datetime(2026, 8, 11, 14, 0, tzinfo=UTC),
        suffix="until-deadline",
    )

    result = apply_replan(
        db,
        user=user,
        request_id="deadline-safe",
        base_versions={TODAY: 2},
        affected_dates=[TODAY],
        reason="calendar_sync",
        now=NOW,
    )

    item = _item(db, task.id)
    assert item.status == "not_scheduled"
    assert item.start_time is None
    assert result.plan_diff["unscheduled"] == [
        {"date": TODAY.isoformat(), "task_id": task.id, "reason": "no_available_slot"}
    ]


def test_replan_keeps_commitment_recovery_gap_between_future_actions(
    db: Session,
) -> None:
    user = _user(db, "recovery-gap")
    goal = Goal(user_id=user.id, title="Сила", category="health", status="active")
    db.add(goal)
    db.flush()
    program = Program(
        user_id=user.id,
        goal_id=goal.id,
        name="Силовой цикл",
        status="active",
        minimum_minutes_week=60,
        comfortable_minutes_week=120,
        maximum_minutes_week=180,
        adaptation_rules={},
    )
    db.add(program)
    db.flush()
    commitment = WeeklyCommitment(
        user_id=user.id,
        goal_id=goal.id,
        program_id=program.id,
        title="Две сессии",
        target_minutes_week=120,
        target_sessions_week=2,
        minimum_block_minutes=60,
        allowed_weekdays=[2],
        splittable=False,
        recovery_gap_minutes=60,
        active=True,
    )
    db.add(commitment)
    db.flush()
    first = _task(db, user, title="Первая сессия", start=time(12), end=time(13))
    second = _task(db, user, title="Вторая сессия", start=time(13), end=time(14))
    first.goal_id = goal.id
    first.program_id = program.id
    first.commitment_id = commitment.id
    second.goal_id = goal.id
    second.program_id = program.id
    second.commitment_id = commitment.id
    _plan(
        db,
        user,
        plan_date=TODAY,
        version=6,
        tasks=[
            (first, time(12), time(13), "planned"),
            (second, time(13), time(14), "planned"),
        ],
    )
    _busy(
        db,
        user,
        start=datetime(2026, 8, 11, 10, 0, tzinfo=UTC),
        end=datetime(2026, 8, 11, 12, 0, tzinfo=UTC),
        suffix="before-recovery",
    )

    apply_replan(
        db,
        user=user,
        request_id="recovery-safe",
        base_versions={TODAY: 6},
        affected_dates=[TODAY],
        reason="calendar_sync",
        now=NOW,
    )

    assert (_item(db, first.id).start_time, _item(db, first.id).end_time) == (
        time(12),
        time(13),
    )
    assert (_item(db, second.id).start_time, _item(db, second.id).end_time) == (
        time(14),
        time(15),
    )


def test_replan_is_atomic_across_two_days_and_rolls_back_on_immutable_conflict(
    db: Session,
) -> None:
    user = _user(db, "atomic")
    first = _task(
        db,
        user,
        title="Гибкая задача сегодня",
        start=time(14),
        end=time(15),
    )
    fixed = _task(
        db,
        user,
        title="Фиксированное завтра",
        plan_date=TOMORROW,
        start=time(12),
        end=time(13),
        scheduling_type="fixed",
    )
    _plan(
        db,
        user,
        plan_date=TODAY,
        version=2,
        tasks=[(first, time(14), time(15), "planned")],
    )
    _plan(
        db,
        user,
        plan_date=TOMORROW,
        version=7,
        tasks=[(fixed, time(12), time(13), "planned")],
    )
    _busy(
        db,
        user,
        start=datetime(2026, 8, 11, 14, 0, tzinfo=UTC),
        end=datetime(2026, 8, 11, 15, 0, tzinfo=UTC),
        suffix="today",
    )
    _busy(
        db,
        user,
        start=datetime(2026, 8, 12, 12, 0, tzinfo=UTC),
        end=datetime(2026, 8, 12, 13, 0, tzinfo=UTC),
        suffix="fixed-conflict",
    )

    with pytest.raises(PlanChangeConflict) as caught:
        apply_replan(
            db,
            user=user,
            request_id="atomic-conflict",
            base_versions={TODAY: 2, TOMORROW: 7},
            affected_dates=[TOMORROW, TODAY],
            reason="calendar_sync",
            now=NOW,
        )

    assert caught.value.code == "immutable_interval_conflict"
    db.expire_all()
    assert db.scalar(select(DayPlan).where(DayPlan.date == TODAY)).version == 2
    assert _item(db, first.id).start_time == time(14)
    assert db.scalar(select(DayPlan).where(DayPlan.date == TOMORROW)).version == 7
    assert _item(db, fixed.id).start_time == time(12)
    assert db.scalar(select(func.count(PlanChange.id))) == 0


def test_two_day_replan_returns_factual_snapshots_and_unscheduled_diff(
    db: Session,
) -> None:
    user = _user(db, "two-days")
    today_task = _task(
        db,
        user,
        title="Только днём",
        start=time(14),
        end=time(15),
        preferred_window="afternoon",
    )
    tomorrow_task = _task(
        db,
        user,
        title="Задача завтра",
        plan_date=TOMORROW,
        start=time(16),
        end=time(17),
        preferred_window="afternoon",
    )
    _plan(
        db,
        user,
        plan_date=TODAY,
        version=1,
        tasks=[(today_task, time(14), time(15), "planned")],
    )
    _plan(
        db,
        user,
        plan_date=TOMORROW,
        version=3,
        tasks=[(tomorrow_task, time(16), time(17), "planned")],
    )
    _busy(
        db,
        user,
        start=datetime(2026, 8, 11, 12, 0, tzinfo=UTC),
        end=datetime(2026, 8, 11, 17, 0, tzinfo=UTC),
        suffix="today-window",
    )
    _busy(
        db,
        user,
        start=datetime(2026, 8, 12, 16, 0, tzinfo=UTC),
        end=datetime(2026, 8, 12, 17, 0, tzinfo=UTC),
        suffix="tomorrow-hour",
    )

    result = apply_replan(
        db,
        user=user,
        request_id="two-day-result",
        base_versions={TODAY: 1, TOMORROW: 3},
        affected_dates=[TODAY, TOMORROW],
        reason="calendar_sync",
        now=NOW,
    )

    assert result.result_versions == {
        TODAY.isoformat(): 2,
        TOMORROW.isoformat(): 4,
    }
    assert result.plan_diff["unscheduled"] == [
        {"date": TODAY.isoformat(), "task_id": today_task.id, "reason": "no_available_slot"}
    ]
    assert result.plan_diff["moved"] == [
        {
            "date": TOMORROW.isoformat(),
            "task_id": tomorrow_task.id,
            "old_start": "16:00:00",
            "old_end": "17:00:00",
            "new_start": "12:00:00",
            "new_end": "13:00:00",
        }
    ]
    assert [snapshot["date"] for snapshot in result.snapshots] == [
        TODAY.isoformat(),
        TOMORROW.isoformat(),
    ]
    assert [snapshot["version"] for snapshot in result.snapshots] == [2, 4]


def test_stale_versions_and_request_id_payload_reuse_are_typed_conflicts(
    db: Session,
) -> None:
    user = _user(db, "idempotency")
    task = _task(db, user, title="Гибкая", start=time(14), end=time(15))
    _plan(
        db,
        user,
        plan_date=TODAY,
        version=8,
        tasks=[(task, time(14), time(15), "planned")],
    )

    with pytest.raises(PlanChangeConflict) as stale:
        apply_replan(
            db,
            user=user,
            request_id="stale-version",
            base_versions={TODAY: 7},
            affected_dates=[TODAY],
            reason="manual",
            now=NOW,
        )
    assert stale.value.code == "stale_plan_version"

    first = apply_replan(
        db,
        user=user,
        request_id="same-request",
        base_versions={TODAY: 8},
        affected_dates=[TODAY],
        reason="manual",
        now=NOW,
    )
    replay = apply_replan(
        db,
        user=user,
        request_id="same-request",
        base_versions={TODAY: 8},
        affected_dates=[TODAY],
        reason="manual",
        now=NOW,
    )
    assert replay == first
    assert db.scalar(select(func.count(PlanChange.id))) == 1

    with pytest.raises(PlanChangeConflict) as reused:
        apply_replan(
            db,
            user=user,
            request_id="same-request",
            base_versions={TODAY: 8},
            affected_dates=[TODAY],
            reason="capacity_change",
            now=NOW,
        )
    assert reused.value.code == "idempotency_conflict"


def test_temporary_mode_reason_requires_a_typed_mode_payload(db: Session) -> None:
    user = _user(db, "mode-contract")
    task = _task(db, user, title="Задача", start=time(16), end=time(17))
    _plan(
        db,
        user,
        plan_date=TODAY,
        version=1,
        tasks=[(task, time(16), time(17), "planned")],
    )

    with pytest.raises(PlanChangeConflict) as missing:
        apply_replan(
            db,
            user=user,
            request_id="missing-mode-payload",
            base_versions={TODAY: 1},
            affected_dates=[TODAY],
            reason="temporary_mode",
            now=NOW,
        )

    assert missing.value.code == "invalid_temporary_mode_request"


def test_temporary_mode_requires_every_overlapped_local_date_in_version_scope(
    db: Session,
) -> None:
    user = _user(db, "mode-date-scope")
    task = _task(db, user, title="Сегодня", start=time(16), end=time(17))
    _plan(
        db,
        user,
        plan_date=TODAY,
        version=1,
        tasks=[(task, time(16), time(17), "planned")],
    )

    with pytest.raises(PlanChangeConflict) as scope:
        apply_replan(
            db,
            user=user,
            request_id="mode-outside-version-scope",
            base_versions={TODAY: 1},
            affected_dates=[TODAY],
            reason="temporary_mode",
            temporary_mode=TemporaryModeRequest(
                mode="travel",
                starts_at=datetime(2026, 8, 12, 8, 0, tzinfo=UTC),
                ends_at=datetime(2026, 8, 12, 20, 0, tzinfo=UTC),
                constraints={},
            ),
            now=NOW,
        )

    assert scope.value.code == "invalid_temporary_mode_dates"


def test_plan_diff_reports_a_changed_unscheduled_reason(db: Session) -> None:
    user = _user(db, "unscheduled-reason")
    task = _task(db, user, title="Нужно уточнить", start=None, end=None)
    task.scheduling_type = "unscheduled"
    plan = _plan(
        db,
        user,
        plan_date=TODAY,
        version=2,
        tasks=[(task, None, None, "not_scheduled")],
    )
    plan.items[0].unscheduled_reason = "legacy_reason"
    db.commit()

    result = apply_replan(
        db,
        user=user,
        request_id="unscheduled-reason-change",
        base_versions={TODAY: 2},
        affected_dates=[TODAY],
        reason="manual",
        now=NOW,
    )

    assert result.plan_diff["unscheduled"] == [
        {
            "date": TODAY.isoformat(),
            "task_id": task.id,
            "reason": "needs_clarification",
        }
    ]


@pytest.mark.parametrize(
    "mode",
    [
        "normal",
        "workload",
        "recovery",
        "sick",
        "travel",
        "vacation",
        "low_sleep",
        "focus_sprint",
    ],
)
def test_temporary_modes_are_typed_dated_and_do_not_destroy_permanent_routine(
    db: Session,
    mode: str,
) -> None:
    user = _user(db, f"mode-{mode}")
    user.work_start_time = time(9)
    user.work_end_time = time(18)
    user.sleep_time = time(23)
    task = _task(db, user, title="Вечерний блок", start=time(19), end=time(20))
    _plan(
        db,
        user,
        plan_date=TODAY,
        version=1,
        tasks=[(task, time(19), time(20), "planned")],
    )
    mode_request = TemporaryModeRequest(
        mode=mode,
        starts_at=datetime(2026, 8, 11, 18, 0, tzinfo=UTC),
        ends_at=datetime(2026, 8, 11, 21, 0, tzinfo=UTC),
        constraints={
            "blocked_intervals": [
                {
                    "start": "2026-08-11T18:00:00+00:00",
                    "end": "2026-08-11T21:00:00+00:00",
                }
            ]
        },
    )

    result = apply_replan(
        db,
        user=user,
        request_id=f"mode-{mode}-request",
        base_versions={TODAY: 1},
        affected_dates=[TODAY],
        reason="temporary_mode",
        temporary_mode=mode_request,
        now=NOW,
    )

    saved_mode = db.scalar(select(TemporaryLifeMode))
    assert result.status == "applied"
    assert saved_mode is not None
    assert saved_mode.mode == mode
    assert saved_mode.status == "active"
    assert user.work_start_time == time(9)
    assert user.work_end_time == time(18)
    assert user.sleep_time == time(23)
    moved = _item(db, task.id)
    assert moved.end_time <= time(18) or moved.start_time >= time(21)


def test_temporary_mode_capacity_limit_unschedules_only_excess_future_load(
    db: Session,
) -> None:
    user = _user(db, "mode-capacity")
    first = _task(db, user, title="Главный блок", start=time(18), end=time(19))
    second = _task(db, user, title="Лишний блок", start=time(19), end=time(20))
    _plan(
        db,
        user,
        plan_date=TODAY,
        version=2,
        tasks=[
            (first, time(18), time(19), "planned"),
            (second, time(19), time(20), "planned"),
        ],
    )

    result = apply_replan(
        db,
        user=user,
        request_id="mode-capacity-request",
        base_versions={TODAY: 2},
        affected_dates=[TODAY],
        reason="temporary_mode",
        temporary_mode=TemporaryModeRequest(
            mode="recovery",
            starts_at=datetime(2026, 8, 11, 10, 0, tzinfo=UTC),
            ends_at=datetime(2026, 8, 11, 23, 0, tzinfo=UTC),
            constraints={"max_flexible_minutes": 60},
        ),
        now=NOW,
    )

    assert _item(db, first.id).status == "planned"
    assert _item(db, second.id).status == "not_scheduled"
    assert result.plan_diff["unscheduled"] == [
        {
            "date": TODAY.isoformat(),
            "task_id": second.id,
            "reason": "capacity_limit",
        }
    ]


def test_api_requires_authenticated_session_and_rejects_user_selection(
    tmp_path: Path,
) -> None:
    api_day = datetime.now(timezone.utc).date() + timedelta(days=1)
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'adaptive-api.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def override_db():
        with factory() as session:
            yield session

    application = FastAPI()
    v2 = APIRouter(prefix="/api/v2")
    v2.include_router(planning_router)
    application.include_router(v2)
    application.dependency_overrides[get_db] = override_db

    with TestClient(application) as client:
        unauthorized = client.post(
            "/api/v2/planning/replan",
            json={
                "request_id": "unauthenticated-replan",
                "reason": "manual",
                "affected_dates": [api_day.isoformat()],
                "base_versions": {api_day.isoformat(): 0},
                "user_id": 999,
            },
        )

        with factory() as db:
            user = _user(db, "api-owner")
            task = _task(
                db,
                user,
                title="API задача",
                plan_date=api_day,
                start=time(16),
                end=time(17),
            )
            _plan(
                db,
                user,
                plan_date=api_day,
                version=2,
                tasks=[(task, time(16), time(17), "planned")],
            )
        application.dependency_overrides[get_authenticated_request] = (
            lambda: SimpleNamespace(user=user)
        )
        rejected_owner = client.post(
            "/api/v2/planning/replan",
            json={
                "request_id": "owner-selection",
                "reason": "manual",
                "affected_dates": [api_day.isoformat()],
                "base_versions": {api_day.isoformat(): 2},
                "user_id": 999,
            },
        )
        applied = client.post(
            "/api/v2/planning/replan",
            json={
                "request_id": "authenticated-replan",
                "reason": "manual",
                "affected_dates": [api_day.isoformat()],
                "base_versions": {api_day.isoformat(): 2},
            },
        )

    assert unauthorized.status_code == 401
    assert rejected_owner.status_code == 422
    assert applied.status_code == 200, applied.text
    assert applied.json()["status"] == "no_change"


def test_concurrent_sqlite_retry_with_same_request_returns_one_factual_result(
    tmp_path: Path,
) -> None:
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'adaptive-concurrent.db'}",
        connect_args={"check_same_thread": False, "timeout": 0.05},
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as setup:
        user = _user(setup, "concurrent")
        task = _task(setup, user, title="Одна задача", start=time(16), end=time(17))
        _plan(
            setup,
            user,
            plan_date=TODAY,
            version=3,
            tasks=[(task, time(16), time(17), "planned")],
        )
        user_id = user.id

    start = Barrier(2)

    def submit() -> object:
        with factory() as worker:
            owned = worker.get(User, user_id)
            start.wait(timeout=2)
            return apply_replan(
                worker,
                user=owned,
                request_id="concurrent-same-request",
                base_versions={TODAY: 3},
                affected_dates=[TODAY],
                reason="manual",
                now=NOW,
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _index: submit(), range(2)))

    assert results[0] == results[1]
    with factory() as verify:
        assert verify.scalar(select(func.count(PlanChange.id))) == 1
        assert verify.scalar(select(DayPlan.version)) == 3


def test_partial_day_capacity_limit_only_applies_inside_mode_interval(
    db: Session,
) -> None:
    user = _user(db, "partial-capacity")
    morning = _task(db, user, title="Внутри режима", start=time(10), end=time(11))
    boundary = _task(db, user, title="На границе", start=time(12), end=time(13))
    evening = _task(db, user, title="Вечером", start=time(18), end=time(19))
    _plan(
        db,
        user,
        plan_date=TODAY,
        version=3,
        tasks=[
            (morning, time(10), time(11), "planned"),
            (boundary, time(12), time(13), "planned"),
            (evening, time(18), time(19), "planned"),
        ],
    )

    apply_replan(
        db,
        user=user,
        request_id="partial-capacity-window",
        base_versions={TODAY: 3},
        affected_dates=[TODAY],
        reason="temporary_mode",
        temporary_mode=TemporaryModeRequest(
            mode="workload",
            starts_at=datetime(2026, 8, 11, 10, 0, tzinfo=UTC),
            ends_at=datetime(2026, 8, 11, 12, 0, tzinfo=UTC),
            constraints={"max_flexible_minutes": 0},
        ),
        now=NOW,
    )

    moved_morning = _item(db, morning.id)
    assert moved_morning.status in {"planned", "not_scheduled"}
    if moved_morning.status == "planned":
        assert moved_morning.start_time >= time(12)
    assert (_item(db, boundary.id).start_time, _item(db, boundary.id).end_time) == (
        time(12),
        time(13),
    )
    assert (_item(db, evening.id).start_time, _item(db, evening.id).end_time) == (
        time(18),
        time(19),
    )


def test_partial_day_reserve_only_consumes_capacity_inside_mode_interval(
    db: Session,
) -> None:
    user = _user(db, "partial-reserve")
    first = _task(db, user, title="Первый", start=time(10), end=time(11))
    second = _task(db, user, title="Второй", start=time(11), end=time(12))
    boundary = _task(db, user, title="После режима", start=time(12), end=time(13))
    evening = _task(db, user, title="Вечером", start=time(18), end=time(19))
    _plan(
        db,
        user,
        plan_date=TODAY,
        version=4,
        tasks=[
            (first, time(10), time(11), "planned"),
            (second, time(11), time(12), "planned"),
            (boundary, time(12), time(13), "planned"),
            (evening, time(18), time(19), "planned"),
        ],
    )

    apply_replan(
        db,
        user=user,
        request_id="partial-reserve-window",
        base_versions={TODAY: 4},
        affected_dates=[TODAY],
        reason="temporary_mode",
        temporary_mode=TemporaryModeRequest(
            mode="recovery",
            starts_at=datetime(2026, 8, 11, 10, 0, tzinfo=UTC),
            ends_at=datetime(2026, 8, 11, 12, 0, tzinfo=UTC),
            constraints={"reserve_minutes": 60},
        ),
        now=NOW,
    )

    assert _item(db, first.id).status == "planned"
    moved_second = _item(db, second.id)
    assert moved_second.status in {"planned", "not_scheduled"}
    if moved_second.status == "planned":
        assert moved_second.start_time >= time(12)
    assert (_item(db, boundary.id).start_time, _item(db, boundary.id).end_time) == (
        time(12),
        time(13),
    )
    assert (_item(db, evening.id).start_time, _item(db, evening.id).end_time) == (
        time(18),
        time(19),
    )


def test_temporary_mode_horizon_is_bounded_before_date_expansion(db: Session) -> None:
    user = _user(db, "bounded-mode-horizon")

    with pytest.raises(PlanChangeConflict) as conflict:
        apply_replan(
            db,
            user=user,
            request_id="multi-year-mode",
            base_versions={TODAY: 0},
            affected_dates=[TODAY],
            reason="temporary_mode",
            temporary_mode=TemporaryModeRequest(
                mode="travel",
                starts_at=NOW,
                ends_at=datetime(9999, 1, 1, tzinfo=UTC),
                constraints={},
            ),
            now=NOW,
        )

    assert conflict.value.code == "temporary_mode_horizon_exceeded"
    assert db.scalar(select(func.count(TemporaryLifeMode.id))) == 0


def test_extreme_mode_end_in_positive_offset_user_timezone_is_typed_and_atomic(
    db: Session,
) -> None:
    user = _user(db, "extreme-positive-offset")
    user.timezone = "Pacific/Kiritimati"
    db.commit()
    local_date = TOMORROW

    with pytest.raises(PlanChangeConflict) as conflict:
        apply_replan(
            db,
            user=user,
            request_id="extreme-positive-offset-mode",
            base_versions={local_date: 0},
            affected_dates=[local_date],
            reason="temporary_mode",
            temporary_mode=TemporaryModeRequest(
                mode="travel",
                starts_at=NOW,
                ends_at=datetime(9999, 12, 31, 23, 59, tzinfo=UTC),
                constraints={},
            ),
            now=NOW,
        )

    assert conflict.value.code == "temporary_mode_horizon_exceeded"
    assert db.scalar(select(func.count(TemporaryLifeMode.id))) == 0
    assert db.scalar(select(func.count(PlanChange.id))) == 0


def test_planning_api_rejects_coerced_versions_without_mutation(
    tmp_path: Path,
) -> None:
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'strict-version-api.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def override_db():
        with factory() as session:
            yield session

    with factory() as setup:
        user = _user(setup, "strict-version-api")
        user.timezone = "Pacific/Kiritimati"
        setup.commit()

    application = FastAPI()
    v2 = APIRouter(prefix="/api/v2")
    v2.include_router(planning_router)
    application.include_router(v2)
    application.dependency_overrides[get_db] = override_db
    application.dependency_overrides[get_authenticated_request] = (
        lambda: SimpleNamespace(user=user)
    )
    operation_now = datetime.now(UTC)
    today = operation_now.astimezone(ZoneInfo(user.timezone)).date().isoformat()

    with TestClient(application) as client:
        responses = [
            client.post(
                "/api/v2/planning/replan",
                json={
                    "request_id": "strict-base-string",
                    "reason": "manual",
                    "affected_dates": [today],
                    "base_versions": {today: "0"},
                },
            ),
            client.post(
                "/api/v2/planning/replan",
                json={
                    "request_id": "strict-base-bool",
                    "reason": "manual",
                    "affected_dates": [today],
                    "base_versions": {today: True},
                },
            ),
            client.post(
                "/api/v2/planning/replan",
                json={
                    "request_id": "strict-base-overflow",
                    "reason": "manual",
                    "affected_dates": [today],
                    "base_versions": {today: 2_147_483_648},
                },
            ),
            client.post(
                "/api/v2/planning/plan-changes/00000000-0000-4000-8000-000000000001/undo",
                json={"request_id": "strict-undo-string", "expected_version": "0"},
            ),
            client.post(
                "/api/v2/planning/plan-changes/00000000-0000-4000-8000-000000000001/undo",
                json={"request_id": "strict-undo-bool", "expected_version": True},
            ),
            client.post(
                "/api/v2/planning/plan-changes/00000000-0000-4000-8000-000000000001/undo",
                json={
                    "request_id": "strict-undo-map-string",
                    "expected_version": {today: "0"},
                },
            ),
            client.post(
                "/api/v2/planning/plan-changes/00000000-0000-4000-8000-000000000001/undo",
                json={
                    "request_id": "strict-undo-overflow",
                    "expected_version": 2_147_483_648,
                },
            ),
        ]
        extreme = client.post(
            "/api/v2/planning/replan",
            json={
                "request_id": "extreme-positive-offset-api",
                "reason": "temporary_mode",
                "affected_dates": [today],
                "base_versions": {today: 0},
                "temporary_mode": {
                    "mode": "travel",
                    "starts_at": operation_now.isoformat(),
                    "ends_at": "9999-12-31T23:59:00Z",
                    "constraints": {},
                },
            },
        )

    assert [response.status_code for response in responses] == [422] * len(responses)
    assert extreme.status_code == 409
    assert extreme.json()["detail"]["code"] == "temporary_mode_horizon_exceeded"
    with factory() as verification:
        assert verification.scalar(select(func.count(PlanChange.id))) == 0
        assert verification.scalar(select(func.count(DayPlan.id))) == 0


def test_database_rejects_duplicate_task_placements_before_plan_mutation(
    db: Session,
) -> None:
    user = _user(db, "duplicate-placement")
    task = _task(db, user, title="Дубликат", start=time(16), end=time(17))
    plan = _plan(
        db,
        user,
        plan_date=TODAY,
        version=7,
        tasks=[(task, time(16), time(17), "planned")],
    )
    plan.items.append(
        PlanItem(
            task_id=task.id,
            title=task.title,
            item_type="task",
            status="planned",
            start_time=time(18),
            end_time=time(19),
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

    db.expire_all()
    saved = db.get(DayPlan, plan.id)
    assert saved.version == 7
    assert len(saved.items) == 1
    assert saved.items[0].task_id == task.id
    assert db.scalar(select(func.count(PlanChange.id))) == 0
