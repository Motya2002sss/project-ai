from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.evidence import Evidence, GoalProgressSnapshot, MetricObservation
from app.models.goal import Goal
from app.models.onboarding import OnboardingPreview, ResourceBudget
from app.models.program import (
    GoalMilestone,
    Program,
    ProgramPhase,
    WeeklyCommitment,
)
from app.models.routine import Routine
from app.models.task import Task
from app.models.user import User
from app.schemas.auth import AccountExportProfile, AccountExportResponse


def export_account_data(db: Session, user: User) -> AccountExportResponse:
    goals = db.scalars(
        select(Goal).where(Goal.user_id == user.id).order_by(Goal.id)
    ).all()
    tasks = db.scalars(
        select(Task).where(Task.user_id == user.id).order_by(Task.id)
    ).all()
    routines = db.scalars(
        select(Routine).where(Routine.user_id == user.id).order_by(Routine.id)
    ).all()
    resource_budget = db.scalar(
        select(ResourceBudget).where(ResourceBudget.user_id == user.id)
    )
    onboarding_previews = db.scalars(
        select(OnboardingPreview)
        .where(OnboardingPreview.user_id == user.id)
        .order_by(OnboardingPreview.created_at, OnboardingPreview.id)
    ).all()
    programs = db.scalars(
        select(Program).where(Program.user_id == user.id).order_by(Program.created_at)
    ).all()
    program_phases = db.scalars(
        select(ProgramPhase)
        .where(ProgramPhase.user_id == user.id)
        .order_by(ProgramPhase.program_id, ProgramPhase.position)
    ).all()
    commitments = db.scalars(
        select(WeeklyCommitment)
        .where(WeeklyCommitment.user_id == user.id)
        .order_by(WeeklyCommitment.created_at)
    ).all()
    milestones = db.scalars(
        select(GoalMilestone)
        .where(GoalMilestone.user_id == user.id)
        .order_by(GoalMilestone.goal_id, GoalMilestone.position)
    ).all()
    evidence = db.scalars(
        select(Evidence)
        .where(Evidence.user_id == user.id)
        .order_by(Evidence.occurred_at, Evidence.id)
    ).all()
    observations = db.scalars(
        select(MetricObservation)
        .where(MetricObservation.user_id == user.id)
        .order_by(MetricObservation.occurred_at, MetricObservation.id)
    ).all()
    progress_snapshots = db.scalars(
        select(GoalProgressSnapshot)
        .where(GoalProgressSnapshot.user_id == user.id)
        .order_by(GoalProgressSnapshot.as_of, GoalProgressSnapshot.id)
    ).all()

    return AccountExportResponse(
        exported_at=datetime.now(timezone.utc),
        profile=AccountExportProfile(
            public_id=user.public_id,
            name=user.name,
            email=user.email,
            timezone=user.timezone,
            work_start_time=_iso_or_none(user.work_start_time),
            work_end_time=_iso_or_none(user.work_end_time),
            sleep_time=_iso_or_none(user.sleep_time),
            created_at=user.created_at,
        ),
        goals=[
            {
                "id": goal.id,
                "title": goal.title,
                "category": goal.category,
                "priority": goal.priority,
                "target_date": _iso_or_none(goal.target_date),
                "status": goal.status,
                "public_id": str(goal.public_id),
                "life_area": goal.life_area,
                "outcome_type": goal.outcome_type,
                "baseline_value": goal.baseline_value,
                "current_value": goal.current_value,
                "target_value": goal.target_value,
                "metric_unit": goal.metric_unit,
                "deadline": _iso_or_none(goal.deadline),
                "intensity": goal.intensity,
                "allocation_minutes_week": goal.allocation_minutes_week,
                "version": goal.version,
            }
            for goal in goals
        ],
        tasks=[
            {
                "id": task.id,
                "goal_id": task.goal_id,
                "title": task.title,
                "description": task.description,
                "target_date": task.target_date.isoformat(),
                "status": task.status,
                "scheduling_type": task.scheduling_type,
                "estimated_minutes": task.estimated_minutes,
            }
            for task in tasks
        ],
        routines=[
            {
                "id": routine.id,
                "title": routine.title,
                "cadence": routine.cadence,
                "weekdays": routine.weekdays,
                "fixed_time": _iso_or_none(routine.fixed_time),
                "preferred_window": routine.preferred_window,
                "estimated_minutes": routine.estimated_minutes,
                "start_date": routine.start_date.isoformat(),
                "end_date": _iso_or_none(routine.end_date),
                "active": routine.active,
            }
            for routine in routines
        ],
        resource_budget=(
            {
                "weekly_available_minutes": resource_budget.weekly_available_minutes,
                "available_days": resource_budget.available_days,
                "minimum_minutes": resource_budget.minimum_minutes,
                "comfortable_minutes": resource_budget.comfortable_minutes,
                "maximum_minutes": resource_budget.maximum_minutes,
                "free_evenings": resource_budget.free_evenings,
                "preferred_windows": resource_budget.preferred_windows,
                "money_budget": resource_budget.money_budget,
                "conflict_priority": resource_budget.conflict_priority,
                "reserve_percent": resource_budget.reserve_percent,
                "allocatable_minutes": resource_budget.allocatable_minutes,
                "allocation": resource_budget.allocation,
                "version": resource_budget.version,
            }
            if resource_budget is not None
            else None
        ),
        onboarding_previews=[
            {
                "id": str(preview.id),
                "status": preview.status,
                "version": preview.version,
                "narrative": preview.narrative,
                "structured_summary": preview.structured_summary,
                "goal_candidates": preview.goal_candidates,
                "resource_budget": preview.resource_budget,
                "allocation": preview.allocation,
                "clarification": preview.clarification,
                "created_at": preview.created_at,
                "applied_at": preview.applied_at,
            }
            for preview in onboarding_previews
        ],
        programs=[
            {
                "id": str(program.id),
                "goal_id": program.goal_id,
                "name": program.name,
                "status": program.status,
                "minimum_minutes_week": program.minimum_minutes_week,
                "comfortable_minutes_week": program.comfortable_minutes_week,
                "maximum_minutes_week": program.maximum_minutes_week,
                "adaptation_rules": program.adaptation_rules,
                "version": program.version,
            }
            for program in programs
        ],
        program_phases=[
            {
                "id": str(phase.id),
                "program_id": str(phase.program_id),
                "title": phase.title,
                "position": phase.position,
                "status": phase.status,
                "start_date": _iso_or_none(phase.start_date),
                "end_date": _iso_or_none(phase.end_date),
                "configuration": phase.configuration,
            }
            for phase in program_phases
        ],
        weekly_commitments=[
            {
                "id": str(commitment.id),
                "goal_id": commitment.goal_id,
                "program_id": str(commitment.program_id),
                "phase_id": str(commitment.phase_id) if commitment.phase_id else None,
                "title": commitment.title,
                "target_minutes_week": commitment.target_minutes_week,
                "target_sessions_week": commitment.target_sessions_week,
                "minimum_block_minutes": commitment.minimum_block_minutes,
                "allowed_weekdays": commitment.allowed_weekdays,
                "preferred_window": commitment.preferred_window,
                "splittable": commitment.splittable,
                "recovery_gap_minutes": commitment.recovery_gap_minutes,
                "active": commitment.active,
                "version": commitment.version,
            }
            for commitment in commitments
        ],
        milestones=[
            {
                "id": str(milestone.id),
                "goal_id": milestone.goal_id,
                "title": milestone.title,
                "description": milestone.description,
                "position": milestone.position,
                "criteria": milestone.criteria,
                "weight": milestone.weight,
                "status": milestone.status,
                "completed_at": milestone.completed_at,
                "version": milestone.version,
            }
            for milestone in milestones
        ],
        evidence=[
            {
                "id": str(item.id),
                "goal_id": item.goal_id,
                "program_id": str(item.program_id) if item.program_id else None,
                "commitment_id": (
                    str(item.commitment_id) if item.commitment_id else None
                ),
                "task_id": item.task_id,
                "evidence_type": item.evidence_type,
                "quantity": item.quantity,
                "unit": item.unit,
                "occurred_at": item.occurred_at,
                "note": item.note,
                "attributes": item.attributes,
            }
            for item in evidence
        ],
        metric_observations=[
            {
                "id": str(observation.id),
                "goal_id": observation.goal_id,
                "value": observation.value,
                "unit": observation.unit,
                "occurred_at": observation.occurred_at,
                "source": observation.source,
                "note": observation.note,
            }
            for observation in observations
        ],
        progress_snapshots=[
            {
                "id": str(snapshot.id),
                "goal_id": snapshot.goal_id,
                "as_of": snapshot.as_of,
                "strategy": snapshot.strategy,
                "percentage": snapshot.percentage,
                "components": snapshot.components,
                "reason": snapshot.reason,
                "formula_version": snapshot.formula_version,
                "forecast_date": _iso_or_none(snapshot.forecast_date),
                "confidence": snapshot.confidence,
            }
            for snapshot in progress_snapshots
        ],
    )


def delete_account_data(db: Session, user: User) -> None:
    db.delete(user)
    db.commit()


def _iso_or_none(value) -> str | None:
    return value.isoformat() if value is not None else None
