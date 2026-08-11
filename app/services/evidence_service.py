import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.evidence import Evidence, GoalProgressSnapshot, MetricObservation
from app.models.goal import Goal
from app.models.message_receipt import MessageReceipt
from app.models.program import GoalMilestone, Program, WeeklyCommitment
from app.models.task import Task
from app.models.user import User
from app.schemas.goals import EvidenceCreate, MetricObservationCreate
from app.schemas.progress import ProgressResult
from app.services.progress_service import recalculate_goal_progress


class EvidenceConflict(ValueError):
    pass


@dataclass(frozen=True)
class EvidenceMutationResult:
    evidence: Evidence
    progress: ProgressResult


@dataclass(frozen=True)
class ObservationMutationResult:
    observation: MetricObservation
    progress: ProgressResult


@dataclass(frozen=True)
class MilestoneMutationResult:
    milestone: GoalMilestone
    progress: ProgressResult


def create_evidence(
    db: Session,
    *,
    user: User,
    goal: Goal,
    request: EvidenceCreate,
) -> EvidenceMutationResult:
    if goal.user_id != user.id:
        raise EvidenceConflict("goal_not_found")
    _lock_user_row(db, user=user)
    goal = _lock_goal(db, user=user, goal=goal)
    fingerprint = _request_fingerprint("goal_evidence", goal=goal, request=request)
    receipt = _find_receipt(db, user=user, request_id=request.request_id)
    if receipt is not None:
        if receipt.source != "goal_evidence":
            raise EvidenceConflict("idempotency_conflict")
        return _replay_evidence_receipt(
            db,
            user=user,
            goal=goal,
            receipt=receipt,
            fingerprint=fingerprint,
        )
    existing = db.scalar(
        select(Evidence).where(
            Evidence.user_id == user.id,
            Evidence.request_id == request.request_id,
        )
    )
    related = _resolve_related_records(db, user=user, goal=goal, request=request)
    if existing is not None:
        if not _same_evidence(existing, request, related):
            raise EvidenceConflict("idempotency_conflict")
        result = EvidenceMutationResult(
            evidence=existing,
            progress=_latest_progress(db, user=user, goal=goal),
        )
        _store_fact_receipt(
            db,
            user=user,
            request_id=request.request_id,
            source="goal_evidence",
            fingerprint=fingerprint,
            record_id=existing.id,
            progress=result.progress,
        )
        db.commit()
        return result

    evidence = Evidence(
        user_id=user.id,
        goal_id=goal.id,
        program_id=related.program_id,
        commitment_id=related.commitment_id,
        task_id=related.task_id,
        request_id=request.request_id,
        evidence_type=request.evidence_type,
        quantity=request.quantity,
        unit=request.unit,
        occurred_at=request.occurred_at,
        note=request.note,
        attributes=request.attributes,
    )
    db.add(evidence)
    db.flush()
    progress = recalculate_goal_progress(
        db, user=user, goal=goal, as_of=_current_as_of(request.occurred_at)
    )
    _store_fact_receipt(
        db,
        user=user,
        request_id=request.request_id,
        source="goal_evidence",
        fingerprint=fingerprint,
        record_id=evidence.id,
        progress=progress,
    )
    db.commit()
    db.refresh(evidence)
    return EvidenceMutationResult(evidence=evidence, progress=progress)


