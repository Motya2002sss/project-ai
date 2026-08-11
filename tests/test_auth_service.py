from datetime import datetime, timedelta, timezone

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from app.auth.apple import AppleIdentity, AppleTokenVerifier, AppleVerificationError
from app.auth.tokens import token_digest
from app.db.base import Base
from app.models.auth import AppSession
from app.services.auth_service import (
    AuthError,
    DeviceMetadata,
    authenticate_access_token,
    create_auth_challenge,
    consume_auth_challenge,
    revoke_session,
    rotate_session,
    sign_in_with_apple,
)


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


@pytest.fixture
def apple_signer():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = jwt.algorithms.RSAAlgorithm.to_jwk(
        private_key.public_key(), as_dict=True
    )
    public_jwk.update({"kid": "apple-test-key", "alg": "RS256", "use": "sig"})

    def sign(**overrides) -> str:
        now = datetime.now(timezone.utc)
        claims = {
            "iss": "https://appleid.apple.com",
            "aud": "com.example.lifeplanner",
            "sub": "000123.apple-user",
            "iat": now,
            "exp": now + timedelta(minutes=5),
            "nonce": "expected-nonce",
            "email": "owner@privaterelay.appleid.com",
            "email_verified": "true",
            "is_private_email": "true",
        }
        claims.update(overrides)
        return jwt.encode(
            claims,
            private_key,
            algorithm="RS256",
            headers={"kid": "apple-test-key"},
        )

    return sign, {"keys": [public_jwk]}


def test_apple_verifier_accepts_signed_claims_and_exact_nonce(apple_signer) -> None:
    sign, jwks = apple_signer
    verifier = AppleTokenVerifier(
        client_id="com.example.lifeplanner",
        jwks_provider=lambda: jwks,
    )

    identity = verifier.verify(sign(), expected_nonce="expected-nonce")

    assert identity == AppleIdentity(
        subject="000123.apple-user",
        email="owner@privaterelay.appleid.com",
        email_verified=True,
        is_private_email=True,
    )


@pytest.mark.parametrize(
    ("claim_overrides", "expected_nonce"),
    [
        ({"aud": "another-client"}, "expected-nonce"),
        ({"iss": "https://attacker.example"}, "expected-nonce"),
        ({"exp": datetime.now(timezone.utc) - timedelta(seconds=1)}, "expected-nonce"),
        ({}, "different-nonce"),
    ],
)
def test_apple_verifier_rejects_untrusted_claims(
    apple_signer,
    claim_overrides: dict,
    expected_nonce: str,
) -> None:
    sign, jwks = apple_signer
    verifier = AppleTokenVerifier(
        client_id="com.example.lifeplanner",
        jwks_provider=lambda: jwks,
    )

    with pytest.raises(AppleVerificationError) as error:
        verifier.verify(sign(**claim_overrides), expected_nonce=expected_nonce)

    assert error.value.reason == "invalid_identity_token"


def test_auth_challenge_is_single_use_and_expires(db: Session) -> None:
    now = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)
    challenge = create_auth_challenge(db, device_id="iphone-1", now=now)

    assert consume_auth_challenge(
        db,
        state=challenge.state,
        nonce=challenge.nonce,
        now=now + timedelta(seconds=1),
    )
    assert not consume_auth_challenge(
        db,
        state=challenge.state,
        nonce=challenge.nonce,
        now=now + timedelta(seconds=2),
    )

    expired = create_auth_challenge(db, device_id="iphone-1", now=now)
    assert not consume_auth_challenge(
        db,
        state=expired.state,
        nonce=expired.nonce,
        now=now + timedelta(minutes=11),
    )


def test_repeated_apple_sign_in_preserves_first_name_and_email(db: Session) -> None:
    first = sign_in_with_apple(
        db,
        identity=AppleIdentity(
            subject="stable-apple-subject",
            email="first@example.com",
            email_verified=True,
            is_private_email=False,
        ),
        provided_name="Матвей",
        device=DeviceMetadata(device_id="iphone-1", platform="ios"),
    )
    second = sign_in_with_apple(
        db,
        identity=AppleIdentity(
            subject="stable-apple-subject",
            email=None,
            email_verified=False,
            is_private_email=False,
        ),
        provided_name=None,
        device=DeviceMetadata(device_id="iphone-2", platform="ios"),
    )

    assert first.user.id == second.user.id
    assert second.user.name == "Матвей"
    assert second.user.email == "first@example.com"
    assert first.session.refresh_token != second.session.refresh_token


def test_refresh_rotation_detects_reuse_and_revokes_family(db: Session) -> None:
    signed_in = sign_in_with_apple(
        db,
        identity=AppleIdentity("rotation-user", None, False, False),
        provided_name=None,
        device=DeviceMetadata(device_id="iphone-1", platform="ios"),
    )
    original_refresh = signed_in.session.refresh_token

    rotated = rotate_session(db, refresh_token=original_refresh)
    assert rotated.refresh_token != original_refresh
    assert authenticate_access_token(db, rotated.access_token).id == signed_in.user.id

    with pytest.raises(AuthError) as error:
        rotate_session(db, refresh_token=original_refresh)

    assert error.value.reason == "refresh_reuse_detected"
    family_rows = db.scalars(
        select(AppSession).where(AppSession.family_id == signed_in.session.family_id)
    ).all()
    assert len(family_rows) == 2
    assert all(row.revoked_at is not None for row in family_rows)


def test_logout_revokes_current_device_without_revoking_other_device(db: Session) -> None:
    identity = AppleIdentity("multi-device-user", None, False, False)
    first = sign_in_with_apple(
        db,
        identity=identity,
        provided_name=None,
        device=DeviceMetadata(device_id="iphone-1", platform="ios"),
    )
    second = sign_in_with_apple(
        db,
        identity=identity,
        provided_name=None,
        device=DeviceMetadata(device_id="ipad-1", platform="ios"),
    )

    revoke_session(db, access_token=first.session.access_token)

    with pytest.raises(AuthError):
        authenticate_access_token(db, first.session.access_token)
    assert authenticate_access_token(db, second.session.access_token).id == second.user.id


def test_database_contains_hashes_not_raw_session_credentials(db: Session) -> None:
    signed_in = sign_in_with_apple(
        db,
        identity=AppleIdentity("hash-user", None, False, False),
        provided_name=None,
        device=DeviceMetadata(device_id="iphone-1", platform="ios"),
    )

    stored = db.scalar(
        select(AppSession).where(
            AppSession.access_token_hash
            == token_digest(signed_in.session.access_token)
        )
    )
    assert stored is not None
    assert stored.access_token_hash != signed_in.session.access_token
    assert stored.refresh_token_hash != signed_in.session.refresh_token
