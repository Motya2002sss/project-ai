from datetime import time
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.models.goal import Goal
from app.models.onboarding import OnboardingPreview, ResourceBudget
from app.models.user import User
from app.schemas.onboarding import ResourceBudgetInput
from app.services.onboarding_service import (
    OnboardingConflict,
    apply_onboarding_preview,
    preview_onboarding,
)


@pytest.fixture
def db(tmp_path: Path) -> Session:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'onboarding.db'}")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        yield session


def budget(**overrides) -> ResourceBudgetInput:
    values = {
        "weekly_available_minutes": 600,
        "available_days": [1, 2, 3, 4, 5],
        "minimum_minutes": 180,
        "comfortable_minutes": 360,
        "maximum_minutes": 480,
        "free_evenings": [2, 4],
        "conflict_priority": "сон и работа",
    }
    values.update(overrides)
    return ResourceBudgetInput(**values)


def test_preview_extracts_routine_and_caps_active_goal_candidates(db: Session) -> None:
    user = User(external_id="onboarding-preview", timezone="Europe/Moscow")
    db.add(user)
    db.commit()

    preview = preview_onboarding(
        db,
        user=user,
        narrative=(
            "Работаю по будням с 9:00 до 18:00, ложусь спать в 23:30. "
            "Хочу стать senior-разработчиком, набрать вес до 78 кг, "
            "сесть на шпагат и прочитать 24 книги."
        ),
        resource_budget=budget(),
        request_id="preview-1",
    )

    assert preview.status == "ready"
    assert preview.structured_summary["work_start"] == "09:00"
    assert preview.structured_summary["work_end"] == "18:00"
    assert preview.structured_summary["sleep_time"] == "23:30"
    assert preview.structured_summary["available_days"] == [1, 2, 3, 4, 5]
    assert preview.goal_candidates == [
        "Стать senior-разработчиком",
        "Набрать вес до 78 кг",
        "Сесть на шпагат",
    ]
    assert preview.allocation["reserved_minutes"] == 120
    assert preview.allocation["allocatable_minutes"] == 480
    assert sum(item["minutes"] for item in preview.allocation["goals"]) <= 480


def test_preview_returns_one_clarification_when_no_goal_is_known(db: Session) -> None:
    user = User(external_id="onboarding-clarification")
    db.add(user)
    db.commit()

    preview = preview_onboarding(
        db,
        user=user,
        narrative="Работаю с 10 до 19 и обычно свободен вечером.",
        resource_budget=budget(),
        request_id="clarification-1",
    )

    assert preview.status == "clarification_required"
    assert preview.clarification == {
        "id": "primary_goals",
        "question": "Какие результаты вы хотите получить в первую очередь?",
        "allows_free_text": True,
    }
    assert isinstance(preview.clarification, dict)


def test_correction_increments_version_and_stale_apply_is_rejected(db: Session) -> None:
    user = User(external_id="onboarding-correction")
    db.add(user)
    db.commit()
    original = preview_onboarding(
        db,
        user=user,
        narrative="Хочу выучить английский.",
        resource_budget=budget(),
        request_id="correction-1",
    )
    original_version = original.version

    corrected = preview_onboarding(
        db,
        user=user,
        narrative="Хочу подготовиться к IELTS и регулярно бегать.",
        resource_budget=budget(comfortable_minutes=420),
        request_id="correction-2",
        preview_id=original.id,
        expected_version=original_version,
    )

    assert corrected.id == original.id
    assert corrected.version == original_version + 1
    assert corrected.goal_candidates == [
        "Подготовиться к IELTS",
        "Регулярно бегать",
    ]
    with pytest.raises(OnboardingConflict, match="stale_preview_version"):
        apply_onboarding_preview(
            db,
            user=user,
            preview_id=corrected.id,
            expected_version=original_version,
        )


def test_preview_and_apply_are_idempotent_and_apply_atomically(db: Session) -> None:
    user = User(external_id="onboarding-apply")
    db.add(user)
    db.commit()
    first = preview_onboarding(
        db,
        user=user,
        narrative=(
            "Работаю с 8:30 до 17:30, ложусь в 23:00. "
            "Хочу накопить подушку и стать senior-разработчиком."
        ),
        resource_budget=budget(),
        request_id="idempotent-preview",
    )
    duplicate = preview_onboarding(
        db,
        user=user,
        narrative="Этот текст не должен заменить первый запрос.",
        resource_budget=budget(),
        request_id="idempotent-preview",
    )

    assert duplicate.id == first.id
    assert duplicate.version == first.version

    applied = apply_onboarding_preview(
        db,
        user=user,
        preview_id=first.id,
        expected_version=first.version,
    )
    applied_again = apply_onboarding_preview(
        db,
        user=user,
        preview_id=first.id,
        expected_version=first.version,
    )

    assert applied.status == "applied"
    assert applied_again.status == "applied"
    assert db.query(Goal).filter(Goal.user_id == user.id).count() == 2
    saved_budget = db.query(ResourceBudget).filter_by(user_id=user.id).one()
    assert saved_budget.reserve_percent == 20
    assert saved_budget.allocatable_minutes == 480
    db.refresh(user)
    assert user.work_start_time == time(8, 30)
    assert user.work_end_time == time(17, 30)
    assert user.sleep_time == time(23, 0)
    assert db.query(OnboardingPreview).filter_by(user_id=user.id).count() == 1
    assert applied.narrative is None


def test_apply_keeps_at_most_three_active_goals(db: Session) -> None:
    user = User(external_id="onboarding-goal-cap")
    db.add(user)
    db.flush()
    db.add_all(
        [
            Goal(user_id=user.id, title="Старая цель 1"),
            Goal(user_id=user.id, title="Старая цель 2"),
        ]
    )
    db.commit()
    preview = preview_onboarding(
        db,
        user=user,
        narrative="Хочу бегать, выучить английский и накопить подушку.",
        resource_budget=budget(),
        request_id="goal-cap-preview",
    )

    apply_onboarding_preview(
        db,
        user=user,
        preview_id=preview.id,
        expected_version=preview.version,
    )

    active = db.query(Goal).filter_by(user_id=user.id, status="active").all()
    paused = db.query(Goal).filter_by(user_id=user.id, status="paused").all()
    assert [goal.title for goal in active] == [
        "Бегать",
        "Выучить английский",
        "Накопить подушку",
    ]
    assert {goal.title for goal in paused} == {"Старая цель 1", "Старая цель 2"}


def test_budget_validation_preserves_twenty_percent_reserve() -> None:
    with pytest.raises(ValueError):
        budget(minimum_minutes=500)
    with pytest.raises(ValueError):
        budget(comfortable_minutes=500)
    with pytest.raises(ValueError):
        budget(available_days=[])
