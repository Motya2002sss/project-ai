from datetime import date
from uuid import UUID

from sqlalchemy import select

from app.models.goal import Goal
from app.models.onboarding import ResourceBudget
from app.models.task import Task
from app.models.user import User
from tests.test_api_v2_auth import api, bearer, begin_apple_sign_in


def test_account_export_is_owned_and_excludes_auth_secrets(api) -> None:
    client, factory = api
    owner = begin_apple_sign_in(
        client,
        device_id="owner-phone",
        identity_token="valid-identity-token-owner",
    )
    other = begin_apple_sign_in(
        client,
        device_id="other-phone",
        identity_token="valid-identity-token-other",
    )
    with factory() as db:
        owner_user = db.scalar(
            select(User).where(User.public_id == UUID(owner["user"]["public_id"]))
        )
        other_user = db.scalar(
            select(User).where(User.public_id == UUID(other["user"]["public_id"]))
        )
        assert owner_user is not None and other_user is not None
        db.add(Goal(user_id=owner_user.id, title="Owner goal"))
        db.add(Goal(user_id=other_user.id, title="Other private goal"))
        db.add(
            ResourceBudget(
                user_id=owner_user.id,
                weekly_available_minutes=600,
                available_days=[1, 2, 3],
                minimum_minutes=120,
                comfortable_minutes=240,
                maximum_minutes=480,
                free_evenings=[2],
                preferred_windows={},
                conflict_priority="Owner budget priority",
                reserve_percent=20,
                allocatable_minutes=480,
                allocation={"goals": []},
            )
        )
        db.add(
            ResourceBudget(
                user_id=other_user.id,
                weekly_available_minutes=300,
                available_days=[6],
                minimum_minutes=60,
                comfortable_minutes=120,
                maximum_minutes=240,
                free_evenings=[],
                preferred_windows={},
                conflict_priority="Other private budget",
                reserve_percent=20,
                allocatable_minutes=240,
                allocation={"goals": []},
            )
        )
        db.commit()

    response = client.get(
        "/api/v2/account/export", headers=bearer(owner["access_token"])
    )

    assert response.status_code == 200
    serialized = response.text
    assert "Owner goal" in serialized
    assert "Owner budget priority" in serialized
    assert "Other private goal" not in serialized
    assert "Other private budget" not in serialized
    assert owner["access_token"] not in serialized
    assert owner["refresh_token"] not in serialized
    assert "token_hash" not in serialized


def test_account_deletion_requires_confirmation_and_keeps_other_user(api) -> None:
    client, factory = api
    owner = begin_apple_sign_in(
        client,
        device_id="delete-phone",
        identity_token="valid-identity-token-delete",
    )
    other = begin_apple_sign_in(
        client,
        device_id="survivor-phone",
        identity_token="valid-identity-token-survivor",
    )
    with factory() as db:
        owner_user = db.scalar(
            select(User).where(User.public_id == UUID(owner["user"]["public_id"]))
        )
        assert owner_user is not None
        goal = Goal(user_id=owner_user.id, title="Delete goal")
        db.add(goal)
        db.flush()
        db.add(
            Task(
                user_id=owner_user.id,
                goal_id=goal.id,
                title="Delete task",
                target_date=date(2026, 8, 11),
            )
        )
        db.commit()

    rejected = client.request(
        "DELETE",
        "/api/v2/account",
        headers=bearer(owner["access_token"]),
        json={"confirmation": "delete"},
    )
    assert rejected.status_code == 422

    deleted = client.request(
        "DELETE",
        "/api/v2/account",
        headers=bearer(owner["access_token"]),
        json={"confirmation": "DELETE"},
    )
    assert deleted.status_code == 204
    assert client.get(
        "/api/v2/me", headers=bearer(owner["access_token"])
    ).status_code == 401
    assert client.get(
        "/api/v2/me", headers=bearer(other["access_token"])
    ).status_code == 200

    with factory() as db:
        assert db.scalar(
            select(User).where(User.public_id == UUID(owner["user"]["public_id"]))
        ) is None
        assert db.scalar(
            select(User).where(User.public_id == UUID(other["user"]["public_id"]))
        ) is not None
