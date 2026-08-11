import importlib.util
from collections.abc import Generator
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.api.v2.auth import get_apple_verifier, router as auth_router
from app.auth.apple import AppleIdentity, AppleVerificationError
from app.db.base import Base
from app.db.session import get_db
from app.models.calendar import CalendarBusyBlock
from app.models.day_plan import DayPlan
from app.models.message_receipt import MessageReceipt
from app.models.plan_change import PlanChange
from app.models.user import User


CALENDAR_SYNC_AVAILABLE = all(
    importlib.util.find_spec(module) is not None
    for module in (
        "app.schemas.calendar",
        "app.services.calendar_service",
        "app.api.v2.calendar",
    )
) and hasattr(importlib.import_module("app.models.calendar"), "CalendarSyncState")

if CALENDAR_SYNC_AVAILABLE:
    from app.api.v2.calendar import router as calendar_router
    from app.models.calendar import CalendarSyncState
    from app.schemas.calendar import CalendarSyncBatch
    from app.services.calendar_service import (
        CalendarSyncConflict,
        get_calendar_sync_state,
        sync_busy_blocks,
    )
else:
    CalendarSyncState = None
    CalendarSyncBatch = None
    CalendarSyncConflict = ValueError
    calendar_router = None
    get_calendar_sync_state = None
    sync_busy_blocks = None


UTC = timezone.utc
RANGE_START = datetime(2026, 8, 11, 0, 0, tzinfo=UTC)
RANGE_END = datetime(2026, 8, 13, 0, 0, tzinfo=UTC)


class FakeAppleVerifier:
    def verify(self, identity_token: str, *, expected_nonce: str) -> AppleIdentity:
        if not identity_token.startswith("valid-identity-token") or not expected_nonce:
            raise AppleVerificationError()
        return AppleIdentity(
            subject=f"apple:{identity_token}",
            email="verified@example.com",
            email_verified=True,
            is_private_email=False,
        )


@pytest.fixture
def db(tmp_path: Path) -> Generator[Session, None, None]:
    if not CALENDAR_SYNC_AVAILABLE:
        pytest.skip("calendar sync is not implemented")
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'calendar-sync.db'}")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session


@pytest.fixture(autouse=True)
def fixed_calendar_validation_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    if CALENDAR_SYNC_AVAILABLE:
        monkeypatch.setattr(
            "app.schemas.calendar._utc_now",
            lambda: datetime(2026, 8, 11, 12, 0, tzinfo=UTC),
        )


@pytest.fixture
def api(
    tmp_path: Path,
) -> Generator[tuple[TestClient, sessionmaker[Session]], None, None]:
    if not CALENDAR_SYNC_AVAILABLE:
        pytest.skip("calendar sync is not implemented")
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'calendar-sync-api.db'}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def override_db():
        with factory() as session:
            yield session

    application = FastAPI()
    v2 = APIRouter(prefix="/api/v2")
    v2.include_router(auth_router)
    v2.include_router(calendar_router)
    application.include_router(v2)
    application.dependency_overrides[get_db] = override_db
    application.dependency_overrides[get_apple_verifier] = FakeAppleVerifier
    with TestClient(application) as client:
        yield client, factory


def _user(db: Session, suffix: str) -> User:
    user = User(external_id=f"calendar-sync-{suffix}")
    db.add(user)
    db.commit()
    return user


def _block(
    *,
    calendar_id: str = "calendar-main",
    event_id: str = "event-1",
    occurrence_id: str = "occurrence-1",
    start: datetime = datetime(2026, 8, 11, 9, 0, tzinfo=UTC),
    end: datetime = datetime(2026, 8, 11, 10, 0, tzinfo=UTC),
    source_revision: str = "1",
) -> dict:
    return {
        "calendar_external_id": calendar_id,
        "external_id": event_id,
        "occurrence_external_id": occurrence_id,
        "occurrence_start": start,
        "occurrence_end": end,
        "source_revision": source_revision,
    }


