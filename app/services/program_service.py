import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.evidence import GoalProgressSnapshot
from app.models.goal import Goal
from app.models.message_receipt import MessageReceipt
from app.models.onboarding import ResourceBudget
from app.models.program import (
    GoalMilestone,
    Program,
    ProgramPhase,
    WeeklyCommitment,
)
from app.models.user import User
from app.schemas.goals import ProgramApplyRequest, ProgramProposalInput
from app.schemas.progress import ProgressResult
from app.services.progress_service import recalculate_goal_progress


class ProgramConflict(ValueError):
    pass


@dataclass(frozen=True)
class ProgramApplyResult:
    program: Program
    progress: ProgressResult


def preview_program_proposal(
    db: Session,
    *,
    user: User,
    goal: Goal,
    proposal: ProgramProposalInput,
) -> ProgramProposalInput:
    _validate_program_capacity(db, user=user, goal=goal, proposal=proposal)
    return proposal


def apply_program_proposal(
    db: Session,
    *,
    user: User,
    goal: Goal,
    request: ProgramApplyRequest,
) -> ProgramApplyResult:
    if goal.user_id != user.id:
        raise ProgramConflict("goal_not_found")
    fingerprint = _fingerprint(request)
    receipt = db.scalar(
        select(MessageReceipt).where(
            MessageReceipt.user_id == user.id,
            MessageReceipt.request_id == request.request_id,
        )
    )
    if receipt is not None:
        payload = receipt.response_payload or {}
        if receipt.source != "program_apply" or payload.get("fingerprint") != fingerprint:
            raise ProgramConflict("idempotency_conflict")
        program_id = payload.get("program_id")
        program = db.get(Program, UUID(program_id)) if program_id else None
        if program is None or program.user_id != user.id or program.goal_id != goal.id:
            raise ProgramConflict("idempotency_record_invalid")
        return ProgramApplyResult(
            program=program,
            progress=_latest_progress(db, user=user, goal=goal),
        )
    if db.scalar(select(User.id).where(User.id == user.id).with_for_update()) is None:
        raise ProgramConflict("goal_not_found")
    locked_goal = db.scalar(
        select(Goal)
        .where(Goal.id == goal.id, Goal.user_id == user.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if locked_goal is None:
        raise ProgramConflict("goal_not_found")
    goal = locked_goal
    receipt = db.scalar(
        select(MessageReceipt).where(
            MessageReceipt.user_id == user.id,
            MessageReceipt.request_id == request.request_id,
        )
    )
    if receipt is not None:
        payload = receipt.response_payload or {}
        if receipt.source != "program_apply" or payload.get("fingerprint") != fingerprint:
            raise ProgramConflict("idempotency_conflict")
        program_id = payload.get("program_id")
        program = db.get(Program, UUID(program_id)) if program_id else None
        if program is None or program.user_id != user.id or program.goal_id != goal.id:
            raise ProgramConflict("idempotency_record_invalid")
        return ProgramApplyResult(
            program=program,
            progress=_latest_progress(db, user=user, goal=goal),
        )
    if not request.confirmation:
        raise ProgramConflict("confirmation_required")
    if goal.version != request.expected_goal_version:
        raise ProgramConflict("stale_goal_version")
    _validate_program_capacity(
        db, user=user, goal=goal, proposal=request.proposal
    )

    proposal = request.proposal
    existing_milestones = {item.position: item for item in goal.milestones}
    proposed_positions = {item.position for item in proposal.milestones}
    if any(
        milestone.status == "completed" and milestone.position not in proposed_positions
        for milestone in existing_milestones.values()
    ):
        raise ProgramConflict("completed_milestone_cannot_be_removed")

    existing_active = db.scalars(
        select(Program).where(
            Program.user_id == user.id,
            Program.goal_id == goal.id,
            Program.status == "active",
        )
    ).all()
    for existing in existing_active:
        existing.status = "archived"
        existing.version += 1

    program = Program(
        user_id=user.id,
        goal_id=goal.id,
        name=proposal.name,
        status="active",
        minimum_minutes_week=proposal.minimum_minutes_week,
        comfortable_minutes_week=proposal.comfortable_minutes_week,
        maximum_minutes_week=proposal.maximum_minutes_week,
        adaptation_rules=proposal.adaptation_rules,
    )
    db.add(program)
    db.flush()

    phases_by_position: dict[int, ProgramPhase] = {}
    for phase_input in sorted(proposal.phases, key=lambda item: item.position):
        phase = ProgramPhase(
            user_id=user.id,
            program_id=program.id,
            title=phase_input.title,
            position=phase_input.position,
            status="planned",
            start_date=phase_input.start_date,
            end_date=phase_input.end_date,
            configuration=phase_input.configuration,
        )
        program.phases.append(phase)
        phases_by_position[phase_input.position] = phase
    db.flush()

    for milestone in list(existing_milestones.values()):
        if milestone.position not in proposed_positions:
            db.delete(milestone)
    for milestone_input in sorted(
        proposal.milestones, key=lambda item: item.position
    ):
        milestone = existing_milestones.get(milestone_input.position)
        if milestone is None:
            milestone = GoalMilestone(
                user_id=user.id,
                goal_id=goal.id,
                title=milestone_input.title,
                description=milestone_input.description,
                position=milestone_input.position,
                criteria=milestone_input.criteria,
                weight=milestone_input.weight,
            )
            goal.milestones.append(milestone)
        elif milestone.status != "completed":
            milestone.title = milestone_input.title
            milestone.description = milestone_input.description
            milestone.criteria = milestone_input.criteria
            milestone.weight = milestone_input.weight
            milestone.version += 1

    for commitment_input in proposal.commitments:
        phase = (
            phases_by_position.get(commitment_input.phase_position)
            if commitment_input.phase_position is not None
            else None
        )
        commitment = WeeklyCommitment(
            user_id=user.id,
            goal_id=goal.id,
            program_id=program.id,
            phase_id=phase.id if phase is not None else None,
            title=commitment_input.title,
            target_minutes_week=commitment_input.target_minutes_week,
            target_sessions_week=commitment_input.target_sessions_week,
            minimum_block_minutes=commitment_input.minimum_block_minutes,
            allowed_weekdays=commitment_input.allowed_weekdays,
            preferred_window=commitment_input.preferred_window,
            splittable=commitment_input.splittable,
            recovery_gap_minutes=commitment_input.recovery_gap_minutes,
        )
        program.commitments.append(commitment)

    goal.allocation_minutes_week = proposal.comfortable_minutes_week
    goal.version += 1
    db.flush()
    progress = recalculate_goal_progress(
        db, user=user, goal=goal, as_of=datetime.now(timezone.utc)
    )
    db.add(
        MessageReceipt(
            user_id=user.id,
            request_id=request.request_id,
            source="program_apply",
            status="applied",
            response_payload={
                "fingerprint": fingerprint,
                "program_id": str(program.id),
            },
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
    )
    db.commit()
    db.refresh(program)
    return ProgramApplyResult(program=program, progress=progress)


def _validate_program_capacity(
    db: Session,
    *,
    user: User,
    goal: Goal,
    proposal: ProgramProposalInput,
) -> None:
    if goal.user_id != user.id:
        raise ProgramConflict("goal_not_found")
    budget = db.scalar(
        select(ResourceBudget).where(ResourceBudget.user_id == user.id)
    )
    if budget is None:
        raise ProgramConflict("resource_budget_required")
    capacity = budget.allocatable_minutes
    if goal.allocation_minutes_week is not None:
        capacity = (
            min(capacity, goal.allocation_minutes_week)
            if capacity is not None
            else goal.allocation_minutes_week
        )
    if capacity is not None and proposal.maximum_minutes_week > capacity:
        raise ProgramConflict("resource_budget_exceeded")


def _latest_progress(db: Session, *, user: User, goal: Goal) -> ProgressResult:
    snapshot = db.scalar(
        select(GoalProgressSnapshot)
        .where(
            GoalProgressSnapshot.user_id == user.id,
            GoalProgressSnapshot.goal_id == goal.id,
        )
        .order_by(GoalProgressSnapshot.created_at.desc())
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


def _fingerprint(request: ProgramApplyRequest) -> str:
    payload = json.dumps(
        request.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
