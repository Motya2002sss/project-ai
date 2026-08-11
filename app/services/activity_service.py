import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import TypeVar
from uuid import UUID

from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.activity import (
    LearningResource,
    LearningSession,
    NutritionLog,
    WorkoutExercise,
    WorkoutSet,
)
from app.models.evidence import Evidence, MetricObservation
from app.models.goal import Goal
from app.models.message_receipt import MessageReceipt
from app.models.program import Program, WeeklyCommitment
from app.models.task import Task
from app.models.user import User
from app.schemas.activity import (
    LearningLogRequest,
    LearningMutationResponse,
    LearningSessionResponse,
    NutritionLogRequest,
    NutritionLogResponse,
    NutritionMutationResponse,
    ProgramAdaptationCandidate,
    ProgramAdaptationRequest,
    ProgramAdaptationResponse,
    WeightTrendResponse,
    WorkoutDraftRequest,
    WorkoutExerciseResponse,
    WorkoutFinishRequest,
    WorkoutMutationResponse,
    WorkoutSetFactInput,
    WorkoutSetResponse,
    WorkoutSnapshotResponse,
)
from app.schemas.progress import ProgressResult
from app.services.progress_service import recalculate_goal_progress
from app.services.planning_service import rebuild_day_plan
from app.services.safety_policy import evaluate_activity_safety


class ActivityConflict(ValueError):
    pass


class ActivityUnavailable(RuntimeError):
    pass


ResponseModel = TypeVar("ResponseModel", bound=BaseModel)


@dataclass(frozen=True)
class ProgramAdaptationContext:
    id: UUID
    name: str
    version: int
    adaptation_rules: dict


CandidateBuilder = Callable[[str, ProgramAdaptationContext], object]
WEIGHT_QUANTUM = Decimal("0.001")


def get_workout_snapshot(
    db: Session,
    *,
    user: User,
    task_id: int,
) -> WorkoutSnapshotResponse:
    task = _owned_workout_task(db, user=user, task_id=task_id, lock=False)
    return _workout_snapshot(db, user=user, task=task)


def save_workout_draft(
    db: Session,
    *,
    user: User,
    task_id: int,
    request: WorkoutDraftRequest,
) -> WorkoutMutationResponse:
    fingerprint = _fingerprint("workout_draft", task_id, request)
    replay = _replay_receipt(
        db,
        user=user,
        request_id=request.request_id,
        source="workout_draft",
        fingerprint=fingerprint,
        response_type=WorkoutMutationResponse,
    )
    if replay is not None:
        return replay
    _lock_user(db, user=user)
    replay = _replay_receipt(
        db,
        user=user,
        request_id=request.request_id,
        source="workout_draft",
        fingerprint=fingerprint,
        response_type=WorkoutMutationResponse,
    )
    if replay is not None:
        return replay
    task = _owned_workout_task(db, user=user, task_id=task_id, lock=True)
    _require_open_workout(task)
    _apply_set_facts(
        db,
        user=user,
        task=task,
        facts=request.sets,
        recorded_at=request.recorded_at,
    )
    db.flush()
    response = WorkoutMutationResponse(
        state="draft",
        workout=_workout_snapshot(db, user=user, task=task),
    )
    _store_receipt(
        db,
        user=user,
        request_id=request.request_id,
        source="workout_draft",
        fingerprint=fingerprint,
        response=response,
    )
    db.commit()
    return response


