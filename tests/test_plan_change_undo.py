from collections.abc import Generator
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models.calendar import CalendarBusyBlock
from app.models.day_plan import DayPlan
from app.models.evidence import Evidence
from app.models.goal import Goal
from app.models.plan_change import PlanChange
from app.models.plan_item import PlanItem
from app.models.task import Task
from app.models.user import User
from app.services.plan_change_service import (
    PlanChangeConflict,
    TemporaryModeRequest,
    apply_replan,
    undo_plan_change,
)


UTC = timezone.utc
NOW = datetime(2026, 8, 11, 10, 0, tzinfo=UTC)
TODAY = NOW.date()


@pytest.fixture
def db(tmp_path: Path) -> Generator[Session, None, None]:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'undo.db'}")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session


def _scenario(db: Session, suffix: str):
    user = User(external_id=f"undo-{suffix}", timezone="UTC")
    db.add(user)
    db.flush()
    task = Task(
        user_id=user.id,
        title="Гибкая задача",
        target_date=TODAY,
        scheduling_type="flexible",
        estimated_minutes=60,
        status="planned",
    )
    db.add(task)
    db.flush()
    plan = DayPlan(user_id=user.id, date=TODAY, version=3, status="draft")
    db.add(plan)
    db.flush()
    plan.items.append(
        PlanItem(
            task_id=task.id,
            title=task.title,
            item_type="task",
            status="planned",
            start_time=time(14),
            end_time=time(15),
        )
    )
    block = CalendarBusyBlock(
        user_id=user.id,
        device_id="iphone",
        provider="apple",
        calendar_external_id="main",
        external_id=f"event-{suffix}",
        occurrence_external_id=f"occurrence-{suffix}",
        occurrence_start=datetime(2026, 8, 11, 14, 0, tzinfo=UTC),
        occurrence_end=datetime(2026, 8, 11, 15, 0, tzinfo=UTC),
        device_timezone="UTC",
        source_revision="1",
        last_seen_client_revision=1,
    )
    db.add(block)
    db.commit()
    applied = apply_replan(
        db,
        user=user,
        request_id=f"apply-{suffix}",
        base_versions={TODAY: 3},
        affected_dates=[TODAY],
        reason="calendar_sync",
        now=NOW,
    )
    db.refresh(block)
    block.deleted_at = NOW + timedelta(minutes=1)
    db.commit()
    return user, task, plan, block, applied


def _item(db: Session, task_id: int) -> PlanItem:
    return db.scalar(select(PlanItem).where(PlanItem.task_id == task_id))


def test_owner_can_undo_latest_compatible_change_and_exact_retry_is_idempotent(
    db: Session,
) -> None:
    user, task, _plan, _block, applied = _scenario(db, "happy")
    moved_start = _item(db, task.id).start_time
    goal = Goal(user_id=user.id, title="Цель", category="personal", status="active")
    db.add(goal)
    db.flush()
    task.goal_id = goal.id
    evidence = Evidence(
        user_id=user.id,
        goal_id=goal.id,
        task_id=task.id,
        request_id="evidence-before-undo",
        evidence_type="completion_note",
        occurred_at=NOW + timedelta(minutes=1),
        note="Факт остаётся фактом",
        attributes={},
    )
    db.add(evidence)
    db.commit()

    undone = undo_plan_change(
        db,
        user=user,
        change_id=applied.change_id,
        request_id="undo-happy",
        expected_version=applied.result_versions[TODAY.isoformat()],
        now=NOW + timedelta(minutes=2),
    )
    replay = undo_plan_change(
        db,
        user=user,
        change_id=applied.change_id,
        request_id="undo-happy",
        expected_version=applied.result_versions[TODAY.isoformat()],
        now=NOW + timedelta(minutes=2),
    )

    assert moved_start != time(14)
    assert undone == replay
    assert undone.status == "undone"
    assert _item(db, task.id).start_time == time(14)
    change = db.get(PlanChange, applied.change_id)
    assert change.status == "undone"
    assert change.undone_at is not None
    assert db.scalar(select(func.count(PlanChange.id))) == 1
    saved_evidence = db.get(Evidence, evidence.id)
    assert saved_evidence is not None
    assert saved_evidence.note == "Факт остаётся фактом"
    assert saved_evidence.task_id == task.id


