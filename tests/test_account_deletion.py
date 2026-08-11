from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select

from app.models.activity import (
    LearningResource,
    LearningSession,
    NutritionLog,
    WorkoutExercise,
    WorkoutSet,
)
from app.models.calendar import (
    CalendarBusyBlock,
    CalendarSyncState,
    TemporaryLifeMode,
)
from app.models.evidence import Evidence
from app.models.goal import Goal
from app.models.onboarding import ResourceBudget
from app.models.program import Program
from app.models.plan_change import PlanChange
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
        owner_goal = Goal(user_id=owner_user.id, title="Owner goal")
        other_goal = Goal(user_id=other_user.id, title="Other private goal")
        db.add_all([owner_goal, other_goal])
        db.flush()
        owner_program = Program(
            user_id=owner_user.id,
            goal_id=owner_goal.id,
            name="Owner program",
            status="active",
            minimum_minutes_week=30,
            comfortable_minutes_week=60,
            maximum_minutes_week=90,
            adaptation_rules={},
        )
        other_program = Program(
            user_id=other_user.id,
            goal_id=other_goal.id,
            name="Other private program",
            status="active",
            minimum_minutes_week=30,
            comfortable_minutes_week=60,
            maximum_minutes_week=90,
            adaptation_rules={},
        )
        db.add_all([owner_program, other_program])
        db.flush()
        db.add_all(
            [
                Evidence(
                    user_id=owner_user.id,
                    goal_id=owner_goal.id,
                    program_id=owner_program.id,
                    request_id="owner-evidence",
                    evidence_type="result",
                    quantity=1,
                    unit="chapter",
                    occurred_at=datetime(2026, 8, 11, tzinfo=timezone.utc),
                    note="Owner evidence note",
                    attributes={},
                ),
                Evidence(
                    user_id=other_user.id,
                    goal_id=other_goal.id,
                    program_id=other_program.id,
                    request_id="other-evidence",
                    evidence_type="result",
                    quantity=1,
                    unit="chapter",
                    occurred_at=datetime(2026, 8, 11, tzinfo=timezone.utc),
                    note="Other private evidence note",
                    attributes={},
                ),
            ]
        )
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
    assert "Owner program" in serialized
    assert "Owner evidence note" in serialized
    assert "Owner budget priority" in serialized
    assert "Other private goal" not in serialized
    assert "Other private program" not in serialized
    assert "Other private evidence note" not in serialized
    assert "Other private budget" not in serialized
    assert owner["access_token"] not in serialized
    assert owner["refresh_token"] not in serialized
    assert "token_hash" not in serialized


def test_account_export_includes_only_the_owners_activity_facts(api) -> None:
    client, factory = api
    owner = begin_apple_sign_in(
        client,
        device_id="activity-export-owner-phone",
        identity_token="valid-identity-token-activity-export-owner",
    )
    other = begin_apple_sign_in(
        client,
        device_id="activity-export-other-phone",
        identity_token="valid-identity-token-activity-export-other",
    )

    def seed_activity(db, user: User, label: str) -> None:
        goal = Goal(user_id=user.id, title=f"{label} activity goal")
        db.add(goal)
        db.flush()
        task = Task(
            user_id=user.id,
            goal_id=goal.id,
            title=f"{label} workout task",
            target_date=date(2026, 8, 11),
        )
        db.add(task)
        db.flush()
        exercise = WorkoutExercise(
            user_id=user.id,
            goal_id=goal.id,
            task_id=task.id,
            name=f"{label} squat",
            position=1,
            note=f"{label} exercise note",
        )
        db.add(exercise)
        db.flush()
        resource = LearningResource(
            user_id=user.id,
            goal_id=goal.id,
            title=f"{label} private book",
            resource_type="book",
            note=f"{label} resource note",
        )
        db.add(resource)
        db.flush()
        db.add_all(
            [
                WorkoutSet(
                    user_id=user.id,
                    workout_exercise_id=exercise.id,
                    position=1,
                    planned_reps=6,
                    actual_reps=5,
                    completion_status="completed",
                    note=f"{label} set note",
                ),
                NutritionLog(
                    user_id=user.id,
                    goal_id=goal.id,
                    task_id=task.id,
                    request_id=f"{label.lower()}-nutrition",
                    occurred_at=datetime(2026, 8, 11, 13, 0, tzinfo=timezone.utc),
                    meal_note=f"{label} private meal",
                ),
                LearningSession(
                    user_id=user.id,
                    goal_id=goal.id,
                    task_id=task.id,
                    learning_resource_id=resource.id,
                    request_id=f"{label.lower()}-learning",
                    occurred_at=datetime(2026, 8, 11, 19, 0, tzinfo=timezone.utc),
                    minutes_spent=30,
                    note=f"{label} private learning note",
                ),
            ]
        )

    with factory() as db:
        owner_user = db.scalar(
            select(User).where(User.public_id == UUID(owner["user"]["public_id"]))
        )
        other_user = db.scalar(
            select(User).where(User.public_id == UUID(other["user"]["public_id"]))
        )
        assert owner_user is not None and other_user is not None
        seed_activity(db, owner_user, "Owner")
        seed_activity(db, other_user, "Other")
        db.commit()

    response = client.get(
        "/api/v2/account/export", headers=bearer(owner["access_token"])
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["workout_exercises"]) == 1
    assert len(payload["workout_sets"]) == 1
    assert len(payload["nutrition_logs"]) == 1
    assert len(payload["learning_resources"]) == 1
    assert len(payload["learning_sessions"]) == 1
    serialized = response.text
    assert "Owner squat" in serialized
    assert "Owner private meal" in serialized
    assert "Owner private book" in serialized
    assert "Owner private learning note" in serialized
    assert "Other squat" not in serialized
    assert "Other private meal" not in serialized
    assert "Other private book" not in serialized
    assert "Other private learning note" not in serialized
    assert owner["access_token"] not in serialized
    assert owner["refresh_token"] not in serialized


