from collections.abc import Generator
from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

import app.models  # noqa: F401
import app.services.planning_service as planning_service
from app.db.base import Base
from app.models.goal import Goal
from app.models.onboarding import ResourceBudget
from app.models.program import Program, ProgramPhase, WeeklyCommitment
from app.models.task import Task
from app.models.user import User
from app.schemas.goals import ProgramCommitmentInput, ProgramProposalInput
from app.services.planning_service import build_day_plan_result
from app.services.routine_service import materialize_weekly_commitments


WEEK_START = date(2026, 8, 3)
NOW = datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def db(tmp_path, monkeypatch) -> Generator[Session, None, None]:
    monkeypatch.setattr(
        planning_service, "get_user_now", lambda user, now=None: now or NOW
    )
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'commitments.db'}")
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with factory() as session:
        yield session


def create_program(
    db: Session,
    *,
    capacity: int = 480,
    available_days: list[int] | None = None,
) -> tuple[User, Goal, Program, ProgramPhase]:
    user = User(external_id="weekly-commitment-user", timezone="UTC")
    db.add(user)
    db.flush()
    db.add(
        ResourceBudget(
            user_id=user.id,
            weekly_available_minutes=capacity * 5 // 4,
            available_days=available_days or [1, 2, 3, 4, 5, 6, 7],
            minimum_minutes=0,
            comfortable_minutes=capacity,
            maximum_minutes=capacity,
            free_evenings=[],
            preferred_windows={},
            reserve_percent=20,
            allocatable_minutes=capacity,
            allocation={},
        )
    )
    goal = Goal(
        user_id=user.id,
        title="Подготовиться к полумарафону",
        status="active",
        outcome_type="consistency",
    )
    db.add(goal)
    db.flush()
    program = Program(
        user_id=user.id,
        goal_id=goal.id,
        name="Базовый цикл",
        status="active",
        minimum_minutes_week=60,
        comfortable_minutes_week=capacity,
        maximum_minutes_week=capacity,
        adaptation_rules={},
    )
    db.add(program)
    db.flush()
    phase = ProgramPhase(
        user_id=user.id,
        program_id=program.id,
        title="Основа",
        position=1,
        status="active",
        start_date=WEEK_START,
        end_date=WEEK_START + timedelta(days=28),
        configuration={},
    )
    db.add(phase)
    db.flush()
    return user, goal, program, phase


def add_commitment(
    db: Session,
    *,
    user: User,
    goal: Goal,
    program: Program,
    phase: ProgramPhase,
    title: str = "Беговая тренировка",
    minutes: int = 120,
    sessions: int = 3,
    minimum_block: int = 30,
    weekdays: list[int] | None = None,
    preferred_window: str | None = "evening",
    splittable: bool = True,
    recovery_gap: int = 60,
    commitment_id: UUID | None = None,
) -> WeeklyCommitment:
    commitment = WeeklyCommitment(
        id=commitment_id,
        user_id=user.id,
        goal_id=goal.id,
        program_id=program.id,
        phase_id=phase.id,
        title=title,
        target_minutes_week=minutes,
        target_sessions_week=sessions,
        minimum_block_minutes=minimum_block,
        allowed_weekdays=weekdays or [1, 3, 5],
        preferred_window=preferred_window,
        splittable=splittable,
        recovery_gap_minutes=recovery_gap,
        active=True,
    )
    db.add(commitment)
    db.commit()
    return commitment