def _batch(
    *,
    request_id: str = "calendar-batch-1",
    client_revision: int = 1,
    blocks: list[dict] | None = None,
    calendar_ids: list[str] | None = None,
    removed_calendar_ids: list[str] | None = None,
    range_start: datetime = RANGE_START,
    range_end: datetime = RANGE_END,
    device_id: str = "iphone-primary",
    provider: str = "apple",
    device_timezone: str = "Europe/Moscow",
):
    assert CalendarSyncBatch is not None
    payload = {
        "request_id": request_id,
        "device_id": device_id,
        "provider": provider,
        "client_revision": client_revision,
        "range_start": range_start,
        "range_end": range_end,
        "device_timezone": device_timezone,
        "calendar_external_ids": (
            calendar_ids if calendar_ids is not None else ["calendar-main"]
        ),
        "busy_blocks": blocks if blocks is not None else [_block()],
    }
    if removed_calendar_ids is not None:
        payload["removed_calendar_external_ids"] = removed_calendar_ids
    return CalendarSyncBatch.model_validate(payload)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def test_calendar_sync_contract_exists() -> None:
    assert CALENDAR_SYNC_AVAILABLE, "calendar sync modules/state are not implemented"


def test_create_app_mounts_authenticated_calendar_routes() -> None:
    from app.main import create_app

    with TestClient(create_app()) as client:
        state = client.get(
            "/api/v2/calendar/sync-state",
            params={"device_id": "iphone-primary", "provider": "apple"},
        )
        mutation = client.put("/api/v2/calendar/busy-blocks", json={})

    assert state.status_code == 401
    assert mutation.status_code == 401


def test_first_import_is_user_owned_versioned_and_does_not_replan(db: Session) -> None:
    user = _user(db, "first")
    day_plan = DayPlan(
        user_id=user.id,
        date=date(2026, 8, 11),
        status="ready",
        version=7,
    )
    db.add(day_plan)
    db.commit()

    result = sync_busy_blocks(db, user=user, sync_batch=_batch(), expected_version=0)

    assert result.version == 1
    assert result.client_revision == 1
    assert result.created_count == 1
    assert result.updated_count == 0
    assert result.tombstoned_count == 0
    assert result.unchanged_count == 0
    assert result.affected_dates == [date(2026, 8, 11)]
    assert result.replan_required is True
    state = get_calendar_sync_state(
        db, user=user, device_id="iphone-primary", provider="apple"
    )
    assert state.status == "ready"
    assert state.version == 1
    assert state.client_revision == 1
    saved = db.scalar(select(CalendarBusyBlock))
    assert saved is not None
    assert saved.user_id == user.id
    assert saved.device_id == "iphone-primary"
    assert saved.occurrence_external_id == "occurrence-1"
    db.refresh(day_plan)
    assert day_plan.version == 7
    assert db.scalar(select(func.count(PlanChange.id))) == 0


def test_exact_request_replay_returns_same_result_without_new_rows(db: Session) -> None:
    user = _user(db, "replay")
    batch = _batch()

    first = sync_busy_blocks(db, user=user, sync_batch=batch, expected_version=0)
    replayed = sync_busy_blocks(db, user=user, sync_batch=batch, expected_version=0)

    assert replayed == first
    assert db.scalar(select(func.count(CalendarBusyBlock.id))) == 1
    assert db.scalar(select(func.count(CalendarSyncState.id))) == 1
    assert db.scalar(select(func.count(MessageReceipt.id))) == 1

    conflicting = _batch(blocks=[_block(source_revision="different")])
    with pytest.raises(CalendarSyncConflict, match="idempotency_conflict"):
        sync_busy_blocks(
            db,
            user=user,
            sync_batch=conflicting,
            expected_version=0,
        )


def test_server_version_and_client_revision_are_monotonic(db: Session) -> None:
    user = _user(db, "revision")
    sync_busy_blocks(db, user=user, sync_batch=_batch(), expected_version=0)

    with pytest.raises(CalendarSyncConflict, match="stale_client_revision"):
        sync_busy_blocks(
            db,
            user=user,
            sync_batch=_batch(request_id="revision-repeat", client_revision=1),
            expected_version=1,
        )
    with pytest.raises(CalendarSyncConflict, match="stale_sync_version"):
        sync_busy_blocks(
            db,
            user=user,
            sync_batch=_batch(request_id="revision-stale", client_revision=2),
            expected_version=0,
        )

    applied = sync_busy_blocks(
        db,
        user=user,
        sync_batch=_batch(request_id="revision-2", client_revision=2),
        expected_version=1,
    )
    assert applied.version == 2
    assert applied.unchanged_count == 1
    assert applied.affected_dates == []
    assert applied.replan_required is False
    assert db.scalar(select(func.count(CalendarBusyBlock.id))) == 1