def finish_workout(
    db: Session,
    *,
    user: User,
    task_id: int,
    request: WorkoutFinishRequest,
) -> WorkoutMutationResponse:
    fingerprint = _fingerprint("workout_finish", task_id, request)
    replay = _replay_receipt(
        db,
        user=user,
        request_id=request.request_id,
        source="workout_finish",
        fingerprint=fingerprint,
        response_type=WorkoutMutationResponse,
    )
    if replay is not None:
        return replay
    _lock_user(db, user=user)
    replay = _replay_receipt(
        db,
        user=user,
        request_id=request.request_id,
        source="workout_finish",
        fingerprint=fingerprint,
        response_type=WorkoutMutationResponse,
    )
    if replay is not None:
        return replay
    task = _owned_workout_task(db, user=user, task_id=task_id, lock=True)
    _require_open_workout(task)
    if request.sets:
        _apply_set_facts(
            db,
            user=user,
            task=task,
            facts=request.sets,
            recorded_at=request.finished_at,
        )
    db.flush()
    exercises, sets_by_exercise = _workout_rows(db, user=user, task_id=task.id)
    planned_set_count = sum(len(items) for items in sets_by_exercise.values())
    completed_set_count = sum(
        1
        for items in sets_by_exercise.values()
        for item in items
        if item.completion_status == "completed"
    )
    elapsed_minutes = int(
        (request.finished_at - request.started_at).total_seconds() // 60
    )
    if elapsed_minutes == 0 and completed_set_count == 0:
        raise ActivityConflict("workout_fact_required")
    evidence = None
    progress = None
    goal = _owned_goal_by_id(db, user=user, goal_id=task.goal_id)
    program = _owned_program_by_id(
        db,
        user=user,
        program_id=task.program_id,
        goal_id=goal.id if goal is not None else None,
    )
    if goal is not None:
        commitment_id = _owned_task_commitment_id(
            db,
            user=user,
            task=task,
            goal=goal,
            program=program,
        )
        evidence = Evidence(
            user_id=user.id,
            goal_id=goal.id,
            program_id=program.id if program is not None else None,
            commitment_id=commitment_id,
            task_id=task.id,
            request_id=request.request_id,
            evidence_type="completion",
            quantity=Decimal(elapsed_minutes),
            unit="minutes",
            occurred_at=request.finished_at,
            note=None,
            attributes={
                "activity_type": "workout",
                "completed_set_count": completed_set_count,
                "planned_set_count": planned_set_count,
                "partial": completed_set_count < planned_set_count,
                "elapsed_minutes": elapsed_minutes,
            },
        )
        db.add(evidence)
        db.flush()
        for exercise in exercises:
            exercise.evidence_id = evidence.id
        progress = recalculate_goal_progress(
            db,
            user=user,
            goal=goal,
            as_of=_current_as_of(request.finished_at),
        )
    task.status = "done"
    db.flush()
    rebuild_day_plan(
        db,
        user,
        plan_date=task.target_date,
        now=request.finished_at,
        commit=False,
    )
    response = WorkoutMutationResponse(
        state="final",
        workout=_snapshot_from_rows(task, exercises, sets_by_exercise),
        evidence_id=evidence.id if evidence is not None else None,
        elapsed_minutes=elapsed_minutes,
        progress=progress,
    )
    _store_receipt(
        db,
        user=user,
        request_id=request.request_id,
        source="workout_finish",
        fingerprint=fingerprint,
        response=response,
    )
    db.commit()
    return response


