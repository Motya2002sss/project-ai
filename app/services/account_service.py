from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.activity import (
    LearningResource,
    LearningSession,
    NutritionLog,
    WorkoutExercise,
    WorkoutSet,
)
from app.models.calendar import (
    CalendarBusyBlock,
    CalendarSyncState,
    TemporaryLifeMode,
)
from app.models.evidence import Evidence, GoalProgressSnapshot, MetricObservation
from app.models.goal import Goal
from app.models.onboarding import OnboardingPreview, ResourceBudget
from app.models.plan_change import PlanChange
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
    workout_exercises = db.scalars(
        select(WorkoutExercise)
        .where(WorkoutExercise.user_id == user.id)
        .order_by(
            WorkoutExercise.task_id,
            WorkoutExercise.position,
            WorkoutExercise.id,
        )
    ).all()
    workout_sets = db.scalars(
        select(WorkoutSet)
        .where(WorkoutSet.user_id == user.id)
        .order_by(
            WorkoutSet.workout_exercise_id,
            WorkoutSet.position,
            WorkoutSet.id,
        )
    ).all()
    nutrition_logs = db.scalars(
        select(NutritionLog)
        .where(NutritionLog.user_id == user.id)
        .order_by(NutritionLog.occurred_at, NutritionLog.id)
    ).all()
    learning_resources = db.scalars(
        select(LearningResource)
        .where(LearningResource.user_id == user.id)
        .order_by(LearningResource.created_at, LearningResource.id)
    ).all()
    learning_sessions = db.scalars(
        select(LearningSession)
        .where(LearningSession.user_id == user.id)
        .order_by(LearningSession.occurred_at, LearningSession.id)
    ).all()
    calendar_busy_blocks = db.scalars(
        select(CalendarBusyBlock)
        .where(CalendarBusyBlock.user_id == user.id)
        .order_by(
            CalendarBusyBlock.occurrence_start,
            CalendarBusyBlock.id,
        )
    ).all()
    calendar_sync_states = db.scalars(
        select(CalendarSyncState)
        .where(CalendarSyncState.user_id == user.id)
        .order_by(
            CalendarSyncState.device_id,
            CalendarSyncState.provider,
            CalendarSyncState.id,
        )
    ).all()
    temporary_life_modes = db.scalars(
        select(TemporaryLifeMode)
        .where(TemporaryLifeMode.user_id == user.id)
        .order_by(TemporaryLifeMode.starts_at, TemporaryLifeMode.id)
    ).all()
    plan_changes = db.scalars(
        select(PlanChange)
        .where(PlanChange.user_id == user.id)
        .order_by(PlanChange.created_at, PlanChange.id)
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
        workout_exercises=[
            {
                "id": str(exercise.id),
                "goal_id": exercise.goal_id,
                "task_id": exercise.task_id,
                "program_id": (
                    str(exercise.program_id) if exercise.program_id else None
                ),
                "evidence_id": (
                    str(exercise.evidence_id) if exercise.evidence_id else None
                ),
                "name": exercise.name,
                "position": exercise.position,
                "note": exercise.note,
                "created_at": exercise.created_at,
                "updated_at": exercise.updated_at,
            }
            for exercise in workout_exercises
        ],
        workout_sets=[
            {
                "id": str(workout_set.id),
                "workout_exercise_id": str(workout_set.workout_exercise_id),
                "position": workout_set.position,
                "planned_weight": workout_set.planned_weight,
                "planned_reps": workout_set.planned_reps,
                "planned_rpe": workout_set.planned_rpe,
                "actual_weight": workout_set.actual_weight,
                "actual_reps": workout_set.actual_reps,
                "actual_rpe": workout_set.actual_rpe,
                "weight_unit": workout_set.weight_unit,
                "completion_status": workout_set.completion_status,
                "note": workout_set.note,
                "completed_at": workout_set.completed_at,
                "created_at": workout_set.created_at,
                "updated_at": workout_set.updated_at,
            }
            for workout_set in workout_sets
        ],
        nutrition_logs=[
            {
                "id": str(log.id),
                "goal_id": log.goal_id,
                "task_id": log.task_id,
                "program_id": str(log.program_id) if log.program_id else None,
                "evidence_id": str(log.evidence_id) if log.evidence_id else None,
                "occurred_at": log.occurred_at,
                "meal_note": log.meal_note,
                "adherence": log.adherence,
                "calories": log.calories,
                "protein_grams": log.protein_grams,
                "fat_grams": log.fat_grams,
                "carbohydrate_grams": log.carbohydrate_grams,
                "target_calories": log.target_calories,
                "target_protein_grams": log.target_protein_grams,
                "target_fat_grams": log.target_fat_grams,
                "target_carbohydrate_grams": log.target_carbohydrate_grams,
                "weight_observation": log.weight_observation,
                "weight_unit": log.weight_unit,
                "created_at": log.created_at,
            }
            for log in nutrition_logs
        ],
        learning_resources=[
            {
                "id": str(resource.id),
                "goal_id": resource.goal_id,
                "program_id": (
                    str(resource.program_id) if resource.program_id else None
                ),
                "title": resource.title,
                "resource_type": resource.resource_type,
                "competency": resource.competency,
                "total_pages": resource.total_pages,
                "total_minutes": resource.total_minutes,
                "total_exercises": resource.total_exercises,
                "total_projects": resource.total_projects,
                "note": resource.note,
                "created_at": resource.created_at,
                "updated_at": resource.updated_at,
            }
            for resource in learning_resources
        ],
        learning_sessions=[
            {
                "id": str(session.id),
                "goal_id": session.goal_id,
                "task_id": session.task_id,
                "program_id": (
                    str(session.program_id) if session.program_id else None
                ),
                "learning_resource_id": (
                    str(session.learning_resource_id)
                    if session.learning_resource_id
                    else None
                ),
                "milestone_id": (
                    str(session.milestone_id) if session.milestone_id else None
                ),
                "evidence_id": (
                    str(session.evidence_id) if session.evidence_id else None
                ),
                "occurred_at": session.occurred_at,
                "competency": session.competency,
                "pages_completed": session.pages_completed,
                "minutes_spent": session.minutes_spent,
                "exercises_completed": session.exercises_completed,
                "projects_completed": session.projects_completed,
                "note": session.note,
                "created_at": session.created_at,
            }
            for session in learning_sessions
        ],
        calendar_busy_blocks=[
            {
                "id": str(block.id),
                "device_id": block.device_id,
                "provider": block.provider,
                "calendar_external_id": block.calendar_external_id,
                "external_id": block.external_id,
                "occurrence_external_id": block.occurrence_external_id,
                "occurrence_start": block.occurrence_start,
                "occurrence_end": block.occurrence_end,
                "device_timezone": block.device_timezone,
                "source_revision": block.source_revision,
                "last_seen_client_revision": block.last_seen_client_revision,
                "deleted_at": block.deleted_at,
                "created_at": block.created_at,
                "updated_at": block.updated_at,
            }
            for block in calendar_busy_blocks
        ],
        calendar_sync_states=[
            {
                "id": str(state.id),
                "device_id": state.device_id,
                "provider": state.provider,
                "version": state.version,
                "client_revision": state.client_revision,
                "range_start": state.range_start,
                "range_end": state.range_end,
                "device_timezone": state.device_timezone,
                "covered_calendar_ids": state.covered_calendar_ids,
                "last_synced_at": state.last_synced_at,
                "created_at": state.created_at,
                "updated_at": state.updated_at,
            }
            for state in calendar_sync_states
        ],
        temporary_life_modes=[
            {
                "id": str(mode.id),
                "request_id": mode.request_id,
                "mode": mode.mode,
                "starts_at": mode.starts_at,
                "ends_at": mode.ends_at,
                "status": mode.status,
                "constraints": mode.constraints,
                "created_at": mode.created_at,
                "updated_at": mode.updated_at,
            }
            for mode in temporary_life_modes
        ],
        plan_changes=[
            {
                "id": str(change.id),
                "request_id": change.request_id,
                "reason": change.reason,
                "status": change.status,
                "base_versions": change.base_versions,
                "result_versions": change.result_versions,
                "affected_dates": change.affected_dates,
                "forward_payload": change.forward_payload,
                "inverse_payload": change.inverse_payload,
                "expires_at": change.expires_at,
                "undone_at": change.undone_at,
                "created_at": change.created_at,
            }
            for change in plan_changes
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