def test_changed_time_updates_stable_occurrence_and_returns_old_and_new_dates(
    db: Session,
) -> None:
    user = _user(db, "changed-time")
    initial = _block(
        start=datetime(2026, 8, 11, 20, 0, tzinfo=UTC),
        end=datetime(2026, 8, 11, 20, 30, tzinfo=UTC),
    )
    sync_busy_blocks(
        db,
        user=user,
        sync_batch=_batch(blocks=[initial]),
        expected_version=0,
    )
    original = db.scalar(select(CalendarBusyBlock))
    assert original is not None
    original_id = original.id
    moved = _block(
        start=datetime(2026, 8, 11, 22, 0, tzinfo=UTC),
        end=datetime(2026, 8, 11, 23, 0, tzinfo=UTC),
        source_revision="2",
    )

    result = sync_busy_blocks(
        db,
        user=user,
        sync_batch=_batch(
            request_id="moved-batch",
            client_revision=2,
            blocks=[moved],
        ),
        expected_version=1,
    )

    assert result.created_count == 0
    assert result.updated_count == 1
    assert result.affected_dates == [date(2026, 8, 11)]
    assert db.scalar(select(func.count(CalendarBusyBlock.id))) == 1
    saved = db.scalar(select(CalendarBusyBlock))
    assert saved is not None and saved.id == original_id
    assert _aware(saved.occurrence_start) == datetime(2026, 8, 11, 22, 0, tzinfo=UTC)
    assert saved.source_revision == "2"


def test_timezone_change_returns_old_and_new_local_dates(db: Session) -> None:
    user = _user(db, "timezone-change")
    late_block = _block(
        start=datetime(2026, 8, 11, 23, 30, tzinfo=UTC),
        end=datetime(2026, 8, 11, 23, 45, tzinfo=UTC),
    )
    sync_busy_blocks(
        db,
        user=user,
        sync_batch=_batch(
            blocks=[late_block],
            device_timezone="UTC",
        ),
        expected_version=0,
    )

    result = sync_busy_blocks(
        db,
        user=user,
        sync_batch=_batch(
            request_id="timezone-change-2",
            client_revision=2,
            blocks=[late_block],
            device_timezone="Europe/Moscow",
        ),
        expected_version=1,
    )

    assert result.created_count == 0
    assert result.updated_count == 1
    assert result.affected_dates == []
    assert result.replan_required is False


def test_affected_dates_use_user_timezone_not_device_timezone(db: Session) -> None:
    user = _user(db, "user-timezone")
    user.timezone = "Pacific/Kiritimati"
    db.commit()
    late_block = _block(
        start=datetime(2026, 8, 11, 23, 30, tzinfo=UTC),
        end=datetime(2026, 8, 11, 23, 45, tzinfo=UTC),
    )

    result = sync_busy_blocks(
        db,
        user=user,
        sync_batch=_batch(blocks=[late_block], device_timezone="UTC"),
        expected_version=0,
    )

    assert result.affected_dates == [date(2026, 8, 12)]