def test_materialization_uses_allowed_days_window_links_and_is_idempotent(
    db: Session,
) -> None:
    user, goal, program, phase = create_program(db)
    commitment = add_commitment(
        db, user=user, goal=goal, program=program, phase=phase
    )

    first = materialize_weekly_commitments(db, user, WEEK_START, now=NOW)
    first.created_tasks[0].status = "done"
    db.commit()
    second = materialize_weekly_commitments(db, user, WEEK_START, now=NOW)
    tasks = (
        db.query(Task)
        .filter(Task.user_id == user.id, Task.commitment_id == commitment.id)
        .order_by(Task.target_date, Task.id)
        .all()
    )

    assert [task.target_date.isoweekday() for task in tasks] == [1, 3, 5]
    assert [task.estimated_minutes for task in tasks] == [40, 40, 40]
    assert all(task.preferred_window == "evening" for task in tasks)
    assert all(task.goal_id == goal.id for task in tasks)
    assert all(task.program_id == program.id for task in tasks)
    assert all(task.commitment_id == commitment.id for task in tasks)
    assert tasks[0].status == "done"
    assert len(first.created_tasks) == 3
    assert second.created_tasks == []
    assert second.shortfalls == []


def test_splittable_and_unsplittable_minimum_blocks(db: Session) -> None:
    user, goal, program, phase = create_program(db)
    split = add_commitment(
        db,
        user=user,
        goal=goal,
        program=program,
        phase=phase,
        title="Разобрать технику",
        minutes=90,
        sessions=0,
        minimum_block=30,
        weekdays=[1],
        splittable=True,
        recovery_gap=0,
    )
    unsplit = add_commitment(
        db,
        user=user,
        goal=goal,
        program=program,
        phase=phase,
        title="Длинная тренировка",
        minutes=90,
        sessions=0,
        minimum_block=30,
        weekdays=[2],
        splittable=False,
        recovery_gap=0,
    )

    result = materialize_weekly_commitments(db, user, WEEK_START, now=NOW)
    split_tasks = [task for task in result.created_tasks if task.commitment_id == split.id]
    unsplit_tasks = [task for task in result.created_tasks if task.commitment_id == unsplit.id]

    assert [task.estimated_minutes for task in split_tasks] == [30, 30, 30]
    assert [task.target_date.isoweekday() for task in split_tasks] == [1, 1, 1]
    assert [task.estimated_minutes for task in unsplit_tasks] == [90]
    assert unsplit_tasks[0].target_date.isoweekday() == 2
    assert result.shortfalls == []


def test_split_load_never_exceeds_declared_minutes(db: Session) -> None:
    user, goal, program, phase = create_program(db)
    commitment = add_commitment(
        db,
        user=user,
        goal=goal,
        program=program,
        phase=phase,
        minutes=100,
        sessions=0,
        minimum_block=30,
        weekdays=[1],
        splittable=True,
        recovery_gap=0,
    )

    result = materialize_weekly_commitments(db, user, WEEK_START, now=NOW)
    durations = [
        task.estimated_minutes
        for task in result.created_tasks
        if task.commitment_id == commitment.id
    ]

    assert durations == [34, 33, 33]
    assert sum(duration or 0 for duration in durations) == 100
    assert result.shortfalls == []


def test_session_only_commitment_uses_minimum_blocks_and_counts_toward_capacity(
    db: Session,
) -> None:
    session_only = ProgramCommitmentInput(
        title="Три коротких практики",
        target_minutes_week=0,
        target_sessions_week=3,
        minimum_block_minutes=30,
        allowed_weekdays=[1, 3, 5],
    )
    with pytest.raises(ValidationError, match="minimum blocks"):
        ProgramCommitmentInput(
            title="Противоречивая нагрузка",
            target_minutes_week=100,
            target_sessions_week=4,
            minimum_block_minutes=30,
            allowed_weekdays=[1, 3, 5],
        )
    with pytest.raises(ValidationError, match="commitments exceed"):
        ProgramProposalInput(
            name="Перегруженная программа",
            minimum_minutes_week=0,
            comfortable_minutes_week=60,
            maximum_minutes_week=60,
            commitments=[session_only],
        )
    user, goal, program, phase = create_program(db)
    commitment = add_commitment(
        db,
        user=user,
        goal=goal,
        program=program,
        phase=phase,
        minutes=0,
        sessions=3,
        minimum_block=30,
        weekdays=[1, 3, 5],
    )

    result = materialize_weekly_commitments(db, user, WEEK_START, now=NOW)

    assert [
        task.estimated_minutes
        for task in result.created_tasks
        if task.commitment_id == commitment.id
    ] == [30, 30, 30]
    assert result.shortfalls == []


