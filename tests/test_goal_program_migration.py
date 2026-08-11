from pathlib import Path

from sqlalchemy import UniqueConstraint, create_engine

from app.db.base import Base
from app.models.evidence import Evidence, GoalProgressSnapshot, MetricObservation
from app.models.goal import Goal
from app.models.program import (
    GoalMilestone,
    Program,
    ProgramPhase,
    WeeklyCommitment,
)
from app.models.task import Task


def column_names(model) -> set[str]:
    return {column.name for column in model.__table__.columns}


def foreign_key_target(model, column_name: str) -> tuple[str, str | None]:
    column = model.__table__.c[column_name]
    foreign_key = next(iter(column.foreign_keys))
    return foreign_key.target_fullname, foreign_key.ondelete


def unique_column_sets(model) -> set[tuple[str, ...]]:
    return {
        tuple(column.name for column in constraint.columns)
        for constraint in model.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }


def index_column_sets(model) -> set[tuple[str, ...]]:
    return {
        tuple(column.name for column in index.columns)
        for index in model.__table__.indexes
    }


def test_goal_has_outcome_strategy_and_optimistic_version_fields() -> None:
    assert {
        "public_id",
        "life_area",
        "outcome_type",
        "baseline_value",
        "current_value",
        "target_value",
        "metric_unit",
        "deadline",
        "intensity",
        "allocation_minutes_week",
        "version",
        "updated_at",
    }.issubset(column_names(Goal))
    assert Goal.__table__.c.public_id.unique is True
    assert Goal.__table__.c.public_id.nullable is False


def test_program_aggregate_is_owned_and_ordered() -> None:
    for model in (GoalMilestone, Program, ProgramPhase, WeeklyCommitment):
        assert "user_id" in column_names(model)
        assert foreign_key_target(model, "user_id") == ("users.id", "CASCADE")

    assert foreign_key_target(GoalMilestone, "goal_id") == (
        "goals.id",
        "CASCADE",
    )
    assert ("goal_id", "position") in unique_column_sets(GoalMilestone)
    assert ("program_id", "position") in unique_column_sets(ProgramPhase)
    assert {
        "minimum_minutes_week",
        "comfortable_minutes_week",
        "maximum_minutes_week",
        "adaptation_rules",
    }.issubset(column_names(Program))
    assert {
        "target_minutes_week",
        "target_sessions_week",
        "minimum_block_minutes",
        "allowed_weekdays",
        "preferred_window",
        "splittable",
        "recovery_gap_minutes",
    }.issubset(column_names(WeeklyCommitment))


def test_evidence_and_observations_are_fact_records_with_time_indexes() -> None:
    for model in (Evidence, MetricObservation):
        assert foreign_key_target(model, "user_id") == ("users.id", "CASCADE")
        assert foreign_key_target(model, "goal_id") == ("goals.id", "CASCADE")
        assert ("user_id", "occurred_at") in index_column_sets(model)
        assert "updated_at" not in column_names(model)

    assert {
        "evidence_type",
        "quantity",
        "unit",
        "occurred_at",
        "note",
        "attributes",
    }.issubset(column_names(Evidence))
    assert {"value", "unit", "occurred_at", "source"}.issubset(
        column_names(MetricObservation)
    )


def test_progress_snapshots_are_immutable_explainable_payloads() -> None:
    assert foreign_key_target(GoalProgressSnapshot, "user_id") == (
        "users.id",
        "CASCADE",
    )
    assert foreign_key_target(GoalProgressSnapshot, "goal_id") == (
        "goals.id",
        "CASCADE",
    )
    assert {
        "as_of",
        "strategy",
        "percentage",
        "components",
        "reason",
        "formula_version",
        "forecast_date",
        "confidence",
        "created_at",
    }.issubset(column_names(GoalProgressSnapshot))
    assert "updated_at" not in column_names(GoalProgressSnapshot)


def test_task_links_to_program_and_commitment_but_has_no_progress_percentage() -> None:
    assert foreign_key_target(Task, "program_id") == ("programs.id", "SET NULL")
    assert foreign_key_target(Task, "commitment_id") == (
        "weekly_commitments.id",
        "SET NULL",
    )
    forbidden = {"progress", "progress_percentage", "outcome_percentage"}
    assert forbidden.isdisjoint(column_names(Task))


def test_goal_program_metadata_creates_on_sqlite(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'goal-program.db'}")

    Base.metadata.create_all(engine)

    assert set(Base.metadata.tables) >= {
        "goal_milestones",
        "programs",
        "program_phases",
        "weekly_commitments",
        "evidence",
        "metric_observations",
        "goal_progress_snapshots",
    }
