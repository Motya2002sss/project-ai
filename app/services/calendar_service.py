import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session

from app.models.calendar import CalendarBusyBlock, CalendarSyncState
from app.models.message_receipt import MessageReceipt
from app.models.user import User
from app.schemas.calendar import (
    CalendarSyncBatch,
    CalendarSyncResult,
    CalendarSyncStateResponse,
)
from app.services.time_service import get_user_timezone


class CalendarSyncConflict(ValueError):
    pass


def get_calendar_sync_state(
    db: Session,
    *,
    user: User,
    device_id: str,
    provider: str,
) -> CalendarSyncStateResponse:
    state = db.scalar(
        select(CalendarSyncState).where(
            CalendarSyncState.user_id == user.id,
            CalendarSyncState.device_id == device_id,
            CalendarSyncState.provider == provider,
        )
    )
    if state is None:
        return CalendarSyncStateResponse(
            status="not_started",
            device_id=device_id,
            provider=provider,
            version=0,
            client_revision=0,
        )
    return CalendarSyncStateResponse(
        status="ready",
        device_id=state.device_id,
        provider=state.provider,
        version=state.version,
        client_revision=state.client_revision,
        range_start=_as_utc(state.range_start),
        range_end=_as_utc(state.range_end),
        device_timezone=state.device_timezone,
        covered_calendar_ids=state.covered_calendar_ids,
        last_synced_at=_as_utc(state.last_synced_at),
    )