def log_nutrition(
    db: Session,
    *,
    user: User,
    request: NutritionLogRequest,
) -> NutritionMutationResponse:
    fingerprint = _fingerprint("nutrition_log", None, request)
    replay = _replay_receipt(
        db,
        user=user,
        request_id=request.request_id,
        source="nutrition_log",
        fingerprint=fingerprint,
        response_type=NutritionMutationResponse,
    )
    if replay is not None:
        return replay
    _lock_user(db, user=user)
    replay = _replay_receipt(
        db,
        user=user,
        request_id=request.request_id,
        source="nutrition_log",
        fingerprint=fingerprint,
        response_type=NutritionMutationResponse,
    )
    if replay is not None:
        return replay
    goal, task, program = _resolve_activity_links(
        db,
        user=user,
        goal_public_id=request.goal_id,
        task_id=request.task_id,
        program_id=request.program_id,
        require_open_task=True,
    )
    if (
        request.weight_observation is not None
        and goal is not None
        and goal.outcome_type == "metric"
        and goal.metric_unit != request.weight_unit
    ):
        raise ActivityConflict("metric_unit_mismatch")
    log = NutritionLog(
        user_id=user.id,
        goal_id=goal.id if goal is not None else None,
        task_id=task.id if task is not None else None,
        program_id=program.id if program is not None else None,
        request_id=request.request_id,
        occurred_at=request.occurred_at,
        meal_note=request.meal_note,
        adherence=request.adherence,
        calories=request.calories,
        protein_grams=request.protein_grams,
        fat_grams=request.fat_grams,
        carbohydrate_grams=request.carbohydrate_grams,
        target_calories=request.target_calories,
        target_protein_grams=request.target_protein_grams,
        target_fat_grams=request.target_fat_grams,
        target_carbohydrate_grams=request.target_carbohydrate_grams,
        weight_observation=request.weight_observation,
        weight_unit=request.weight_unit,
    )
    db.add(log)
    db.flush()
    progress = None
    if (
        request.weight_observation is not None
        and goal is not None
        and goal.outcome_type == "metric"
    ):
        observation = MetricObservation(
            user_id=user.id,
            goal_id=goal.id,
            request_id=request.request_id,
            value=request.weight_observation,
            unit=request.weight_unit,
            occurred_at=request.occurred_at,
            source="manual",
            note=None,
        )
        db.add(observation)
        db.flush()
        progress = recalculate_goal_progress(
            db,
            user=user,
            goal=goal,
            as_of=_current_as_of(request.occurred_at),
        )
    response = NutritionMutationResponse(
        log=NutritionLogResponse.model_validate(log),
        weight_trend=_weight_trend(
            db,
            user=user,
            unit=request.weight_unit,
        )
        if request.weight_observation is not None
        else None,
        progress=progress,
    )
    _store_receipt(
        db,
        user=user,
        request_id=request.request_id,
        source="nutrition_log",
        fingerprint=fingerprint,
        response=response,
    )
    db.commit()
    return response


def log_learning(
    db: Session,
    *,
    user: User,
    request: LearningLogRequest,
) -> LearningMutationResponse:
    fingerprint = _fingerprint("learning_log", None, request)
    replay = _replay_receipt(
        db,
        user=user,
        request_id=request.request_id,
        source="learning_log",
        fingerprint=fingerprint,
        response_type=LearningMutationResponse,
    )
    if replay is not None:
        return replay
    _lock_user(db, user=user)
    replay = _replay_receipt(
        db,
        user=user,
        request_id=request.request_id,
        source="learning_log",
        fingerprint=fingerprint,
        response_type=LearningMutationResponse,
    )
    if replay is not None:
        return replay
    resource = None
    if request.resource_id is not None:
        resource = db.scalar(
            select(LearningResource).where(
                LearningResource.id == request.resource_id,
                LearningResource.user_id == user.id,
            )
        )
        if resource is None:
            raise ActivityConflict("related_record_not_found")
    goal, task, program = _resolve_activity_links(
        db,
        user=user,
        goal_public_id=request.goal_id,
        task_id=request.task_id,
        program_id=request.program_id,
        derived_goal_id=resource.goal_id if resource is not None else None,
        derived_program_id=resource.program_id if resource is not None else None,
        require_open_task=True,
    )
    if resource is not None:
        if goal is not None and resource.goal_id not in (None, goal.id):
            raise ActivityConflict("related_record_not_found")
        if program is not None and resource.program_id not in (None, program.id):
            raise ActivityConflict("related_record_not_found")
    commitment_id = (
        _owned_task_commitment_id(
            db,
            user=user,
            task=task,
            goal=goal,
            program=program,
        )
        if task is not None and goal is not None
        else None
    )
    session = LearningSession(
        user_id=user.id,
        goal_id=goal.id if goal is not None else None,
        task_id=task.id if task is not None else None,
        program_id=program.id if program is not None else None,
        learning_resource_id=resource.id if resource is not None else None,
        request_id=request.request_id,
        occurred_at=request.occurred_at,
        competency=request.competency,
        pages_completed=request.pages_completed,
        minutes_spent=request.minutes_spent,
        exercises_completed=request.exercises_completed,
        projects_completed=request.projects_completed,
        note=request.note,
    )
    db.add(session)
    db.flush()
    evidence = None
    progress = None
    if goal is not None:
        quantity, unit = _learning_quantity(request)
        evidence = Evidence(
            user_id=user.id,
            goal_id=goal.id,
            program_id=program.id if program is not None else None,
            commitment_id=commitment_id,
            task_id=task.id if task is not None else None,
            request_id=request.request_id,
            evidence_type="session",
            quantity=quantity,
            unit=unit,
            occurred_at=request.occurred_at,
            note=None,
            attributes={
                key: value
                for key, value in {
                    "activity_type": "learning",
                    "pages_completed": request.pages_completed,
                    "minutes_spent": request.minutes_spent,
                    "exercises_completed": request.exercises_completed,
                    "projects_completed": request.projects_completed,
                }.items()
                if value is not None
            },
        )
        db.add(evidence)
        db.flush()
        session.evidence_id = evidence.id
        progress = recalculate_goal_progress(
            db,
            user=user,
            goal=goal,
            as_of=_current_as_of(request.occurred_at),
        )
    if task is not None:
        task.status = "done"
        db.flush()
        rebuild_day_plan(
            db,
            user,
            plan_date=task.target_date,
            now=request.occurred_at,
            commit=False,
        )
    response = LearningMutationResponse(
        session=LearningSessionResponse.model_validate(session),
        evidence_id=evidence.id if evidence is not None else None,
        task_status=task.status if task is not None else None,
        progress=progress,
    )
    _store_receipt(
        db,
        user=user,
        request_id=request.request_id,
        source="learning_log",
        fingerprint=fingerprint,
        response=response,
    )
    db.commit()
    return response


