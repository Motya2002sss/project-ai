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


class IdempotencyConflict(ValueError):
    pass


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
    fingerprint: str,
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
        stored_fingerprint = (existing.response_payload or {}).get(
            "_request_fingerprint"
        )
        if existing.source != source or stored_fingerprint != fingerprint:
            raise IdempotencyConflict("idempotency_conflict")
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
        response_payload={"_request_fingerprint": fingerprint},
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

        stored_fingerprint = (existing.response_payload or {}).get(
            "_request_fingerprint"
        )
        if existing.source != source or stored_fingerprint != fingerprint:
            raise IdempotencyConflict("idempotency_conflict")

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
    fingerprint = (receipt.response_payload or {}).get("_request_fingerprint")
    receipt.status = "completed"
    receipt.response_payload = response.model_dump(mode="json")
    if fingerprint:
        receipt.response_payload["_request_fingerprint"] = fingerprint
    db.commit()


def fail_message_request(db: Session, receipt: MessageReceipt) -> None:
    receipt.status = "failed"
    fingerprint = (receipt.response_payload or {}).get("_request_fingerprint")
    receipt.response_payload = (
        {"_request_fingerprint": fingerprint} if fingerprint else None
    )
    db.commit()
