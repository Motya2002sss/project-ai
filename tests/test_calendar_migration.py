import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import CheckConstraint, UniqueConstraint, create_engine, event, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models.user import User


CALENDAR_MODELS_AVAILABLE = (
    importlib.util.find_spec("app.models.calendar") is not None
    and importlib.util.find_spec("app.models.plan_change") is not None
)

if CALENDAR_MODELS_AVAILABLE:
    from app.models.calendar import (
        CalendarBusyBlock,
        CalendarSyncState,
        TemporaryLifeMode,
    )
    from app.models.plan_change import PlanChange
else:
    CalendarBusyBlock = None
    TemporaryLifeMode = None
    PlanChange = None


def _models():
    assert CALENDAR_MODELS_AVAILABLE, "calendar models are not implemented"
    return CalendarBusyBlock, TemporaryLifeMode, PlanChange


def _column_names(model) -> set[str]:
    return {column.name for column in model.__table__.columns}


def _unique_sets(model) -> set[tuple[str, ...]]:
    return {
        tuple(column.name for column in constraint.columns)
        for constraint in model.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }


def _index_sets(model) -> set[tuple[str, ...]]:
    return {
        tuple(column.name for column in index.columns)
        for index in model.__table__.indexes
    }


def _foreign_key(model, column: str) -> tuple[str, str | None]:
    foreign_key = next(iter(model.__table__.c[column].foreign_keys))
    return foreign_key.target_fullname, foreign_key.ondelete


@pytest.fixture
def db() -> Session:
    if not CALENDAR_MODELS_AVAILABLE:
        pytest.skip("calendar models are not implemented")
    engine = create_engine("sqlite+pysqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_busy_blocks_are_privacy_minimal_and_deduplicated() -> None:
    busy, _mode, _change = _models()
    columns = _column_names(busy)

    assert {
        "user_id",
        "device_id",
        "provider",
        "calendar_external_id",
        "external_id",
        "occurrence_external_id",
        "occurrence_start",
        "occurrence_end",
        "device_timezone",
        "source_revision",
        "last_seen_client_revision",
        "deleted_at",
    } <= columns
    assert {"title", "notes", "description", "location"}.isdisjoint(columns)
    assert (
        "user_id",
        "device_id",
        "provider",
        "calendar_external_id",
        "occurrence_external_id",
    ) in _unique_sets(busy)
    assert (
        "user_id",
        "occurrence_start",
        "occurrence_end",
        "deleted_at",
    ) in _index_sets(busy)
    assert busy.__table__.c.occurrence_start.type.timezone is True
    assert busy.__table__.c.occurrence_end.type.timezone is True


def test_temporary_modes_and_plan_changes_have_typed_versioned_contracts() -> None:
    _busy, mode, change = _models()

    assert {
        "user_id",
        "request_id",
        "mode",
        "starts_at",
        "ends_at",
        "status",
        "constraints",
    } <= _column_names(mode)
    assert ("user_id", "request_id") in _unique_sets(mode)
    assert ("user_id", "starts_at", "ends_at") in _index_sets(mode)
    assert {
        "user_id",
        "request_id",
        "reason",
        "status",
        "base_versions",
        "result_versions",
        "affected_dates",
        "forward_payload",
        "inverse_payload",
        "expires_at",
        "undone_at",
    } <= _column_names(change)
    assert ("user_id", "request_id") in _unique_sets(change)
    assert ("user_id", "created_at", "id") in _index_sets(change)
    assert any(
        isinstance(constraint, CheckConstraint)
        for constraint in mode.__table__.constraints
    )
    assert any(
        isinstance(constraint, CheckConstraint)
        for constraint in change.__table__.constraints
    )


def test_plan_change_schema_cannot_store_raw_capture_text() -> None:
    _busy, _mode, change = _models()

    assert {
        "capture_text",
        "raw_text",
        "source_text",
        "message",
        "transcript",
    }.isdisjoint(_column_names(change))


def test_calendar_rows_are_directly_user_owned_and_cascade() -> None:
    for model in (*_models(), CalendarSyncState):
        assert _foreign_key(model, "user_id") == ("users.id", "CASCADE")
        assert any(
            columns and columns[0] == "user_id"
            for columns in _index_sets(model)
        )


def test_account_deletion_removes_calendar_and_change_rows(db: Session) -> None:
    busy, mode, change = _models()
    now = datetime(2026, 8, 11, 9, 0, tzinfo=timezone.utc)
    user = User(external_id="calendar-cascade")
    db.add(user)
    db.flush()
    db.add_all(
        [
            busy(
                user_id=user.id,
                device_id="iphone-cascade",
                provider="apple",
                calendar_external_id="calendar-main",
                external_id="event-1",
                occurrence_external_id="occurrence-1",
                occurrence_start=now,
                occurrence_end=now + timedelta(hours=1),
                device_timezone="Europe/Moscow",
                source_revision="1",
                last_seen_client_revision=1,
            ),
            mode(
                user_id=user.id,
                request_id="mode-1",
                mode="travel",
                starts_at=now,
                ends_at=now + timedelta(days=3),
                status="active",
                constraints={"available_minutes": 30},
            ),
            change(
                user_id=user.id,
                request_id="change-1",
                reason="calendar_sync",
                status="applied",
                base_versions={"2026-08-11": 1},
                result_versions={"2026-08-11": 2},
                affected_dates=["2026-08-11"],
                forward_payload={"moved": [{"task_id": 1}]},
                inverse_payload={"moved": [{"task_id": 1}]},
                expires_at=now + timedelta(days=7),
            ),
        ]
    )
    db.commit()

    db.delete(user)
    db.commit()

    for model in _models():
        assert db.scalar(select(model)) is None


def test_calendar_intervals_reject_non_positive_ranges(db: Session) -> None:
    busy, mode, _change = _models()
    now = datetime(2026, 8, 11, 9, 0, tzinfo=timezone.utc)
    user = User(external_id="calendar-invalid-range")
    db.add(user)
    db.flush()
    db.add(
        busy(
            user_id=user.id,
            device_id="iphone-invalid-range",
            provider="apple",
            calendar_external_id="calendar-main",
            external_id="invalid-event",
            occurrence_external_id="invalid-occurrence",
            occurrence_start=now,
            occurrence_end=now,
            device_timezone="UTC",
            source_revision="1",
            last_seen_client_revision=1,
        )
    )
    with pytest.raises(Exception):
        db.commit()
    db.rollback()

    db.add(
        mode(
            user_id=user.id,
            request_id="invalid-mode",
            mode="travel",
            starts_at=now,
            ends_at=now - timedelta(minutes=1),
            status="active",
            constraints={},
        )
    )
    with pytest.raises(Exception):
        db.commit()


def test_calendar_migration_follows_activity_head() -> None:
    migration = (
        Path(__file__).parents[1]
        / "migrations"
        / "versions"
        / "e5d4c3b2a611_calendar_and_plan_changes.py"
    )

    assert migration.exists(), "calendar migration is missing"
    source = migration.read_text(encoding="utf-8")
    assert 'down_revision: Union[str, None] = "d4c3f2b5a644"' in source
    assert "title" not in source
    assert "notes" not in source