def test_account_export_includes_only_owned_calendar_and_plan_change_facts(api) -> None:
    client, factory = api
    owner = begin_apple_sign_in(
        client,
        device_id="calendar-export-owner-phone",
        identity_token="valid-identity-token-calendar-export-owner",
    )
    other = begin_apple_sign_in(
        client,
        device_id="calendar-export-other-phone",
        identity_token="valid-identity-token-calendar-export-other",
    )

    def seed_calendar(db, user: User, label: str) -> None:
        starts_at = datetime(2026, 8, 11, 9, 0, tzinfo=timezone.utc)
        db.add_all(
            [
                CalendarBusyBlock(
                    user_id=user.id,
                    device_id=f"{label.lower()}-iphone",
                    provider="apple",
                    calendar_external_id=f"{label}-calendar",
                    external_id=f"{label}-event",
                    occurrence_external_id=f"{label}-occurrence",
                    occurrence_start=starts_at,
                    occurrence_end=starts_at + timedelta(hours=1),
                    device_timezone="Europe/Moscow",
                    source_revision=f"{label}-revision",
                    last_seen_client_revision=1,
                ),
                CalendarSyncState(
                    user_id=user.id,
                    device_id=f"{label.lower()}-iphone",
                    provider="apple",
                    version=1,
                    client_revision=1,
                    range_start=starts_at - timedelta(days=1),
                    range_end=starts_at + timedelta(days=7),
                    device_timezone="Europe/Moscow",
                    covered_calendar_ids=[f"{label}-calendar"],
                    last_synced_at=starts_at,
                ),
                TemporaryLifeMode(
                    user_id=user.id,
                    request_id=f"{label.lower()}-temporary-mode",
                    mode="travel",
                    starts_at=starts_at,
                    ends_at=starts_at + timedelta(days=3),
                    status="active",
                    constraints={"marker": f"{label} mode"},
                ),
                PlanChange(
                    user_id=user.id,
                    request_id=f"{label.lower()}-plan-change",
                    reason="calendar_sync",
                    status="applied",
                    base_versions={"2026-08-11": 1},
                    result_versions={"2026-08-11": 2},
                    affected_dates=["2026-08-11"],
                    forward_payload={"marker": f"{label} forward change"},
                    inverse_payload={"marker": f"{label} inverse change"},
                    expires_at=starts_at + timedelta(days=7),
                ),
            ]
        )

    with factory() as db:
        owner_user = db.scalar(
            select(User).where(User.public_id == UUID(owner["user"]["public_id"]))
        )
        other_user = db.scalar(
            select(User).where(User.public_id == UUID(other["user"]["public_id"]))
        )
        assert owner_user is not None and other_user is not None
        seed_calendar(db, owner_user, "Owner")
        seed_calendar(db, other_user, "Other")
        db.commit()

    response = client.get(
        "/api/v2/account/export", headers=bearer(owner["access_token"])
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["calendar_busy_blocks"]) == 1
    assert len(payload["calendar_sync_states"]) == 1
    assert len(payload["temporary_life_modes"]) == 1
    assert len(payload["plan_changes"]) == 1
    assert all(
        "user_id" not in item
        for collection in (
            payload["calendar_busy_blocks"],
            payload["calendar_sync_states"],
            payload["temporary_life_modes"],
            payload["plan_changes"],
        )
        for item in collection
    )
    serialized = response.text
    assert "Owner-calendar" in serialized
    assert "Owner mode" in serialized
    assert "Owner forward change" in serialized
    assert "Other-calendar" not in serialized
    assert "Other mode" not in serialized
    assert "Other forward change" not in serialized
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
        program = Program(
            user_id=owner_user.id,
            goal_id=goal.id,
            name="Delete program",
            status="active",
            minimum_minutes_week=30,
            comfortable_minutes_week=60,
            maximum_minutes_week=90,
            adaptation_rules={},
        )
        db.add(program)
        db.flush()
        db.add(
            Task(
                user_id=owner_user.id,
                goal_id=goal.id,
                title="Delete task",
                target_date=date(2026, 8, 11),
            )
        )
        db.add(
            Evidence(
                user_id=owner_user.id,
                goal_id=goal.id,
                program_id=program.id,
                request_id="delete-evidence",
                evidence_type="result",
                occurred_at=datetime(2026, 8, 11, tzinfo=timezone.utc),
                note="Delete this private note",
                attributes={},
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
        assert db.query(Program).filter_by(user_id=owner_user.id).count() == 0
        assert db.query(Evidence).filter_by(user_id=owner_user.id).count() == 0