def test_missing_remote_occurrence_is_tombstoned_only_in_covered_calendar(
    db: Session,
) -> None:
    user = _user(db, "tombstone")
    first = _block(event_id="event-1", occurrence_id="occurrence-1")
    second = _block(
        calendar_id="calendar-main",
        event_id="event-2",
        occurrence_id="occurrence-2",
        start=datetime(2026, 8, 11, 11, 0, tzinfo=UTC),
        end=datetime(2026, 8, 11, 12, 0, tzinfo=UTC),
    )
    other_calendar = _block(
        calendar_id="calendar-secondary",
        event_id="event-2",
        occurrence_id="occurrence-2",
        start=datetime(2026, 8, 11, 13, 0, tzinfo=UTC),
        end=datetime(2026, 8, 11, 14, 0, tzinfo=UTC),
    )
    sync_busy_blocks(
        db,
        user=user,
        sync_batch=_batch(
            blocks=[first, second, other_calendar],
            calendar_ids=["calendar-main", "calendar-secondary"],
        ),
        expected_version=0,
    )

    result = sync_busy_blocks(
        db,
        user=user,
        sync_batch=_batch(
            request_id="tombstone-batch",
            client_revision=2,
            blocks=[first],
            calendar_ids=["calendar-main"],
        ),
        expected_version=1,
    )

    assert result.tombstoned_count == 1
    rows = db.scalars(
        select(CalendarBusyBlock).order_by(CalendarBusyBlock.calendar_external_id)
    ).all()
    main_second = next(
        row
        for row in rows
        if row.calendar_external_id == "calendar-main" and row.external_id == "event-2"
    )
    secondary = next(
        row for row in rows if row.calendar_external_id == "calendar-secondary"
    )
    assert main_second.deleted_at is not None
    assert secondary.deleted_at is None


def test_partial_sync_retains_omitted_calendar_coverage(db: Session) -> None:
    user = _user(db, "partial-coverage")
    main = _block(calendar_id="calendar-main")
    secondary = _block(
        calendar_id="calendar-secondary",
        event_id="event-secondary",
        occurrence_id="occurrence-secondary",
        start=datetime(2026, 8, 11, 11, 0, tzinfo=UTC),
        end=datetime(2026, 8, 11, 12, 0, tzinfo=UTC),
    )
    sync_busy_blocks(
        db,
        user=user,
        sync_batch=_batch(
            blocks=[main, secondary],
            calendar_ids=["calendar-main", "calendar-secondary"],
        ),
        expected_version=0,
    )

    sync_busy_blocks(
        db,
        user=user,
        sync_batch=_batch(
            request_id="partial-coverage-2",
            client_revision=2,
            blocks=[main],
            calendar_ids=["calendar-main"],
        ),
        expected_version=1,
    )

    state = get_calendar_sync_state(
        db,
        user=user,
        device_id="iphone-primary",
        provider="apple",
    )
    assert state.covered_calendar_ids == ["calendar-main", "calendar-secondary"]
    secondary_row = db.scalar(
        select(CalendarBusyBlock).where(
            CalendarBusyBlock.calendar_external_id == "calendar-secondary"
        )
    )
    assert secondary_row is not None
    assert secondary_row.deleted_at is None


def test_explicit_full_calendar_removal_is_global_versioned_and_idempotent(
    db: Session,
) -> None:
    user = _user(db, "full-removal")
    main = _block(calendar_id="calendar-main")
    secondary = _block(
        calendar_id="calendar-secondary",
        event_id="event-secondary",
        occurrence_id="occurrence-secondary",
        start=datetime(2026, 8, 12, 9, 0, tzinfo=UTC),
        end=datetime(2026, 8, 12, 10, 0, tzinfo=UTC),
    )
    sync_busy_blocks(
        db,
        user=user,
        sync_batch=_batch(
            blocks=[main, secondary],
            calendar_ids=["calendar-main", "calendar-secondary"],
        ),
        expected_version=0,
    )
    removal = _batch(
        request_id="full-removal-2",
        client_revision=2,
        blocks=[],
        calendar_ids=[],
        removed_calendar_ids=["calendar-main", "calendar-secondary"],
        range_start=RANGE_START,
        range_end=datetime(2026, 8, 11, 12, 0, tzinfo=UTC),
    )

    result = sync_busy_blocks(
        db,
        user=user,
        sync_batch=removal,
        expected_version=1,
    )
    replayed = sync_busy_blocks(
        db,
        user=user,
        sync_batch=removal,
        expected_version=1,
    )

    assert replayed == result
    assert result.version == 2
    assert result.client_revision == 2
    assert result.tombstoned_count == 2
    assert result.affected_dates == [date(2026, 8, 11), date(2026, 8, 12)]
    assert result.replan_required is True
    state = get_calendar_sync_state(
        db,
        user=user,
        device_id="iphone-primary",
        provider="apple",
    )
    assert state.covered_calendar_ids == []
    assert all(
        row.deleted_at is not None
        for row in db.scalars(select(CalendarBusyBlock)).all()
    )
    assert db.scalar(select(func.count(MessageReceipt.id))) == 2

    conflicting = _batch(
        request_id="full-removal-2",
        client_revision=2,
        blocks=[],
        calendar_ids=[],
        removed_calendar_ids=["calendar-main"],
        range_start=RANGE_START,
        range_end=datetime(2026, 8, 11, 12, 0, tzinfo=UTC),
    )
    with pytest.raises(CalendarSyncConflict, match="idempotency_conflict"):
        sync_busy_blocks(
            db,
            user=user,
            sync_batch=conflicting,
            expected_version=1,
        )


