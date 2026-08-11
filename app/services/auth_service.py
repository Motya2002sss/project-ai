from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.auth.apple import AppleIdentity
from app.auth.tokens import new_opaque_token, token_digest
from app.core.config import settings
from app.models.auth import AppSession, AuthChallenge, AuthIdentity
from app.models.user import User


class AuthError(ValueError):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class DeviceMetadata:
    device_id: str | None = None
    device_name: str | None = None
    platform: str | None = None
    os_version: str | None = None


@dataclass(frozen=True)
class SessionPair:
    access_token: str
    refresh_token: str
    access_expires_at: datetime
    refresh_expires_at: datetime
    family_id: UUID


@dataclass(frozen=True)
class SignInResult:
    user: User
    session: SessionPair


@dataclass(frozen=True)
class AuthChallengePair:
    state: str
    nonce: str
    expires_at: datetime


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def create_auth_challenge(
    db: Session,
    *,
    device_id: str | None,
    now: datetime | None = None,
) -> AuthChallengePair:
    current = now or _utc_now()
    state = new_opaque_token()
    nonce = new_opaque_token()
    expires_at = current + timedelta(minutes=10)
    db.add(
        AuthChallenge(
            state_hash=token_digest(state),
            nonce_hash=token_digest(nonce),
            device_id=device_id,
            expires_at=expires_at,
        )
    )
    db.commit()
    return AuthChallengePair(state=state, nonce=nonce, expires_at=expires_at)


def consume_auth_challenge(
    db: Session,
    *,
    state: str,
    nonce: str,
    now: datetime | None = None,
) -> bool:
    current = now or _utc_now()
    challenge = db.scalar(
        select(AuthChallenge)
        .where(
            AuthChallenge.state_hash == token_digest(state),
            AuthChallenge.nonce_hash == token_digest(nonce),
        )
        .with_for_update()
    )
    if (
        challenge is None
        or challenge.consumed_at is not None
        or _as_aware(challenge.expires_at) <= current
    ):
        return False
    challenge.consumed_at = current
    db.commit()
    return True


def sign_in_with_apple(
    db: Session,
    *,
    identity: AppleIdentity,
    provided_name: str | None,
    device: DeviceMetadata,
    now: datetime | None = None,
) -> SignInResult:
    current = now or _utc_now()
    auth_identity = db.scalar(
        select(AuthIdentity)
        .where(
            AuthIdentity.provider == "apple",
            AuthIdentity.subject == identity.subject,
        )
        .with_for_update()
    )
    safe_name = provided_name.strip()[:255] if provided_name else None
    verified_email = (
        identity.email.strip()[:320]
        if identity.email and identity.email_verified
        else None
    )

    if auth_identity is None:
        user = User(name=safe_name or None, email=verified_email)
        db.add(user)
        db.flush()
        auth_identity = AuthIdentity(
            user_id=user.id,
            provider="apple",
            subject=identity.subject,
            last_authenticated_at=current,
        )
        db.add(auth_identity)
    else:
        user = db.get(User, auth_identity.user_id)
        if user is None:
            raise AuthError("identity_user_missing")
        auth_identity.last_authenticated_at = current
        if user.name is None and safe_name:
            user.name = safe_name
        if user.email is None and verified_email:
            user.email = verified_email

    session_pair = _issue_session(
        db,
        user=user,
        device=device,
        family_id=uuid4(),
        now=current,
    )
    db.commit()
    return SignInResult(user=user, session=session_pair)


def _issue_session(
    db: Session,
    *,
    user: User,
    device: DeviceMetadata,
    family_id: UUID,
    now: datetime,
    parent_session_id: UUID | None = None,
) -> SessionPair:
    access_token = new_opaque_token()
    refresh_token = new_opaque_token()
    access_expires_at = now + timedelta(minutes=settings.access_token_ttl_minutes)
    refresh_expires_at = now + timedelta(days=settings.refresh_token_ttl_days)
    db.add(
        AppSession(
            user_id=user.id,
            family_id=family_id,
            parent_session_id=parent_session_id,
            access_token_hash=token_digest(access_token),
            refresh_token_hash=token_digest(refresh_token),
            access_expires_at=access_expires_at,
            refresh_expires_at=refresh_expires_at,
            device_id=device.device_id,
            device_name=device.device_name,
            platform=device.platform,
            os_version=device.os_version,
            last_seen_at=now,
        )
    )
    db.flush()
    return SessionPair(
        access_token=access_token,
        refresh_token=refresh_token,
        access_expires_at=access_expires_at,
        refresh_expires_at=refresh_expires_at,
        family_id=family_id,
    )


def authenticate_access_token(
    db: Session,
    access_token: str,
    *,
    now: datetime | None = None,
) -> User:
    current = now or _utc_now()
    session = db.scalar(
        select(AppSession).where(
            AppSession.access_token_hash == token_digest(access_token)
        )
    )
    if (
        session is None
        or session.revoked_at is not None
        or _as_aware(session.access_expires_at) <= current
    ):
        raise AuthError("invalid_access_token")
    user = db.get(User, session.user_id)
    if user is None:
        raise AuthError("invalid_access_token")
    session.last_seen_at = current
    db.commit()
    return user


def rotate_session(
    db: Session,
    *,
    refresh_token: str,
    now: datetime | None = None,
) -> SessionPair:
    current = now or _utc_now()
    previous = db.scalar(
        select(AppSession)
        .where(AppSession.refresh_token_hash == token_digest(refresh_token))
        .with_for_update()
    )
    if previous is None:
        raise AuthError("invalid_refresh_token")
    if previous.rotated_at is not None:
        previous.reuse_detected_at = current
        db.execute(
            update(AppSession)
            .where(AppSession.family_id == previous.family_id)
            .values(revoked_at=current)
        )
        db.commit()
        raise AuthError("refresh_reuse_detected")
    if (
        previous.revoked_at is not None
        or _as_aware(previous.refresh_expires_at) <= current
    ):
        if previous.revoked_at is None:
            previous.revoked_at = current
            db.commit()
        raise AuthError("invalid_refresh_token")

    user = db.get(User, previous.user_id)
    if user is None:
        raise AuthError("invalid_refresh_token")
    previous.rotated_at = current
    session_pair = _issue_session(
        db,
        user=user,
        device=DeviceMetadata(
            device_id=previous.device_id,
            device_name=previous.device_name,
            platform=previous.platform,
            os_version=previous.os_version,
        ),
        family_id=previous.family_id,
        parent_session_id=previous.id,
        now=current,
    )
    db.commit()
    return session_pair


def revoke_session(
    db: Session,
    *,
    access_token: str,
    now: datetime | None = None,
) -> bool:
    current = now or _utc_now()
    session = db.scalar(
        select(AppSession).where(
            AppSession.access_token_hash == token_digest(access_token)
        )
    )
    if session is None:
        return False
    db.execute(
        update(AppSession)
        .where(AppSession.family_id == session.family_id)
        .where(AppSession.revoked_at.is_(None))
        .values(revoked_at=current)
    )
    db.commit()
    return True


def revoke_all_sessions(
    db: Session,
    *,
    user: User,
    now: datetime | None = None,
) -> int:
    current = now or _utc_now()
    result = db.execute(
        update(AppSession)
        .where(AppSession.user_id == user.id)
        .where(AppSession.revoked_at.is_(None))
        .values(revoked_at=current)
    )
    db.commit()
    return result.rowcount or 0