def propose_program_adaptation(
    db: Session,
    *,
    user: User,
    program_id: UUID,
    request: ProgramAdaptationRequest,
    candidate_builder: CandidateBuilder | None = None,
) -> ProgramAdaptationResponse:
    fingerprint = _fingerprint(
        "program_adaptation",
        str(program_id),
        request,
    )
    replay = _replay_receipt(
        db,
        user=user,
        request_id=request.request_id,
        source="program_adaptation",
        fingerprint=fingerprint,
        response_type=ProgramAdaptationResponse,
    )
    if replay is not None:
        return replay
    _lock_user(db, user=user)
    replay = _replay_receipt(
        db,
        user=user,
        request_id=request.request_id,
        source="program_adaptation",
        fingerprint=fingerprint,
        response_type=ProgramAdaptationResponse,
    )
    if replay is not None:
        return replay
    program = db.scalar(
        select(Program).where(
            Program.id == program_id,
            Program.user_id == user.id,
        )
    )
    if program is None:
        raise ActivityConflict("program_not_found")
    decision = evaluate_activity_safety(request.prompt)
    if not decision.allowed:
        response = ProgramAdaptationResponse(
            status="refused",
            confirmation_required=False,
            reason=decision.reason,
            safe_message=decision.safe_message,
        )
        _store_receipt(
            db,
            user=user,
            request_id=request.request_id,
            source="program_adaptation",
            fingerprint=fingerprint,
            response=response,
        )
        db.commit()
        return response
    if candidate_builder is None:
        raise ActivityUnavailable("adaptation_provider_unavailable")
    context = ProgramAdaptationContext(
        id=program.id,
        name=program.name,
        version=program.version,
        adaptation_rules=dict(program.adaptation_rules),
    )
    try:
        raw_candidate = candidate_builder(request.prompt, context)
    except Exception as error:
        raise ActivityUnavailable("adaptation_provider_unavailable") from error
    try:
        candidate = ProgramAdaptationCandidate.model_validate(raw_candidate)
    except (TypeError, ValidationError) as error:
        raise ActivityConflict("invalid_adaptation_candidate") from error
    encoded = json.dumps(
        candidate.model_dump(mode="json", exclude_none=True),
        ensure_ascii=False,
        sort_keys=True,
        allow_nan=False,
    )
    if len(encoded) > 10_000:
        raise ActivityConflict("invalid_adaptation_candidate")
    candidate_decision = evaluate_activity_safety(encoded)
    if not candidate_decision.allowed:
        response = ProgramAdaptationResponse(
            status="refused",
            confirmation_required=False,
            reason=candidate_decision.reason,
            safe_message=candidate_decision.safe_message,
        )
    else:
        response = ProgramAdaptationResponse(
            status="confirmation_required",
            confirmation_required=True,
            base_version=program.version,
            candidate=candidate,
        )
    _store_receipt(
        db,
        user=user,
        request_id=request.request_id,
        source="program_adaptation",
        fingerprint=fingerprint,
        response=response,
    )
    db.commit()
    return response


