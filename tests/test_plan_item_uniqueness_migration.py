import importlib
import importlib.util
from datetime import date
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.models.day_plan import DayPlan
from app.models.plan_item import PlanItem
from app.models.task import Task
from app.models.user import User


MIGRATION_MODULE = (
    "migrations.versions.a7f6e5d4c833_unique_plan_task_placement"
)
CONSTRAINT_NAME = "uq_plan_items_day_plan_task"


def _migration():
    assert importlib.util.find_spec(MIGRATION_MODULE) is not None, (
        "plan item uniqueness migration is missing"
    )
    return importlib.import_module(MIGRATION_MODULE)


def _legacy_plan_items(connection) -> sa.Table:
    metadata = sa.MetaData()
    table = sa.Table(
        "plan_items",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("day_plan_id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(255), nullable=False),
    )
    metadata.create_all(connection)
    return table


def _run_migration(connection, migration, monkeypatch, operation: str) -> None:
    context = MigrationContext.configure(connection)
    monkeypatch.setattr(migration, "op", Operations(context))
    getattr(migration, operation)()


def _unique_constraint_names(connection) -> set[str]:
    return {
        item["name"]
        for item in inspect(connection).get_unique_constraints("plan_items")
    }


def test_plan_item_uniqueness_migration_is_single_head_after_f6() -> None:
    migration = _migration()

    assert migration.revision == "a7f6e5d4c833"
    assert migration.down_revision == "f6e5d4c3b722"


def test_plan_item_uniqueness_migration_upgrades_and_downgrades_clean_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _migration()
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'migration.db'}")

    with engine.begin() as connection:
        table = _legacy_plan_items(connection)
        connection.execute(
            table.insert(),
            [
                {
                    "id": 1,
                    "day_plan_id": 10,
                    "task_id": 20,
                    "title": "Первая задача",
                },
                {
                    "id": 2,
                    "day_plan_id": 10,
                    "task_id": None,
                    "title": "Якорь без задачи",
                },
                {
                    "id": 3,
                    "day_plan_id": 10,
                    "task_id": None,
                    "title": "Ещё один якорь",
                },
            ],
        )

        _run_migration(connection, migration, monkeypatch, "upgrade")

        assert CONSTRAINT_NAME in _unique_constraint_names(connection)
        assert connection.scalar(select(sa.func.count()).select_from(table)) == 3

        _run_migration(connection, migration, monkeypatch, "downgrade")

        assert CONSTRAINT_NAME not in _unique_constraint_names(connection)
        assert connection.scalar(select(sa.func.count()).select_from(table)) == 3


def test_plan_item_uniqueness_migration_refuses_legacy_duplicates_without_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _migration()
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'duplicates.db'}")

    with engine.begin() as connection:
        table = _legacy_plan_items(connection)
        connection.execute(
            table.insert(),
            [
                {"id": 1, "day_plan_id": 7, "task_id": 9, "title": "A"},
                {"id": 2, "day_plan_id": 7, "task_id": 9, "title": "B"},
                {"id": 3, "day_plan_id": 3, "task_id": 5, "title": "C"},
                {"id": 4, "day_plan_id": 3, "task_id": 5, "title": "D"},
            ],
        )

        with pytest.raises(RuntimeError) as refusal:
            _run_migration(connection, migration, monkeypatch, "upgrade")

        message = str(refusal.value)
        assert "No rows were changed" in message
        assert "day_plan_id=3, task_id=5, count=2" in message
        assert "day_plan_id=7, task_id=9, count=2" in message
        assert message.index("day_plan_id=3") < message.index("day_plan_id=7")
        assert "resolve" in message.lower()
        assert CONSTRAINT_NAME not in _unique_constraint_names(connection)
        assert connection.scalar(select(sa.func.count()).select_from(table)) == 4


def test_plan_item_task_identity_is_unique_across_independent_sessions(
    tmp_path: Path,
) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'constraint.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    with factory() as setup:
        user = User(external_id="plan-item-db-race", timezone="UTC")
        setup.add(user)
        setup.flush()
        plan_date = date(2026, 8, 11)
        task = Task(
            user_id=user.id,
            title="Одна задача",
            target_date=plan_date,
            status="planned",
        )
        setup.add(task)
        setup.flush()
        plan = DayPlan(user_id=user.id, date=plan_date, version=0)
        setup.add(plan)
        setup.commit()
        plan_id = plan.id
        task_id = task.id

    first = Session(engine)
    second = Session(engine)
    try:
        first.add(
            PlanItem(
                day_plan_id=plan_id,
                task_id=task_id,
                title="Первая запись",
                item_type="task",
                status="planned",
            )
        )
        second.add(
            PlanItem(
                day_plan_id=plan_id,
                task_id=task_id,
                title="Конкурирующая запись",
                item_type="task",
                status="planned",
            )
        )

        first.commit()
        with pytest.raises(IntegrityError):
            second.commit()
        second.rollback()
    finally:
        first.close()
        second.close()

    with factory() as verification:
        saved = verification.scalars(
            select(PlanItem).where(
                PlanItem.day_plan_id == plan_id,
                PlanItem.task_id == task_id,
            )
        ).all()
        assert len(saved) == 1