def test_undo_rejects_other_owner_expired_already_undone_and_reused_request(
    db: Session,
) -> None:
    owner, _task, _plan, _block, applied = _scenario(db, "guards")
    other = User(external_id="undo-other", timezone="UTC")
    db.add(other)
    db.commit()

    with pytest.raises(PlanChangeConflict) as foreign:
        undo_plan_change(
            db,
            user=other,
            change_id=applied.change_id,
            request_id="foreign-undo",
            expected_version=applied.result_versions[TODAY.isoformat()],
            now=NOW + timedelta(minutes=2),
        )
    assert foreign.value.code == "change_not_found"

    change = db.get(PlanChange, applied.change_id)
    change.expires_at = NOW + timedelta(minutes=1)
    db.commit()
    with pytest.raises(PlanChangeConflict) as expired:
        undo_plan_change(
            db,
            user=owner,
            change_id=applied.change_id,
            request_id="expired-undo",
            expected_version=applied.result_versions[TODAY.isoformat()],
            now=NOW + timedelta(minutes=2),
        )
    assert expired.value.code == "change_expired"

    change.expires_at = NOW + timedelta(minutes=30)
    db.commit()
    undo_plan_change(
        db,
        user=owner,
        change_id=applied.change_id,
        request_id="valid-undo",
        expected_version=applied.result_versions[TODAY.isoformat()],
        now=NOW + timedelta(minutes=2),
    )
    with pytest.raises(PlanChangeConflict) as already:
        undo_plan_change(
            db,
            user=owner,
            change_id=applied.change_id,
            request_id="different-undo",
            expected_version=applied.result_versions[TODAY.isoformat()],
            now=NOW + timedelta(minutes=3),
        )
    assert already.value.code == "change_already_undone"

    with pytest.raises(PlanChangeConflict) as reused:
        undo_plan_change(
            db,
            user=owner,
            change_id=applied.change_id,
            request_id="valid-undo",
            expected_version=999,
            now=NOW + timedelta(minutes=3),
        )
    assert reused.value.code == "idempotency_conflict"


def test_undo_requires_latest_change_and_matching_current_version(db: Session) -> None:
    user, _task, plan, _block, first = _scenario(db, "latest")
    second = apply_replan(
        db,
        user=user,
        request_id="apply-latest-second",
        base_versions={TODAY: first.result_versions[TODAY.isoformat()]},
        affected_dates=[TODAY],
        reason="temporary_mode",
        temporary_mode=TemporaryModeRequest(
            mode="focus_sprint",
            starts_at=NOW,
            ends_at=NOW + timedelta(hours=1),
            constraints={},
        ),
        now=NOW,
    )

    with pytest.raises(PlanChangeConflict) as not_latest:
        undo_plan_change(
            db,
            user=user,
            change_id=first.change_id,
            request_id="undo-old-change",
            expected_version=second.result_versions[TODAY.isoformat()],
            now=NOW + timedelta(minutes=3),
        )
    assert not_latest.value.code == "change_not_latest"

    db.refresh(plan)
    plan.version += 1
    db.commit()
    with pytest.raises(PlanChangeConflict) as intervening:
        undo_plan_change(
            db,
            user=user,
            change_id=second.change_id,
            request_id="undo-stale-current",
            expected_version=second.result_versions[TODAY.isoformat()],
            now=NOW + timedelta(minutes=3),
        )
    assert intervening.value.code == "stale_plan_version"


def test_undo_service_rejects_boolean_expected_version_without_mutation(
    db: Session,
) -> None:
    user, task, _plan, _block, applied = _scenario(db, "strict-bool-version")
    moved_start = _item(db, task.id).start_time

    with pytest.raises(PlanChangeConflict) as invalid:
        undo_plan_change(
            db,
            user=user,
            change_id=applied.change_id,
            request_id="undo-bool-version",
            expected_version=True,
            now=NOW + timedelta(minutes=2),
        )

    assert invalid.value.code == "invalid_expected_version"
    assert _item(db, task.id).start_time == moved_start
    assert db.get(PlanChange, applied.change_id).status == "applied"