def _owned_workout_task(
    db: Session,
    *,
    user: User,
    task_id: int,
    lock: bool,
) -> Task:
    statement = select(Task).where(Task.id == task_id, Task.user_id == user.id)
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    task = db.scalar(statement)
    if task is None:
        raise ActivityConflict("workout_not_found")
    has_exercise = db.scalar(
        select(WorkoutExercise.id)
        .where(
            WorkoutExercise.user_id == user.id,
            WorkoutExercise.task_id == task.id,
        )
        .limit(1)
    )
    if has_exercise is None:
        raise ActivityConflict("workout_not_found")
    return task


def _require_open_workout(task: Task) -> None:
    if task.status == "done":
        raise ActivityConflict("workout_already_finished")
    if task.status != "planned":
        raise ActivityConflict("workout_not_active")


def _apply_set_facts(
    db: Session,
    *,
    user: User,
    task: Task,
    facts: list[WorkoutSetFactInput],
    recorded_at: datetime,
) -> None:
    requested_ids = [fact.set_id for fact in facts]
    rows = db.scalars(
        select(WorkoutSet)
        .join(
            WorkoutExercise,
            WorkoutExercise.id == WorkoutSet.workout_exercise_id,
        )
        .where(
            WorkoutSet.id.in_(requested_ids),
            WorkoutSet.user_id == user.id,
            WorkoutExercise.user_id == user.id,
            WorkoutExercise.task_id == task.id,
        )
        .with_for_update()
    ).all()
    by_id = {row.id: row for row in rows}
    if len(by_id) != len(requested_ids):
        raise ActivityConflict("workout_not_found")
    for fact in facts:
        row = by_id[fact.set_id]
        row.actual_weight = fact.actual_weight
        row.actual_reps = fact.actual_reps
        row.actual_rpe = fact.actual_rpe
        row.completion_status = fact.completion_status
        row.note = fact.note
        row.completed_at = (
            recorded_at if fact.completion_status in {"completed", "skipped"} else None
        )


def _workout_snapshot(
    db: Session,
    *,
    user: User,
    task: Task,
) -> WorkoutSnapshotResponse:
    exercises, sets_by_exercise = _workout_rows(db, user=user, task_id=task.id)
    if not exercises:
        raise ActivityConflict("workout_not_found")
    return _snapshot_from_rows(task, exercises, sets_by_exercise)


def _workout_rows(
    db: Session,
    *,
    user: User,
    task_id: int,
) -> tuple[list[WorkoutExercise], dict[UUID, list[WorkoutSet]]]:
    exercises = list(
        db.scalars(
            select(WorkoutExercise)
            .where(
                WorkoutExercise.user_id == user.id,
                WorkoutExercise.task_id == task_id,
            )
            .order_by(WorkoutExercise.position.asc(), WorkoutExercise.id.asc())
        )
    )
    sets_by_exercise: dict[UUID, list[WorkoutSet]] = {
        exercise.id: [] for exercise in exercises
    }
    if exercises:
        sets = db.scalars(
            select(WorkoutSet)
            .where(
                WorkoutSet.user_id == user.id,
                WorkoutSet.workout_exercise_id.in_(sets_by_exercise),
            )
            .order_by(
                WorkoutSet.workout_exercise_id.asc(),
                WorkoutSet.position.asc(),
                WorkoutSet.id.asc(),
            )
        ).all()
        for item in sets:
            sets_by_exercise[item.workout_exercise_id].append(item)
    return exercises, sets_by_exercise