def create_metric_observation(
    db: Session,
    *,
    user: User,
    goal: Goal,
    request: MetricObservationCreate,
) -> ObservationMutationResult:
    if goal.user_id != user.id:
        raise EvidenceConflict("goal_not_found")
    _lock_user_row(db, user=user)
    goal = _lock_goal(db, user=user, goal=goal)
    if goal.outcome_type != "metric" or goal.metric_unit != request.unit:
        raise EvidenceConflict("metric_unit_mismatch")
    fingerprint = _request_fingerprint(
        "metric_observation", goal=goal, request=request
    )
    receipt = _find_receipt(db, user=user, request_id=request.request_id)
    if receipt is not None:
        if receipt.source != "metric_observation":
            raise EvidenceConflict("idempotency_conflict")
        return _replay_observation_receipt(
            db,
            user=user,
            goal=goal,
            receipt=receipt,
            fingerprint=fingerprint,
        )
    existing = db.scalar(
        select(MetricObservation).where(
            MetricObservation.user_id == user.id,
            MetricObservation.request_id == request.request_id,
        )
    )
    if existing is not None:
        if not _same_observation(existing, request, goal):
            raise EvidenceConflict("idempotency_conflict")
        result = ObservationMutationResult(
            observation=existing,
            progress=_latest_progress(db, user=user, goal=goal),
        )
        _store_fact_receipt(
            db,
            user=user,
            request_id=request.request_id,
            source="metric_observation",
            fingerprint=fingerprint,
            record_id=existing.id,
            progress=result.progress,
        )
        db.commit()
        return result

    observation = MetricObservation(
        user_id=user.id,
        goal_id=goal.id,
        request_id=request.request_id,
        value=request.value,
        unit=request.unit,
        occurred_at=request.occurred_at,
        source=request.source,
        note=request.note,
    )
    db.add(observation)
    db.flush()
    progress = recalculate_goal_progress(
        db, user=user, goal=goal, as_of=_current_as_of(request.occurred_at)
    )
    _store_fact_receipt(
        db,
        user=user,
        request_id=request.request_id,
        source="metric_observation",
        fingerprint=fingerprint,
        record_id=observation.id,
        progress=progress,
    )
    db.commit()
    db.refresh(observation)
    return ObservationMutationResult(observation=observation, progress=progress)


def complete_milestone(
    db: Session,
    *,
    user: User,
    goal: Goal,
    milestone_id: UUID,
    expected_version: int,
    confirmation: bool,
    occurred_at: datetime,
    request_id: str | None = None,
) -> MilestoneMutationResult:
    if goal.user_id != user.id:
        raise EvidenceConflict("milestone_not_found")
    _lock_user_row(db, user=user)
    goal = _lock_goal(db, user=user, goal=goal)
    milestone = db.scalar(
        select(GoalMilestone)
        .where(
            GoalMilestone.id == milestone_id,
            GoalMilestone.user_id == user.id,
            GoalMilestone.goal_id == goal.id,
        )
        .with_for_update()
    )
    if milestone is None:
        raise EvidenceConflict("milestone_not_found")
    fingerprint = _milestone_fingerprint(
        goal=goal,
        milestone_id=milestone_id,
        expected_version=expected_version,
        confirmation=confirmation,
        occurred_at=occurred_at,
    )
    if request_id is not None:
        receipt = db.scalar(
            select(MessageReceipt).where(
                MessageReceipt.user_id == user.id,
                MessageReceipt.request_id == request_id,
            )
        )
        if receipt is not None:
            payload = receipt.response_payload or {}
            if (
                receipt.source != "milestone_complete"
                or payload.get("fingerprint") != fingerprint
                or payload.get("milestone_id") != str(milestone_id)
            ):
                raise EvidenceConflict("idempotency_conflict")
            return MilestoneMutationResult(
                milestone=milestone,
                progress=_latest_progress(db, user=user, goal=goal),
            )
    if not confirmation:
        raise EvidenceConflict("confirmation_required")
    if milestone.status == "completed":
        if request_id is not None:
            _store_milestone_receipt(
                db,
                user=user,
                request_id=request_id,
                fingerprint=fingerprint,
                milestone_id=milestone_id,
            )
            db.commit()
        return MilestoneMutationResult(
            milestone=milestone,
            progress=_latest_progress(db, user=user, goal=goal),
        )
    if milestone.version != expected_version:
        raise EvidenceConflict("stale_milestone_version")
    milestone.status = "completed"
    milestone.completed_at = occurred_at
    milestone.version += 1
    goal.version += 1
    progress = recalculate_goal_progress(db, user=user, goal=goal, as_of=occurred_at)
    if request_id is not None:
        _store_milestone_receipt(
            db,
            user=user,
            request_id=request_id,
            fingerprint=fingerprint,
            milestone_id=milestone_id,
        )
    db.commit()
    db.refresh(milestone)
    return MilestoneMutationResult(milestone=milestone, progress=progress)


