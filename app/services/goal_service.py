import hashlib
import json
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.llm.schemas import ParsedTask
from app.models.goal import Goal
from app.models.message_receipt import MessageReceipt
from app.models.user import User
from app.schemas.goals import (
    GoalCreateRequest,
    GoalDeleteRequest,
    GoalMutationResponse,
    GoalResponse,
    GoalUpdateRequest,
    GoalVersionRequest,
)
from app.schemas.progress import ProgressResult
from app.services.progress_service import recalculate_goal_progress


class GoalConflict(ValueError):
    pass


def create_goals_from_titles(
    db: Session,
    user: User,
    titles: list[str],
) -> list[Goal]:
    goals: list[Goal] = []

    for title in titles:
        normalized_title = title.strip()

        if not normalized_title:
            continue

        exists = (
            db.query(Goal)
            .filter(
                Goal.user_id == user.id,
                Goal.title.ilike(normalized_title),
                Goal.status == "active",
            )
            .one_or_none()
        )

        if exists:
            continue

        goal = Goal(
            user_id=user.id,
            title=normalized_title[:255],
            category="personal",
            priority="medium",
            status="active",
        )

        db.add(goal)
        goals.append(goal)

    db.commit()

    for goal in goals:
        db.refresh(goal)

    return goals


def list_active_goals(db: Session, user: User) -> list[Goal]:
    return (
        db.query(Goal)
        .filter(
            Goal.user_id == user.id,
            Goal.status == "active",
        )
        .order_by(Goal.id.asc())
        .all()
    )


def format_goals(goals: list[Goal]) -> str:
    if not goals:
        return "Активных целей пока нет."

    lines = []

    for goal in goals:
        lines.append(f"{goal.id}. {goal.title}")

    return "\n".join(lines)


def suggest_tasks_from_goals(goals: list[Goal]) -> list[ParsedTask]:
    suggestions: list[ParsedTask] = []

    for goal in goals:
        title = goal.title.lower()

        if any(word in title for word in ["деньги", "финанс", "накоп", "сбереж", "долг", "бюджет"]):
            suggestions.append(
                ParsedTask(
                    title=f"Сделать один финансовый шаг по цели: {goal.title}",
                    priority="high",
                    estimated_minutes=45,
                )
            )
            continue

        if any(word in title for word in ["уч", "язык", "курс", "экзам", "книг", "математ", "англий"]):
            suggestions.append(
                ParsedTask(
                    title=f"Позаниматься 30-45 минут по цели: {goal.title}",
                    priority="high",
                    estimated_minutes=45,
                )
            )
            continue

        if any(word in title for word in ["здоров", "спорт", "трен", "зал", "жим", "бег", "сон"]):
            suggestions.append(
                ParsedTask(
                    title=f"Сделать короткий шаг для здоровья/спорта: {goal.title}",
                    priority="high",
                    estimated_minutes=45,
                )
            )
            continue

        if any(word in title for word in ["сем", "родител", "дет", "отношен", "друз"]):
            suggestions.append(
                ParsedTask(
                    title=f"Сделать один шаг для отношений: {goal.title}",
                    priority="medium",
                    estimated_minutes=30,
                )
            )
            continue

        if any(word in title for word in ["рис", "музык", "твор", "пис", "фото", "дизайн"]):
            suggestions.append(
                ParsedTask(
                    title=f"Выделить время на творческий шаг: {goal.title}",
                    priority="medium",
                    estimated_minutes=45,
                )
            )
            continue

        if any(word in title for word in ["проект", "прилож", "продукт", "стартап", "карьер", "работ"]):
            suggestions.append(
                ParsedTask(
                    title=f"Сделать один конкретный шаг по проекту/карьере: {goal.title}",
                    priority="high",
                    estimated_minutes=60,
                )
            )
            continue

        suggestions.append(
            ParsedTask(
                title=f"Сделать следующий маленький шаг по цели: {goal.title}",
                priority="medium",
                estimated_minutes=45,
            )
        )

    unique: list[ParsedTask] = []
    seen: set[str] = set()

    for task in suggestions:
        key = task.title.lower()

        if key in seen:
            continue

        seen.add(key)
        unique.append(task)

    return unique


def get_owned_goal(db: Session, *, user: User, public_id: UUID) -> Goal | None:
    return db.scalar(
        select(Goal).where(Goal.user_id == user.id, Goal.public_id == public_id)
    )


