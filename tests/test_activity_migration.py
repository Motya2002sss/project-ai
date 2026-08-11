import importlib
import importlib.util
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import CheckConstraint, String, UniqueConstraint, create_engine, event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models.goal import Goal
from app.models.program import Program
from app.models.task import Task
from app.models.user import User


ACTIVITY_MODULE_AVAILABLE = importlib.util.find_spec("app.models.activity") is not None

if ACTIVITY_MODULE_AVAILABLE:
    from app.models.activity import (
        LearningResource,
        LearningSession,
        NutritionLog,
        WorkoutExercise,
        WorkoutSet,
    )
else:
    LearningResource = None
    LearningSession = None
    NutritionLog = None
    WorkoutExercise = None
    WorkoutSet = None


def _models():
    assert ACTIVITY_MODULE_AVAILABLE, "activity models are not implemented"
    return (
        WorkoutExercise,
        WorkoutSet,
        NutritionLog,
        LearningResource,
        LearningSession,
    )


def _column_names(model) -> set[str]:
    return {column.name for column in model.__table__.columns}


def _foreign_key(model, column_name: str) -> tuple[str, str | None]:
    foreign_key = next(iter(model.__table__.c[column_name].foreign_keys))
    return foreign_key.target_fullname, foreign_key.ondelete


def _unique_column_sets(model) -> set[tuple[str, ...]]:
    return {
        tuple(column.name for column in constraint.columns)
        for constraint in model.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }


def _index_column_sets(model) -> set[tuple[str, ...]]:
    return {
        tuple(column.name for column in index.columns)
        for index in model.__table__.indexes
    }