@dataclass(frozen=True)
class _RelatedRecords:
    goal_id: int
    program_id: UUID | None
    commitment_id: UUID | None
    task_id: int | None


def _resolve_related_records(
    db: Session,
    *,
    user: User,
    goal: Goal,
    request: EvidenceCreate,
) -> _RelatedRecords:
    program = None
    if request.program_id is not None:
        program = db.scalar(
            select(Program).where(
                Program.id == request.program_id,
                Program.user_id == user.id,
                Program.goal_id == goal.id,
            )
        )
        if program is None:
            raise EvidenceConflict("related_record_not_found")
    commitment = None
    if request.commitment_id is not None:
        commitment = db.scalar(
            select(WeeklyCommitment).where(
                WeeklyCommitment.id == request.commitment_id,
                WeeklyCommitment.user_id == user.id,
                WeeklyCommitment.goal_id == goal.id,
            )
        )
        if commitment is None:
            raise EvidenceConflict("related_record_not_found")
        if program is not None and commitment.program_id != program.id:
            raise EvidenceConflict("related_record_not_found")
        if program is None:
            program = db.get(Program, commitment.program_id)
    task = None
    if request.task_id is not None:
        task = db.scalar(
            select(Task).where(
                Task.id == request.task_id,
                Task.user_id == user.id,
                Task.goal_id == goal.id,
            )
        )
        if task is None:
            raise EvidenceConflict("related_record_not_found")
    return _RelatedRecords(
        goal_id=goal.id,
        program_id=program.id if program is not None else None,
        commitment_id=commitment.id if commitment is not None else None,
        task_id=task.id if task is not None else None,
    )


def _same_evidence(
    existing: Evidence,
    request: EvidenceCreate,
    related: _RelatedRecords,
) -> bool:
    return (
        existing.goal_id == related.goal_id
        and existing.program_id == related.program_id
        and existing.commitment_id == related.commitment_id
        and existing.task_id == related.task_id
        and existing.evidence_type == request.evidence_type
        and existing.quantity == request.quantity
        and existing.unit == request.unit
        and _aware(existing.occurred_at) == _aware(request.occurred_at)
        and existing.note == request.note
        and existing.attributes == request.attributes
    )


def _same_observation(
    existing: MetricObservation,
    request: MetricObservationCreate,
    goal: Goal,
) -> bool:
    return (
        existing.goal_id == goal.id
        and existing.value == request.value
        and existing.unit == request.unit
        and _aware(existing.occurred_at) == _aware(request.occurred_at)
        and existing.source == request.source
        and existing.note == request.note
    )


def _latest_progress(db: Session, *, user: User, goal: Goal) -> ProgressResult:
    snapshot = db.scalar(
        select(GoalProgressSnapshot)
        .where(
            GoalProgressSnapshot.user_id == user.id,
            GoalProgressSnapshot.goal_id == goal.id,
        )
        .order_by(
            GoalProgressSnapshot.as_of.desc(),
            GoalProgressSnapshot.created_at.desc(),
        )
        .limit(1)
    )
    if snapshot is None:
        return recalculate_goal_progress(
            db, user=user, goal=goal, as_of=datetime.now(timezone.utc)
        )
    return ProgressResult(
        strategy=snapshot.strategy,
        percentage=snapshot.percentage,
        components=snapshot.components,
        reason=snapshot.reason,
        formula_version=snapshot.formula_version,
        forecast_date=snapshot.forecast_date,
        confidence=snapshot.confidence,
    )


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _current_as_of(occurred_at: datetime) -> datetime:
    return max(datetime.now(timezone.utc), _aware(occurred_at))