def test_recovery_gap_is_enforced_between_real_plan_intervals(db: Session) -> None:
    user, goal, program, phase = create_program(db)
    commitment = add_commitment(
        db,
        user=user,
        goal=goal,
        program=program,
        phase=phase,
        minutes=90,
        sessions=3,
        minimum_block=30,
        weekdays=[1],
        recovery_gap=60,
    )

    materialized = materialize_weekly_commitments(db, user, WEEK_START, now=NOW)
    result = build_day_plan_result(db, user, plan_date=WEEK_START, now=NOW)
    intervals = sorted(
        (
            item.start_time,
            item.end_time,
        )
        for item in result.day_plan.items
        if item.task is not None and item.task.commitment_id == commitment.id
    )

    assert len(materialized.created_tasks) == 3
    assert materialized.shortfalls == []
    assert len(intervals) == 3
    for previous, current in zip(intervals, intervals[1:]):
        previous_end = previous[1].hour * 60 + previous[1].minute
        current_start = current[0].hour * 60 + current[0].minute
        assert current_start - previous_end >= 60
    assert result.commitment_shortfalls == []


def test_reserved_capacity_is_never_materialized_as_available(db: Session) -> None:
    user, goal, program, phase = create_program(db, capacity=240)
    goal.priority = "low"
    low = add_commitment(
        db,
        user=user,
        goal=goal,
        program=program,
        phase=phase,
        title="Низкий приоритет",
        minutes=180,
        sessions=3,
        minimum_block=60,
        commitment_id=UUID("00000000-0000-0000-0000-000000000001"),
    )
    initial = materialize_weekly_commitments(db, user, WEEK_START, now=NOW)
    assert sum(task.estimated_minutes or 0 for task in initial.created_tasks) == 180

    high_goal = Goal(
        user_id=user.id,
        title="Приоритетное направление",
        status="active",
        priority="high",
        outcome_type="consistency",
    )
    db.add(high_goal)
    db.flush()
    high_program = Program(
        user_id=user.id,
        goal_id=high_goal.id,
        name="Приоритетная программа",
        status="active",
        minimum_minutes_week=60,
        comfortable_minutes_week=240,
        maximum_minutes_week=240,
        adaptation_rules={},
    )
    db.add(high_program)
    db.flush()
    high_phase = ProgramPhase(
        user_id=user.id,
        program_id=high_program.id,
        title="Приоритетная фаза",
        position=1,
        status="planned",
        start_date=WEEK_START,
        end_date=WEEK_START + timedelta(days=28),
        configuration={},
    )
    db.add(high_phase)
    db.flush()
    high = add_commitment(
        db,
        user=user,
        goal=high_goal,
        program=high_program,
        phase=high_phase,
        title="Высокий приоритет",
        minutes=180,
        sessions=3,
        minimum_block=60,
        commitment_id=UUID("00000000-0000-0000-0000-000000000002"),
    )

    result = materialize_weekly_commitments(db, user, WEEK_START, now=NOW)

    active_loads: dict[UUID, int] = {
        commitment_id: sum(
            task.estimated_minutes or 0
            for task in db.query(Task).filter(
                Task.commitment_id == commitment_id,
                Task.status.in_(["planned", "done"]),
            )
        )
        for commitment_id in (low.id, high.id)
    }
    assert active_loads == {low.id: 60, high.id: 180}
    assert db.query(Task).filter(
        Task.commitment_id == low.id, Task.status == "cancelled"
    ).count() == 2
    assert all(
        task.priority == "high"
        for task in db.query(Task).filter(
            Task.commitment_id == high.id, Task.status == "planned"
        )
    )
    assert len(result.shortfalls) == 1
    assert result.shortfalls[0].commitment_id == low.id
    assert result.shortfalls[0].missing_minutes == 120
    assert result.shortfalls[0].missing_sessions == 2
    assert result.shortfalls[0].reason == "resource_capacity"

    retry = materialize_weekly_commitments(db, user, WEEK_START, now=NOW)
    assert retry.created_tasks == []
    assert len(retry.shortfalls) == 1
    assert db.query(Task).filter(
        Task.commitment_id.is_not(None), Task.status.in_(["planned", "done"])
    ).count() == 4