def test_calendar_removal_is_scoped_to_owner_device_and_provider(db: Session) -> None:
    owner = _user(db, "removal-owner")
    other = _user(db, "removal-other")
    sync_busy_blocks(db, user=owner, sync_batch=_batch(), expected_version=0)
    sync_busy_blocks(
        db,
        user=owner,
        sync_batch=_batch(
            request_id="owner-second-device",
            device_id="iphone-secondary",
        ),
        expected_version=0,
    )
    sync_busy_blocks(
        db,
        user=owner,
        sync_batch=_batch(
            request_id="owner-google-provider",
            provider="google",
        ),
        expected_version=0,
    )
    sync_busy_blocks(
        db,
        user=other,
        sync_batch=_batch(request_id="other-owner-device"),
        expected_version=0,
    )

    sync_busy_blocks(
        db,
        user=owner,
        sync_batch=_batch(
            request_id="owner-removal",
            client_revision=2,
            blocks=[],
            calendar_ids=[],
            removed_calendar_ids=["calendar-main"],
        ),
        expected_version=1,
    )

    rows = db.scalars(select(CalendarBusyBlock)).all()
    removed = next(
        row
        for row in rows
        if row.user_id == owner.id
        and row.device_id == "iphone-primary"
        and row.provider == "apple"
    )
    owner_second_device = next(
        row
        for row in rows
        if row.user_id == owner.id and row.device_id == "iphone-secondary"
    )
    other_owner = next(row for row in rows if row.user_id == other.id)
    other_provider = next(
        row
        for row in rows
        if row.user_id == owner.id
        and row.device_id == "iphone-primary"
        and row.provider == "google"
    )
    assert removed.deleted_at is not None
    assert owner_second_device.deleted_at is None
    assert other_owner.deleted_at is None
    assert other_provider.calendar_external_id == "calendar-main"
    assert other_provider.deleted_at is None


def test_historical_tombstones_are_excluded_from_active_scope_query(
    db: Session,
) -> None:
    user = _user(db, "bounded-tombstones")
    sync_busy_blocks(
        db,
        user=user,
        sync_batch=_batch(),
        expected_version=0,
    )
    sync_busy_blocks(
        db,
        user=user,
        sync_batch=_batch(
            request_id="bounded-tombstones-2",
            client_revision=2,
            blocks=[],
        ),
        expected_version=1,
    )
    statements: list[str] = []
    bind = db.get_bind()

    def capture_statement(
        _connection,
        _cursor,
        statement,
        _parameters,
        _context,
        _executemany,
    ) -> None:
        statements.append(" ".join(statement.lower().split()))

    event.listen(bind, "before_cursor_execute", capture_statement)
    try:
        result = sync_busy_blocks(
            db,
            user=user,
            sync_batch=_batch(
                request_id="bounded-tombstones-3",
                client_revision=3,
                blocks=[],
            ),
            expected_version=2,
        )
    finally:
        event.remove(bind, "before_cursor_execute", capture_statement)

    assert result.tombstoned_count == 0
    scope_queries = [
        statement
        for statement in statements
        if "from calendar_busy_blocks" in statement
        and "occurrence_end >" in statement
    ]
    assert scope_queries
    assert all("calendar_busy_blocks.deleted_at is null" in item for item in scope_queries)