def _lock_goal(db: Session, *, user: User, goal: Goal) -> Goal:
    locked = db.scalar(
        select(Goal)
        .where(Goal.id == goal.id, Goal.user_id == user.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if locked is None:
        raise EvidenceConflict("goal_not_found")
    return locked


def _lock_user_row(db: Session, *, user: User) -> None:
    if db.scalar(select(User.id).where(User.id == user.id).with_for_update()) is None:
        raise EvidenceConflict("goal_not_found")


def _find_receipt(
    db: Session, *, user: User, request_id: str
) -> MessageReceipt | None:
    return db.scalar(
        select(MessageReceipt).where(
            MessageReceipt.user_id == user.id,
            MessageReceipt.request_id == request_id,
        )
    )


def _request_fingerprint(operation: str, *, goal: Goal, request) -> str:
    payload = json.dumps(
        {
            "operation": operation,
            "goal_id": str(goal.public_id),
            "request": request.model_dump(mode="json"),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _store_fact_receipt(
    db: Session,
    *,
    user: User,
    request_id: str,
    source: str,
    fingerprint: str,
    record_id: UUID,
    progress: ProgressResult,
) -> None:
    db.add(
        MessageReceipt(
            user_id=user.id,
            request_id=request_id,
            source=source,
            status="applied",
            response_payload={
                "fingerprint": fingerprint,
                "record_id": str(record_id),
                "progress": progress.model_dump(mode="json"),
            },
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
    )


def _replay_evidence_receipt(
    db: Session,
    *,
    user: User,
    goal: Goal,
    receipt: MessageReceipt,
    fingerprint: str,
) -> EvidenceMutationResult:
    payload = receipt.response_payload or {}
    if payload.get("fingerprint") != fingerprint:
        raise EvidenceConflict("idempotency_conflict")
    try:
        record_id = UUID(str(payload["record_id"]))
        progress = ProgressResult.model_validate(payload["progress"])
    except (KeyError, TypeError, ValueError) as error:
        raise EvidenceConflict("idempotency_record_invalid") from error
    evidence = db.scalar(
        select(Evidence).where(
            Evidence.id == record_id,
            Evidence.user_id == user.id,
            Evidence.goal_id == goal.id,
        )
    )
    if evidence is None:
        raise EvidenceConflict("idempotency_record_invalid")
    return EvidenceMutationResult(evidence=evidence, progress=progress)


def _replay_observation_receipt(
    db: Session,
    *,
    user: User,
    goal: Goal,
    receipt: MessageReceipt,
    fingerprint: str,
) -> ObservationMutationResult:
    payload = receipt.response_payload or {}
    if payload.get("fingerprint") != fingerprint:
        raise EvidenceConflict("idempotency_conflict")
    try:
        record_id = UUID(str(payload["record_id"]))
        progress = ProgressResult.model_validate(payload["progress"])
    except (KeyError, TypeError, ValueError) as error:
        raise EvidenceConflict("idempotency_record_invalid") from error
    observation = db.scalar(
        select(MetricObservation).where(
            MetricObservation.id == record_id,
            MetricObservation.user_id == user.id,
            MetricObservation.goal_id == goal.id,
        )
    )
    if observation is None:
        raise EvidenceConflict("idempotency_record_invalid")
    return ObservationMutationResult(observation=observation, progress=progress)


def _milestone_fingerprint(
    *,
    goal: Goal,
    milestone_id: UUID,
    expected_version: int,
    confirmation: bool,
    occurred_at: datetime,
) -> str:
    payload = json.dumps(
        {
            "goal_id": str(goal.public_id),
            "milestone_id": str(milestone_id),
            "expected_version": expected_version,
            "confirmation": confirmation,
            "occurred_at": _aware(occurred_at).isoformat(),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _store_milestone_receipt(
    db: Session,
    *,
    user: User,
    request_id: str,
    fingerprint: str,
    milestone_id: UUID,
) -> None:
    db.add(
        MessageReceipt(
            user_id=user.id,
            request_id=request_id,
            source="milestone_complete",
            status="applied",
            response_payload={
                "fingerprint": fingerprint,
                "milestone_id": str(milestone_id),
            },
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
    )
