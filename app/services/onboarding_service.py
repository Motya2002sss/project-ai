import re
from datetime import datetime, time, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.goal import Goal
from app.models.onboarding import (
    OnboardingPreview,
    OnboardingRequestReceipt,
    ResourceBudget,
)
from app.models.user import User
from app.schemas.onboarding import ResourceBudgetInput


class OnboardingConflict(ValueError):
    pass


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _time_value(raw: str | None) -> str | None:
    if raw is None:
        return None
    hour_text, _, minute_text = raw.partition(":")
    hour = int(hour_text)
    minute = int(minute_text or "0")
    if hour > 23 or minute > 59:
        return None
    return f"{hour:02d}:{minute:02d}"


def _extract_routine(narrative: str, budget: ResourceBudgetInput) -> dict:
    work_match = re.search(
        r"работ\w*[^.!?]{0,80}?с\s*(\d{1,2}(?::\d{1,2})?)\s*до\s*(\d{1,2}(?::\d{1,2})?)",
        narrative,
        flags=re.IGNORECASE,
    )
    sleep_match = re.search(
        r"лож\w*(?:\s+спать)?[^.!?]{0,30}?(?:в\s*)?(\d{1,2}(?::\d{1,2})?)",
        narrative,
        flags=re.IGNORECASE,
    )
    return {
        "work_start": _time_value(work_match.group(1)) if work_match else None,
        "work_end": _time_value(work_match.group(2)) if work_match else None,
        "sleep_time": _time_value(sleep_match.group(1)) if sleep_match else None,
        "available_days": budget.available_days,
        "free_evenings": budget.free_evenings,
        "preferred_windows": budget.preferred_windows,
    }


def _sentence_case(value: str) -> str:
    value = value.strip(" \t\n—–-,:;")
    if not value:
        return value
    return value[0].upper() + value[1:]


def _extract_goal_candidates(narrative: str) -> list[str]:
    candidates: list[str] = []
    for match in re.finditer(
        r"(?:\bхочу\b|\bмои\s+цели\s*[:—-])\s*(.+?)(?:[.!?]|$)",
        narrative,
        flags=re.IGNORECASE,
    ):
        goal_text = match.group(1)
        parts = re.split(r"\s*,\s*|\s+и\s+", goal_text, flags=re.IGNORECASE)
        for part in parts:
            normalized = re.sub(r"^(?:я\s+)?хочу\s+", "", part, flags=re.IGNORECASE)
            normalized = _sentence_case(normalized)[:255]
            if normalized and normalized.casefold() not in {
                item.casefold() for item in candidates
            }:
                candidates.append(normalized)
            if len(candidates) == 3:
                return candidates
    return candidates


def _budget_payload(budget: ResourceBudgetInput) -> dict:
    payload = budget.model_dump(mode="json")
    payload["allocatable_minutes"] = (
        budget.weekly_available_minutes * (100 - budget.reserve_percent) // 100
    )
    return payload


def _allocation(goals: list[str], budget: ResourceBudgetInput) -> dict:
    allocatable = budget.weekly_available_minutes * (100 - budget.reserve_percent) // 100
    target = min(budget.comfortable_minutes, allocatable)
    allocations: list[dict] = []
    if goals:
        base, remainder = divmod(target, len(goals))
        for index, title in enumerate(goals):
            minutes = base + (1 if index < remainder else 0)
            percent = round(minutes / target * 100) if target else 0
            allocations.append(
                {"title": title, "minutes": minutes, "percent": percent}
            )
    return {
        "reserved_minutes": budget.weekly_available_minutes - allocatable,
        "reserve_percent": budget.reserve_percent,
        "allocatable_minutes": allocatable,
        "planned_minutes": sum(item["minutes"] for item in allocations),
        "goals": allocations,
    }


