from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.auth.apple import AppleIdentity
from app.db.base import Base
from app.db.session import get_db
from app.main import create_app
from app.models.onboarding import OnboardingPreview, ResourceBudget
from app.models.user import User
from app.services.auth_service import DeviceMetadata, sign_in_with_apple


@pytest.fixture
def api(tmp_path: Path) -> Generator[tuple[TestClient, sessionmaker[Session], str], None, None]:
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'onboarding-api.db'}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        signed_in = sign_in_with_apple(
            db,
            identity=AppleIdentity(
                subject="onboarding-api-user",
                email=None,
                email_verified=False,
                is_private_email=False,
            ),
            provided_name="Матвей",
            device=DeviceMetadata(device_id="iphone-1", platform="ios"),
        )
        access_token = signed_in.session.access_token

    def override_db():
        with factory() as db:
            yield db

    application = create_app()
    application.dependency_overrides[get_db] = override_db
    with TestClient(application) as client:
        yield client, factory, access_token


def headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def preview_payload(request_id: str = "api-preview-1") -> dict:
    return {
        "request_id": request_id,
        "narrative": (
            "Работаю по будням с 9 до 18. "
            "Хочу стать senior-разработчиком и регулярно тренироваться."
        ),
        "resource_budget": {
            "weekly_available_minutes": 600,
            "available_days": [1, 2, 3, 4, 5],
            "minimum_minutes": 180,
            "comfortable_minutes": 360,
            "maximum_minutes": 480,
            "free_evenings": [2, 4],
            "conflict_priority": "сон и работа",
        },
    }


def test_onboarding_requires_auth_and_rejects_client_user_id(api) -> None:
    client, _factory, token = api

    assert client.get("/api/v2/onboarding").status_code == 401
    payload = preview_payload()
    payload["user_id"] = 999
    response = client.post(
        "/api/v2/onboarding/preview", json=payload, headers=headers(token)
    )
    assert response.status_code == 422


def test_get_onboarding_is_read_only(api) -> None:
    client, factory, token = api

    first = client.get("/api/v2/onboarding", headers=headers(token))
    second = client.get("/api/v2/onboarding", headers=headers(token))

    assert first.status_code == 200
    assert first.json() == {"status": "not_started", "preview": None}
    assert second.json() == first.json()
    with factory() as db:
        assert db.query(OnboardingPreview).count() == 0
        assert db.query(ResourceBudget).count() == 0


def test_preview_correction_and_apply_flow(api) -> None:
    client, factory, token = api
    preview_response = client.post(
        "/api/v2/onboarding/preview",
        json=preview_payload(),
        headers=headers(token),
    )
    assert preview_response.status_code == 200, preview_response.text
    preview = preview_response.json()
    assert preview["status"] == "ready"
    assert preview["version"] == 1

    corrected_payload = preview_payload("api-preview-correction")
    corrected_payload.update(
        {
            "preview_id": preview["id"],
            "expected_version": preview["version"],
            "narrative": "Работаю с 9 до 18. Хочу подготовиться к IELTS.",
        }
    )
    corrected_response = client.post(
        "/api/v2/onboarding/preview",
        json=corrected_payload,
        headers=headers(token),
    )
    assert corrected_response.status_code == 200
    corrected = corrected_response.json()
    assert corrected["version"] == 2

    stale = client.post(
        "/api/v2/onboarding/apply",
        json={"preview_id": preview["id"], "expected_version": 1},
        headers=headers(token),
    )
    assert stale.status_code == 409
    assert stale.json()["detail"] == "stale_preview_version"

    applied = client.post(
        "/api/v2/onboarding/apply",
        json={"preview_id": preview["id"], "expected_version": 2},
        headers=headers(token),
    )
    assert applied.status_code == 200, applied.text
    assert applied.json()["status"] == "applied"
    assert client.get("/api/v2/onboarding", headers=headers(token)).json()[
        "status"
    ] == "completed"

    with factory() as db:
        user = db.query(User).filter(User.name == "Матвей").one()
        assert len(user.goals) == 1
        assert user.goals[0].title == "Подготовиться к IELTS"
