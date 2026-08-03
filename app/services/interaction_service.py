from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.interaction import PendingInteraction
from app.models.user import User


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def expire_pending_interactions(db: Session, user: User) -> None:
    now = _utc_now()
    pending = (
        db.query(PendingInteraction)
        .filter(
            PendingInteraction.user_id == user.id,
            PendingInteraction.status == "pending",
        )
        .all()
    )

    for interaction in pending:
        if _as_aware(interaction.expires_at) <= now:
            interaction.status = "expired"
            interaction.resolved_at = now

    db.flush()


def get_pending_interaction(
    db: Session,
    user: User,
    interaction_id: str | None = None,
) -> PendingInteraction | None:
    expire_pending_interactions(db, user)
    query = db.query(PendingInteraction).filter(
        PendingInteraction.user_id == user.id,
        PendingInteraction.status == "pending",
    )

    if interaction_id:
        query = query.filter(PendingInteraction.id == interaction_id)

    return query.order_by(PendingInteraction.created_at.desc()).first()


def create_pending_interaction(
    db: Session,
    user: User,
    *,
    source: str,
    kind: str,
    original_message: str,
    context: dict,
    question: str,
    options: list[dict] | None = None,
    base_plan_version: int | None = None,
    commit: bool = True,
) -> PendingInteraction:
    now = _utc_now()
    active = (
        db.query(PendingInteraction)
        .filter(
            PendingInteraction.user_id == user.id,
            PendingInteraction.status == "pending",
        )
        .all()
    )

    for interaction in active:
        interaction.status = "superseded"
        interaction.resolved_at = now

    interaction = PendingInteraction(
        id=str(uuid4()),
        user_id=user.id,
        source=source,
        kind=kind,
        status="pending",
        original_message=original_message[:4000],
        context=context,
        question=question,
        options=options or [],
        base_plan_version=base_plan_version,
        expires_at=now + timedelta(minutes=settings.interaction_ttl_minutes),
    )
    db.add(interaction)
    db.flush()

    if commit:
        db.commit()
        db.refresh(interaction)

    return interaction


def resolve_interaction(
    db: Session,
    interaction: PendingInteraction,
    *,
    status: str = "resolved",
    commit: bool = True,
) -> None:
    interaction.status = status
    interaction.resolved_at = _utc_now()
    db.flush()

    if commit:
        db.commit()