def sync_busy_blocks(
    db: Session,
    *,
    user: User,
    sync_batch: CalendarSyncBatch,
    expected_version: int,
) -> CalendarSyncResult:
    fingerprint = _fingerprint(sync_batch, expected_version=expected_version)
    replay = _replay_receipt(
        db,
        user=user,
        request_id=sync_batch.request_id,
        fingerprint=fingerprint,
    )
    if replay is not None:
        return replay
    _lock_user(db, user=user)
    replay = _replay_receipt(
        db,
        user=user,
        request_id=sync_batch.request_id,
        fingerprint=fingerprint,
    )
    if replay is not None:
        return replay
    state = db.scalar(
        select(CalendarSyncState)
        .where(
            CalendarSyncState.user_id == user.id,
            CalendarSyncState.device_id == sync_batch.device_id,
            CalendarSyncState.provider == sync_batch.provider,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    current_version = state.version if state is not None else 0
    current_client_revision = state.client_revision if state is not None else 0
    if expected_version != current_version:
        raise CalendarSyncConflict("stale_sync_version")
    if sync_batch.client_revision <= current_client_revision:
        raise CalendarSyncConflict("stale_client_revision")

    covered_calendar_ids = (
        set(state.covered_calendar_ids) if state is not None else set()
    )
    covered_calendar_ids.update(sync_batch.calendar_external_ids)
    covered_calendar_ids.difference_update(
        sync_batch.removed_calendar_external_ids
    )
    if len(covered_calendar_ids) > 50:
        raise CalendarSyncConflict("calendar_scope_limit_exceeded")

    synced_at = datetime.now(timezone.utc)
    range_start = _as_utc(sync_batch.range_start)
    range_end = _as_utc(sync_batch.range_end)
    incoming_pairs = [
        (block.calendar_external_id, block.occurrence_external_id)
        for block in sync_batch.busy_blocks
    ]
    scope_rows = db.scalars(
        select(CalendarBusyBlock)
        .where(
            CalendarBusyBlock.user_id == user.id,
            CalendarBusyBlock.device_id == sync_batch.device_id,
            CalendarBusyBlock.provider == sync_batch.provider,
            CalendarBusyBlock.calendar_external_id.in_(
                sync_batch.calendar_external_ids
            ),
            CalendarBusyBlock.deleted_at.is_(None),
            CalendarBusyBlock.occurrence_end > range_start,
            CalendarBusyBlock.occurrence_start < range_end,
        )
        .with_for_update()
    ).all()
    removed_rows: list[CalendarBusyBlock] = []
    if sync_batch.removed_calendar_external_ids:
        removed_rows = db.scalars(
            select(CalendarBusyBlock)
            .where(
                CalendarBusyBlock.user_id == user.id,
                CalendarBusyBlock.device_id == sync_batch.device_id,
                CalendarBusyBlock.provider == sync_batch.provider,
                CalendarBusyBlock.calendar_external_id.in_(
                    sync_batch.removed_calendar_external_ids
                ),
                CalendarBusyBlock.deleted_at.is_(None),
            )
            .with_for_update()
        ).all()
    stable_rows: list[CalendarBusyBlock] = []
    if incoming_pairs:
        stable_rows = db.scalars(
            select(CalendarBusyBlock)
            .where(
                CalendarBusyBlock.user_id == user.id,
                CalendarBusyBlock.device_id == sync_batch.device_id,
                CalendarBusyBlock.provider == sync_batch.provider,
                tuple_(
                    CalendarBusyBlock.calendar_external_id,
                    CalendarBusyBlock.occurrence_external_id,
                ).in_(incoming_pairs),
            )
            .with_for_update()
        ).all()
    rows_by_id = {row.id: row for row in [*scope_rows, *stable_rows]}
    rows_by_identity = {
        (row.calendar_external_id, row.occurrence_external_id): row
        for row in rows_by_id.values()
    }
    incoming_identities = set(incoming_pairs)
    affected_dates: set[date] = set()
    affected_timezone = get_user_timezone(user).key
    created_count = 0
    updated_count = 0
    unchanged_count = 0

    for incoming in sync_batch.busy_blocks:
        identity = (
            incoming.calendar_external_id,
            incoming.occurrence_external_id,
        )
        occurrence_start = _as_utc(incoming.occurrence_start)
        occurrence_end = _as_utc(incoming.occurrence_end)
        existing = rows_by_identity.get(identity)
        if existing is None:
            block = CalendarBusyBlock(
                user_id=user.id,
                device_id=sync_batch.device_id,
                provider=sync_batch.provider,
                calendar_external_id=incoming.calendar_external_id,
                external_id=incoming.external_id,
                occurrence_external_id=incoming.occurrence_external_id,
                occurrence_start=occurrence_start,
                occurrence_end=occurrence_end,
                device_timezone=sync_batch.device_timezone,
                source_revision=incoming.source_revision,
                last_seen_client_revision=sync_batch.client_revision,
            )
            db.add(block)
            rows_by_identity[identity] = block
            created_count += 1
            affected_dates.update(
                _local_dates(
                    occurrence_start,
                    occurrence_end,
                    affected_timezone,
                )
            )
            continue

        old_start = _as_utc(existing.occurrence_start)
        old_end = _as_utc(existing.occurrence_end)
        schedule_changed = (
            old_start != occurrence_start
            or old_end != occurrence_end
            or existing.deleted_at is not None
        )
        metadata_changed = (
            existing.external_id != incoming.external_id
            or existing.source_revision != incoming.source_revision
            or existing.device_timezone != sync_batch.device_timezone
        )
        if schedule_changed:
            affected_dates.update(
                _local_dates(
                    old_start,
                    old_end,
                    affected_timezone,
                )
            )
            affected_dates.update(
                _local_dates(
                    occurrence_start,
                    occurrence_end,
                    affected_timezone,
                )
            )
        if schedule_changed or metadata_changed:
            updated_count += 1
        else:
            unchanged_count += 1
        existing.external_id = incoming.external_id
        existing.occurrence_start = occurrence_start
        existing.occurrence_end = occurrence_end
        existing.device_timezone = sync_batch.device_timezone
        existing.source_revision = incoming.source_revision
        existing.last_seen_client_revision = sync_batch.client_revision
        existing.deleted_at = None

    tombstoned_count = 0
    for existing in scope_rows:
        identity = (
            existing.calendar_external_id,
            existing.occurrence_external_id,
        )
        if identity in incoming_identities or existing.deleted_at is not None:
            continue
        affected_dates.update(
            _local_dates(
                _as_utc(existing.occurrence_start),
                _as_utc(existing.occurrence_end),
                affected_timezone,
            )
        )
        existing.deleted_at = synced_at
        tombstoned_count += 1
    for existing in removed_rows:
        affected_dates.update(
            _local_dates(
                _as_utc(existing.occurrence_start),
                _as_utc(existing.occurrence_end),
                affected_timezone,
            )
        )
        existing.deleted_at = synced_at
        tombstoned_count += 1

    next_version = current_version + 1
    if state is None:
        state = CalendarSyncState(
            user_id=user.id,
            device_id=sync_batch.device_id,
            provider=sync_batch.provider,
            version=next_version,
            client_revision=sync_batch.client_revision,
            range_start=range_start,
            range_end=range_end,
            device_timezone=sync_batch.device_timezone,
            covered_calendar_ids=sorted(covered_calendar_ids),
            last_synced_at=synced_at,
        )
        db.add(state)
    else:
        state.version = next_version
        state.client_revision = sync_batch.client_revision
        state.range_start = range_start
        state.range_end = range_end
        state.device_timezone = sync_batch.device_timezone
        state.covered_calendar_ids = sorted(covered_calendar_ids)
        state.last_synced_at = synced_at
    result = CalendarSyncResult(
        version=next_version,
        client_revision=sync_batch.client_revision,
        created_count=created_count,
        updated_count=updated_count,
        tombstoned_count=tombstoned_count,
        unchanged_count=unchanged_count,
        affected_dates=sorted(affected_dates),
        replan_required=bool(affected_dates),
        synced_at=synced_at,
    )
    _store_receipt(
        db,
        user=user,
        request_id=sync_batch.request_id,
        fingerprint=fingerprint,
        result=result,
    )
    db.commit()
    return result


def _local_dates(start: datetime, end: datetime, timezone_name: str) -> set[date]:
    zone = ZoneInfo(timezone_name)
    local_start = start.astimezone(zone)
    local_last_instant = (end - timedelta(microseconds=1)).astimezone(zone)
    current = local_start.date()
    last = local_last_instant.date()
    result: set[date] = set()
    while current <= last:
        result.add(current)
        current += timedelta(days=1)
    return result


def _fingerprint(sync_batch: CalendarSyncBatch, *, expected_version: int) -> str:
    sync_payload = sync_batch.model_dump(mode="json")
    if not sync_batch.removed_calendar_external_ids:
        sync_payload.pop("removed_calendar_external_ids", None)
    payload = json.dumps(
        {
            "expected_version": expected_version,
            "sync_batch": sync_payload,
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
    fingerprint: str,
) -> CalendarSyncResult | None:
    receipt = db.scalar(
        select(MessageReceipt).where(
            MessageReceipt.user_id == user.id,
            MessageReceipt.request_id == request_id,
        )
    )
    if receipt is None:
        return None
    payload = receipt.response_payload or {}
    if receipt.source != "calendar_sync" or payload.get("fingerprint") != fingerprint:
        raise CalendarSyncConflict("idempotency_conflict")
    try:
        return CalendarSyncResult.model_validate(payload["result"])
    except (KeyError, TypeError, ValueError) as error:
        raise CalendarSyncConflict("idempotency_record_invalid") from error


def _store_receipt(
    db: Session,
    *,
    user: User,
    request_id: str,
    fingerprint: str,
    result: CalendarSyncResult,
) -> None:
    db.add(
        MessageReceipt(
            user_id=user.id,
            request_id=request_id,
            source="calendar_sync",
            status="applied",
            response_payload={
                "fingerprint": fingerprint,
                "result": result.model_dump(mode="json"),
            },
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
    )


def _lock_user(db: Session, *, user: User) -> None:
    owned = db.scalar(select(User.id).where(User.id == user.id).with_for_update())
    if owned is None:
        raise CalendarSyncConflict("account_not_found")


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