def _snapshot_from_rows(
    task: Task,
    exercises: list[WorkoutExercise],
    sets_by_exercise: dict[UUID, list[WorkoutSet]],
) -> WorkoutSnapshotResponse:
    return WorkoutSnapshotResponse(
        task_id=task.id,
        task_status=task.status,
        exercises=[
            WorkoutExerciseResponse(
                id=exercise.id,
                name=exercise.name,
                position=exercise.position,
                note=exercise.note,
                sets=[
                    WorkoutSetResponse.model_validate(item)
                    for item in sets_by_exercise[exercise.id]
                ],
            )
            for exercise in exercises
        ],
    )


def _resolve_activity_links(
    db: Session,
    *,
    user: User,
    goal_public_id: UUID | None,
    task_id: int | None,
    program_id: UUID | None,
    derived_goal_id: int | None = None,
    derived_program_id: UUID | None = None,
    require_open_task: bool = False,
) -> tuple[Goal | None, Task | None, Program | None]:
    goal = None
    if goal_public_id is not None:
        goal = db.scalar(
            select(Goal).where(
                Goal.public_id == goal_public_id,
                Goal.user_id == user.id,
            )
        )
        if goal is None:
            raise ActivityConflict("related_record_not_found")
    task = None
    if task_id is not None:
        task = db.scalar(
            select(Task)
            .where(Task.id == task_id, Task.user_id == user.id)
            .with_for_update()
        )
        if task is None:
            raise ActivityConflict("related_record_not_found")
        if require_open_task and task.status != "planned":
            raise ActivityConflict("activity_task_not_active")
        goal = _merge_related_goal(db, user=user, goal=goal, goal_id=task.goal_id)
    goal = _merge_related_goal(
        db,
        user=user,
        goal=goal,
        goal_id=derived_goal_id,
    )
    canonical_program_id = task.program_id if task is not None else None
    if (
        derived_program_id is not None
        and canonical_program_id is not None
        and derived_program_id != canonical_program_id
    ):
        raise ActivityConflict("related_record_not_found")
    canonical_program_id = canonical_program_id or derived_program_id
    if (
        program_id is not None
        and canonical_program_id is not None
        and program_id != canonical_program_id
    ):
        raise ActivityConflict("related_record_not_found")
    requested_program_id = program_id or canonical_program_id
    program = _owned_program_by_id(
        db,
        user=user,
        program_id=requested_program_id,
        goal_id=goal.id if goal is not None else None,
    )
    if requested_program_id is not None and program is None:
        raise ActivityConflict("related_record_not_found")
    if program is not None:
        goal = _merge_related_goal(
            db,
            user=user,
            goal=goal,
            goal_id=program.goal_id,
        )
    if task is not None and program is not None and task.program_id not in (
        None,
        program.id,
    ):
        raise ActivityConflict("related_record_not_found")
    return goal, task, program


def _owned_task_commitment_id(
    db: Session,
    *,
    user: User,
    task: Task,
    goal: Goal,
    program: Program | None,
) -> UUID | None:
    if task.commitment_id is None:
        return None
    statement = select(WeeklyCommitment.id).where(
        WeeklyCommitment.id == task.commitment_id,
        WeeklyCommitment.user_id == user.id,
        WeeklyCommitment.goal_id == goal.id,
    )
    if program is not None:
        statement = statement.where(WeeklyCommitment.program_id == program.id)
    commitment_id = db.scalar(statement)
    if commitment_id is None:
        raise ActivityConflict("related_record_not_found")
    return commitment_id


def _merge_related_goal(
    db: Session,
    *,
    user: User,
    goal: Goal | None,
    goal_id: int | None,
) -> Goal | None:
    if goal_id is None:
        return goal
    if goal is not None:
        if goal.id != goal_id:
            raise ActivityConflict("related_record_not_found")
        return goal
    resolved = _owned_goal_by_id(db, user=user, goal_id=goal_id)
    if resolved is None:
        raise ActivityConflict("related_record_not_found")
    return resolved