def test_archived_program_cancels_only_future_candidates(db: Session) -> None:
    user, goal, program, phase = create_program(db)
    commitment = add_commitment(
        db, user=user, goal=goal, program=program, phase=phase
    )
    materialize_weekly_commitments(db, user, WEEK_START, now=NOW)
    future_plan = build_day_plan_result(
        db,
        user,
        plan_date=WEEK_START + timedelta(days=2),
        now=NOW,
    ).day_plan
    previous_plan_version = future_plan.version
    assert any(
        item.task is not None and item.task.commitment_id == commitment.id
        for item in future_plan.items
    )
    tasks = (
        db.query(Task)
        .filter(Task.commitment_id == commitment.id)
        .order_by(Task.target_date, Task.id)
        .all()
    )
    tasks[0].status = "done"
    program.status = "archived"
    db.commit()

    result = materialize_weekly_commitments(db, user, WEEK_START, now=NOW)
    db.refresh(tasks[0])
    remaining = db.query(Task).filter(Task.commitment_id == commitment.id).all()

    assert result.created_tasks == []
    assert tasks[0].status == "done"
    assert [task.status for task in remaining].count("cancelled") == 2
    assert not db.query(Task).filter(
        Task.commitment_id == commitment.id, Task.status == "planned"
    ).count()
    db.expire(future_plan, ["items"])
    assert not any(
        item.task is not None and item.task.commitment_id == commitment.id
        for item in future_plan.items
    )
    assert future_plan.version > previous_plan_version


def test_locked_commitment_candidate_is_immutable_during_priority_reallocation(
    db: Session,
) -> None:
    user, low_goal, low_program, low_phase = create_program(db, capacity=240)
    low_goal.priority = "low"
    low = add_commitment(
        db,
        user=user,
        goal=low_goal,
        program=low_program,
        phase=low_phase,
        minutes=60,
        sessions=1,
        minimum_block=60,
        weekdays=[1],
        recovery_gap=0,
    )
    locked = materialize_weekly_commitments(
        db, user, WEEK_START, now=NOW
    ).created_tasks[0]
    locked.scheduling_type = "fixed"
    locked.fixed_start = time(17, 0)
    locked.fixed_end = time(18, 0)
    locked.is_locked = True
    db.commit()

    high_goal = Goal(
        user_id=user.id,
        title="Срочное направление",
        status="active",
        priority="high",
        outcome_type="consistency",
    )
    db.add(high_goal)
    db.flush()
    high_program = Program(
        user_id=user.id,
        goal_id=high_goal.id,
        name="Срочная программа",
        status="active",
        minimum_minutes_week=60,
        comfortable_minutes_week=240,
        maximum_minutes_week=240,
        adaptation_rules={},
    )
    db.add(high_program)
    db.flush()
    high_phase = ProgramPhase(
        user_id=user.id,
        program_id=high_program.id,
        title="Срочная фаза",
        position=1,
        status="planned",
        start_date=WEEK_START,
        end_date=WEEK_START + timedelta(days=28),
        configuration={},
    )
    db.add(high_phase)
    db.flush()
    high = add_commitment(
        db,
        user=user,
        goal=high_goal,
        program=high_program,
        phase=high_phase,
        minutes=240,
        sessions=4,
        minimum_block=60,
        recovery_gap=0,
    )

    result = materialize_weekly_commitments(db, user, WEEK_START, now=NOW)
    db.refresh(locked)
    high_minutes = sum(
        task.estimated_minutes or 0
        for task in db.query(Task).filter(
            Task.commitment_id == high.id, Task.status == "planned"
        )
    )

    assert locked.commitment_id == low.id
    assert locked.status == "planned"
    assert locked.is_locked is True
    assert high_minutes == 180
    high_shortfall = next(
        item for item in result.shortfalls if item.commitment_id == high.id
    )
    assert high_shortfall.missing_minutes == 60
    assert high_shortfall.missing_sessions == 1