def test_latest_change_order_is_causal_when_two_changes_share_a_timestamp(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ids = iter(
        [
            UUID("ffffffff-ffff-4fff-8fff-ffffffffffff"),
            UUID("00000000-0000-4000-8000-000000000001"),
        ]
    )
    monkeypatch.setattr("app.services.plan_change_service.uuid4", lambda: next(ids))
    user, _task, _plan, _block, first = _scenario(db, "same-timestamp")
    second = apply_replan(
        db,
        user=user,
        request_id="same-timestamp-second",
        base_versions={TODAY: first.result_versions[TODAY.isoformat()]},
        affected_dates=[TODAY],
        reason="temporary_mode",
        temporary_mode=TemporaryModeRequest(
            mode="focus_sprint",
            starts_at=NOW,
            ends_at=NOW + timedelta(hours=1),
            constraints={},
        ),
        now=NOW,
    )

    with pytest.raises(PlanChangeConflict) as old:
        undo_plan_change(
            db,
            user=user,
            change_id=first.change_id,
            request_id="same-timestamp-old-undo",
            expected_version=second.result_versions[TODAY.isoformat()],
            now=NOW + timedelta(minutes=1),
        )

    assert old.value.code == "change_not_latest"


def test_undo_never_rewrites_task_completion_or_other_facts(db: Session) -> None:
    user, task, _plan, _block, applied = _scenario(db, "completion")
    task.status = "done"
    db.commit()

    with pytest.raises(PlanChangeConflict) as completion:
        undo_plan_change(
            db,
            user=user,
            change_id=applied.change_id,
            request_id="undo-after-completion",
            expected_version=applied.result_versions[TODAY.isoformat()],
            now=NOW + timedelta(minutes=2),
        )

    assert completion.value.code == "task_fact_changed"
    db.refresh(task)
    assert task.status == "done"
    assert _item(db, task.id).status == "planned"


def test_undo_rejects_changed_scheduling_facts_instead_of_restoring_stale_shape(
    db: Session,
) -> None:
    user, task, _plan, _block, applied = _scenario(db, "task-fact")
    task.estimated_minutes = 30
    db.commit()

    with pytest.raises(PlanChangeConflict) as changed:
        undo_plan_change(
            db,
            user=user,
            change_id=applied.change_id,
            request_id="undo-after-duration-change",
            expected_version=applied.result_versions[TODAY.isoformat()],
            now=NOW + timedelta(minutes=2),
        )

    assert changed.value.code == "task_fact_changed"
    assert _item(db, task.id).start_time != time(14)


def test_undo_rejects_replaced_placement_identity_even_when_times_match(
    db: Session,
) -> None:
    user, task, plan, _block, applied = _scenario(db, "placement-fact")
    current = _item(db, task.id)
    replacement = PlanItem(
        id=current.id + 1000,
        task_id=task.id,
        title=current.title,
        item_type=current.item_type,
        status=current.status,
        start_time=current.start_time,
        end_time=current.end_time,
        unscheduled_reason=current.unscheduled_reason,
    )
    plan.items.remove(current)
    db.flush()
    plan.items.append(replacement)
    db.commit()

    with pytest.raises(PlanChangeConflict) as replaced:
        undo_plan_change(
            db,
            user=user,
            change_id=applied.change_id,
            request_id="undo-after-placement-replacement",
            expected_version=applied.result_versions[TODAY.isoformat()],
            now=NOW + timedelta(minutes=2),
        )

    assert replaced.value.code == "placement_fact_changed"
    assert _item(db, task.id).id == replacement.id


def test_undo_refuses_to_restore_a_placement_into_a_current_busy_block(
    db: Session,
) -> None:
    user, task, _plan, block, applied = _scenario(db, "busy")
    block.deleted_at = None
    db.commit()

    with pytest.raises(PlanChangeConflict) as conflict:
        undo_plan_change(
            db,
            user=user,
            change_id=applied.change_id,
            request_id="undo-into-busy",
            expected_version=applied.result_versions[TODAY.isoformat()],
            now=NOW + timedelta(minutes=2),
        )

    assert conflict.value.code == "restore_interval_conflict"
    assert _item(db, task.id).start_time != time(14)


def test_undo_restores_the_previous_plan_status_with_the_placement(db: Session) -> None:
    user = User(external_id="undo-plan-status", timezone="UTC")
    db.add(user)
    db.flush()
    task = Task(
        user_id=user.id,
        title="Только днём",
        target_date=TODAY,
        scheduling_type="flexible",
        preferred_window="afternoon",
        estimated_minutes=60,
        status="planned",
    )
    db.add(task)
    db.flush()
    plan = DayPlan(user_id=user.id, date=TODAY, version=2, status="draft")
    db.add(plan)
    db.flush()
    plan.items.append(
        PlanItem(
            task_id=task.id,
            title=task.title,
            item_type="task",
            status="planned",
            start_time=time(14),
            end_time=time(15),
        )
    )
    block = CalendarBusyBlock(
        user_id=user.id,
        device_id="iphone",
        provider="apple",
        calendar_external_id="main",
        external_id="event-plan-status",
        occurrence_external_id="occurrence-plan-status",
        occurrence_start=datetime(2026, 8, 11, 12, 0, tzinfo=UTC),
        occurrence_end=datetime(2026, 8, 11, 17, 0, tzinfo=UTC),
        device_timezone="UTC",
        source_revision="1",
        last_seen_client_revision=1,
    )
    db.add(block)
    db.commit()

    applied = apply_replan(
        db,
        user=user,
        request_id="apply-plan-status",
        base_versions={TODAY: 2},
        affected_dates=[TODAY],
        reason="calendar_sync",
        now=NOW,
    )
    db.refresh(plan)
    assert plan.status == "overloaded"
    block.deleted_at = NOW + timedelta(minutes=1)
    db.commit()

    undo_plan_change(
        db,
        user=user,
        change_id=applied.change_id,
        request_id="undo-plan-status",
        expected_version=applied.result_versions[TODAY.isoformat()],
        now=NOW + timedelta(minutes=2),
    )

    db.refresh(plan)
    assert plan.status == "draft"
    assert _item(db, task.id).status == "planned"
    assert _item(db, task.id).start_time == time(14)


def test_no_change_does_not_hide_latest_meaningful_change_from_undo(
    db: Session,
) -> None:
    user, task, _plan, _block, meaningful = _scenario(db, "noop-chain")
    no_change = apply_replan(
        db,
        user=user,
        request_id="noop-after-meaningful",
        base_versions={TODAY: meaningful.result_versions[TODAY.isoformat()]},
        affected_dates=[TODAY],
        reason="manual",
        now=NOW + timedelta(minutes=1),
    )
    replay = apply_replan(
        db,
        user=user,
        request_id="noop-after-meaningful",
        base_versions={TODAY: meaningful.result_versions[TODAY.isoformat()]},
        affected_dates=[TODAY],
        reason="manual",
        now=NOW + timedelta(minutes=1),
    )

    assert no_change == replay
    assert no_change.status == "no_change"
    assert no_change.expires_at is None
    saved_no_change = db.get(PlanChange, no_change.change_id)
    assert saved_no_change.forward_payload["result"]["status"] == "no_change"
    assert saved_no_change.inverse_payload["undoable"] is False

    undone = undo_plan_change(
        db,
        user=user,
        change_id=meaningful.change_id,
        request_id="undo-through-noop",
        expected_version=meaningful.result_versions[TODAY.isoformat()],
        now=NOW + timedelta(minutes=2),
    )

    assert undone.status == "undone"
    assert _item(db, task.id).start_time == time(14)


def test_undo_removes_a_day_plan_that_did_not_exist_before_replan(
    db: Session,
) -> None:
    tomorrow = TODAY + timedelta(days=1)
    user = User(external_id="undo-new-day", timezone="UTC")
    db.add(user)
    db.flush()
    task = Task(
        user_id=user.id,
        title="Завтрашняя задача",
        target_date=tomorrow,
        scheduling_type="flexible",
        estimated_minutes=60,
        status="planned",
    )
    db.add(task)
    db.commit()

    applied = apply_replan(
        db,
        user=user,
        request_id="apply-new-day",
        base_versions={tomorrow: 0},
        affected_dates=[tomorrow],
        reason="manual",
        now=NOW,
    )
    assert applied.result_versions[tomorrow.isoformat()] == 1

    undone = undo_plan_change(
        db,
        user=user,
        change_id=applied.change_id,
        request_id="undo-new-day",
        expected_version=1,
        now=NOW + timedelta(minutes=1),
    )

    assert undone.result_versions == {tomorrow.isoformat(): 0}
    assert undone.snapshots == [
        {
            "date": tomorrow.isoformat(),
            "version": 0,
            "status": "absent",
            "items": [],
        }
    ]
    assert db.scalar(
        select(DayPlan).where(
            DayPlan.user_id == user.id,
            DayPlan.date == tomorrow,
        )
    ) is None
    assert db.scalar(select(func.count(PlanItem.id))) == 0
