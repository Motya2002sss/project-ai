from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.models.evidence import Evidence, MetricObservation
from app.models.goal import Goal
from app.models.program import GoalMilestone, Program, WeeklyCommitment
from app.models.user import User
from app.schemas.goals import (
    EvidenceCreate,
    MetricObservationCreate,
    ProgramApplyRequest,
    ProgramCommitmentInput,
    ProgramMilestoneInput,
    ProgramPhaseInput,
    ProgramProposalInput,
)
from app.services.evidence_service import (
    EvidenceConflict,
    complete_milestone,
    create_evidence,
    create_metric_observation,
)
from app.services.program_service import ProgramConflict, apply_program_proposal


D = Decimal
NOW = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def db(tmp_path: Path) -> Session:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'evidence.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        yield session


def create_users_and_goal(db: Session, *, outcome_type: str = "consistency"):
    owner = User(external_id=f"evidence-owner-{outcome_type}")
    other = User(external_id=f"evidence-other-{outcome_type}")
    db.add_all([owner, other])
    db.flush()
    goal = Goal(
        user_id=owner.id,
        title="Цель",
        outcome_type=outcome_type,
        baseline_value=D("72") if outcome_type == "metric" else None,
        current_value=D("72") if outcome_type == "metric" else None,
        target_value=D("78") if outcome_type == "metric" else None,
        metric_unit="kg" if outcome_type == "metric" else None,
    )
    db.add(goal)
    db.commit()
    return owner, other, goal


def proposal() -> ProgramProposalInput:
    return ProgramProposalInput(
        name="Базовая программа",
        minimum_minutes_week=60,
        comfortable_minutes_week=120,
        maximum_minutes_week=180,
        adaptation_rules={"missed_session": "move_future_only"},
        milestones=[
            ProgramMilestoneInput(title="Первый этап", position=1, weight=D("1")),
            ProgramMilestoneInput(title="Второй этап", position=2, weight=D("1")),
        ],
        phases=[ProgramPhaseInput(title="Основа", position=1)],
        commitments=[
            ProgramCommitmentInput(
                title="Практика",
                phase_position=1,
                target_minutes_week=120,
                target_sessions_week=3,
                minimum_block_minutes=20,
                allowed_weekdays=[1, 3, 5],
                preferred_window="evening",
                splittable=True,
                recovery_gap_minutes=60,
            )
        ],
    )


def test_partial_evidence_is_idempotent_and_recalculates_same_transaction(
    db: Session,
) -> None:
    owner, _other, goal = create_users_and_goal(db)
    program = Program(
        user_id=owner.id,
        goal_id=goal.id,
        name="Program",
        status="active",
        minimum_minutes_week=30,
        comfortable_minutes_week=60,
        maximum_minutes_week=90,
        adaptation_rules={},
    )
    db.add(program)
    db.flush()
    commitment = WeeklyCommitment(
        user_id=owner.id,
        goal_id=goal.id,
        program_id=program.id,
        title="Practice",
        target_minutes_week=60,
        target_sessions_week=2,
        minimum_block_minutes=15,
        allowed_weekdays=[1, 3],
    )
    db.add(commitment)
    db.commit()
    request = EvidenceCreate(
        request_id="partial-1",
        evidence_type="partial",
        quantity=D("30"),
        unit="minutes",
        occurred_at=NOW,
        commitment_id=commitment.id,
        note="Сделал половину без выдуманного успеха",
    )

    first = create_evidence(db, user=owner, goal=goal, request=request)
    duplicate = create_evidence(db, user=owner, goal=goal, request=request)

    assert first.evidence.id == duplicate.evidence.id
    assert db.query(Evidence).filter_by(user_id=owner.id).count() == 1
    assert first.progress.percentage == D("12.50")
    assert duplicate.progress.percentage == first.progress.percentage


def test_evidence_rejects_cross_user_program_links(db: Session) -> None:
    owner, other, goal = create_users_and_goal(db)
    other_goal = Goal(user_id=other.id, title="Other", outcome_type="consistency")
    db.add(other_goal)
    db.flush()
    other_program = Program(
        user_id=other.id,
        goal_id=other_goal.id,
        name="Other program",
        status="active",
        minimum_minutes_week=10,
        comfortable_minutes_week=20,
        maximum_minutes_week=30,
        adaptation_rules={},
    )
    db.add(other_program)
    db.commit()

    with pytest.raises(EvidenceConflict, match="related_record_not_found"):
        create_evidence(
            db,
            user=owner,
            goal=goal,
            request=EvidenceCreate(
                request_id="cross-user",
                evidence_type="session",
                quantity=D("20"),
                unit="minutes",
                occurred_at=NOW,
                program_id=other_program.id,
            ),
        )


