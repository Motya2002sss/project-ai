import importlib.util
from collections.abc import Generator
from datetime import date, datetime, time, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.api.v2.auth import get_apple_verifier, router as auth_router
from app.auth.apple import AppleIdentity, AppleVerificationError
from app.db.base import Base
from app.db.session import get_db
from app.models.activity import (
    LearningResource,
    LearningSession,
    NutritionLog,
    WorkoutExercise,
    WorkoutSet,
)
from app.models.day_plan import DayPlan
from app.models.evidence import Evidence, GoalProgressSnapshot, MetricObservation
from app.models.goal import Goal
from app.models.message_receipt import MessageReceipt
from app.models.program import Program, WeeklyCommitment
from app.models.plan_item import PlanItem
from app.models.task import Task
from app.models.user import User


ACTIVITY_API_AVAILABLE = all(
    importlib.util.find_spec(module) is not None
    for module in (
        "app.schemas.activity",
        "app.services.activity_service",
        "app.services.safety_policy",
        "app.api.v2.activities",
    )
)

if ACTIVITY_API_AVAILABLE:
    from app.api.v2.activities import (
        get_adaptation_candidate_builder,
        router as activity_router,
    )
    from app.schemas.activity import ProgramAdaptationRequest
    from app.services.activity_service import (
        ActivityConflict,
        propose_program_adaptation,
    )
else:
    activity_router = None
    get_adaptation_candidate_builder = None
    ProgramAdaptationRequest = None
    ActivityConflict = ValueError
    propose_program_adaptation = None


NOW = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)
D = Decimal


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
def api(
    tmp_path: Path,
) -> Generator[tuple[TestClient, sessionmaker[Session]], None, None]:
    if not ACTIVITY_API_AVAILABLE:
        pytest.skip("activity API is not implemented")
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'activity-api.db'}",
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

    application = FastAPI()
    v2 = APIRouter(prefix="/api/v2")
    v2.include_router(auth_router)
    v2.include_router(activity_router)
    application.include_router(v2)
    application.dependency_overrides[get_db] = override_db
    application.dependency_overrides[get_apple_verifier] = FakeAppleVerifier
    with TestClient(application) as client:
        yield client, factory


def _sign_in(client: TestClient, identity: str, *, device_id: str) -> dict:
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


def _user(db: Session, signed_in: dict) -> User:
    user = db.scalar(
        select(User).where(User.public_id == UUID(signed_in["user"]["public_id"]))
    )
    assert user is not None
    return user


def _seed_workout(
    db: Session,
    user: User,
) -> tuple[Goal, Program, Task, list[WorkoutSet]]:
    goal = Goal(
        user_id=user.id,
        title="Набрать силу",
        category="health",
        outcome_type="consistency",
    )
    db.add(goal)
    db.flush()
    program = Program(
        user_id=user.id,
        goal_id=goal.id,
        name="Силовая база",
        status="active",
        minimum_minutes_week=60,
        comfortable_minutes_week=120,
        maximum_minutes_week=180,
        adaptation_rules={"progression": "confirm_only"},
    )
    db.add(program)
    db.flush()
    commitment = WeeklyCommitment(
        user_id=user.id,
        goal_id=goal.id,
        program_id=program.id,
        title="Силовая тренировка",
        target_minutes_week=120,
        target_sessions_week=2,
        minimum_block_minutes=30,
        allowed_weekdays=[2, 5],
    )
    db.add(commitment)
    db.flush()
    task = Task(
        user_id=user.id,
        goal_id=goal.id,
        program_id=program.id,
        commitment_id=commitment.id,
        title="Тренировка на силу",
        target_date=date(2026, 8, 11),
        estimated_minutes=65,
    )
    db.add(task)
    db.flush()
    exercise = WorkoutExercise(
        user_id=user.id,
        goal_id=goal.id,
        task_id=task.id,
        program_id=program.id,
        name="Жим лёжа",
        position=1,
    )
    db.add(exercise)
    db.flush()
    sets = [
        WorkoutSet(
            user_id=user.id,
            workout_exercise_id=exercise.id,
            position=position,
            planned_weight=D("80"),
            planned_reps=6,
        )
        for position in range(1, 5)
    ]
    db.add_all(sets)
    db.commit()
    return goal, program, task, sets


def _set_fact(set_id: UUID, reps: int, *, status: str = "completed") -> dict:
    return {
        "set_id": str(set_id),
        "actual_weight": "80",
        "actual_reps": reps,
        "actual_rpe": "8",
        "completion_status": status,
    }


def _seed_learning(
    db: Session,
    user: User,
    *,
    task_status: str = "planned",
) -> tuple[Goal, Program, WeeklyCommitment, Task, LearningResource]:
    goal = Goal(
        user_id=user.id,
        title="Изучить архитектуру",
        category="learning",
        outcome_type="consistency",
    )
    db.add(goal)
    db.flush()
    program = Program(
        user_id=user.id,
        goal_id=goal.id,
        name="Architecture",
        status="active",
        minimum_minutes_week=30,
        comfortable_minutes_week=90,
        maximum_minutes_week=150,
        adaptation_rules={},
    )
    db.add(program)
    db.flush()
    commitment = WeeklyCommitment(
        user_id=user.id,
        goal_id=goal.id,
        program_id=program.id,
        title="Чтение",
        target_minutes_week=90,
        target_sessions_week=3,
        minimum_block_minutes=20,
        allowed_weekdays=[1, 3, 5],
    )
    db.add(commitment)
    db.flush()
    task = Task(
        user_id=user.id,
        goal_id=goal.id,
        program_id=program.id,
        commitment_id=commitment.id,
        title="Прочитать главу",
        target_date=date(2026, 8, 11),
        status=task_status,
    )
    resource = LearningResource(
        user_id=user.id,
        goal_id=goal.id,
        program_id=program.id,
        title="DDIA",
        resource_type="book",
        competency="Архитектура данных",
        total_pages=616,
    )
    db.add_all([task, resource])
    db.commit()
    return goal, program, commitment, task, resource