def create_goal_v2(
    db: Session,
    *,
    user: User,
    request: GoalCreateRequest,
) -> GoalMutationResponse:
    replay = _replay_receipt(
        db,
        user=user,
        request_id=request.request_id,
        operation="goal_create",
        fingerprint=_fingerprint("goal_create", None, request),
    )
    if replay is not None:
        return replay
    _lock_user_row(db, user=user)
    replay = _replay_receipt(
        db,
        user=user,
        request_id=request.request_id,
        operation="goal_create",
        fingerprint=_fingerprint("goal_create", None, request),
    )
    if replay is not None:
        return replay
    active_count = db.scalar(
        select(func.count(Goal.id)).where(
            Goal.user_id == user.id,
            Goal.status == "active",
        )
    )
    if (active_count or 0) >= 3:
        raise GoalConflict("active_goal_limit")
    goal = Goal(
        user_id=user.id,
        title=request.title.strip(),
        category="personal",
        priority="medium",
        status="active",
        life_area=request.life_area,
        outcome_type=request.outcome_type,
        baseline_value=request.baseline_value,
        current_value=request.baseline_value,
        target_value=request.target_value,
        metric_unit=request.metric_unit,
        deadline=request.deadline,
        intensity=request.intensity,
        allocation_minutes_week=request.allocation_minutes_week,
    )
    db.add(goal)
    db.flush()
    progress = recalculate_goal_progress(
        db, user=user, goal=goal, as_of=datetime.now(timezone.utc)
    )
    response = _goal_mutation_response(goal, progress)
    _store_receipt(
        db,
        user=user,
        request_id=request.request_id,
        operation="goal_create",
        fingerprint=_fingerprint("goal_create", None, request),
        response=response,
    )
    db.commit()
    return response


def update_goal_v2(
    db: Session,
    *,
    user: User,
    goal: Goal,
    request: GoalUpdateRequest,
) -> GoalMutationResponse:
    if goal.user_id != user.id:
        raise GoalConflict("goal_not_found")
    fingerprint = _fingerprint("goal_update", goal.public_id, request)
    replay = _replay_receipt(
        db,
        user=user,
        request_id=request.request_id,
        operation="goal_update",
        fingerprint=fingerprint,
    )
    if replay is not None:
        return replay
    _lock_user_row(db, user=user)
    goal = _lock_owned_goal(db, user=user, goal_id=goal.id)
    if goal is None:
        raise GoalConflict("goal_not_found")
    replay = _replay_receipt(
        db,
        user=user,
        request_id=request.request_id,
        operation="goal_update",
        fingerprint=fingerprint,
    )
    if replay is not None:
        return replay
    if goal.version != request.expected_version:
        raise GoalConflict("stale_goal_version")
    risky_change = (
        "deadline" in request.model_fields_set and request.deadline != goal.deadline
    ) or (
        "intensity" in request.model_fields_set
        and request.intensity != goal.intensity
    )
    if risky_change and not request.confirmation:
        raise GoalConflict("confirmation_required")

    mutable_fields = (
        "title",
        "life_area",
        "baseline_value",
        "target_value",
        "metric_unit",
        "deadline",
        "intensity",
        "allocation_minutes_week",
    )
    for field in mutable_fields:
        if field in request.model_fields_set:
            value = getattr(request, field)
            if field in {"title", "life_area"} and value is None:
                raise GoalConflict("invalid_goal_update")
            setattr(goal, field, value)
    if goal.outcome_type == "metric" and (
        goal.baseline_value is None
        or goal.target_value is None
        or goal.metric_unit is None
        or goal.baseline_value == goal.target_value
    ):
        raise GoalConflict("invalid_metric_goal")
    goal.version += 1
    progress = recalculate_goal_progress(
        db, user=user, goal=goal, as_of=datetime.now(timezone.utc)
    )
    response = _goal_mutation_response(goal, progress)
    _store_receipt(
        db,
        user=user,
        request_id=request.request_id,
        operation="goal_update",
        fingerprint=fingerprint,
        response=response,
    )
    db.commit()
    return response


