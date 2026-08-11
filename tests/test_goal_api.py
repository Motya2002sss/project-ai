from datetime import date
from uuid import UUID

import pytest
from sqlalchemy import select

from app.models.goal import Goal
from app.models.user import User
from app.schemas.goals import GoalUpdateRequest
from app.services.goal_service import GoalConflict, update_goal_v2
from tests.test_api_v2_auth import api, bearer, begin_apple_sign_in


def create_goal(client, token: str, *, request_id: str, title: str, **extra):
    payload = {
        "request_id": request_id,
        "title": title,
        "life_area": "career",
        "outcome_type": "milestone",
        **extra,
    }
    return client.post("/api/v2/goals", json=payload, headers=bearer(token))


def test_goal_create_is_idempotent_and_caps_three_active_goals(api) -> None:
    client, _factory = api
    signed_in = begin_apple_sign_in(client, identity_token="valid-identity-token-goal-cap")
    token = signed_in["access_token"]

    first = create_goal(client, token, request_id="goal-create-1", title="Первая")
    duplicate = create_goal(client, token, request_id="goal-create-1", title="Первая")
    conflict = create_goal(client, token, request_id="goal-create-1", title="Другая")
    second = create_goal(client, token, request_id="goal-create-2", title="Вторая")
    third = create_goal(client, token, request_id="goal-create-3", title="Третья")
    fourth = create_goal(client, token, request_id="goal-create-4", title="Четвёртая")

    assert first.status_code == 201, first.text
    assert duplicate.status_code == 201
    assert duplicate.json() == first.json()
    assert conflict.status_code == 409
    assert conflict.json()["detail"] == "idempotency_conflict"
    assert second.status_code == 201
    assert third.status_code == 201
    assert fourth.status_code == 409
    assert fourth.json()["detail"] == "active_goal_limit"


def test_goal_update_uses_version_and_confirmation_for_risky_fields(api) -> None:
    client, _factory = api
    signed_in = begin_apple_sign_in(client, identity_token="valid-identity-token-goal-update")
    token = signed_in["access_token"]
    created = create_goal(
        client, token, request_id="goal-update-create", title="Стать senior"
    ).json()
    goal_id = created["goal"]["public_id"]

    stale = client.patch(
        f"/api/v2/goals/{goal_id}",
        json={
            "request_id": "goal-update-stale",
            "expected_version": 2,
            "title": "Staff",
        },
        headers=bearer(token),
    )
    unconfirmed = client.patch(
        f"/api/v2/goals/{goal_id}",
        json={
            "request_id": "goal-update-risky",
            "expected_version": 1,
            "deadline": "2027-01-01",
        },
        headers=bearer(token),
    )
    updated = client.patch(
        f"/api/v2/goals/{goal_id}",
        json={
            "request_id": "goal-update-ok",
            "expected_version": 1,
            "deadline": "2027-01-01",
            "intensity": "comfortable",
            "confirmation": True,
        },
        headers=bearer(token),
    )

    assert stale.status_code == 409
    assert stale.json()["detail"] == "stale_goal_version"
    assert unconfirmed.status_code == 409
    assert unconfirmed.json()["detail"] == "confirmation_required"
    assert updated.status_code == 200, updated.text
    assert updated.json()["goal"]["version"] == 2
    assert updated.json()["goal"]["deadline"] == "2027-01-01"


def test_pause_resume_respects_cap_and_other_user_gets_opaque_404(api) -> None:
    client, factory = api
    owner = begin_apple_sign_in(client, identity_token="valid-identity-token-goal-owner")
    other = begin_apple_sign_in(client, identity_token="valid-identity-token-goal-other")
    created = create_goal(
        client,
        owner["access_token"],
        request_id="goal-pause-create",
        title="Private goal",
    ).json()
    goal_id = created["goal"]["public_id"]

    hidden = client.patch(
        f"/api/v2/goals/{goal_id}",
        json={
            "request_id": "attacker-update",
            "expected_version": 1,
            "title": "Stolen",
        },
        headers=bearer(other["access_token"]),
    )
    paused = client.post(
        f"/api/v2/goals/{goal_id}/pause",
        json={"request_id": "pause-1", "expected_version": 1},
        headers=bearer(owner["access_token"]),
    )
    resumed = client.post(
        f"/api/v2/goals/{goal_id}/resume",
        json={"request_id": "resume-1", "expected_version": 2},
        headers=bearer(owner["access_token"]),
    )

    assert hidden.status_code == 404
    assert hidden.json()["detail"] == "Goal not found"
    assert paused.status_code == 200
    assert paused.json()["goal"]["status"] == "paused"
    assert resumed.status_code == 200
    assert resumed.json()["goal"]["status"] == "active"
    with factory() as db:
        user = db.scalar(
            select(User).where(User.public_id == UUID(owner["user"]["public_id"]))
        )
        assert user is not None
        saved = db.scalar(select(Goal).where(Goal.user_id == user.id))
        assert saved is not None and saved.title == "Private goal"