def test_activity_module_contract_exists() -> None:
    assert ACTIVITY_API_AVAILABLE, "activity API modules are not implemented"


def test_create_app_mounts_activity_routes() -> None:
    from app.main import create_app

    with TestClient(create_app()) as client:
        response = client.get("/api/v2/activities/workouts/1")

    assert response.status_code == 401


def test_workout_draft_retry_and_finish_are_factual_and_idempotent(api) -> None:
    client, factory = api
    signed_in = _sign_in(
        client,
        "valid-identity-token-workout",
        device_id="workout-iphone",
    )
    headers = _bearer(signed_in["access_token"])
    with factory() as db:
        _goal, _program, task, sets = _seed_workout(db, _user(db, signed_in))
        plan = DayPlan(
            user_id=task.user_id,
            date=task.target_date,
            version=3,
            status="draft",
        )
        plan.items.append(
            PlanItem(
                task_id=task.id,
                title=task.title,
                item_type="task",
                status="planned",
                start_time=time(18, 0),
                end_time=time(19, 5),
            )
        )
        db.add(plan)
        db.commit()
        task_id = task.id
        set_ids = [item.id for item in sets]

    draft_payload = {
        "request_id": "workout-draft-1",
        "recorded_at": "2026-08-11T18:20:00Z",
        "sets": [_set_fact(set_ids[0], 6), _set_fact(set_ids[1], 6)],
    }
    first_draft = client.patch(
        f"/api/v2/activities/workouts/{task_id}/draft",
        json=draft_payload,
        headers=headers,
    )
    replayed_draft = client.patch(
        f"/api/v2/activities/workouts/{task_id}/draft",
        json=draft_payload,
        headers=headers,
    )

    assert first_draft.status_code == 200, first_draft.text
    assert replayed_draft.json() == first_draft.json()
    assert first_draft.json()["state"] == "draft"
    assert first_draft.json()["report_required"] is False
    draft_sets = first_draft.json()["workout"]["exercises"][0]["sets"]
    assert [item["actual_reps"] for item in draft_sets] == [6, 6, None, None]

    finish_payload = {
        "request_id": "workout-finish-1",
        "started_at": "2026-08-11T18:00:00Z",
        "finished_at": "2026-08-11T19:05:00Z",
        "sets": [
            _set_fact(set_ids[0], 6),
            _set_fact(set_ids[1], 6),
            _set_fact(set_ids[2], 6),
            _set_fact(set_ids[3], 5),
        ],
    }
    finished = client.post(
        f"/api/v2/activities/workouts/{task_id}/finish",
        json=finish_payload,
        headers=headers,
    )
    replayed_finish = client.post(
        f"/api/v2/activities/workouts/{task_id}/finish",
        json=finish_payload,
        headers=headers,
    )

    assert finished.status_code == 200, finished.text
    assert replayed_finish.json() == finished.json()
    body = finished.json()
    assert body["state"] == "final"
    assert body["elapsed_minutes"] == 65
    assert body["report_required"] is False
    assert [
        item["actual_reps"]
        for item in body["workout"]["exercises"][0]["sets"]
    ] == [6, 6, 6, 5]
    assert body["workout"]["task_status"] == "done"
    assert body["progress"]["strategy"] == "consistency"
    with factory() as db:
        assert db.scalar(select(func.count(WorkoutSet.id))) == 4
        assert db.scalar(select(func.count(Evidence.id))) == 1
        assert db.scalar(select(func.count(GoalProgressSnapshot.id))) == 1
        evidence = db.scalar(select(Evidence))
        assert evidence is not None
        assert evidence.quantity == D("65")
        assert evidence.unit == "minutes"
        task = db.get(Task, task_id)
        assert task is not None
        plan = db.scalar(select(DayPlan).where(DayPlan.user_id == task.user_id))
        assert plan is not None and plan.version == 4
        item = db.scalar(
            select(PlanItem).where(
                PlanItem.day_plan_id == plan.id,
                PlanItem.task_id == task_id,
            )
        )
        assert item is not None and item.status == "done"
        assert evidence.commitment_id == task.commitment_id
        assert evidence.attributes == {
            "activity_type": "workout",
            "completed_set_count": 4,
            "planned_set_count": 4,
            "partial": False,
            "elapsed_minutes": 65,
        }


