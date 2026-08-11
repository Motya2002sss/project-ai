import base64
import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import and_, case, func, or_, select, union_all
from sqlalchemy.orm import Session

from app.models.evidence import Evidence, GoalProgressSnapshot
from app.models.goal import Goal
from app.models.program import GoalMilestone, Program, ProgramPhase, WeeklyCommitment
from app.models.user import User
from app.schemas.goals import GoalResponse
from app.schemas.path import (
    EvidencePageResponse,
    EvidenceSummary,
    FormulaExplanation,
    GoalPathResponse,
    MilestoneSummary,
    NextStepSummary,
    PathResponse,
    PhaseSummary,
    ProgramSummary,
)
from app.schemas.progress import ProgressResult
from app.services.time_service import get_user_now


PATH_GOAL_LIMIT = 3
RECENT_EVIDENCE_LIMIT = 3


class EvidenceCursorError(ValueError):
    pass


@dataclass(frozen=True)
class _EvidenceRecord:
    id: UUID
    goal_id: int
    evidence_type: str
    quantity: Decimal | None
    unit: str | None
    occurred_at: datetime


@dataclass(frozen=True)
class _SnapshotRecord:
    goal_id: int
    strategy: str
    percentage: Decimal | None
    components: dict
    reason: str | None
    formula_version: str
    forecast_date: date | None
    confidence: str


def get_path_read_model(db: Session, *, user: User) -> PathResponse:
    goals = list(
        db.scalars(
            select(Goal)
            .where(Goal.user_id == user.id, Goal.status == "active")
            .order_by(
                case(
                    (Goal.priority == "high", 0),
                    (Goal.priority == "medium", 1),
                    (Goal.priority == "low", 2),
                    else_=1,
                ),
                Goal.id,
            )
            .limit(PATH_GOAL_LIMIT)
        ).all()
    )
    return PathResponse(
        goals=_build_goal_paths(
            db,
            user=user,
            goals=goals,
            as_of_date=get_user_now(user).date(),
        )
    )


def get_goal_detail_read_model(
    db: Session,
    *,
    user: User,
    goal: Goal,
) -> GoalPathResponse:
    if goal.user_id != user.id:
        raise ValueError("goal_not_owned")
    return _build_goal_paths(
        db,
        user=user,
        goals=[goal],
        as_of_date=get_user_now(user).date(),
    )[0]


def list_goal_evidence_page(
    db: Session,
    *,
    user: User,
    goal: Goal,
    limit: int,
    cursor: str | None,
) -> EvidencePageResponse:
    if goal.user_id != user.id:
        raise ValueError("goal_not_owned")
    statement = select(
        Evidence.id,
        Evidence.goal_id,
        Evidence.evidence_type,
        Evidence.quantity,
        Evidence.unit,
        Evidence.occurred_at,
    ).where(
        Evidence.user_id == user.id,
        Evidence.goal_id == goal.id,
    )
    if cursor:
        occurred_at, evidence_id = _decode_cursor(cursor)
        statement = statement.where(
            or_(
                Evidence.occurred_at < occurred_at,
                and_(
                    Evidence.occurred_at == occurred_at,
                    Evidence.id < evidence_id,
                ),
            )
        )
    rows = list(
        db.execute(
            statement.order_by(Evidence.occurred_at.desc(), Evidence.id.desc()).limit(
                limit + 1
            )
        ).all()
    )
    records = [_EvidenceRecord(*row) for row in rows]
    has_more = len(records) > limit
    page = records[:limit]
    next_cursor = _encode_cursor(page[-1]) if has_more and page else None
    return EvidencePageResponse(
        items=[_evidence_summary(item) for item in page],
        next_cursor=next_cursor,
    )


