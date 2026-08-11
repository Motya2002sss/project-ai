from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.api.v2.auth import get_apple_verifier
from app.auth.apple import AppleIdentity, AppleVerificationError
from app.db.base import Base
from app.db.session import get_db
from app.main import create_app


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
def api(tmp_path: Path) -> Generator[tuple[TestClient, sessionmaker[Session]], None, None]:
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'api-v2-auth.db'}",
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
        with factory() as db:
            yield db

    application = create_app()
    application.dependency_overrides[get_db] = override_db
    application.dependency_overrides[get_apple_verifier] = FakeAppleVerifier
    with TestClient(application) as client:
        yield client, factory


def begin_apple_sign_in(
    client: TestClient,
    *,
    device_id: str = "iphone-1",
    identity_token: str = "valid-identity-token",
) -> dict:
    challenge_response = client.post(
        "/api/v2/auth/challenge", json={"device_id": device_id}
    )
    assert challenge_response.status_code == 200
    challenge = challenge_response.json()
    response = client.post(
        "/api/v2/auth/apple",
        json={
            "identity_token": identity_token,
            "state": challenge["state"],
            "nonce": challenge["nonce"],
            "name": "Матвей",
            "device": {"device_id": device_id, "platform": "ios"},
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def bearer(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def test_v2_me_requires_a_valid_session(api) -> None:
    client, _factory = api

    response = client.get("/api/v2/me")

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid authentication credentials"


def test_apple_sign_in_returns_session_and_internal_public_identity(api) -> None:
    client, _factory = api

    signed_in = begin_apple_sign_in(client)
    me = client.get("/api/v2/me", headers=bearer(signed_in["access_token"]))

    assert signed_in["token_type"] == "bearer"
    assert signed_in["refresh_token"] != signed_in["access_token"]
    assert me.status_code == 200
    assert me.json() == {
        "public_id": signed_in["user"]["public_id"],
        "name": "Матвей",
        "email": "verified@example.com",
        "timezone": "UTC",
    }


def test_sign_in_rejects_unknown_or_reused_challenge(api) -> None:
    client, _factory = api
    challenge = client.post(
        "/api/v2/auth/challenge", json={"device_id": "iphone-1"}
    ).json()
    payload = {
        "identity_token": "valid-identity-token",
        "state": challenge["state"],
        "nonce": challenge["nonce"],
        "device": {"device_id": "iphone-1", "platform": "ios"},
    }

    assert client.post("/api/v2/auth/apple", json=payload).status_code == 200
    assert client.post("/api/v2/auth/apple", json=payload).status_code == 401


def test_auth_requests_forbid_client_provided_user_identity(api) -> None:
    client, _factory = api
    challenge = client.post(
        "/api/v2/auth/challenge", json={"device_id": "iphone-1"}
    ).json()

    response = client.post(
        "/api/v2/auth/apple",
        json={
            "identity_token": "valid-identity-token",
            "state": challenge["state"],
            "nonce": challenge["nonce"],
            "device": {"device_id": "iphone-1", "platform": "ios"},
            "user_id": 999,
        },
    )

    assert response.status_code == 422


def test_refresh_rotates_and_reuse_revokes_the_new_session(api) -> None:
    client, _factory = api
    signed_in = begin_apple_sign_in(client)

    refresh = client.post(
        "/api/v2/auth/refresh",
        json={"refresh_token": signed_in["refresh_token"]},
    )
    assert refresh.status_code == 200
    rotated = refresh.json()
    assert rotated["refresh_token"] != signed_in["refresh_token"]

    reused = client.post(
        "/api/v2/auth/refresh",
        json={"refresh_token": signed_in["refresh_token"]},
    )
    assert reused.status_code == 401
    assert reused.json()["detail"] == "Invalid authentication credentials"
    assert client.get(
        "/api/v2/me", headers=bearer(rotated["access_token"])
    ).status_code == 401


def test_logout_revokes_current_device_without_revoking_another_device(api) -> None:
    client, _factory = api
    first = begin_apple_sign_in(client, device_id="iphone-1")
    second = begin_apple_sign_in(client, device_id="ipad-1")

    logout = client.post("/api/v2/auth/logout", headers=bearer(first["access_token"]))

    assert logout.status_code == 204
    assert client.get(
        "/api/v2/me", headers=bearer(first["access_token"])
    ).status_code == 401
    assert client.get(
        "/api/v2/me", headers=bearer(second["access_token"])
    ).status_code == 200


def test_revoke_all_invalidates_every_device(api) -> None:
    client, _factory = api
    first = begin_apple_sign_in(client, device_id="iphone-1")
    second = begin_apple_sign_in(client, device_id="ipad-1")

    response = client.post(
        "/api/v2/auth/revoke-all", headers=bearer(first["access_token"])
    )

    assert response.status_code == 204
    assert client.get(
        "/api/v2/me", headers=bearer(first["access_token"])
    ).status_code == 401
    assert client.get(
        "/api/v2/me", headers=bearer(second["access_token"])
    ).status_code == 401