def test_overlaps_and_same_event_ids_in_two_calendars_are_distinct(db: Session) -> None:
    user = _user(db, "overlap")
    blocks = [
        _block(calendar_id="calendar-a", event_id="shared", occurrence_id="same"),
        _block(
            calendar_id="calendar-b",
            event_id="shared",
            occurrence_id="same",
            start=datetime(2026, 8, 11, 9, 30, tzinfo=UTC),
            end=datetime(2026, 8, 11, 10, 30, tzinfo=UTC),
        ),
    ]

    result = sync_busy_blocks(
        db,
        user=user,
        sync_batch=_batch(
            blocks=blocks,
            calendar_ids=["calendar-a", "calendar-b"],
        ),
        expected_version=0,
    )

    assert result.created_count == 2
    assert db.scalar(select(func.count(CalendarBusyBlock.id))) == 2


def test_same_event_time_with_distinct_occurrence_ids_is_not_a_copy(
    db: Session,
) -> None:
    user = _user(db, "same-event-time")
    blocks = [
        _block(event_id="recurring-event", occurrence_id="occurrence-a"),
        _block(event_id="recurring-event", occurrence_id="occurrence-b"),
    ]

    result = sync_busy_blocks(
        db,
        user=user,
        sync_batch=_batch(blocks=blocks),
        expected_version=0,
    )

    assert result.created_count == 2
    assert db.scalar(select(func.count(CalendarBusyBlock.id))) == 2


def test_same_remote_identity_is_isolated_between_users(db: Session) -> None:
    first = _user(db, "owner-one")
    second = _user(db, "owner-two")

    sync_busy_blocks(db, user=first, sync_batch=_batch(), expected_version=0)
    sync_busy_blocks(db, user=second, sync_batch=_batch(), expected_version=0)

    assert db.scalar(select(func.count(CalendarBusyBlock.id))) == 2
    assert db.scalar(select(func.count(CalendarSyncState.id))) == 2
    assert set(db.scalars(select(CalendarBusyBlock.user_id))) == {first.id, second.id}


def test_same_remote_identity_on_two_devices_has_separate_sync_scope(
    db: Session,
) -> None:
    user = _user(db, "two-devices")

    sync_busy_blocks(
        db,
        user=user,
        sync_batch=_batch(device_id="iphone-one"),
        expected_version=0,
    )
    sync_busy_blocks(
        db,
        user=user,
        sync_batch=_batch(
            request_id="calendar-batch-device-two",
            device_id="iphone-two",
        ),
        expected_version=0,
    )

    assert db.scalar(select(func.count(CalendarBusyBlock.id))) == 2
    assert db.scalar(select(func.count(CalendarSyncState.id))) == 2


def test_schema_rejects_sensitive_content_invalid_ranges_and_unbounded_batches() -> None:
    assert CalendarSyncBatch is not None
    with pytest.raises(ValidationError):
        CalendarSyncBatch.model_validate(
            {
                **_batch().model_dump(),
                "busy_blocks": [{**_block(), "title": "Private meeting"}],
            }
        )
    with pytest.raises(ValidationError):
        _batch(device_timezone="Not/A-Timezone")
    with pytest.raises(ValidationError):
        _batch(
            range_start=RANGE_START,
            range_end=RANGE_START + timedelta(days=63),
        )
    with pytest.raises(ValidationError):
        _batch(
            blocks=[
                _block(
                    start=datetime(2026, 8, 11, 10, 0),
                    end=datetime(2026, 8, 11, 11, 0),
                )
            ]
        )
    with pytest.raises(ValidationError):
        _batch(
            blocks=[
                _block(
                    start=datetime(2026, 8, 11, 10, 0, tzinfo=UTC),
                    end=datetime(2026, 8, 11, 9, 0, tzinfo=UTC),
                )
            ]
        )
    with pytest.raises(ValidationError):
        _batch(blocks=[_block()] * 1001)
    with pytest.raises(ValidationError):
        _batch(client_revision=2_147_483_648)
    with pytest.raises(ValidationError):
        _batch(
            blocks=[],
            calendar_ids=["calendar-main"],
            removed_calendar_ids=["calendar-main"],
        )
    with pytest.raises(ValidationError):
        _batch(blocks=[], calendar_ids=[], removed_calendar_ids=[])
    far_start = datetime(9999, 12, 31, 0, 0, tzinfo=UTC)
    far_end = datetime(9999, 12, 31, 23, 59, tzinfo=UTC)
    with pytest.raises(ValidationError):
        _batch(
            range_start=far_start,
            range_end=far_end,
            device_timezone="Pacific/Kiritimati",
            blocks=[
                _block(
                    start=datetime(9999, 12, 31, 23, 0, tzinfo=UTC),
                    end=datetime(9999, 12, 31, 23, 30, tzinfo=UTC),
                )
            ],
        )
    negative_twelve = timezone(-timedelta(hours=12))
    with pytest.raises(ValidationError):
        _batch(
            range_start=datetime(9999, 12, 30, 0, 0, tzinfo=negative_twelve),
            range_end=datetime(9999, 12, 31, 23, 59, tzinfo=negative_twelve),
            blocks=[],
        )