def _build_goal_paths(
    db: Session,
    *,
    user: User,
    goals: list[Goal],
    as_of_date: date,
) -> list[GoalPathResponse]:
    if not goals:
        return []
    goal_ids = [goal.id for goal in goals]
    milestones = list(
        db.scalars(
            select(GoalMilestone)
            .where(
                GoalMilestone.user_id == user.id,
                GoalMilestone.goal_id.in_(goal_ids),
            )
            .order_by(GoalMilestone.goal_id, GoalMilestone.position)
        ).all()
    )
    programs = _current_programs(db, user=user, goal_ids=goal_ids)
    program_ids = [program.id for program in programs]
    phases = (
        list(
            db.scalars(
                select(ProgramPhase)
                .where(
                    ProgramPhase.user_id == user.id,
                    ProgramPhase.program_id.in_(program_ids),
                )
                .order_by(ProgramPhase.program_id, ProgramPhase.position)
            ).all()
        )
        if program_ids
        else []
    )
    commitments = (
        list(
            db.scalars(
                select(WeeklyCommitment)
                .where(
                    WeeklyCommitment.user_id == user.id,
                    WeeklyCommitment.program_id.in_(program_ids),
                    WeeklyCommitment.active.is_(True),
                )
                .order_by(
                    WeeklyCommitment.program_id,
                    WeeklyCommitment.created_at,
                    WeeklyCommitment.id,
                )
            ).all()
        )
        if program_ids
        else []
    )
    snapshots = _latest_snapshots(db, user=user, goal_ids=goal_ids)
    evidence = _recent_evidence(db, user=user, goal_ids=goal_ids)

    milestones_by_goal: dict[int, list[GoalMilestone]] = {}
    for item in milestones:
        milestones_by_goal.setdefault(item.goal_id, []).append(item)
    programs_by_goal = {program.goal_id: program for program in programs}
    phases_by_program: dict[UUID, list[ProgramPhase]] = {}
    for item in phases:
        phases_by_program.setdefault(item.program_id, []).append(item)
    commitments_by_program: dict[UUID, list[WeeklyCommitment]] = {}
    for item in commitments:
        commitments_by_program.setdefault(item.program_id, []).append(item)
    snapshots_by_goal = {snapshot.goal_id: snapshot for snapshot in snapshots}
    evidence_by_goal: dict[int, list[_EvidenceRecord]] = {}
    for item in evidence:
        evidence_by_goal.setdefault(item.goal_id, []).append(item)

    result: list[GoalPathResponse] = []
    for goal in goals:
        program = programs_by_goal.get(goal.id)
        program_phases = phases_by_program.get(program.id, []) if program else []
        current_phase = _select_current_phase(program_phases, as_of_date)
        program_commitments = (
            commitments_by_program.get(program.id, []) if program else []
        )
        next_step = _select_next_step(program_commitments, current_phase)
        progress = _progress_result(goal, snapshots_by_goal.get(goal.id))
        result.append(
            GoalPathResponse(
                goal=GoalResponse.model_validate(goal),
                progress=progress,
                formula=_formula_explanation(progress),
                milestones=[
                    MilestoneSummary(
                        id=item.id,
                        title=item.title,
                        description=item.description,
                        position=item.position,
                        weight=item.weight,
                        status=item.status,
                        completed_at=item.completed_at,
                    )
                    for item in milestones_by_goal.get(goal.id, [])
                ],
                current_program=_program_summary(program) if program else None,
                current_phase=_phase_summary(current_phase) if current_phase else None,
                next_step=_next_step_summary(next_step) if next_step else None,
                recent_evidence=[
                    _evidence_summary(item)
                    for item in evidence_by_goal.get(goal.id, [])
                ],
            )
        )
    return result


def _current_programs(
    db: Session,
    *,
    user: User,
    goal_ids: list[int],
) -> list[Program]:
    ranked = (
        select(
            Program.id.label("program_id"),
            func.row_number()
            .over(
                partition_by=Program.goal_id,
                order_by=(Program.created_at.desc(), Program.id.desc()),
            )
            .label("position"),
        )
        .where(
            Program.user_id == user.id,
            Program.goal_id.in_(goal_ids),
            Program.status == "active",
        )
        .subquery()
    )
    return list(
        db.scalars(
            select(Program)
            .join(ranked, ranked.c.program_id == Program.id)
            .where(ranked.c.position == 1)
        ).all()
    )