def test_one_off_weekly_work_reduces_commitment_capacity(db: Session) -> None:
    user, goal, program, phase = create_program(db, capacity=240)
    db.add(
        Task(
            user_id=user.id,
            title="Разовая встреча",
            target_date=WEEK_START + timedelta(days=1),
            scheduling_type="fixed",
            fixed_start=time(18, 0),
            fixed_end=time(19, 0),
            is_locked=True,
            status="planned",
        )
    )
    commitment = add_commitment(
        db,
        user=user,
        goal=goal,
        program=program,
        phase=phase,
        minutes=240,
        sessions=4,
        minimum_block=60,
        recovery_gap=0,
    )

    result = materialize_weekly_commitments(db, user, WEEK_START, now=NOW)

    assert sum(task.estimated_minutes or 0 for task in result.created_tasks) == 180
    assert len(result.shortfalls) == 1
    assert result.shortfalls[0].commitment_id == commitment.id
    assert result.shortfalls[0].missing_minutes == 60
    assert result.shortfalls[0].missing_sessions == 1
    assert result.shortfalls[0].reason == "resource_capacity"


def test_day_planner_preserves_fixed_events_while_placing_commitment(db: Session) -> None:
    user, goal, program, phase = create_program(db)
    commitment = add_commitment(
        db,
        user=user,
        goal=goal,
        program=program,
        phase=phase,
        minutes=60,
        sessions=1,
        minimum_block=60,
        weekdays=[1],
        preferred_window="evening",
        recovery_gap=0,
    )
    fixed = Task(
        user_id=user.id,
        title="Врач",
        target_date=WEEK_START,
        estimated_minutes=60,
        scheduling_type="fixed",
        fixed_start=time(18, 0),
        fixed_end=time(19, 0),
        is_locked=True,
        status="planned",
    )
    db.add(fixed)
    db.commit()

    result = build_day_plan_result(
        db, user, plan_date=WEEK_START, now=NOW
    )
    fixed_item = next(item for item in result.day_plan.items if item.task_id == fixed.id)
    commitment_item = next(
        item
        for item in result.day_plan.items
        if item.task is not None and item.task.commitment_id == commitment.id
    )

    assert fixed_item.start_time == time(18, 0)
    assert fixed_item.end_time == time(19, 0)
    assert commitment_item.start_time == time(17, 0)
    assert commitment_item.end_time == time(18, 0)
    assert result.commitment_shortfalls == []


def test_blocked_preferred_window_is_an_explicit_placement_shortfall(
    db: Session,
) -> None:
    user, goal, program, phase = create_program(db)
    commitment = add_commitment(
        db,
        user=user,
        goal=goal,
        program=program,
        phase=phase,
        minutes=60,
        sessions=1,
        minimum_block=60,
        weekdays=[1],
        preferred_window="evening",
        recovery_gap=0,
    )
    db.add(
        Task(
            user_id=user.id,
            title="Недвижимое вечернее событие",
            target_date=WEEK_START,
            estimated_minutes=360,
            scheduling_type="fixed",
            fixed_start=time(17, 0),
            fixed_end=time(23, 0),
            is_locked=True,
            status="planned",
        )
    )
    db.commit()

    result = build_day_plan_result(db, user, plan_date=WEEK_START, now=NOW)
    commitment_item = next(
        item
        for item in result.day_plan.items
        if item.task is not None and item.task.commitment_id == commitment.id
    )

    assert commitment_item.status == "not_scheduled"
    assert commitment_item.unscheduled_reason == "no_available_slot"
    assert len(result.commitment_shortfalls) == 1
    assert result.commitment_shortfalls[0].commitment_id == commitment.id
    assert result.commitment_shortfalls[0].missing_minutes == 60
    assert result.commitment_shortfalls[0].missing_sessions == 1
    assert result.commitment_shortfalls[0].reason == "placement_no_available_slot"


