from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.models.evidence import Evidence, GoalProgressSnapshot, MetricObservation
from app.models.goal import Goal
from app.models.program import GoalMilestone, Program, WeeklyCommitment
from app.models.task import Task
from app.models.user import User
from app.services.progress_service import (
    MetricPoint,
    MilestoneProgressInput,
    calculate_consistency_progress,
    calculate_metric_progress,
    calculate_milestone_progress,
    recalculate_goal_progress,
)


D = Decimal
AS_OF = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def db(tmp_path: Path) -> Session:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'progress.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        yield session


def test_metric_progress_supports_increasing_and_decreasing_targets() -> None:
    increasing = calculate_metric_progress(
        baseline=D("72"), current=D("75"), target=D("78"), as_of=AS_OF
    )
    decreasing = calculate_metric_progress(
        baseline=D("90"), current=D("85"), target=D("80"), as_of=AS_OF
    )

    assert increasing.percentage == D("50.00")
    assert increasing.components["direction"] == "increase"
    assert decreasing.percentage == D("50.00")
    assert decreasing.components["direction"] == "decrease"


def test_metric_progress_is_nullable_without_a_defensible_denominator() -> None:
    missing = calculate_metric_progress(
        baseline=None, current=D("75"), target=D("78"), as_of=AS_OF
    )
    equal = calculate_metric_progress(
        baseline=D("78"), current=D("78"), target=D("78"), as_of=AS_OF
    )

    assert missing.percentage is None
    assert missing.reason == "insufficient_data"
    assert equal.percentage is None
    assert equal.reason == "invalid_target"


def test_metric_display_clamps_reached_or_prebaseline_values() -> None:
    reached = calculate_metric_progress(
        baseline=D("72"), current=D("80"), target=D("78"), as_of=AS_OF
    )
    before = calculate_metric_progress(
        baseline=D("72"), current=D("70"), target=D("78"), as_of=AS_OF
    )

    assert reached.percentage == D("100.00")
    assert before.percentage == D("0.00")


def test_metric_pace_forecast_and_confidence_are_evidence_based() -> None:
    observations = [
        MetricPoint(value=D("72") + D(index), occurred_at=AS_OF - timedelta(days=35 - index * 7))
        for index in range(6)
    ]
    result = calculate_metric_progress(
        baseline=D("72"),
        current=D("77"),
        target=D("78"),
        observations=observations,
        as_of=AS_OF,
    )

    assert result.percentage == D("83.33")
    assert result.components["pace_per_day"] == "0.1429"
    assert result.forecast_date == date(2026, 8, 18)
    assert result.confidence == "high"


def test_milestone_progress_uses_all_weights_or_equal_fallback() -> None:
    weighted = calculate_milestone_progress(
        [
            MilestoneProgressInput(status="completed", weight=D("1")),
            MilestoneProgressInput(status="pending", weight=D("3")),
        ]
    )
    equal = calculate_milestone_progress(
        [
            MilestoneProgressInput(status="completed"),
            MilestoneProgressInput(status="completed"),
            MilestoneProgressInput(status="pending"),
        ]
    )
    mixed = calculate_milestone_progress(
        [
            MilestoneProgressInput(status="completed", weight=D("1")),
            MilestoneProgressInput(status="pending"),
        ]
    )

    assert weighted.percentage == D("25.00")
    assert weighted.components["method"] == "weighted"
    assert equal.percentage == D("66.67")
    assert equal.components["method"] == "equal"
    assert mixed.percentage is None
    assert mixed.reason == "invalid_milestone_weights"


def test_consistency_progress_accepts_partial_minutes_or_sessions() -> None:
    minutes = calculate_consistency_progress(
        planned_minutes=D("360"),
        completed_minutes=D("150"),
        planned_sessions=3,
        completed_sessions=2,
        window_days=7,
        evidence_count=2,
    )
    sessions = calculate_consistency_progress(
        planned_minutes=D("0"),
        completed_minutes=D("0"),
        planned_sessions=3,
        completed_sessions=2,
        window_days=7,
        evidence_count=2,
    )

    assert minutes.percentage == D("41.67")
    assert minutes.components["denominator"] == "minutes"
    assert sessions.percentage == D("66.67")
    assert sessions.components["denominator"] == "sessions"


def test_consistency_does_not_punish_or_invent_progress() -> None:
    no_commitment = calculate_consistency_progress(
        planned_minutes=D("0"),
        completed_minutes=D("300"),
        planned_sessions=0,
        completed_sessions=10,
        window_days=28,
        evidence_count=10,
    )
    over_delivery = calculate_consistency_progress(
        planned_minutes=D("100"),
        completed_minutes=D("150"),
        planned_sessions=1,
        completed_sessions=1,
        window_days=7,
        evidence_count=1,
    )

    assert no_commitment.percentage is None
    assert no_commitment.reason == "insufficient_data"
    assert over_delivery.percentage == D("100.00")
    assert over_delivery.components["completed_minutes"] == "150"