def test_metric_observation_is_idempotent_updates_current_and_checks_unit(
    db: Session,
) -> None:
    owner, _other, goal = create_users_and_goal(db, outcome_type="metric")
    request = MetricObservationCreate(
        request_id="weight-1",
        value=D("75"),
        unit="kg",
        occurred_at=NOW,
        source="manual",
        note="Утреннее измерение",
    )

    first = create_metric_observation(db, user=owner, goal=goal, request=request)
    duplicate = create_metric_observation(db, user=owner, goal=goal, request=request)

    assert first.observation.id == duplicate.observation.id
    assert db.query(MetricObservation).count() == 1
    assert goal.current_value == D("75")
    assert first.progress.percentage == D("50.00")
    with pytest.raises(EvidenceConflict, match="idempotency_conflict"):
        create_evidence(
            db,
            user=owner,
            goal=goal,
            request=EvidenceCreate(
                request_id="weight-1",
                evidence_type="note",
                occurred_at=NOW,
                note="Same key for a different mutation",
            ),
        )
    with pytest.raises(EvidenceConflict, match="metric_unit_mismatch"):
        create_metric_observation(
            db,
            user=owner,
            goal=goal,
            request=MetricObservationCreate(
                request_id="weight-wrong-unit",
                value=D("165"),
                unit="lb",
                occurred_at=NOW,
                source="manual",
            ),
        )


def test_milestone_requires_confirmation_version_and_ownership(db: Session) -> None:
    owner, other, goal = create_users_and_goal(db, outcome_type="milestone")
    milestone = GoalMilestone(
        user_id=owner.id,
        goal_id=goal.id,
        title="Этап",
        position=1,
        criteria={"kind": "manual_confirmation"},
    )
    db.add(milestone)
    db.commit()

    with pytest.raises(EvidenceConflict, match="confirmation_required"):
        complete_milestone(
            db,
            user=owner,
            goal=goal,
            milestone_id=milestone.id,
            expected_version=1,
            confirmation=False,
            occurred_at=NOW,
        )
    with pytest.raises(EvidenceConflict, match="milestone_not_found"):
        complete_milestone(
            db,
            user=other,
            goal=goal,
            milestone_id=milestone.id,
            expected_version=1,
            confirmation=True,
            occurred_at=NOW,
        )
    result = complete_milestone(
        db,
        user=owner,
        goal=goal,
        milestone_id=milestone.id,
        expected_version=1,
        confirmation=True,
        occurred_at=NOW,
    )

    assert result.milestone.status == "completed"
    assert result.progress.percentage == D("100.00")


def test_program_apply_validates_budget_and_preserves_order(db: Session) -> None:
    owner, _other, goal = create_users_and_goal(db, outcome_type="milestone")
    from app.models.onboarding import ResourceBudget

    with pytest.raises(ProgramConflict, match="resource_budget_required"):
        apply_program_proposal(
            db,
            user=owner,
            goal=goal,
            request=ProgramApplyRequest(
                request_id="program-without-budget",
                expected_goal_version=goal.version,
                confirmation=True,
                proposal=proposal(),
            ),
        )
    db.add(
        ResourceBudget(
            user_id=owner.id,
            weekly_available_minutes=300,
            available_days=[1, 2, 3, 4, 5],
            minimum_minutes=60,
            comfortable_minutes=180,
            maximum_minutes=240,
            free_evenings=[2, 4],
            preferred_windows={},
            reserve_percent=20,
            allocatable_minutes=240,
            allocation={"goals": []},
        )
    )
    db.commit()
    request = ProgramApplyRequest(
        request_id="program-1",
        expected_goal_version=goal.version,
        confirmation=True,
        proposal=proposal(),
    )

    result = apply_program_proposal(db, user=owner, goal=goal, request=request)
    duplicate = apply_program_proposal(db, user=owner, goal=goal, request=request)

    assert [phase.position for phase in result.program.phases] == [1]
    assert [milestone.position for milestone in goal.milestones] == [1, 2]
    assert result.program.commitments[0].phase_id == result.program.phases[0].id
    assert duplicate.program.id == result.program.id
    assert db.query(Program).filter_by(user_id=owner.id).count() == 1
    too_large = proposal().model_copy(
        update={"maximum_minutes_week": 300, "comfortable_minutes_week": 260}
    )
    with pytest.raises(ProgramConflict, match="resource_budget_exceeded"):
        apply_program_proposal(
            db,
            user=owner,
            goal=goal,
            request=ProgramApplyRequest(
                request_id="program-too-large",
                expected_goal_version=goal.version,
                confirmation=True,
                proposal=too_large,
            ),
        )


def test_evidence_note_is_bounded_before_persistence() -> None:
    with pytest.raises(ValueError):
        EvidenceCreate(
            request_id="long-note",
            evidence_type="note",
            occurred_at=NOW,
            note="x" * 1001,
        )
