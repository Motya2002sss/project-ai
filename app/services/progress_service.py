from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP
from typing import Iterable, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.evidence import Evidence, GoalProgressSnapshot, MetricObservation
from app.models.goal import Goal
from app.models.program import GoalMilestone, WeeklyCommitment
from app.models.user import User
from app.schemas.progress import ProgressConfidence, ProgressResult


D = Decimal
PERCENT_QUANTUM = D("0.01")
PACE_QUANTUM = D("0.0001")
FORMULA_VERSION = "progress-v1"


@dataclass(frozen=True)
class MetricPoint:
    value: Decimal
    occurred_at: datetime


@dataclass(frozen=True)
class MilestoneProgressInput:
    status: str
    weight: Decimal | None = None


def _percentage(numerator: Decimal, denominator: Decimal) -> Decimal:
    if denominator <= 0:
        raise ValueError("denominator_must_be_positive")
    ratio = max(D("0"), min(D("1"), numerator / denominator))
    return (ratio * D("100")).quantize(PERCENT_QUANTUM, rounding=ROUND_HALF_UP)


def _confidence(sample_count: int, span_days: int) -> ProgressConfidence:
    if sample_count >= 6 and span_days >= 28:
        return "high"
    if sample_count >= 3 and span_days >= 14:
        return "medium"
    return "low"