def _latest_snapshots(
    db: Session,
    *,
    user: User,
    goal_ids: list[int],
) -> list[_SnapshotRecord]:
    branches = []
    for index, goal_id in enumerate(goal_ids):
        latest = (
            select(GoalProgressSnapshot)
            .with_only_columns(
                GoalProgressSnapshot.goal_id,
                GoalProgressSnapshot.strategy,
                GoalProgressSnapshot.percentage,
                GoalProgressSnapshot.components,
                GoalProgressSnapshot.reason,
                GoalProgressSnapshot.formula_version,
                GoalProgressSnapshot.forecast_date,
                GoalProgressSnapshot.confidence,
            )
            .where(
                GoalProgressSnapshot.user_id == user.id,
                GoalProgressSnapshot.goal_id == goal_id,
            )
            .order_by(
                GoalProgressSnapshot.as_of.desc(),
                GoalProgressSnapshot.created_at.desc(),
                GoalProgressSnapshot.id.desc(),
            )
            .limit(1)
            .subquery(f"latest_snapshot_{index}")
        )
        branches.append(select(*latest.c))
    statement = branches[0] if len(branches) == 1 else union_all(*branches)
    return [_SnapshotRecord(*row) for row in db.execute(statement).all()]


def _recent_evidence(
    db: Session,
    *,
    user: User,
    goal_ids: list[int],
) -> list[_EvidenceRecord]:
    branches = []
    for index, goal_id in enumerate(goal_ids):
        latest = (
            select(
                Evidence.id,
                Evidence.goal_id,
                Evidence.evidence_type,
                Evidence.quantity,
                Evidence.unit,
                Evidence.occurred_at,
            )
            .where(Evidence.user_id == user.id, Evidence.goal_id == goal_id)
            .order_by(Evidence.occurred_at.desc(), Evidence.id.desc())
            .limit(RECENT_EVIDENCE_LIMIT)
            .subquery(f"latest_evidence_{index}")
        )
        branches.append(select(*latest.c))
    statement = branches[0] if len(branches) == 1 else union_all(*branches)
    records = [_EvidenceRecord(*row) for row in db.execute(statement).all()]
    goal_order = {goal_id: index for index, goal_id in enumerate(goal_ids)}
    records.sort(
        key=lambda item: (
            goal_order[item.goal_id],
            -_aware(item.occurred_at).timestamp(),
            -item.id.int,
        )
    )
    return records


def _select_current_phase(
    phases: list[ProgramPhase],
    as_of_date: date,
) -> ProgramPhase | None:
    if not phases:
        return None
    active = [
        phase
        for phase in phases
        if phase.status == "active"
        and (phase.start_date is None or phase.start_date <= as_of_date)
        and (phase.end_date is None or phase.end_date >= as_of_date)
    ]
    if active:
        return min(active, key=lambda item: item.position)
    dated = [
        phase
        for phase in phases
        if phase.status == "planned"
        and (phase.start_date is None or phase.start_date <= as_of_date)
        and (phase.end_date is None or phase.end_date >= as_of_date)
    ]
    if dated:
        return min(dated, key=lambda item: item.position)
    return None


def _select_next_step(
    commitments: list[WeeklyCommitment],
    current_phase: ProgramPhase | None,
) -> WeeklyCommitment | None:
    if not commitments:
        return None
    if current_phase is not None:
        matching = [
            item for item in commitments if item.phase_id == current_phase.id
        ]
        if matching:
            return matching[0]
    phase_free = [item for item in commitments if item.phase_id is None]
    return phase_free[0] if phase_free else None