def set_goal_status_v2(
    db: Session,
    *,
    user: User,
    goal: Goal,
    request: GoalVersionRequest,
    target_status: str,
) -> GoalMutationResponse:
    if goal.user_id != user.id:
        raise GoalConflict("goal_not_found")
    operation = f"goal_{target_status}"
    fingerprint = _fingerprint(operation, goal.public_id, request)
    replay = _replay_receipt(
        db,
        user=user,
        request_id=request.request_id,
        operation=operation,
        fingerprint=fingerprint,
    )
    if replay is not None:
        return replay
    _lock_user_row(db, user=user)
    goal = _lock_owned_goal(db, user=user, goal_id=goal.id)
    if goal is None:
        raise GoalConflict("goal_not_found")
    replay = _replay_receipt(
        db,
        user=user,
        request_id=request.request_id,
        operation=operation,
        fingerprint=fingerprint,
    )
    if replay is not None:
        return replay
    if goal.version != request.expected_version:
        raise GoalConflict("stale_goal_version")
    if target_status == "active" and goal.status != "active":
        active_count = db.scalar(
            select(func.count(Goal.id)).where(
                Goal.user_id == user.id,
                Goal.status == "active",
            )
        )
        if (active_count or 0) >= 3:
            raise GoalConflict("active_goal_limit")
    goal.status = target_status
    goal.version += 1
    progress = recalculate_goal_progress(
        db, user=user, goal=goal, as_of=datetime.now(timezone.utc)
    )
    response = _goal_mutation_response(goal, progress)
    _store_receipt(
        db,
        user=user,
        request_id=request.request_id,
        operation=operation,
        fingerprint=fingerprint,
        response=response,
    )
    db.commit()
    return response


def delete_goal_v2(
    db: Session,
    *,
    user: User,
    public_id: UUID,
    request: GoalDeleteRequest,
) -> None:
    operation = "goal_delete"
    fingerprint = _fingerprint(operation, public_id, request)
    receipt = db.scalar(
        select(MessageReceipt).where(
            MessageReceipt.user_id == user.id,
            MessageReceipt.request_id == request.request_id,
        )
    )
    if receipt is not None:
        payload = receipt.response_payload or {}
        if (
            receipt.source != operation
            or payload.get("fingerprint") != fingerprint
            or payload.get("deleted") is not True
        ):
            raise GoalConflict("idempotency_conflict")
        return
    _lock_user_row(db, user=user)
    receipt = db.scalar(
        select(MessageReceipt).where(
            MessageReceipt.user_id == user.id,
            MessageReceipt.request_id == request.request_id,
        )
    )
    if receipt is not None:
        payload = receipt.response_payload or {}
        if (
            receipt.source == operation
            and payload.get("fingerprint") == fingerprint
            and payload.get("deleted") is True
        ):
            return
        raise GoalConflict("idempotency_conflict")
    goal = db.scalar(
        select(Goal)
        .where(Goal.user_id == user.id, Goal.public_id == public_id)
        .with_for_update()
    )
    if goal is None:
        raise GoalConflict("goal_not_found")
    if goal.version != request.expected_version:
        raise GoalConflict("stale_goal_version")
    db.delete(goal)
    db.add(
        MessageReceipt(
            user_id=user.id,
            request_id=request.request_id,
            source=operation,
            status="applied",
            response_payload={"fingerprint": fingerprint, "deleted": True},
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
    )
    db.commit()


def _goal_mutation_response(
    goal: Goal, progress: ProgressResult
) -> GoalMutationResponse:
    return GoalMutationResponse(
        goal=GoalResponse.model_validate(goal),
        progress=progress,
    )


def _lock_owned_goal(
    db: Session, *, user: User, goal_id: int
) -> Goal | None:
    return db.scalar(
        select(Goal)
        .where(Goal.id == goal_id, Goal.user_id == user.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


def _lock_user_row(db: Session, *, user: User) -> None:
    if db.scalar(select(User.id).where(User.id == user.id).with_for_update()) is None:
        raise GoalConflict("goal_not_found")


def _fingerprint(operation: str, public_id: UUID | None, request) -> str:
    payload = json.dumps(
        {
            "operation": operation,
            "public_id": str(public_id) if public_id is not None else None,
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
    operation: str,
    fingerprint: str,
) -> GoalMutationResponse | None:
    receipt = db.scalar(
        select(MessageReceipt).where(
            MessageReceipt.user_id == user.id,
            MessageReceipt.request_id == request_id,
        )
    )
    if receipt is None:
        return None
    payload = receipt.response_payload or {}
    if receipt.source != operation or payload.get("fingerprint") != fingerprint:
        raise GoalConflict("idempotency_conflict")
    response = payload.get("response")
    if not isinstance(response, dict):
        raise GoalConflict("idempotency_record_invalid")
    return GoalMutationResponse.model_validate(response)


def _store_receipt(
    db: Session,
    *,
    user: User,
    request_id: str,
    operation: str,
    fingerprint: str,
    response: GoalMutationResponse,
) -> None:
    db.add(
        MessageReceipt(
            user_id=user.id,
            request_id=request_id,
            source=operation,
            status="applied",
            response_payload={
                "fingerprint": fingerprint,
                "response": response.model_dump(mode="json"),
            },
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
    )