def _owned_goal_by_id(
    db: Session,
    *,
    user: User,
    goal_id: int | None,
) -> Goal | None:
    if goal_id is None:
        return None
    return db.scalar(
        select(Goal).where(Goal.id == goal_id, Goal.user_id == user.id)
    )


def _owned_program_by_id(
    db: Session,
    *,
    user: User,
    program_id: UUID | None,
    goal_id: int | None,
) -> Program | None:
    if program_id is None:
        return None
    statement = select(Program).where(
        Program.id == program_id,
        Program.user_id == user.id,
    )
    if goal_id is not None:
        statement = statement.where(Program.goal_id == goal_id)
    return db.scalar(statement)


def _weight_trend(
    db: Session,
    *,
    user: User,
    unit: str,
) -> WeightTrendResponse | None:
    rows = db.scalars(
        select(NutritionLog)
        .where(
            NutritionLog.user_id == user.id,
            NutritionLog.weight_unit == unit,
            NutritionLog.weight_observation.is_not(None),
        )
        .order_by(
            NutritionLog.occurred_at.desc(),
            NutritionLog.created_at.desc(),
            NutritionLog.id.desc(),
        )
        .limit(2)
    ).all()
    if not rows or rows[0].weight_observation is None:
        return None
    current = rows[0].weight_observation.quantize(WEIGHT_QUANTUM)
    previous = (
        rows[1].weight_observation.quantize(WEIGHT_QUANTUM)
        if len(rows) > 1 and rows[1].weight_observation is not None
        else None
    )
    return WeightTrendResponse(
        current=current,
        previous=previous,
        delta=current - previous if previous is not None else None,
        unit=unit,
    )


def _learning_quantity(request: LearningLogRequest) -> tuple[Decimal, str]:
    facts = (
        (request.minutes_spent, "minutes"),
        (request.pages_completed, "pages"),
        (request.exercises_completed, "exercises"),
        (request.projects_completed, "projects"),
    )
    for value, unit in facts:
        if value is not None and value > 0:
            return Decimal(value), unit
    raise ActivityConflict("learning_fact_required")


def _fingerprint(
    operation: str,
    subject_id: int | str | None,
    request: BaseModel,
) -> str:
    payload = json.dumps(
        {
            "operation": operation,
            "subject_id": subject_id,
            "request": request.model_dump(mode="json"),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _replay_receipt(
    db: Session,
    *,
    user: User,
    request_id: str,
    source: str,
    fingerprint: str,
    response_type: type[ResponseModel],
) -> ResponseModel | None:
    receipt = db.scalar(
        select(MessageReceipt).where(
            MessageReceipt.user_id == user.id,
            MessageReceipt.request_id == request_id,
        )
    )
    if receipt is None:
        return None
    payload = receipt.response_payload or {}
    if receipt.source != source or payload.get("fingerprint") != fingerprint:
        raise ActivityConflict("idempotency_conflict")
    try:
        serialized_response = json.dumps(
            payload["response"],
            ensure_ascii=False,
            allow_nan=False,
        )
        return response_type.model_validate_json(serialized_response)
    except (KeyError, TypeError, ValueError) as error:
        raise ActivityConflict("idempotency_record_invalid") from error


def _store_receipt(
    db: Session,
    *,
    user: User,
    request_id: str,
    source: str,
    fingerprint: str,
    response: BaseModel,
) -> None:
    db.add(
        MessageReceipt(
            user_id=user.id,
            request_id=request_id,
            source=source,
            status="applied",
            response_payload={
                "fingerprint": fingerprint,
                "response": response.model_dump(mode="json"),
            },
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
    )


def _lock_user(db: Session, *, user: User) -> None:
    owned = db.scalar(select(User.id).where(User.id == user.id).with_for_update())
    if owned is None:
        raise ActivityConflict("account_not_found")


def _current_as_of(value: datetime) -> datetime:
    return max(datetime.now(timezone.utc), value)