def test_recalculation_uses_owned_metric_observations_and_persists_snapshot(
    db: Session,
) -> None:
    user = User(external_id="metric-owner")
    db.add(user)
    db.flush()
    goal = Goal(
        user_id=user.id,
        title="Набрать вес",
        outcome_type="metric",
        baseline_value=D("72"),
        current_value=D("72"),
        target_value=D("78"),
        metric_unit="kg",
    )
    db.add(goal)
    db.flush()
    db.add_all(
        [
            MetricObservation(
                user_id=user.id,
                goal_id=goal.id,
                request_id="metric-1",
                value=D("73"),
                unit="kg",
                occurred_at=AS_OF - timedelta(days=14),
                source="manual",
            ),
            MetricObservation(
                user_id=user.id,
                goal_id=goal.id,
                request_id="metric-2",
                value=D("75"),
                unit="kg",
                occurred_at=AS_OF,
                source="manual",
            ),
        ]
    )
    db.commit()

    result = recalculate_goal_progress(db, user=user, goal=goal, as_of=AS_OF)

    assert result.percentage == D("50.00")
    assert goal.current_value == D("75")
    snapshot = db.query(GoalProgressSnapshot).filter_by(goal_id=goal.id).one()
    assert snapshot.formula_version == "progress-v1"
    assert snapshot.components["current"] == "75.0000"


def test_recalculation_counts_only_factual_evidence_in_rolling_window(
    db: Session,
) -> None:
    user = User(external_id="consistency-owner")
    db.add(user)
    db.flush()
    goal = Goal(user_id=user.id, title="Бегать", outcome_type="consistency")
    db.add(goal)
    db.flush()
    program = Program(
        user_id=user.id,
        goal_id=goal.id,
        name="Бег",
        status="active",
        minimum_minutes_week=60,
        comfortable_minutes_week=90,
        maximum_minutes_week=120,
        adaptation_rules={},
    )
    db.add(program)
    db.flush()
    commitment = WeeklyCommitment(
        user_id=user.id,
        goal_id=goal.id,
        program_id=program.id,
        title="Бег",
        target_minutes_week=90,
        target_sessions_week=3,
        minimum_block_minutes=20,
        allowed_weekdays=[1, 3, 5],
        splittable=False,
    )
    db.add(commitment)
    db.flush()
    db.add_all(
        [
            Evidence(
                user_id=user.id,
                goal_id=goal.id,
                commitment_id=commitment.id,
                request_id="run-in-window",
                evidence_type="session",
                quantity=D("180"),
                unit="minutes",
                occurred_at=AS_OF - timedelta(days=2),
                attributes={},
            ),
            Evidence(
                user_id=user.id,
                goal_id=goal.id,
                commitment_id=commitment.id,
                request_id="run-too-old",
                evidence_type="session",
                quantity=D("999"),
                unit="minutes",
                occurred_at=AS_OF - timedelta(days=40),
                attributes={},
            ),
        ]
    )
    db.commit()

    result = recalculate_goal_progress(db, user=user, goal=goal, as_of=AS_OF)

    assert result.percentage == D("50.00")
    assert result.components["planned_minutes"] == "360"
    assert result.components["completed_minutes"] == "180.0000"


def test_completed_tasks_never_become_goal_outcome_progress(db: Session) -> None:
    user = User(external_id="task-count-owner")
    db.add(user)
    db.flush()
    goal = Goal(user_id=user.id, title="Неизмеримая цель", outcome_type="consistency")
    db.add(goal)
    db.flush()
    for index in range(12):
        db.add(
            Task(
                user_id=user.id,
                goal_id=goal.id,
                title=f"Выполненная задача {index}",
                target_date=AS_OF.date(),
                status="done",
            )
        )
    db.commit()

    result = recalculate_goal_progress(db, user=user, goal=goal, as_of=AS_OF)

    assert result.percentage is None
    assert result.reason == "insufficient_data"


def test_recalculation_rejects_another_users_goal(db: Session) -> None:
    owner = User(external_id="progress-owner")
    attacker = User(external_id="progress-attacker")
    db.add_all([owner, attacker])
    db.flush()
    goal = Goal(user_id=owner.id, title="Private", outcome_type="milestone")
    db.add(goal)
    db.commit()

    with pytest.raises(ValueError, match="goal_not_owned"):
        recalculate_goal_progress(db, user=attacker, goal=goal, as_of=AS_OF)