def test_partial_workout_finish_preserves_unfinished_sets(api) -> None:
    client, factory = api
    signed_in = _sign_in(
        client,
        "valid-identity-token-partial-workout",
        device_id="partial-workout-iphone",
    )
    with factory() as db:
        _goal, _program, task, sets = _seed_workout(db, _user(db, signed_in))
        task_id = task.id
        set_ids = [item.id for item in sets]

    response = client.post(
        f"/api/v2/activities/workouts/{task_id}/finish",
        json={
            "request_id": "partial-workout-finish",
            "started_at": "2026-08-11T18:00:00Z",
            "finished_at": "2026-08-11T18:35:00Z",
            "sets": [
                _set_fact(set_ids[0], 6),
                _set_fact(set_ids[1], 5),
                {
                    "set_id": str(set_ids[2]),
                    "completion_status": "skipped",
                },
            ],
        },
        headers=_bearer(signed_in["access_token"]),
    )

    assert response.status_code == 200, response.text
    facts = response.json()["workout"]["exercises"][0]["sets"]
    assert [item["completion_status"] for item in facts] == [
        "completed",
        "completed",
        "skipped",
        "planned",
    ]
    with factory() as db:
        evidence = db.scalar(select(Evidence))
        assert evidence is not None
        assert evidence.attributes["partial"] is True
        assert evidence.attributes["completed_set_count"] == 2


