import importlib
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models.auth import AppSession, AuthIdentity
from app.models.user import User


@pytest.fixture
def db() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_users_receive_distinct_stable_public_uuids(db: Session) -> None:
    first = User(external_id="auth-user-1")
    second = User(external_id="auth-user-2")
    db.add_all([first, second])
    db.commit()

    assert isinstance(first.public_id, UUID)
    assert first.public_id != second.public_id
    persisted = db.scalar(select(User).where(User.id == first.id))
    assert persisted is not None
    assert persisted.public_id == first.public_id


def test_apple_subject_is_unique_across_all_users(db: Session) -> None:
    first = User(external_id="identity-owner-1")
    second = User(external_id="identity-owner-2")
    db.add_all([first, second])
    db.flush()
    db.add(AuthIdentity(user_id=first.id, provider="apple", subject="apple-subject"))
    db.commit()

    db.add(AuthIdentity(user_id=second.id, provider="apple", subject="apple-subject"))
    with pytest.raises(IntegrityError):
        db.commit()


def test_session_schema_stores_only_token_hashes_and_rotation_identity() -> None:
    columns = set(AppSession.__table__.c.keys())

    assert {
        "user_id",
        "family_id",
        "parent_session_id",
        "access_token_hash",
        "refresh_token_hash",
        "access_expires_at",
        "refresh_expires_at",
        "rotated_at",
        "revoked_at",
        "reuse_detected_at",
    }.issubset(columns)
    assert "access_token" not in columns
    assert "refresh_token" not in columns


def test_deleting_user_cascades_identity_and_sessions(db: Session) -> None:
    user = User(external_id="cascade-user")
    db.add(user)
    db.flush()
    identity = AuthIdentity(user_id=user.id, provider="apple", subject="cascade-subject")
    session = AppSession(
        user_id=user.id,
        family_id=uuid4(),
        access_token_hash="a" * 64,
        refresh_token_hash="b" * 64,
        access_expires_at=datetime(2026, 8, 11, 12, 15, tzinfo=timezone.utc),
        refresh_expires_at=datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc),
    )
    db.add_all([identity, session])
    db.commit()

    db.delete(user)
    db.commit()

    assert db.scalar(select(AuthIdentity)) is None
    assert db.scalar(select(AppSession)) is None


def test_auth_migration_follows_current_schema_head() -> None:
    migration = importlib.import_module(
        "migrations.versions.a1f0c9e2d311_production_auth"
    )

    assert migration.revision == "a1f0c9e2d311"
    assert migration.down_revision == "e7a31c4d8f20"