def _progress_result(
    goal: Goal,
    snapshot: _SnapshotRecord | None,
) -> ProgressResult:
    if snapshot is None:
        strategy = goal.outcome_type
        if strategy not in {"metric", "milestone", "consistency"}:
            strategy = "unknown"
        return ProgressResult(
            strategy=strategy,
            percentage=None,
            components={},
            reason="not_calculated",
            confidence="low",
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


def _formula_explanation(progress: ProgressResult) -> FormulaExplanation:
    if progress.reason == "invalid_target":
        return FormulaExplanation(
            strategy=progress.strategy,
            label="Нужно уточнить цель",
            explanation=(
                "Процент появится после исправления исходного и целевого значений."
            ),
        )
    if progress.reason == "invalid_milestone_weights":
        return FormulaExplanation(
            strategy=progress.strategy,
            label="Нужно исправить веса этапов",
            explanation=(
                "Процент появится после того, как веса всех этапов будут заданы "
                "единообразно."
            ),
        )
    if progress.percentage is None or progress.reason in {
        "not_calculated",
        "insufficient_data",
    }:
        return FormulaExplanation(
            strategy=progress.strategy,
            label="Недостаточно данных",
            explanation="Процент появится после накопления данных для проверяемой формулы.",
        )
    if progress.strategy == "metric":
        return FormulaExplanation(
            strategy="metric",
            label="Измеримый результат",
            explanation="Изменение от исходного значения до целевого значения.",
        )
    if progress.strategy == "milestone":
        method = progress.components.get("method")
        if method == "weighted":
            explanation = "Сумма подтверждённых весов этапов относительно общего веса."
        elif method == "equal":
            explanation = "Подтверждённые этапы относительно всех определённых этапов."
        else:
            return FormulaExplanation(
                strategy="milestone",
                label="Недостаточно данных",
                explanation="Процент появится после определения проверяемого состава этапов.",
            )
        return FormulaExplanation(
            strategy="milestone",
            label="Этапы пути",
            explanation=explanation,
        )
    if progress.strategy == "consistency":
        denominator = progress.components.get("denominator")
        if denominator == "minutes":
            explanation = "Фактические минуты относительно запланированных минут."
        elif denominator == "sessions":
            explanation = "Фактические сессии относительно запланированных сессий."
        else:
            return FormulaExplanation(
                strategy="consistency",
                label="Недостаточно данных",
                explanation="Процент появится после определения проверяемой недельной нагрузки.",
            )
        return FormulaExplanation(
            strategy="consistency",
            label="Регулярность",
            explanation=explanation,
        )
    return FormulaExplanation(
        strategy="unknown",
        label="Недостаточно данных",
        explanation="Процент появится только после определения проверяемой формулы.",
    )


def _program_summary(program: Program) -> ProgramSummary:
    return ProgramSummary(
        id=program.id,
        name=program.name,
        status=program.status,
        minimum_minutes_week=program.minimum_minutes_week,
        comfortable_minutes_week=program.comfortable_minutes_week,
        maximum_minutes_week=program.maximum_minutes_week,
        version=program.version,
    )


def _phase_summary(phase: ProgramPhase) -> PhaseSummary:
    return PhaseSummary(
        id=phase.id,
        title=phase.title,
        position=phase.position,
        status=phase.status,
        start_date=phase.start_date,
        end_date=phase.end_date,
    )


def _next_step_summary(commitment: WeeklyCommitment) -> NextStepSummary:
    return NextStepSummary(
        commitment_id=commitment.id,
        title=commitment.title,
        target_minutes_week=commitment.target_minutes_week,
        target_sessions_week=commitment.target_sessions_week,
        minimum_block_minutes=commitment.minimum_block_minutes,
        allowed_weekdays=commitment.allowed_weekdays,
        preferred_window=commitment.preferred_window,
    )


def _evidence_summary(evidence: _EvidenceRecord) -> EvidenceSummary:
    return EvidenceSummary(
        id=evidence.id,
        evidence_type=evidence.evidence_type,
        quantity=evidence.quantity,
        unit=evidence.unit,
        occurred_at=evidence.occurred_at,
    )


def _encode_cursor(evidence: _EvidenceRecord) -> str:
    payload = json.dumps(
        {
            "occurred_at": _aware(evidence.occurred_at).isoformat(),
            "id": str(evidence.id),
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        raw = base64.b64decode(padded, altchars=b"-_", validate=True)
        payload = json.loads(raw.decode("utf-8"))
        if set(payload) != {"occurred_at", "id"}:
            raise ValueError
        occurred_at = datetime.fromisoformat(payload["occurred_at"])
        if occurred_at.tzinfo is None:
            raise ValueError
        return occurred_at, UUID(payload["id"])
    except (TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise EvidenceCursorError("invalid_cursor") from error


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