def preview_onboarding(
    db: Session,
    *,
    user: User,
    narrative: str,
    resource_budget: ResourceBudgetInput,
    request_id: str,
    preview_id: UUID | None = None,
    expected_version: int | None = None,
    now: datetime | None = None,
) -> OnboardingPreview:
    existing_receipt = db.scalar(
        select(OnboardingRequestReceipt).where(
            OnboardingRequestReceipt.user_id == user.id,
            OnboardingRequestReceipt.request_id == request_id,
        )
    )
    if existing_receipt is not None:
        existing = db.get(OnboardingPreview, existing_receipt.preview_id)
        if existing is None or existing.user_id != user.id:
            raise OnboardingConflict("request_receipt_invalid")
        return existing

    current = now or _utc_now()
    goals = _extract_goal_candidates(narrative)
    summary = _extract_routine(narrative, resource_budget)
    budget_payload = _budget_payload(resource_budget)
    allocation = _allocation(goals, resource_budget)
    clarification = None
    status = "ready"
    if not goals:
        status = "clarification_required"
        clarification = {
            "id": "primary_goals",
            "question": "Какие результаты вы хотите получить в первую очередь?",
            "allows_free_text": True,
        }

    if preview_id is None:
        preview = OnboardingPreview(
            user_id=user.id,
            status=status,
            narrative=narrative,
            narrative_expires_at=current + timedelta(hours=24),
            structured_summary=summary,
            goal_candidates=goals,
            resource_budget=budget_payload,
            allocation=allocation,
            clarification=clarification,
        )
        db.add(preview)
        db.flush()
    else:
        preview = db.scalar(
            select(OnboardingPreview)
            .where(
                OnboardingPreview.id == preview_id,
                OnboardingPreview.user_id == user.id,
            )
            .with_for_update()
        )
        if preview is None:
            raise OnboardingConflict("preview_not_found")
        if preview.status == "applied":
            raise OnboardingConflict("preview_already_applied")
        if expected_version is None or preview.version != expected_version:
            raise OnboardingConflict("stale_preview_version")
        preview.status = status
        preview.version += 1
        preview.narrative = narrative
        preview.narrative_expires_at = current + timedelta(hours=24)
        preview.structured_summary = summary
        preview.goal_candidates = goals
        preview.resource_budget = budget_payload
        preview.allocation = allocation
        preview.clarification = clarification

    db.add(
        OnboardingRequestReceipt(
            user_id=user.id,
            preview_id=preview.id,
            request_id=request_id,
        )
    )
    db.commit()
    db.refresh(preview)
    return preview


def _parse_time(value: str | None) -> time | None:
    return time.fromisoformat(value) if value else None


def apply_onboarding_preview(
    db: Session,
    *,
    user: User,
    preview_id: UUID,
    expected_version: int,
    now: datetime | None = None,
) -> OnboardingPreview:
    preview = db.scalar(
        select(OnboardingPreview)
        .where(
            OnboardingPreview.id == preview_id,
            OnboardingPreview.user_id == user.id,
        )
        .with_for_update()
    )
    if preview is None:
        raise OnboardingConflict("preview_not_found")
    if preview.status == "applied":
        return preview
    if preview.version != expected_version:
        raise OnboardingConflict("stale_preview_version")
    if preview.status != "ready":
        raise OnboardingConflict("clarification_required")

    budget_values = preview.resource_budget
    saved_budget = db.scalar(
        select(ResourceBudget)
        .where(ResourceBudget.user_id == user.id)
        .with_for_update()
    )
    if saved_budget is None:
        saved_budget = ResourceBudget(user_id=user.id)
        db.add(saved_budget)
    else:
        saved_budget.version += 1
    for field in (
        "weekly_available_minutes",
        "available_days",
        "minimum_minutes",
        "comfortable_minutes",
        "maximum_minutes",
        "free_evenings",
        "preferred_windows",
        "money_budget",
        "conflict_priority",
        "reserve_percent",
        "allocatable_minutes",
    ):
        setattr(saved_budget, field, budget_values.get(field))
    saved_budget.allocation = preview.allocation

    selected_titles = preview.goal_candidates[:3]
    selected_keys = {title.casefold() for title in selected_titles}
    existing_goals = db.scalars(
        select(Goal).where(Goal.user_id == user.id).order_by(Goal.id.asc())
    ).all()
    goals_by_title = {goal.title.casefold(): goal for goal in existing_goals}
    for goal in existing_goals:
        if goal.status == "active" and goal.title.casefold() not in selected_keys:
            goal.status = "paused"

    for title in selected_titles:
        existing = goals_by_title.get(title.casefold())
        if existing is not None:
            existing.status = "active"
        else:
            db.add(
                Goal(
                    user_id=user.id,
                    title=title,
                    category="personal",
                    priority="medium",
                    status="active",
                )
            )

    user.work_start_time = _parse_time(preview.structured_summary.get("work_start"))
    user.work_end_time = _parse_time(preview.structured_summary.get("work_end"))
    user.sleep_time = _parse_time(preview.structured_summary.get("sleep_time"))
    preview.status = "applied"
    preview.applied_at = now or _utc_now()
    preview.narrative = None
    preview.narrative_expires_at = None
    db.commit()
    db.refresh(preview)
    return preview


def get_latest_onboarding_preview(
    db: Session, *, user: User
) -> OnboardingPreview | None:
    return db.scalar(
        select(OnboardingPreview)
        .where(OnboardingPreview.user_id == user.id)
        .order_by(OnboardingPreview.created_at.desc(), OnboardingPreview.id.desc())
        .limit(1)
    )