def test_zero_workout_finish_does_not_complete_task_or_create_progress(api) -> None:
    client, factory = api
    signed_in = _sign_in(
        client,
        "valid-identity-token-zero-workout",
        device_id="zero-workout-iphone",
    )
    with factory() as db:
        _goal, _program, task, _sets = _seed_workout(db, _user(db, signed_in))
        task_id = task.id

    response = client.post(
        f"/api/v2/activities/workouts/{task_id}/finish",
        json={
            "request_id": "zero-workout-finish",
            "started_at": "2026-08-11T18:00:00Z",
            "finished_at": "2026-08-11T18:00:00Z",
            "sets": [],
        },
        headers=_bearer(signed_in["access_token"]),
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "workout_fact_required"
    with factory() as db:
        saved_task = db.get(Task, task_id)
        assert saved_task is not None and saved_task.status == "planned"
        assert db.scalar(select(func.count(Evidence.id))) == 0
        assert db.scalar(select(func.count(GoalProgressSnapshot.id))) == 0


def test_cancelled_workout_cannot_be_edited_or_finished(api) -> None:
    client, factory = api
    signed_in = _sign_in(
        client,
        "valid-identity-token-cancelled-workout",
        device_id="cancelled-workout-iphone",
    )
    with factory() as db:
        _goal, _program, task, sets = _seed_workout(db, _user(db, signed_in))
        task.status = "cancelled"
        db.commit()
        task_id = task.id
        set_id = sets[0].id
    headers = _bearer(signed_in["access_token"])

    draft = client.patch(
        f"/api/v2/activities/workouts/{task_id}/draft",
        json={
            "request_id": "cancelled-workout-draft",
            "recorded_at": "2026-08-11T18:20:00Z",
            "sets": [_set_fact(set_id, 6)],
        },
        headers=headers,
    )
    finish = client.post(
        f"/api/v2/activities/workouts/{task_id}/finish",
        json={
            "request_id": "cancelled-workout-finish",
            "started_at": "2026-08-11T18:00:00Z",
            "finished_at": "2026-08-11T18:30:00Z",
            "sets": [_set_fact(set_id, 6)],
        },
        headers=headers,
    )

    assert draft.status_code == 409
    assert draft.json()["detail"] == "workout_not_active"
    assert finish.status_code == 409
    assert finish.json()["detail"] == "workout_not_active"
    with factory() as db:
        saved_task = db.get(Task, task_id)
        saved_set = db.get(WorkoutSet, set_id)
        assert saved_task is not None and saved_task.status == "cancelled"
        assert saved_set is not None and saved_set.actual_reps is None
        assert db.scalar(select(func.count(Evidence.id))) == 0


def test_workout_ownership_is_opaque_and_does_not_mutate(api) -> None:
    client, factory = api
    owner = _sign_in(
        client,
        "valid-identity-token-workout-owner",
        device_id="owner-iphone",
    )
    attacker = _sign_in(
        client,
        "valid-identity-token-workout-attacker",
        device_id="attacker-iphone",
    )
    with factory() as db:
        _goal, _program, task, sets = _seed_workout(db, _user(db, owner))
        task_id = task.id
        set_id = sets[0].id

    response = client.patch(
        f"/api/v2/activities/workouts/{task_id}/draft",
        json={
            "request_id": "stolen-draft",
            "recorded_at": "2026-08-11T18:20:00Z",
            "sets": [_set_fact(set_id, 6)],
        },
        headers=_bearer(attacker["access_token"]),
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Workout not found"
    with factory() as db:
        saved = db.get(WorkoutSet, set_id)
        assert saved is not None
        assert saved.actual_reps is None


def test_draft_idempotency_key_rejects_a_different_payload(api) -> None:
    client, factory = api
    signed_in = _sign_in(
        client,
        "valid-identity-token-draft-conflict",
        device_id="draft-conflict-iphone",
    )
    with factory() as db:
        _goal, _program, task, sets = _seed_workout(db, _user(db, signed_in))
        task_id = task.id
        set_id = sets[0].id
    headers = _bearer(signed_in["access_token"])
    payload = {
        "request_id": "same-draft-key",
        "recorded_at": "2026-08-11T18:20:00Z",
        "sets": [_set_fact(set_id, 6)],
    }

    assert client.patch(
        f"/api/v2/activities/workouts/{task_id}/draft",
        json=payload,
        headers=headers,
    ).status_code == 200
    payload["sets"] = [_set_fact(set_id, 4)]
    conflict = client.patch(
        f"/api/v2/activities/workouts/{task_id}/draft",
        json=payload,
        headers=headers,
    )

    assert conflict.status_code == 409
    assert conflict.json()["detail"] == "idempotency_conflict"


def test_nutrition_keeps_unknown_macros_null_and_returns_weight_trend(api) -> None:
    client, factory = api
    signed_in = _sign_in(
        client,
        "valid-identity-token-nutrition",
        device_id="nutrition-iphone",
    )
    headers = _bearer(signed_in["access_token"])
    with factory() as db:
        user = _user(db, signed_in)
        goal = Goal(
            user_id=user.id,
            title="Набрать вес",
            category="health",
            outcome_type="metric",
            baseline_value=D("72"),
            current_value=D("72"),
            target_value=D("78"),
            metric_unit="kg",
        )
        db.add(goal)
        db.commit()
        goal_id = goal.public_id

    text_only = client.post(
        "/api/v2/activities/nutrition",
        json={
            "request_id": "nutrition-text-only",
            "occurred_at": "2026-08-10T13:00:00Z",
            "meal_note": "Обед в кафе, состав не считал",
            "adherence": "not_recorded",
        },
        headers=headers,
    )
    first_weight = client.post(
        "/api/v2/activities/nutrition",
        json={
            "request_id": "weight-log-1",
            "occurred_at": "2026-08-10T07:00:00Z",
            "goal_id": str(goal_id),
            "weight_observation": "74",
            "weight_unit": "kg",
        },
        headers=headers,
    )
    second_payload = {
        "request_id": "weight-log-2",
        "occurred_at": "2026-08-11T07:00:00Z",
        "goal_id": str(goal_id),
        "weight_observation": "75",
        "weight_unit": "kg",
    }
    second_weight = client.post(
        "/api/v2/activities/nutrition",
        json=second_payload,
        headers=headers,
    )
    replayed = client.post(
        "/api/v2/activities/nutrition",
        json=second_payload,
        headers=headers,
    )

    assert text_only.status_code == 201, text_only.text
    for field in (
        "calories",
        "protein_grams",
        "fat_grams",
        "carbohydrate_grams",
        "target_calories",
        "target_protein_grams",
        "target_fat_grams",
        "target_carbohydrate_grams",
    ):
        assert text_only.json()["log"][field] is None
    assert first_weight.status_code == 201, first_weight.text
    assert second_weight.status_code == 201, second_weight.text
    assert replayed.json() == second_weight.json()
    assert second_weight.json()["weight_trend"] == {
        "current": "75.000",
        "previous": "74.000",
        "delta": "1.000",
        "unit": "kg",
    }
    assert second_weight.json()["progress"]["percentage"] == "50.00"
    assert second_weight.json()["report_required"] is False
    with factory() as db:
        assert db.scalar(select(func.count(NutritionLog.id))) == 3
        assert db.scalar(select(func.count(MetricObservation.id))) == 2
        saved_goal = db.scalar(select(Goal).where(Goal.public_id == goal_id))
        assert saved_goal is not None and saved_goal.current_value == D("75")


def test_nutrition_task_only_inherits_its_program(api) -> None:
    client, factory = api
    signed_in = _sign_in(
        client,
        "valid-identity-token-nutrition-links",
        device_id="nutrition-links-iphone",
    )
    with factory() as db:
        _goal, program, _commitment, task, _resource = _seed_learning(
            db, _user(db, signed_in)
        )
        task_id = task.id
        program_id = program.id

    response = client.post(
        "/api/v2/activities/nutrition",
        json={
            "request_id": "nutrition-task-links",
            "occurred_at": "2026-08-11T13:00:00Z",
            "task_id": task_id,
            "meal_note": "Обед",
        },
        headers=_bearer(signed_in["access_token"]),
    )

    assert response.status_code == 201, response.text
    with factory() as db:
        log = db.scalar(select(NutritionLog))
        assert log is not None
        assert log.program_id == program_id


def test_learning_log_creates_minutes_evidence_and_completes_without_report(api) -> None:
    client, factory = api
    signed_in = _sign_in(
        client,
        "valid-identity-token-learning",
        device_id="learning-iphone",
    )
    headers = _bearer(signed_in["access_token"])
    with factory() as db:
        user = _user(db, signed_in)
        goal = Goal(
            user_id=user.id,
            title="Изучить архитектуру",
            category="learning",
            outcome_type="consistency",
        )
        db.add(goal)
        db.flush()
        program = Program(
            user_id=user.id,
            goal_id=goal.id,
            name="Architecture",
            status="active",
            minimum_minutes_week=30,
            comfortable_minutes_week=90,
            maximum_minutes_week=150,
            adaptation_rules={},
        )
        db.add(program)
        db.flush()
        db.add(
            WeeklyCommitment(
                user_id=user.id,
                goal_id=goal.id,
                program_id=program.id,
                title="Чтение",
                target_minutes_week=90,
                target_sessions_week=3,
                minimum_block_minutes=20,
                allowed_weekdays=[1, 3, 5],
            )
        )
        task = Task(
            user_id=user.id,
            goal_id=goal.id,
            program_id=program.id,
            title="Прочитать главу",
            target_date=date(2026, 8, 11),
        )
        resource = LearningResource(
            user_id=user.id,
            goal_id=goal.id,
            program_id=program.id,
            title="DDIA",
            resource_type="book",
            competency="Архитектура данных",
            total_pages=616,
        )
        db.add_all([task, resource])
        db.flush()
        plan = DayPlan(
            user_id=user.id,
            date=task.target_date,
            version=5,
            status="draft",
        )
        plan.items.append(
            PlanItem(
                task_id=task.id,
                title=task.title,
                item_type="task",
                status="planned",
                start_time=time(19, 0),
                end_time=time(19, 45),
            )
        )
        db.add(plan)
        db.commit()
        task_id = task.id
        resource_id = resource.id
        goal_id = goal.public_id
        program_id = program.id

    payload = {
        "request_id": "learning-log-1",
        "occurred_at": "2026-08-11T19:00:00Z",
        "goal_id": str(goal_id),
        "program_id": str(program_id),
        "task_id": task_id,
        "resource_id": str(resource_id),
        "competency": "Архитектура данных",
        "pages_completed": 24,
        "minutes_spent": 45,
        "exercises_completed": 2,
        "projects_completed": 1,
        "note": "Разобрал репликацию",
    }
    response = client.post(
        "/api/v2/activities/learning", json=payload, headers=headers
    )
    replayed = client.post(
        "/api/v2/activities/learning", json=payload, headers=headers
    )

    assert response.status_code == 201, response.text
    assert replayed.json() == response.json()
    body = response.json()
    assert body["session"]["pages_completed"] == 24
    assert body["session"]["minutes_spent"] == 45
    assert body["session"]["exercises_completed"] == 2
    assert body["session"]["projects_completed"] == 1
    assert body["task_status"] == "done"
    assert body["report_required"] is False
    assert body["progress"]["strategy"] == "consistency"
    with factory() as db:
        assert db.scalar(select(func.count(LearningSession.id))) == 1
        assert db.scalar(select(func.count(Evidence.id))) == 1
        evidence = db.scalar(select(Evidence))
        assert evidence is not None
        assert evidence.quantity == D("45")
        assert evidence.unit == "minutes"
        assert evidence.note is None
        plan = db.scalar(select(DayPlan).where(DayPlan.user_id == evidence.user_id))
        assert plan is not None and plan.version == 6
        item = db.scalar(
            select(PlanItem).where(
                PlanItem.day_plan_id == plan.id,
                PlanItem.task_id == task_id,
            )
        )
        assert item is not None and item.status == "done"


def test_learning_task_only_inherits_program_and_commitment_evidence(api) -> None:
    client, factory = api
    signed_in = _sign_in(
        client,
        "valid-identity-token-learning-links",
        device_id="learning-links-iphone",
    )
    with factory() as db:
        _goal, program, commitment, task, _resource = _seed_learning(
            db, _user(db, signed_in)
        )
        task_id = task.id
        program_id = program.id
        commitment_id = commitment.id

    response = client.post(
        "/api/v2/activities/learning",
        json={
            "request_id": "learning-task-links",
            "occurred_at": "2026-08-11T19:00:00Z",
            "task_id": task_id,
            "minutes_spent": 15,
        },
        headers=_bearer(signed_in["access_token"]),
    )

    assert response.status_code == 201, response.text
    with factory() as db:
        session = db.scalar(select(LearningSession))
        evidence = db.scalar(select(Evidence))
        assert session is not None and session.program_id == program_id
        assert evidence is not None and evidence.program_id == program_id
        assert evidence.commitment_id == commitment_id


@pytest.mark.parametrize("task_status", ["done", "cancelled"])
def test_learning_rejects_closed_task_without_duplicate_progress(
    api,
    task_status: str,
) -> None:
    client, factory = api
    signed_in = _sign_in(
        client,
        f"valid-identity-token-learning-{task_status}",
        device_id=f"learning-{task_status}-iphone",
    )
    with factory() as db:
        _goal, _program, _commitment, task, _resource = _seed_learning(
            db,
            _user(db, signed_in),
            task_status=task_status,
        )
        task_id = task.id

    response = client.post(
        "/api/v2/activities/learning",
        json={
            "request_id": f"learning-closed-{task_status}",
            "occurred_at": "2026-08-11T19:00:00Z",
            "task_id": task_id,
            "minutes_spent": 15,
        },
        headers=_bearer(signed_in["access_token"]),
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "activity_task_not_active"
    with factory() as db:
        saved_task = db.get(Task, task_id)
        assert saved_task is not None and saved_task.status == task_status
        assert db.scalar(select(func.count(LearningSession.id))) == 0
        assert db.scalar(select(func.count(Evidence.id))) == 0
        assert db.scalar(select(func.count(GoalProgressSnapshot.id))) == 0


def test_learning_rejects_zero_work_without_evidence_or_completion(api) -> None:
    client, factory = api
    signed_in = _sign_in(
        client,
        "valid-identity-token-learning-zero",
        device_id="learning-zero-iphone",
    )
    with factory() as db:
        _goal, _program, _commitment, task, _resource = _seed_learning(
            db, _user(db, signed_in)
        )
        task_id = task.id

    response = client.post(
        "/api/v2/activities/learning",
        json={
            "request_id": "learning-zero-work",
            "occurred_at": "2026-08-11T19:00:00Z",
            "task_id": task_id,
            "pages_completed": 0,
            "minutes_spent": 0,
            "exercises_completed": 0,
            "projects_completed": 0,
        },
        headers=_bearer(signed_in["access_token"]),
    )

    assert response.status_code == 422
    with factory() as db:
        saved_task = db.get(Task, task_id)
        assert saved_task is not None and saved_task.status == "planned"
        assert db.scalar(select(func.count(LearningSession.id))) == 0
        assert db.scalar(select(func.count(Evidence.id))) == 0
        assert db.scalar(select(func.count(GoalProgressSnapshot.id))) == 0


def test_zero_learning_dimension_does_not_hide_another_positive_fact(api) -> None:
    client, factory = api
    signed_in = _sign_in(
        client,
        "valid-identity-token-learning-positive-pages",
        device_id="learning-positive-pages-iphone",
    )
    with factory() as db:
        goal, _program, _commitment, task, _resource = _seed_learning(
            db, _user(db, signed_in)
        )
        task_id = task.id
        goal_id = goal.public_id

    response = client.post(
        "/api/v2/activities/learning",
        json={
            "request_id": "learning-positive-pages",
            "occurred_at": "2026-08-11T19:00:00Z",
            "goal_id": str(goal_id),
            "task_id": task_id,
            "minutes_spent": 0,
            "pages_completed": 24,
        },
        headers=_bearer(signed_in["access_token"]),
    )

    assert response.status_code == 201, response.text
    with factory() as db:
        evidence = db.scalar(select(Evidence))
        assert evidence is not None
        assert evidence.quantity == D("24")
        assert evidence.unit == "pages"


def test_activity_endpoints_require_auth_and_forbid_client_owner(api) -> None:
    client, _factory = api

    unauthorized = client.post(
        "/api/v2/activities/nutrition",
        json={
            "request_id": "unauthorized-nutrition",
            "occurred_at": "2026-08-11T13:00:00Z",
            "meal_note": "Обед",
        },
    )
    signed_in = _sign_in(
        client,
        "valid-identity-token-extra-owner",
        device_id="extra-owner-iphone",
    )
    extra_owner = client.post(
        "/api/v2/activities/nutrition",
        json={
            "request_id": "extra-owner-nutrition",
            "occurred_at": "2026-08-11T13:00:00Z",
            "meal_note": "Обед",
            "user_id": 999,
        },
        headers=_bearer(signed_in["access_token"]),
    )

    assert unauthorized.status_code == 401
    assert extra_owner.status_code == 422


def test_rejected_adaptation_precedes_provider_and_mutation(api) -> None:
    _client, factory = api
    with factory() as db:
        user = User(external_id="adaptation-owner")
        db.add(user)
        db.flush()
        goal = Goal(
            user_id=user.id,
            title="Сила",
            category="health",
            outcome_type="consistency",
        )
        db.add(goal)
        db.flush()
        program = Program(
            user_id=user.id,
            goal_id=goal.id,
            name="Safe program",
            status="active",
            minimum_minutes_week=60,
            comfortable_minutes_week=120,
            maximum_minutes_week=180,
            adaptation_rules={"increase": "confirmation_required"},
        )
        db.add(program)
        db.commit()
        program_id = program.id
        original_rules = dict(program.adaptation_rules)
        calls: list[str] = []

        def provider(prompt: str, _program: Program) -> dict:
            calls.append(prompt)
            return {"changes": [{"weight_delta": 30}]}

        refused = propose_program_adaptation(
            db,
            user=user,
            program_id=program_id,
            request=ProgramAdaptationRequest(
                request_id="unsafe-adaptation",
                prompt="После травмы больно, но увеличь 1ПМ завтра на 30 кг",
            ),
            candidate_builder=provider,
        )
        replayed = propose_program_adaptation(
            db,
            user=user,
            program_id=program_id,
            request=ProgramAdaptationRequest(
                request_id="unsafe-adaptation",
                prompt="После травмы больно, но увеличь 1ПМ завтра на 30 кг",
            ),
            candidate_builder=provider,
        )

        assert refused.status == "refused"
        assert replayed == refused
        assert refused.confirmation_required is False
        assert refused.candidate is None
        assert calls == []
        with pytest.raises(ActivityConflict, match="idempotency_conflict"):
            propose_program_adaptation(
                db,
                user=user,
                program_id=program_id,
                request=ProgramAdaptationRequest(
                    request_id="unsafe-adaptation",
                    prompt="Болит плечо, но всё равно резко увеличь нагрузку",
                ),
                candidate_builder=provider,
            )
        db.refresh(program)
        assert program.adaptation_rules == original_rules
        assert db.scalar(select(func.count(MessageReceipt.id))) == 1


def test_allowed_adaptation_returns_candidate_but_never_applies_it(api) -> None:
    _client, factory = api
    with factory() as db:
        user = User(external_id="candidate-owner")
        db.add(user)
        db.flush()
        goal = Goal(
            user_id=user.id,
            title="Сила",
            category="health",
            outcome_type="consistency",
        )
        db.add(goal)
        db.flush()
        program = Program(
            user_id=user.id,
            goal_id=goal.id,
            name="Current program",
            status="active",
            minimum_minutes_week=60,
            comfortable_minutes_week=120,
            maximum_minutes_week=180,
            adaptation_rules={"load": "stable"},
        )
        db.add(program)
        db.commit()
        original_version = program.version
        original_rules = dict(program.adaptation_rules)

        calls: list[str] = []

        def provider(prompt: str, _program) -> dict:
            calls.append(prompt)
            return {
                "summary": "Перенести сессию на субботу",
                "changes": [
                    {"kind": "schedule", "weekday": 6},
                    {
                        "kind": "exercise_load",
                        "exercise": "Жим лёжа",
                        "weight_delta": D("2.5"),
                        "weight_unit": "kg",
                    },
                ],
            }

        request = ProgramAdaptationRequest(
            request_id="safe-adaptation",
            prompt="Оставь вес прежним и перенеси тренировку на субботу",
        )
        result = propose_program_adaptation(
            db,
            user=user,
            program_id=program.id,
            request=request,
            candidate_builder=provider,
        )
        replayed = propose_program_adaptation(
            db,
            user=user,
            program_id=program.id,
            request=request,
            candidate_builder=provider,
        )

        assert result.status == "confirmation_required"
        assert replayed == result
        assert calls == [request.prompt]
        assert result.confirmation_required is True
        assert result.candidate is not None
        assert result.candidate.model_dump(mode="json", exclude_none=True) == {
            "summary": "Перенести сессию на субботу",
            "changes": [
                {"kind": "schedule", "weekday": 6},
                {
                    "kind": "exercise_load",
                    "exercise": "Жим лёжа",
                    "weight_delta": "2.5",
                    "weight_unit": "kg",
                },
            ],
        }
        with pytest.raises(ActivityConflict, match="idempotency_conflict"):
            propose_program_adaptation(
                db,
                user=user,
                program_id=program.id,
                request=ProgramAdaptationRequest(
                    request_id="safe-adaptation",
                    prompt="Перенеси тренировку на воскресенье",
                ),
                candidate_builder=provider,
            )
        db.refresh(program)
        assert program.version == original_version
        assert program.adaptation_rules == original_rules
        assert db.scalar(select(func.count(MessageReceipt.id))) == 1


@pytest.mark.parametrize(
    "candidate",
    [
        {
            "summary": "Некорректный день",
            "changes": [{"kind": "schedule", "weekday": 8}],
        },
        {
            "summary": "Некорректный вес",
            "changes": [
                {
                    "kind": "exercise_load",
                    "exercise": "Жим лёжа",
                    "weight_delta": D("NaN"),
                    "weight_unit": "kg",
                }
            ],
        },
        {
            "summary": "Бесконечный вес",
            "changes": [
                {
                    "kind": "exercise_load",
                    "exercise": "Жим лёжа",
                    "weight_delta": D("Infinity"),
                    "weight_unit": "kg",
                }
            ],
        },
        {
            "summary": "Лишнее поле",
            "changes": [{"kind": "schedule", "weekday": 6}],
            "raw_provider_payload": {"unsafe": True},
        },
        {
            "summary": "Слишком много изменений",
            "changes": [{"kind": "schedule", "weekday": 6}] * 21,
        },
    ],
)
def test_adaptation_candidate_is_bounded_and_domain_validated(
    api,
    candidate: dict,
) -> None:
    _client, factory = api
    with factory() as db:
        user = User(external_id="invalid-candidate-owner")
        db.add(user)
        db.flush()
        goal = Goal(user_id=user.id, title="Сила", outcome_type="consistency")
        db.add(goal)
        db.flush()
        program = Program(
            user_id=user.id,
            goal_id=goal.id,
            name="Current program",
            status="active",
            minimum_minutes_week=60,
            comfortable_minutes_week=120,
            maximum_minutes_week=180,
            adaptation_rules={},
        )
        db.add(program)
        db.commit()

        with pytest.raises(ActivityConflict, match="invalid_adaptation_candidate"):
            propose_program_adaptation(
                db,
                user=user,
                program_id=program.id,
                request=ProgramAdaptationRequest(
                    request_id="invalid-adaptation-candidate",
                    prompt="Предложи безопасную корректировку программы",
                ),
                candidate_builder=lambda _prompt, _program: candidate,
            )

        assert db.scalar(select(func.count(MessageReceipt.id))) == 0


@pytest.mark.parametrize(
    "change",
    [
        {"kind": "schedule", "weekday": True},
        {"kind": "schedule", "weekday": "6"},
        {"kind": "session_duration", "minutes": True},
        {"kind": "session_duration", "minutes": "45"},
        {"kind": "weekly_frequency", "sessions_per_week": True},
        {"kind": "weekly_frequency", "sessions_per_week": "3"},
        {
            "kind": "exercise_load",
            "exercise": "Жим лёжа",
            "weight_delta": True,
            "weight_unit": "kg",
        },
        {
            "kind": "exercise_load",
            "exercise": "Жим лёжа",
            "weight_delta": "2.5",
            "weight_unit": "kg",
        },
        {
            "kind": "exercise_load",
            "exercise": "Жим лёжа",
            "weight_delta": 2.5,
            "weight_unit": "kg",
        },
        {
            "kind": "exercise_volume",
            "exercise": "Жим лёжа",
            "sets_delta": True,
        },
        {
            "kind": "exercise_volume",
            "exercise": "Жим лёжа",
            "sets_delta": "1",
        },
        {
            "kind": "exercise_volume",
            "exercise": "Жим лёжа",
            "reps_delta": True,
        },
        {
            "kind": "exercise_volume",
            "exercise": "Жим лёжа",
            "reps_delta": "2",
        },
        {"kind": "recovery_gap", "minutes": True},
        {"kind": "recovery_gap", "minutes": "120"},
    ],
    ids=[
        "schedule-bool",
        "schedule-string",
        "duration-bool",
        "duration-string",
        "frequency-bool",
        "frequency-string",
        "load-bool",
        "load-string",
        "load-float",
        "sets-bool",
        "sets-string",
        "reps-bool",
        "reps-string",
        "recovery-bool",
        "recovery-string",
    ],
)
def test_adaptation_provider_output_rejects_coerced_numeric_fields(
    api,
    change: dict,
) -> None:
    _client, factory = api
    with factory() as db:
        user = User(external_id="coerced-candidate-owner")
        db.add(user)
        db.flush()
        goal = Goal(user_id=user.id, title="Сила", outcome_type="consistency")
        db.add(goal)
        db.flush()
        program = Program(
            user_id=user.id,
            goal_id=goal.id,
            name="Current program",
            status="active",
            minimum_minutes_week=60,
            comfortable_minutes_week=120,
            maximum_minutes_week=180,
            adaptation_rules={},
        )
        db.add(program)
        db.commit()

        with pytest.raises(ActivityConflict, match="invalid_adaptation_candidate"):
            propose_program_adaptation(
                db,
                user=user,
                program_id=program.id,
                request=ProgramAdaptationRequest(
                    request_id="coerced-adaptation-candidate",
                    prompt="Предложи безопасную корректировку программы",
                ),
                candidate_builder=lambda _prompt, _program: {
                    "summary": "Корректировка",
                    "changes": [change],
                },
            )

        assert db.scalar(select(func.count(MessageReceipt.id))) == 0


def test_adaptation_route_is_typed_unavailable_without_a_real_provider(api) -> None:
    client, factory = api
    signed_in = _sign_in(
        client,
        "valid-identity-token-adaptation-unavailable",
        device_id="adaptation-unavailable-iphone",
    )
    with factory() as db:
        user = _user(db, signed_in)
        goal = Goal(
            user_id=user.id,
            title="Сила",
            category="health",
            outcome_type="consistency",
        )
        db.add(goal)
        db.flush()
        program = Program(
            user_id=user.id,
            goal_id=goal.id,
            name="Current program",
            status="active",
            minimum_minutes_week=60,
            comfortable_minutes_week=120,
            maximum_minutes_week=180,
            adaptation_rules={"load": "stable"},
        )
        db.add(program)
        db.commit()
        program_id = program.id

    payload = {
        "request_id": "adaptation-provider-missing",
        "prompt": "Перенеси спокойную тренировку на субботу",
    }
    response = client.post(
        f"/api/v2/activities/programs/{program_id}/adaptation-candidate",
        json=payload,
        headers=_bearer(signed_in["access_token"]),
    )

    assert response.status_code == 503
    assert response.json() == {
        "status": "unavailable",
        "reason": "adaptation_provider_unavailable",
        "retryable": True,
        "safe_message": "Корректировка программы временно недоступна. Попробуйте позже.",
    }
    with factory() as db:
        assert db.scalar(select(func.count(MessageReceipt.id))) == 0

    assert get_adaptation_candidate_builder is not None

    def timeout_provider(_prompt, _program):
        raise TimeoutError("provider timeout")

    client.app.dependency_overrides[get_adaptation_candidate_builder] = lambda: (
        timeout_provider
    )
    timed_out = client.post(
        f"/api/v2/activities/programs/{program_id}/adaptation-candidate",
        json=payload,
        headers=_bearer(signed_in["access_token"]),
    )

    assert timed_out.status_code == 503
    assert timed_out.json()["retryable"] is True
    with factory() as db:
        assert db.scalar(select(func.count(MessageReceipt.id))) == 0

    def failed_provider(_prompt, _program):
        raise RuntimeError("provider failure")

    client.app.dependency_overrides[get_adaptation_candidate_builder] = lambda: (
        failed_provider
    )
    failed = client.post(
        f"/api/v2/activities/programs/{program_id}/adaptation-candidate",
        json=payload,
        headers=_bearer(signed_in["access_token"]),
    )

    assert failed.status_code == 503
    assert failed.json()["retryable"] is True
    with factory() as db:
        assert db.scalar(select(func.count(MessageReceipt.id))) == 0

    client.app.dependency_overrides[get_adaptation_candidate_builder] = lambda: (
        lambda _prompt, _program: {
            "summary": "Перенести сессию на субботу",
            "changes": [{"kind": "schedule", "weekday": 6}],
        }
    )
    recovered = client.post(
        f"/api/v2/activities/programs/{program_id}/adaptation-candidate",
        json=payload,
        headers=_bearer(signed_in["access_token"]),
    )

    assert recovered.status_code == 200
    assert recovered.json()["status"] == "confirmation_required"
    with factory() as db:
        assert db.scalar(select(func.count(MessageReceipt.id))) == 1