def test_only_current_and_next_detailed_weeks_are_generated(db: Session) -> None:
    user, goal, program, phase = create_program(db)
    add_commitment(db, user=user, goal=goal, program=program, phase=phase)

    next_week = materialize_weekly_commitments(
        db, user, WEEK_START + timedelta(days=7), now=NOW
    )
    far_week = materialize_weekly_commitments(
        db, user, WEEK_START + timedelta(days=14), now=NOW
    )

    assert len(next_week.created_tasks) == 3
    assert far_week.created_tasks == []
    assert far_week.shortfalls == []
    assert far_week.skipped_reason == "outside_detailed_horizon"
    assert not db.query(Task).filter(Task.target_date >= WEEK_START + timedelta(days=14)).count()


def test_midweek_materialization_keeps_completed_fact_and_never_backfills_past(
    db: Session,
) -> None:
    user, goal, program, phase = create_program(db)
    commitment = add_commitment(
        db,
        user=user,
        goal=goal,
        program=program,
        phase=phase,
        minutes=120,
        sessions=3,
        minimum_block=30,
        weekdays=[1, 3, 5],
        recovery_gap=60,
    )
    completed = Task(
        user_id=user.id,
        goal_id=goal.id,
        program_id=program.id,
        commitment_id=commitment.id,
        title=commitment.title,
        estimated_minutes=40,
        target_date=WEEK_START,
        scheduling_type="flexible",
        status="done",
    )
    db.add(completed)
    db.commit()
    wednesday = datetime(2026, 8, 5, 10, 0, tzinfo=timezone.utc)

    result = materialize_weekly_commitments(
        db, user, WEEK_START, now=wednesday
    )
    tasks = (
        db.query(Task)
        .filter(Task.commitment_id == commitment.id)
        .order_by(Task.target_date, Task.id)
        .all()
    )

    assert tasks[0].id == completed.id
    assert tasks[0].status == "done"
    assert [task.target_date.isoweekday() for task in tasks] == [1, 3, 5]
    assert result.shortfalls == []


def test_inactive_or_out_of_range_phase_does_not_generate_tasks(db: Session) -> None:
    user, goal, program, phase = create_program(db)
    commitment = add_commitment(
        db, user=user, goal=goal, program=program, phase=phase
    )
    phase.status = "completed"
    db.commit()

    completed_phase = materialize_weekly_commitments(
        db, user, WEEK_START, now=NOW
    )
    phase.status = "active"
    phase.start_date = WEEK_START + timedelta(days=14)
    db.commit()
    future_phase = materialize_weekly_commitments(
        db, user, WEEK_START, now=NOW
    )

    assert completed_phase.created_tasks == []
    assert future_phase.created_tasks == []
    assert not db.query(Task).filter(Task.commitment_id == commitment.id).count()


def test_commitment_days_intersect_with_resource_availability(db: Session) -> None:
    user, goal, program, phase = create_program(
        db, available_days=[2, 4]
    )
    commitment = add_commitment(
        db,
        user=user,
        goal=goal,
        program=program,
        phase=phase,
        minutes=60,
        sessions=1,
        minimum_block=60,
        weekdays=[1, 2, 3],
        recovery_gap=0,
    )

    result = materialize_weekly_commitments(db, user, WEEK_START, now=NOW)

    assert len(result.created_tasks) == 1
    assert result.created_tasks[0].commitment_id == commitment.id
    assert result.created_tasks[0].target_date.isoweekday() == 2