@pytest.fixture
def db() -> Session:
    if not ACTIVITY_MODULE_AVAILABLE:
        pytest.skip("activity models are not implemented")
    engine = create_engine("sqlite+pysqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _workout_parents(db: Session, *, suffix: str = "") -> tuple[User, Goal, Task, Program]:
    user = User(external_id=f"activity-owner{suffix}")
    db.add(user)
    db.flush()
    goal = Goal(
        user_id=user.id,
        title="Стать сильнее",
        category="health",
    )
    db.add(goal)
    db.flush()
    program = Program(
        user_id=user.id,
        goal_id=goal.id,
        name="Силовая база",
        minimum_minutes_week=60,
        comfortable_minutes_week=120,
        maximum_minutes_week=180,
    )
    task = Task(
        user_id=user.id,
        goal_id=goal.id,
        title="Тренировка на силу",
        target_date=date(2026, 8, 11),
        estimated_minutes=60,
    )
    db.add_all([program, task])
    db.flush()
    return user, goal, task, program


def test_workout_sets_keep_planned_and_actual_facts_separate() -> None:
    _, workout_set, _, _, _ = _models()

    assert {
        "planned_weight",
        "planned_reps",
        "planned_rpe",
        "actual_weight",
        "actual_reps",
        "actual_rpe",
        "completion_status",
    }.issubset(_column_names(workout_set))
    assert workout_set.__table__.c.actual_weight.nullable is True
    assert workout_set.__table__.c.actual_reps.nullable is True
    assert workout_set.__table__.c.actual_rpe.nullable is True


def test_set_position_is_unique_and_partial_workout_is_valid(db: Session) -> None:
    workout_exercise, workout_set, _, _, _ = _models()
    user, goal, task, program = _workout_parents(db)
    exercise = workout_exercise(
        user_id=user.id,
        goal_id=goal.id,
        task_id=task.id,
        program_id=program.id,
        name="Жим лёжа",
        position=1,
    )
    db.add(exercise)
    db.flush()
    db.add_all(
        [
            workout_set(
                user_id=user.id,
                workout_exercise_id=exercise.id,
                position=1,
                planned_weight=Decimal("80.00"),
                planned_reps=6,
                actual_weight=Decimal("80.00"),
                actual_reps=6,
                completion_status="completed",
            ),
            workout_set(
                user_id=user.id,
                workout_exercise_id=exercise.id,
                position=2,
                planned_weight=Decimal("80.00"),
                planned_reps=6,
                actual_weight=Decimal("80.00"),
                actual_reps=5,
                completion_status="completed",
            ),
            workout_set(
                user_id=user.id,
                workout_exercise_id=exercise.id,
                position=3,
                planned_weight=Decimal("80.00"),
                planned_reps=6,
                completion_status="planned",
            ),
        ]
    )
    db.commit()

    saved_sets = list(
        db.scalars(
            select(workout_set)
            .where(workout_set.workout_exercise_id == exercise.id)
            .order_by(workout_set.position)
        )
    )
    assert [row.actual_reps for row in saved_sets] == [6, 5, None]
    assert [row.completion_status for row in saved_sets] == [
        "completed",
        "completed",
        "planned",
    ]
    assert ("workout_exercise_id", "position") in _unique_column_sets(workout_set)

    db.add(
        workout_set(
            user_id=user.id,
            workout_exercise_id=exercise.id,
            position=3,
            planned_reps=6,
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()


def test_nutrition_log_accepts_text_without_invented_macros(db: Session) -> None:
    _, _, nutrition_log, _, _ = _models()
    user = User(external_id="nutrition-owner")
    db.add(user)
    db.flush()
    log = nutrition_log(
        user_id=user.id,
        request_id="nutrition-text-only",
        occurred_at=datetime(2026, 8, 11, 12, 30, tzinfo=timezone.utc),
        meal_note="Обед в кафе, состав не считал",
        adherence="not_recorded",
    )
    db.add(log)
    db.commit()

    assert {
        "calories",
        "protein_grams",
        "fat_grams",
        "carbohydrate_grams",
        "target_calories",
        "target_protein_grams",
        "target_fat_grams",
        "target_carbohydrate_grams",
        "weight_observation",
    }.issubset(_column_names(nutrition_log))
    assert log.calories is None
    assert log.protein_grams is None
    assert log.fat_grams is None
    assert log.carbohydrate_grams is None
    assert log.target_calories is None
    assert log.target_protein_grams is None
    assert log.target_fat_grams is None
    assert log.target_carbohydrate_grams is None


def test_learning_records_pages_minutes_exercises_projects_and_evidence_links(
    db: Session,
) -> None:
    _, _, _, learning_resource, learning_session = _models()
    user = User(external_id="learning-owner")
    db.add(user)
    db.flush()
    goal = Goal(user_id=user.id, title="Освоить архитектуру", category="learning")
    db.add(goal)
    db.flush()
    resource = learning_resource(
        user_id=user.id,
        goal_id=goal.id,
        title="Designing Data-Intensive Applications",
        resource_type="book",
        competency="Архитектура данных",
        total_pages=616,
        total_exercises=12,
        total_projects=1,
    )
    db.add(resource)
    db.flush()
    session = learning_session(
        user_id=user.id,
        goal_id=goal.id,
        learning_resource_id=resource.id,
        request_id="learning-session-1",
        occurred_at=datetime(2026, 8, 11, 18, 0, tzinfo=timezone.utc),
        competency="Архитектура данных",
        pages_completed=24,
        minutes_spent=45,
        exercises_completed=2,
        projects_completed=1,
    )
    db.add(session)
    db.commit()

    assert session.pages_completed == 24
    assert session.minutes_spent == 45
    assert session.exercises_completed == 2
    assert session.projects_completed == 1
    assert _foreign_key(learning_session, "evidence_id") == (
        "evidence.id",
        "SET NULL",
    )
    assert _foreign_key(learning_session, "milestone_id") == (
        "goal_milestones.id",
        "SET NULL",
    )
    assert _foreign_key(learning_session, "learning_resource_id") == (
        "learning_resources.id",
        "SET NULL",
    )


def test_deleting_learning_resource_preserves_session_facts(db: Session) -> None:
    _, _, _, learning_resource, learning_session = _models()
    user = User(external_id="learning-resource-delete")
    db.add(user)
    db.flush()
    resource = learning_resource(
        user_id=user.id,
        title="Курс",
        resource_type="course",
    )
    db.add(resource)
    db.flush()
    session = learning_session(
        user_id=user.id,
        learning_resource_id=resource.id,
        request_id="preserved-learning-session",
        occurred_at=datetime(2026, 8, 11, 18, 0, tzinfo=timezone.utc),
        minutes_spent=30,
    )
    db.add(session)
    db.commit()
    session_id = session.id

    db.delete(resource)
    db.commit()

    saved = db.get(learning_session, session_id)
    assert saved is not None
    assert saved.learning_resource_id is None
    assert saved.minutes_spent == 30


def test_activity_rows_are_directly_owned_and_indexed() -> None:
    for model in _models():
        assert _foreign_key(model, "user_id") == ("users.id", "CASCADE")
        assert any(
            columns and columns[0] == "user_id"
            for columns in _index_column_sets(model)
        ), model.__name__
        assert any(
            isinstance(constraint, CheckConstraint)
            for constraint in model.__table__.constraints
        ), model.__name__

    workout_exercise, workout_set, nutrition_log, learning_resource, learning_session = (
        _models()
    )
    assert _foreign_key(workout_exercise, "task_id") == ("tasks.id", "CASCADE")
    assert _foreign_key(workout_exercise, "program_id") == (
        "programs.id",
        "SET NULL",
    )
    assert _foreign_key(workout_set, "workout_exercise_id") == (
        "workout_exercises.id",
        "CASCADE",
    )
    for model in (nutrition_log, learning_session):
        assert _foreign_key(model, "task_id") == ("tasks.id", "SET NULL")
        assert _foreign_key(model, "program_id") == ("programs.id", "SET NULL")
        assert _foreign_key(model, "goal_id") == ("goals.id", "SET NULL")
    assert _foreign_key(learning_resource, "program_id") == (
        "programs.id",
        "SET NULL",
    )


def test_sensitive_activity_notes_are_bounded_strings() -> None:
    workout_exercise, workout_set, nutrition_log, learning_resource, learning_session = (
        _models()
    )
    sensitive_columns = (
        (workout_exercise, "note"),
        (workout_set, "note"),
        (nutrition_log, "meal_note"),
        (learning_resource, "note"),
        (learning_session, "note"),
    )

    for model, column_name in sensitive_columns:
        column_type = model.__table__.c[column_name].type
        assert isinstance(column_type, String)
        assert column_type.length is not None
        assert column_type.length <= 2000


def test_account_deletion_cascades_every_activity_record(db: Session) -> None:
    workout_exercise, workout_set, nutrition_log, learning_resource, learning_session = (
        _models()
    )
    user, goal, task, program = _workout_parents(db, suffix="-cascade")
    exercise = workout_exercise(
        user_id=user.id,
        goal_id=goal.id,
        task_id=task.id,
        program_id=program.id,
        name="Присед",
        position=1,
    )
    db.add(exercise)
    db.flush()
    workout_fact = workout_set(
        user_id=user.id,
        workout_exercise_id=exercise.id,
        position=1,
        planned_reps=5,
    )
    nutrition_fact = nutrition_log(
        user_id=user.id,
        goal_id=goal.id,
        task_id=task.id,
        program_id=program.id,
        request_id="cascade-nutrition",
        occurred_at=datetime(2026, 8, 11, 13, 0, tzinfo=timezone.utc),
        meal_note="Обед",
    )
    resource = learning_resource(
        user_id=user.id,
        goal_id=goal.id,
        program_id=program.id,
        title="Курс",
        resource_type="course",
    )
    db.add_all([workout_fact, nutrition_fact, resource])
    db.flush()
    learning_fact = learning_session(
        user_id=user.id,
        goal_id=goal.id,
        task_id=task.id,
        program_id=program.id,
        learning_resource_id=resource.id,
        request_id="cascade-learning",
        occurred_at=datetime(2026, 8, 11, 19, 0, tzinfo=timezone.utc),
        minutes_spent=30,
    )
    db.add(learning_fact)
    db.commit()

    db.delete(user)
    db.commit()

    for model in _models():
        assert db.scalar(select(model)) is None, model.__name__


def test_activity_constraints_reject_negative_facts(db: Session) -> None:
    workout_exercise, workout_set, _, _, _ = _models()
    user, goal, task, program = _workout_parents(db, suffix="-negative")
    exercise = workout_exercise(
        user_id=user.id,
        goal_id=goal.id,
        task_id=task.id,
        program_id=program.id,
        name="Тяга",
        position=1,
    )
    db.add(exercise)
    db.flush()
    db.add(
        workout_set(
            user_id=user.id,
            workout_exercise_id=exercise.id,
            position=1,
            actual_reps=-1,
            completion_status="completed",
        )
    )

    with pytest.raises(IntegrityError):
        db.commit()


def test_activity_metadata_creates_on_sqlite(tmp_path: Path) -> None:
    _models()
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'activity.db'}")

    Base.metadata.create_all(engine)

    assert set(Base.metadata.tables) >= {
        "workout_exercises",
        "workout_sets",
        "nutrition_logs",
        "learning_resources",
        "learning_sessions",
    }


def test_activity_migration_follows_current_schema_head() -> None:
    assert (
        importlib.util.find_spec(
            "migrations.versions.d4c3f2b5a644_activity_evidence"
        )
        is not None
    ), "activity migration is not implemented"
    migration = importlib.import_module(
        "migrations.versions.d4c3f2b5a644_activity_evidence"
    )

    assert migration.revision == "d4c3f2b5a644"
    assert migration.down_revision == "c3d2e1f4a5b6"


def test_learning_history_fk_has_follow_up_migration_for_existing_databases(
    monkeypatch,
) -> None:
    module_name = "migrations.versions.f6e5d4c3b722_preserve_learning_history"
    assert importlib.util.find_spec(module_name) is not None
    migration = importlib.import_module(module_name)
    calls: list[tuple[str, tuple, dict]] = []

    monkeypatch.setattr(
        migration.op,
        "drop_constraint",
        lambda *args, **kwargs: calls.append(("drop", args, kwargs)),
    )
    monkeypatch.setattr(
        migration.op,
        "create_foreign_key",
        lambda *args, **kwargs: calls.append(("create", args, kwargs)),
    )
    monkeypatch.setattr(
        migration.op,
        "create_unique_constraint",
        lambda *args, **kwargs: calls.append(("create_unique", args, kwargs)),
    )

    migration.upgrade()

    assert migration.down_revision == "e5d4c3b2a611"
    foreign_key_create = next(call for call in calls if call[0] == "create")
    assert foreign_key_create == (
        "create",
        (
            "fk_learning_sessions_learning_resource_id",
            "learning_sessions",
            "learning_resources",
            ["learning_resource_id"],
            ["id"],
        ),
        {"ondelete": "SET NULL"},
    )