def test_offset_instants_are_normalized_to_utc_after_timezone_validation(
    db: Session,
) -> None:
    user = _user(db, "utc-normalization")
    plus_three = timezone(timedelta(hours=3))
    block = _block(
        start=datetime(2026, 8, 11, 12, 0, tzinfo=plus_three),
        end=datetime(2026, 8, 11, 13, 0, tzinfo=plus_three),
    )

    sync_busy_blocks(
        db,
        user=user,
        sync_batch=_batch(blocks=[block]),
        expected_version=0,
    )

    saved = db.scalar(select(CalendarBusyBlock))
    assert saved is not None
    assert _aware(saved.occurrence_start) == datetime(2026, 8, 11, 9, 0, tzinfo=UTC)
    assert _aware(saved.occurrence_end) == datetime(2026, 8, 11, 10, 0, tzinfo=UTC)


def _sign_in(client: TestClient, identity: str, device_id: str) -> dict:
    challenge = client.post(
        "/api/v2/auth/challenge", json={"device_id": device_id}
    ).json()
    response = client.post(
        "/api/v2/auth/apple",
        json={
            "identity_token": identity,
            "state": challenge["state"],
            "nonce": challenge["nonce"],
            "device": {"device_id": device_id, "platform": "ios"},
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_api_is_session_owned_privacy_strict_and_get_is_read_safe(api) -> None:
    client, factory = api
    signed_in = _sign_in(
        client,
        "valid-identity-token-calendar-api",
        "calendar-api-iphone",
    )
    headers = _bearer(signed_in["access_token"])

    empty_state = client.get(
        "/api/v2/calendar/sync-state",
        params={"device_id": "calendar-api-iphone", "provider": "apple"},
        headers=headers,
    )
    unauthorized = client.put(
        "/api/v2/calendar/busy-blocks",
        json={"expected_version": 0, **_batch().model_dump(mode="json")},
    )
    private_payload = {
        "expected_version": 0,
        **_batch(device_id="calendar-api-iphone").model_dump(mode="json"),
    }
    private_payload["busy_blocks"][0]["location"] = "Home"
    rejected_private = client.put(
        "/api/v2/calendar/busy-blocks",
        json=private_payload,
        headers=headers,
    )
    owner_payload = {
        "expected_version": 0,
        **_batch(device_id="calendar-api-iphone").model_dump(mode="json"),
        "user_id": 999,
    }
    rejected_owner = client.put(
        "/api/v2/calendar/busy-blocks",
        json=owner_payload,
        headers=headers,
    )

    assert empty_state.status_code == 200, empty_state.text
    assert empty_state.json()["status"] == "not_started"
    assert empty_state.json()["version"] == 0
    assert unauthorized.status_code == 401
    assert rejected_private.status_code == 422
    assert rejected_owner.status_code == 422
    with factory() as db:
        assert db.scalar(select(func.count(CalendarSyncState.id))) == 0

    applied_payload = {
        "expected_version": 0,
        **_batch(device_id="calendar-api-iphone").model_dump(mode="json"),
    }
    applied = client.put(
        "/api/v2/calendar/busy-blocks",
        json=applied_payload,
        headers=headers,
    )
    assert applied.status_code == 200, applied.text
    assert applied.json()["affected_dates"] == ["2026-08-11"]
    assert applied.json()["replan_required"] is True