def test_metric_evidence_endpoint_returns_authoritative_progress(api) -> None:
    client, _factory = api
    signed_in = begin_apple_sign_in(client, identity_token="valid-identity-token-goal-metric")
    token = signed_in["access_token"]
    created = create_goal(
        client,
        token,
        request_id="metric-create",
        title="Набрать вес",
        outcome_type="metric",
        baseline_value="72",
        target_value="78",
        metric_unit="kg",
    ).json()
    goal_id = created["goal"]["public_id"]

    observation = client.post(
        f"/api/v2/goals/{goal_id}/observations",
        json={
            "request_id": "metric-observation-1",
            "value": "75",
            "unit": "kg",
            "occurred_at": "2026-08-11T12:00:00Z",
            "source": "manual",
        },
        headers=bearer(token),
    )

    assert observation.status_code == 201, observation.text
    assert observation.json()["progress"]["percentage"] == "50.00"
    assert observation.json()["goal"]["current_value"] == "75"


def test_goal_requests_forbid_client_user_identity(api) -> None:
    client, _factory = api
    signed_in = begin_apple_sign_in(client, identity_token="valid-identity-token-goal-extra")

    response = create_goal(
        client,
        signed_in["access_token"],
        request_id="goal-extra-user",
        title="No client owner",
        user_id=999,
    )

    assert response.status_code == 422


def test_goal_deletion_requires_confirmation_and_is_idempotent(api) -> None:
    client, factory = api
    signed_in = begin_apple_sign_in(
        client, identity_token="valid-identity-token-goal-delete"
    )
    token = signed_in["access_token"]
    created = create_goal(
        client,
        token,
        request_id="delete-create",
        title="Удаляемая цель",
    ).json()
    goal_id = created["goal"]["public_id"]

    rejected = client.request(
        "DELETE",
        f"/api/v2/goals/{goal_id}",
        json={
            "request_id": "delete-rejected",
            "expected_version": 1,
            "confirmation": "NO",
        },
        headers=bearer(token),
    )
    deleted = client.request(
        "DELETE",
        f"/api/v2/goals/{goal_id}",
        json={
            "request_id": "delete-confirmed",
            "expected_version": 1,
            "confirmation": "DELETE",
        },
        headers=bearer(token),
    )
    replayed = client.request(
        "DELETE",
        f"/api/v2/goals/{goal_id}",
        json={
            "request_id": "delete-confirmed",
            "expected_version": 1,
            "confirmation": "DELETE",
        },
        headers=bearer(token),
    )

    assert rejected.status_code == 422
    assert deleted.status_code == 204
    assert replayed.status_code == 204
    with factory() as db:
        assert db.scalar(select(Goal).where(Goal.public_id == UUID(goal_id))) is None


def test_goal_update_reloads_locked_version_in_a_long_lived_session(api) -> None:
    client, factory = api
    signed_in = begin_apple_sign_in(
        client, identity_token="valid-identity-token-goal-concurrency"
    )
    created = create_goal(
        client,
        signed_in["access_token"],
        request_id="concurrency-create",
        title="Concurrent goal",
    ).json()
    public_id = UUID(created["goal"]["public_id"])

    with factory() as first_db, factory() as stale_db:
        first_user = first_db.scalar(
            select(User).where(
                User.public_id == UUID(signed_in["user"]["public_id"])
            )
        )
        stale_user = stale_db.scalar(
            select(User).where(
                User.public_id == UUID(signed_in["user"]["public_id"])
            )
        )
        first_goal = first_db.scalar(select(Goal).where(Goal.public_id == public_id))
        stale_goal = stale_db.scalar(select(Goal).where(Goal.public_id == public_id))
        assert first_user and stale_user and first_goal and stale_goal

        update_goal_v2(
            first_db,
            user=first_user,
            goal=first_goal,
            request=GoalUpdateRequest(
                request_id="concurrency-first",
                expected_version=1,
                title="First write",
            ),
        )
        with pytest.raises(GoalConflict, match="stale_goal_version"):
            update_goal_v2(
                stale_db,
                user=stale_user,
                goal=stale_goal,
                request=GoalUpdateRequest(
                    request_id="concurrency-stale",
                    expected_version=1,
                    title="Lost write",
                ),
            )


def test_resume_cannot_exceed_three_active_goals(api) -> None:
    client, _factory = api
    signed_in = begin_apple_sign_in(
        client, identity_token="valid-identity-token-goal-resume-cap"
    )
    token = signed_in["access_token"]
    first = create_goal(
        client, token, request_id="resume-cap-1", title="Первая"
    ).json()
    goal_id = first["goal"]["public_id"]
    assert client.post(
        f"/api/v2/goals/{goal_id}/pause",
        json={"request_id": "resume-cap-pause", "expected_version": 1},
        headers=bearer(token),
    ).status_code == 200
    for index in range(2, 5):
        assert create_goal(
            client,
            token,
            request_id=f"resume-cap-{index}",
            title=f"Цель {index}",
        ).status_code == 201

    resumed = client.post(
        f"/api/v2/goals/{goal_id}/resume",
        json={"request_id": "resume-cap-retry", "expected_version": 2},
        headers=bearer(token),
    )

    assert resumed.status_code == 409
    assert resumed.json()["detail"] == "active_goal_limit"
