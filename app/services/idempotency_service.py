from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.message_receipt import MessageReceipt
from app.models.user import User
from app.schemas.api import MessageResponse


@dataclass
class ReceiptReservation:
    receipt: MessageReceipt | None = None
    cached_response: MessageResponse | None = None
    processing: bool = False


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def reserve_message_request(
    db: Session,
    user: User,
    *,
    request_id: str,
    source: str,
) -> ReceiptReservation:
    existing = (
        db.query(MessageReceipt)
        .filter(
            MessageReceipt.user_id == user.id,
            MessageReceipt.request_id == request_id,
        )
        .one_or_none()
    )
    now = _utc_now()

    if existing and _as_aware(existing.expires_at) <= now:
        db.delete(existing)
        db.commit()
        existing = None

    if existing:
        if existing.status == "completed" and existing.response_payload:
            return ReceiptReservation(
                receipt=existing,
                cached_response=MessageResponse.model_validate(existing.response_payload),
            )

        return ReceiptReservation(receipt=existing, processing=existing.status == "processing")

    receipt = MessageReceipt(
        user_id=user.id,
        request_id=request_id,
        source=source,
        status="processing",
        expires_at=now + timedelta(hours=settings.idempotency_ttl_hours),
    )
    db.add(receipt)

    try:
        db.commit()
        db.refresh(receipt)
        return ReceiptReservation(receipt=receipt)
    except IntegrityError:
        db.rollback()
        existing = (
            db.query(MessageReceipt)
            .filter(
                MessageReceipt.user_id == user.id,
                MessageReceipt.request_id == request_id,
            )
            .one()
        )

        if existing.status == "completed" and existing.response_payload:
            return ReceiptReservation(
                receipt=existing,
                cached_response=MessageResponse.model_validate(existing.response_payload),
            )

        return ReceiptReservation(receipt=existing, processing=True)


def complete_message_request(
    db: Session,
    receipt: MessageReceipt,
    response: MessageResponse,
) -> None:
    receipt.status = "completed"
    receipt.response_payload = response.model_dump(mode="json")
    db.commit()


def fail_message_request(db: Session, receipt: MessageReceipt) -> None:
    receipt.status = "failed"
    receipt.response_payload = None
    db.commit()