def calculate_metric_progress(
    *,
    baseline: Decimal | None,
    current: Decimal | None,
    target: Decimal | None,
    as_of: datetime,
    observations: Sequence[MetricPoint] = (),
) -> ProgressResult:
    if baseline is None or current is None or target is None:
        return ProgressResult(
            strategy="metric",
            percentage=None,
            components={},
            reason="insufficient_data",
        )
    distance = target - baseline
    if distance == 0:
        return ProgressResult(
            strategy="metric",
            percentage=None,
            components={
                "baseline": str(baseline),
                "current": str(current),
                "target": str(target),
            },
            reason="invalid_target",
        )

    direction = D("1") if distance > 0 else D("-1")
    percentage = _percentage((current - baseline) * direction, abs(distance))
    ordered = sorted(observations, key=lambda point: point.occurred_at)
    span_days = 0
    pace: Decimal | None = None
    forecast_date = None
    if len(ordered) >= 2:
        span_seconds = (
            ordered[-1].occurred_at - ordered[0].occurred_at
        ).total_seconds()
        span_days = max(0, int(span_seconds // 86400))
        if span_seconds > 0:
            signed_change = (ordered[-1].value - ordered[0].value) * direction
            daily = signed_change / D(str(span_seconds / 86400))
            if daily > 0:
                pace = daily.quantize(PACE_QUANTUM, rounding=ROUND_HALF_UP)
                remaining = max(D("0"), (target - current) * direction)
                if remaining == 0:
                    forecast_date = as_of.date()
                else:
                    days = int(
                        (remaining / daily).to_integral_value(rounding=ROUND_CEILING)
                    )
                    forecast_date = as_of.date() + timedelta(days=days)

    components = {
        "baseline": str(baseline),
        "current": str(current),
        "target": str(target),
        "direction": "increase" if direction > 0 else "decrease",
        "observation_count": len(ordered),
        "pace_per_day": str(pace) if pace is not None else None,
    }
    return ProgressResult(
        strategy="metric",
        percentage=percentage,
        components=components,
        formula_version=FORMULA_VERSION,
        forecast_date=forecast_date,
        confidence=_confidence(len(ordered), span_days),
    )


def calculate_milestone_progress(
    milestones: Iterable[MilestoneProgressInput],
) -> ProgressResult:
    items = list(milestones)
    if not items:
        return ProgressResult(
            strategy="milestone",
            percentage=None,
            components={"milestone_count": 0},
            reason="insufficient_data",
        )
    weights = [item.weight for item in items]
    all_unweighted = all(weight is None for weight in weights)
    all_weighted = all(weight is not None and weight > 0 for weight in weights)
    if not all_unweighted and not all_weighted:
        return ProgressResult(
            strategy="milestone",
            percentage=None,
            components={"milestone_count": len(items)},
            reason="invalid_milestone_weights",
        )

    completed = [item for item in items if item.status == "completed"]
    if all_unweighted:
        numerator = D(len(completed))
        denominator = D(len(items))
        method = "equal"
    else:
        numerator = sum((item.weight or D("0")) for item in completed)
        denominator = sum((item.weight or D("0")) for item in items)
        method = "weighted"
    return ProgressResult(
        strategy="milestone",
        percentage=_percentage(numerator, denominator),
        components={
            "method": method,
            "completed_count": len(completed),
            "milestone_count": len(items),
            "completed_weight": str(numerator),
            "total_weight": str(denominator),
        },
        formula_version=FORMULA_VERSION,
        confidence=_confidence(len(items), len(items) * 7),
    )


def calculate_consistency_progress(
    *,
    planned_minutes: Decimal,
    completed_minutes: Decimal,
    planned_sessions: int,
    completed_sessions: int,
    window_days: int,
    evidence_count: int,
) -> ProgressResult:
    components = {
        "window_days": window_days,
        "planned_minutes": str(planned_minutes),
        "completed_minutes": str(completed_minutes),
        "planned_sessions": planned_sessions,
        "completed_sessions": completed_sessions,
        "evidence_count": evidence_count,
    }
    if planned_minutes > 0:
        denominator = "minutes"
        percentage = _percentage(completed_minutes, planned_minutes)
    elif planned_sessions > 0:
        denominator = "sessions"
        percentage = _percentage(D(completed_sessions), D(planned_sessions))
    else:
        return ProgressResult(
            strategy="consistency",
            percentage=None,
            components=components,
            reason="insufficient_data",
        )
    components["denominator"] = denominator
    components["pace_per_day"] = str(
        (completed_minutes / D(window_days)).quantize(
            PACE_QUANTUM, rounding=ROUND_HALF_UP
        )
        if window_days > 0
        else D("0")
    )
    return ProgressResult(
        strategy="consistency",
        percentage=percentage,
        components=components,
        formula_version=FORMULA_VERSION,
        confidence=_confidence(evidence_count, window_days),
    )


def recalculate_goal_progress(
    db: Session,
    *,
    user: User,
    goal: Goal,
    as_of: datetime | None = None,
) -> ProgressResult:
    if goal.user_id != user.id:
        raise ValueError("goal_not_owned")
    current_time = as_of or datetime.now(timezone.utc)
    strategy = goal.outcome_type

    if strategy == "metric":
        observations = db.scalars(
            select(MetricObservation)
            .where(
                MetricObservation.user_id == user.id,
                MetricObservation.goal_id == goal.id,
                MetricObservation.occurred_at <= current_time,
            )
            .order_by(MetricObservation.occurred_at.asc(), MetricObservation.id.asc())
        ).all()
        if goal.metric_unit:
            observations = [
                observation
                for observation in observations
                if observation.unit == goal.metric_unit
            ]
        current_value = observations[-1].value if observations else goal.current_value
        if observations:
            goal.current_value = current_value
        result = calculate_metric_progress(
            baseline=goal.baseline_value,
            current=current_value,
            target=goal.target_value,
            observations=[
                MetricPoint(
                    value=observation.value,
                    occurred_at=_aware(observation.occurred_at),
                )
                for observation in observations
            ],
            as_of=current_time,
        )
    elif strategy == "milestone":
        milestones = db.scalars(
            select(GoalMilestone)
            .where(
                GoalMilestone.user_id == user.id,
                GoalMilestone.goal_id == goal.id,
            )
            .order_by(GoalMilestone.position.asc())
        ).all()
        result = calculate_milestone_progress(
            [
                MilestoneProgressInput(
                    status=milestone.status,
                    weight=milestone.weight,
                )
                for milestone in milestones
            ]
        )
    elif strategy == "consistency":
        window_days = 28
        window_start = current_time - timedelta(days=window_days)
        commitments = db.scalars(
            select(WeeklyCommitment).where(
                WeeklyCommitment.user_id == user.id,
                WeeklyCommitment.goal_id == goal.id,
                WeeklyCommitment.active.is_(True),
            )
        ).all()
        evidence = db.scalars(
            select(Evidence).where(
                Evidence.user_id == user.id,
                Evidence.goal_id == goal.id,
                Evidence.occurred_at >= window_start,
                Evidence.occurred_at <= current_time,
            )
        ).all()
        weeks = D(window_days) / D("7")
        planned_minutes = sum(
            (
                D(
                    max(
                        commitment.target_minutes_week,
                        commitment.target_sessions_week
                        * commitment.minimum_block_minutes,
                    )
                    if commitment.target_minutes_week > 0
                    else 0
                )
                * weeks
                for commitment in commitments
            ),
            D("0"),
        )
        planned_sessions = sum(
            int(D(commitment.target_sessions_week) * weeks)
            for commitment in commitments
        )
        completed_minutes = sum(
            (
                item.quantity or D("0")
                for item in evidence
                if item.unit == "minutes"
            ),
            D("0"),
        )
        completed_sessions = sum(
            1 for item in evidence if item.evidence_type in {"session", "completion"}
        )
        result = calculate_consistency_progress(
            planned_minutes=planned_minutes,
            completed_minutes=completed_minutes,
            planned_sessions=planned_sessions,
            completed_sessions=completed_sessions,
            window_days=window_days,
            evidence_count=len(evidence),
        )
    else:
        result = ProgressResult(
            strategy="unknown",
            percentage=None,
            components={},
            reason="insufficient_data",
        )

    db.add(
        GoalProgressSnapshot(
            user_id=user.id,
            goal_id=goal.id,
            as_of=current_time,
            strategy=result.strategy,
            percentage=result.percentage,
            components=result.components,
            reason=result.reason,
            formula_version=result.formula_version,
            forecast_date=result.forecast_date,
            confidence=result.confidence,
        )
    )
    db.flush()
    return result


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
