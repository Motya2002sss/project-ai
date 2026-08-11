import hashlib
import json
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from threading import RLock
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.models.calendar import CalendarBusyBlock, TemporaryLifeMode
from app.models.day_plan import DayPlan
from app.models.message_receipt import MessageReceipt
from app.models.plan_change import PlanChange
from app.models.plan_item import PlanItem
from app.models.task import Task
from app.models.user import User
from app.services.planning_service import (
    FlexibleCapacityLimit,
    TimeInterval,
    _day_bounds,
    assert_plan_has_no_overlaps,
    build_day_plan_result,
    intervals_overlap,
)
from app.services.time_service import get_user_now, get_user_timezone


SUPPORTED_REPLAN_REASONS = {
    "calendar_sync",
    "temporary_mode",
    "capacity_change",
    "manual",
}
SUPPORTED_TEMPORARY_MODES = {
    "normal",
    "workload",
    "recovery",
    "sick",
    "travel",
    "vacation",
    "low_sleep",
    "focus_sprint",
}
MAX_AFFECTED_DAYS = 14
MAX_PLAN_VERSION = 2_147_483_647
UNDO_WINDOW = timedelta(minutes=15)
RECEIPT_TTL = timedelta(days=30)
_SQLITE_WRITE_LOCKS = tuple(RLock() for _ in range(64))


class PlanChangeConflict(ValueError):
    def __init__(self, code: str, **details: Any) -> None:
        self.code = code
        self.details = details
        super().__init__(code)


@dataclass(frozen=True)
class TemporaryModeRequest:
    mode: str
    starts_at: datetime
    ends_at: datetime
    constraints: dict[str, Any]


@dataclass(frozen=True)
class PlanMutationResult:
    status: str
    request_id: str
    change_id: UUID
    reason: str
    base_versions: dict[str, int]
    result_versions: dict[str, int]
    affected_dates: list[str]
    plan_diff: dict[str, list[dict[str, Any]]]
    snapshots: list[dict[str, Any]]
    expires_at: datetime | None

    def to_payload(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "request_id": self.request_id,
            "change_id": str(self.change_id),
            "reason": self.reason,
            "base_versions": self.base_versions,
            "result_versions": self.result_versions,
            "affected_dates": self.affected_dates,
            "plan_diff": self.plan_diff,
            "snapshots": self.snapshots,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "PlanMutationResult":
        expires_at = payload.get("expires_at")
        return cls(
            status=payload["status"],
            request_id=payload["request_id"],
            change_id=UUID(payload["change_id"]),
            reason=payload["reason"],
            base_versions=dict(payload["base_versions"]),
            result_versions=dict(payload["result_versions"]),
            affected_dates=list(payload["affected_dates"]),
            plan_diff=dict(payload["plan_diff"]),
            snapshots=list(payload["snapshots"]),
            expires_at=datetime.fromisoformat(expires_at) if expires_at else None,
        )


def apply_replan(
    db: Session,
    *,
    user: User,
    request_id: str,
    base_versions: dict[date | str, int],
    affected_dates: list[date],
    reason: str,
    temporary_mode: TemporaryModeRequest | None = None,
    now: datetime | None = None,
) -> PlanMutationResult:
    with _serialized_sqlite_write(db, user_id=user.id):
        return _apply_replan(
            db,
            user=user,
            request_id=request_id,
            base_versions=base_versions,
            affected_dates=affected_dates,
            reason=reason,
            temporary_mode=temporary_mode,
            now=now,
        )


def _apply_replan(
    db: Session,
    *,
    user: User,
    request_id: str,
    base_versions: dict[date | str, int],
    affected_dates: list[date],
    reason: str,
    temporary_mode: TemporaryModeRequest | None = None,
    now: datetime | None = None,
) -> PlanMutationResult:
    operation_now = _require_aware(now or datetime.now(timezone.utc), "now")
    dates = _normalize_dates(
        affected_dates,
        earliest_date=get_user_now(user, operation_now).date(),
    )
    versions = _normalize_base_versions(base_versions, dates=dates)
    _validate_request_id(request_id)
    if reason not in SUPPORTED_REPLAN_REASONS:
        raise PlanChangeConflict("unsupported_replan_reason")
    normalized_mode = _normalize_mode(temporary_mode)
    if (reason == "temporary_mode") != (normalized_mode is not None):
        raise PlanChangeConflict("invalid_temporary_mode_request")
    if normalized_mode is not None:
        mode_dates = _mode_local_dates(normalized_mode, user=user)
        requested_dates = set(dates)
        if not mode_dates.issubset(requested_dates):
            raise PlanChangeConflict(
                "invalid_temporary_mode_dates",
                missing_dates=sorted(
                    item.isoformat() for item in mode_dates - requested_dates
                ),
            )
    fingerprint = _fingerprint(
        {
            "operation": "replan",
            "request_id": request_id,
            "base_versions": versions,
            "affected_dates": [item.isoformat() for item in dates],
            "reason": reason,
            "temporary_mode": _mode_payload(normalized_mode),
        }
    )

    try:
        replay = _replay_apply(
            db,
            user=user,
            request_id=request_id,
            fingerprint=fingerprint,
        )
        if replay is not None:
            return replay
        _lock_user(db, user=user)
        replay = _replay_apply(
            db,
            user=user,
            request_id=request_id,
            fingerprint=fingerprint,
        )
        if replay is not None:
            return replay

        plans = _lock_plans(db, user=user, dates=dates)
        for plan_date in dates:
            current_version = plans[plan_date].version if plan_date in plans else 0
            if versions[plan_date.isoformat()] != current_version:
                raise PlanChangeConflict(
                    "stale_plan_version",
                    date=plan_date.isoformat(),
                    expected=versions[plan_date.isoformat()],
                    current=current_version,
                )
        _assert_unique_task_placements(plans.values())
        originally_absent_dates = [
            plan_date.isoformat() for plan_date in dates if plan_date not in plans
        ]

        mode_row = None
        if normalized_mode is not None:
            existing_mode = db.scalar(
                select(TemporaryLifeMode).where(
                    TemporaryLifeMode.user_id == user.id,
                    TemporaryLifeMode.request_id == request_id,
                )
            )
            if existing_mode is not None:
                raise PlanChangeConflict("idempotency_conflict")
            mode_row = TemporaryLifeMode(
                user_id=user.id,
                request_id=request_id,
                mode=normalized_mode.mode,
                starts_at=_as_utc(normalized_mode.starts_at),
                ends_at=_as_utc(normalized_mode.ends_at),
                status="active",
                constraints=normalized_mode.constraints,
            )
            db.add(mode_row)
            db.flush()

        before_by_date: dict[date, dict[int, dict[str, Any]]] = {}
        before_plan_statuses = {
            plan_date.isoformat(): plan.status
            for plan_date, plan in plans.items()
        }
        for plan_date, plan in plans.items():
            before_by_date[plan_date] = _placement_map(plan)
        task_ids = sorted(
            {
                task_id
                for placements in before_by_date.values()
                for task_id in placements
            }
        )
        tasks = {
            task.id: task
            for task in db.scalars(
                select(Task)
                .where(Task.user_id == user.id, Task.id.in_(task_ids))
                .order_by(Task.id.asc())
                .with_for_update()
            ).all()
        } if task_ids else {}
        built_plans: dict[date, DayPlan] = {}
        for plan_date in dates:
            additional_occupied, capacity_limits = _planning_constraints(
                db,
                user=user,
                plan_date=plan_date,
            )
            existing_plan = plans.get(plan_date)
            if existing_plan is not None:
                _assert_replannable_plan(
                    existing_plan,
                    tasks=tasks,
                    occupied=additional_occupied,
                    now=operation_now,
                    user=user,
                )
            build = build_day_plan_result(
                db,
                user,
                plan_date=plan_date,
                now=operation_now,
                commit=False,
                additional_occupied=additional_occupied,
                immutable_before=operation_now,
                materialize_sources=False,
                flexible_capacity_limits=capacity_limits,
                preserve_item_identity=True,
            )
            if build.conflicts:
                raise PlanChangeConflict(
                    "immutable_interval_conflict",
                    date=plan_date.isoformat(),
                    task_ids=sorted({item.task_id for item in build.conflicts}),
                )
            built_plans[plan_date] = build.day_plan

        after_by_date = {
            plan_date: _placement_map(built_plans[plan_date])
            for plan_date in dates
        }
        result_task_ids = sorted(
            {
                task_id
                for placements in after_by_date.values()
                for task_id in placements
                if task_id not in tasks
            }
        )
        if result_task_ids:
            tasks.update(
                {
                    task.id: task
                    for task in db.scalars(
                        select(Task).where(
                            Task.user_id == user.id,
                            Task.id.in_(result_task_ids),
                        ).order_by(Task.id.asc())
                    ).all()
                }
            )
        changes = _placement_changes(
            dates=dates,
            before=before_by_date,
            after=after_by_date,
            tasks=tasks,
        )
        result_versions = {
            plan_date.isoformat(): built_plans[plan_date].version
            for plan_date in dates
        }
        status_changed = any(
            before_plan_statuses.get(plan_date.isoformat())
            != built_plans[plan_date].status
            for plan_date in dates
        )
        is_undoable = bool(changes or mode_row is not None or status_changed)
        result_expires_at = operation_now + UNDO_WINDOW if is_undoable else None
        latest_created_at = db.scalar(
            select(PlanChange.created_at)
            .where(PlanChange.user_id == user.id)
            .order_by(PlanChange.created_at.desc(), PlanChange.id.desc())
            .limit(1)
        )
        change_created_at = _as_utc(operation_now)
        if (
            latest_created_at is not None
            and _as_utc(latest_created_at) >= change_created_at
        ):
            change_created_at = _as_utc(latest_created_at) + timedelta(microseconds=1)
        change_id = uuid4()
        result = PlanMutationResult(
            status="applied" if is_undoable else "no_change",
            request_id=request_id,
            change_id=change_id,
            reason=reason,
            base_versions=versions,
            result_versions=result_versions,
            affected_dates=[item.isoformat() for item in dates],
            plan_diff=_plan_diff(changes),
            snapshots=[
                _day_snapshot(built_plans[plan_date]) for plan_date in dates
            ],
            expires_at=result_expires_at,
        )
        db.add(
            PlanChange(
                id=change_id,
                user_id=user.id,
                request_id=request_id,
                reason=reason,
                status="applied",
                base_versions=versions,
                result_versions=result_versions,
                affected_dates=[item.isoformat() for item in dates],
                forward_payload={
                    "fingerprint": fingerprint,
                    "changes": changes,
                    "result": result.to_payload(),
                    "mode_id": str(mode_row.id) if mode_row else None,
                    "plan_statuses": {
                        plan_date.isoformat(): built_plans[plan_date].status
                        for plan_date in dates
                    },
                },
                inverse_payload={
                    "changes": changes,
                    "mode_id": str(mode_row.id) if mode_row else None,
                    "plan_statuses": before_plan_statuses,
                    "originally_absent_dates": originally_absent_dates,
                    "undoable": is_undoable,
                },
                # The existing column is non-nullable. A semantic no-op has no
                # undo window, so it stores its creation instant only as a
                # schema-compatible sentinel and exposes ``expires_at=None``.
                expires_at=result_expires_at or operation_now,
                created_at=change_created_at,
            )
        )
        db.commit()
        return result
    except IntegrityError as error:
        db.rollback()
        replay = _replay_apply(
            db,
            user=user,
            request_id=request_id,
            fingerprint=fingerprint,
        )
        if replay is not None:
            return replay
        raise PlanChangeConflict(
            "concurrent_write_conflict",
            retryable=True,
        ) from error
    except OperationalError as error:
        db.rollback()
        if "database is locked" in str(error).lower():
            raise PlanChangeConflict(
                "concurrent_write_conflict",
                retryable=True,
            ) from error
        raise
    except Exception:
        db.rollback()
        raise


def undo_plan_change(
    db: Session,
    *,
    user: User,
    change_id: UUID,
    request_id: str,
    expected_version: int | dict[date | str, int],
    now: datetime | None = None,
) -> PlanMutationResult:
    with _serialized_sqlite_write(db, user_id=user.id):
        return _undo_plan_change(
            db,
            user=user,
            change_id=change_id,
            request_id=request_id,
            expected_version=expected_version,
            now=now,
        )


def _undo_plan_change(
    db: Session,
    *,
    user: User,
    change_id: UUID,
    request_id: str,
    expected_version: int | dict[date | str, int],
    now: datetime | None = None,
) -> PlanMutationResult:
    operation_now = _require_aware(now or datetime.now(timezone.utc), "now")
    _validate_request_id(request_id)
    expected_payload: int | dict[str, int]
    if isinstance(expected_version, dict):
        expected_payload = {
            (key.isoformat() if isinstance(key, date) else str(key)): value
            for key, value in expected_version.items()
        }
    else:
        expected_payload = expected_version
    fingerprint = _fingerprint(
        {
            "operation": "undo",
            "request_id": request_id,
            "change_id": str(change_id),
            "expected_version": expected_payload,
        }
    )

    try:
        replay = _replay_undo(
            db,
            user=user,
            request_id=request_id,
            fingerprint=fingerprint,
        )
        if replay is not None:
            return replay
        _lock_user(db, user=user)
        replay = _replay_undo(
            db,
            user=user,
            request_id=request_id,
            fingerprint=fingerprint,
        )
        if replay is not None:
            return replay

        change = db.scalar(
            select(PlanChange)
            .where(PlanChange.id == change_id, PlanChange.user_id == user.id)
            .with_for_update()
        )
        if change is None:
            raise PlanChangeConflict("change_not_found")
        if change.status != "applied":
            raise PlanChangeConflict("change_already_undone")
        if not _is_undoable_change(change):
            raise PlanChangeConflict("change_not_undoable")
        if _as_utc(change.expires_at) <= _as_utc(operation_now):
            raise PlanChangeConflict("change_expired")
        candidates = db.scalars(
            select(PlanChange)
            .where(PlanChange.user_id == user.id, PlanChange.status == "applied")
            .order_by(PlanChange.created_at.desc(), PlanChange.id.desc())
            .with_for_update()
        ).all()
        latest = next(
            (candidate for candidate in candidates if _is_undoable_change(candidate)),
            None,
        )
        if latest is None or latest.id != change.id:
            raise PlanChangeConflict("change_not_latest")

        dates = [date.fromisoformat(value) for value in change.affected_dates]
        plans = _lock_plans(db, user=user, dates=dates)
        expected_versions = _undo_expected_versions(
            expected_payload,
            affected_dates=change.affected_dates,
        )
        for plan_date in dates:
            plan = plans.get(plan_date)
            current = plan.version if plan else 0
            result_version = int(change.result_versions[plan_date.isoformat()])
            if current != result_version or current != expected_versions[plan_date.isoformat()]:
                raise PlanChangeConflict(
                    "stale_plan_version",
                    date=plan_date.isoformat(),
                    expected=expected_versions[plan_date.isoformat()],
                    current=current,
                )
        _assert_unique_task_placements(plans.values())

        changes = list(change.inverse_payload.get("changes", []))
        current_placements = {
            plan_date: _placement_map(plans[plan_date]) for plan_date in dates
        }
        for item in changes:
            plan_date = date.fromisoformat(item["date"])
            current = current_placements[plan_date].get(int(item["task_id"]))
            if current != item.get("after"):
                raise PlanChangeConflict(
                    "placement_fact_changed",
                    date=item["date"],
                    task_id=int(item["task_id"]),
                )
        changed_task_ids = sorted({int(item["task_id"]) for item in changes})
        tasks = {
            task.id: task
            for task in db.scalars(
                select(Task).where(
                    Task.user_id == user.id,
                    Task.id.in_(changed_task_ids),
                ).order_by(Task.id.asc()).with_for_update()
            ).all()
        } if changed_task_ids else {}
        for item in changes:
            task = tasks.get(int(item["task_id"]))
            expected_fact = item.get("task_fact")
            incompatible = task is None
            if task is not None and expected_fact is not None:
                incompatible = _serialize_task_fact(task) != expected_fact
            elif task is not None:
                incompatible = task.status != item["task_status"]
            if incompatible:
                raise PlanChangeConflict(
                    "task_fact_changed",
                    task_id=int(item["task_id"]),
                )

        mode_id_raw = change.inverse_payload.get("mode_id")
        mode_id = UUID(mode_id_raw) if mode_id_raw else None
        for plan_date in dates:
            occupied, _ = _planning_constraints(
                db,
                user=user,
                plan_date=plan_date,
                excluded_mode_id=mode_id,
            )
            _assert_restore_compatible(
                plan_date=plan_date,
                changes=changes,
                occupied=occupied,
                now=operation_now,
                user=user,
            )

        changes_by_date: dict[date, list[dict[str, Any]]] = {}
        for item in changes:
            changes_by_date.setdefault(date.fromisoformat(item["date"]), []).append(item)
        previous_statuses = dict(change.inverse_payload.get("plan_statuses", {}))
        originally_absent_dates = {
            date.fromisoformat(value)
            for value in change.inverse_payload.get("originally_absent_dates", [])
        }
        deleted_dates: set[date] = set()
        for plan_date in dates:
            day_changes = changes_by_date.get(plan_date, [])
            plan = plans[plan_date]
            current_by_task = {
                item.task_id: item
                for item in plan.items
                if item.task_id is not None
            }
            for item in day_changes:
                task_id = int(item["task_id"])
                before = item.get("before")
                current = current_by_task.get(task_id)
                if before is None:
                    if current is not None:
                        plan.items.remove(current)
                    continue
                task = tasks[task_id]
                if current is None:
                    current = PlanItem(
                        task_id=task_id,
                        title=task.title,
                        item_type="task",
                        status="planned",
                    )
                    plan.items.append(current)
                _restore_placement(current, before)
            previous_status = previous_statuses.get(plan_date.isoformat())
            status_changed = previous_status is not None and plan.status != previous_status
            if previous_status is not None:
                plan.status = previous_status
            if day_changes or status_changed:
                plan.version += 1
            db.flush()
            if plan_date in originally_absent_dates:
                if plan.items:
                    raise PlanChangeConflict(
                        "plan_fact_changed",
                        date=plan_date.isoformat(),
                    )
                db.delete(plan)
                deleted_dates.add(plan_date)
                db.flush()
            else:
                assert_plan_has_no_overlaps(plan, user)

        if mode_id is not None:
            mode = db.scalar(
                select(TemporaryLifeMode).where(
                    TemporaryLifeMode.id == mode_id,
                    TemporaryLifeMode.user_id == user.id,
                )
            )
            if mode is not None and mode.status == "active":
                mode.status = "cancelled"

        change.status = "undone"
        change.undone_at = operation_now
        result_versions = {
            plan_date.isoformat(): (
                0 if plan_date in deleted_dates else plans[plan_date].version
            )
            for plan_date in dates
        }
        result = PlanMutationResult(
            status="undone",
            request_id=request_id,
            change_id=change.id,
            reason=change.reason,
            base_versions=dict(change.result_versions),
            result_versions=result_versions,
            affected_dates=list(change.affected_dates),
            plan_diff=_inverse_plan_diff(changes),
            snapshots=[
                (
                    _absent_day_snapshot(plan_date)
                    if plan_date in deleted_dates
                    else _day_snapshot(plans[plan_date])
                )
                for plan_date in dates
            ],
            expires_at=None,
        )
        db.add(
            MessageReceipt(
                user_id=user.id,
                request_id=request_id,
                source="plan_change_undo",
                status="applied",
                response_payload={
                    "fingerprint": fingerprint,
                    "result": result.to_payload(),
                },
                expires_at=operation_now + RECEIPT_TTL,
            )
        )
        db.commit()
        return result
    except IntegrityError as error:
        db.rollback()
        replay = _replay_undo(
            db,
            user=user,
            request_id=request_id,
            fingerprint=fingerprint,
        )
        if replay is not None:
            return replay
        raise PlanChangeConflict(
            "concurrent_write_conflict",
            retryable=True,
        ) from error
    except OperationalError as error:
        db.rollback()
        if "database is locked" in str(error).lower():
            raise PlanChangeConflict(
                "concurrent_write_conflict",
                retryable=True,
            ) from error
        raise
    except Exception:
        db.rollback()
        raise


@contextmanager
def _serialized_sqlite_write(db: Session, *, user_id: int):
    bind = db.get_bind()
    if bind.dialect.name != "sqlite":
        yield
        return
    lock = _SQLITE_WRITE_LOCKS[user_id % len(_SQLITE_WRITE_LOCKS)]
    with lock:
        yield


def _validate_request_id(request_id: str) -> None:
    if not request_id or len(request_id) > 128:
        raise PlanChangeConflict("invalid_request_id")


def _normalize_dates(values: list[date], *, earliest_date: date) -> list[date]:
    dates = sorted(set(values))
    if not dates or len(dates) > MAX_AFFECTED_DAYS or len(dates) != len(values):
        raise PlanChangeConflict("invalid_affected_dates")
    if dates[0] < earliest_date:
        raise PlanChangeConflict("past_date_not_replannable")
    return dates


def _normalize_base_versions(
    values: dict[date | str, int],
    *,
    dates: list[date],
) -> dict[str, int]:
    normalized = {
        (key.isoformat() if isinstance(key, date) else str(key)): value
        for key, value in values.items()
    }
    expected_keys = {item.isoformat() for item in dates}
    if set(normalized) != expected_keys or any(
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 0 <= value <= MAX_PLAN_VERSION
        for value in normalized.values()
    ):
        raise PlanChangeConflict("invalid_base_versions")
    return {key: normalized[key] for key in sorted(normalized)}


def _normalize_mode(value: TemporaryModeRequest | None) -> TemporaryModeRequest | None:
    if value is None:
        return None
    if value.mode not in SUPPORTED_TEMPORARY_MODES:
        raise PlanChangeConflict("unsupported_temporary_mode")
    starts_at = _require_aware(value.starts_at, "starts_at")
    ends_at = _require_aware(value.ends_at, "ends_at")
    if ends_at <= starts_at:
        raise PlanChangeConflict("invalid_temporary_mode_interval")
    constraints = _normalize_mode_constraints(value.constraints)
    for blocked in constraints.get("blocked_intervals", []):
        blocked_start = datetime.fromisoformat(blocked["start"])
        blocked_end = datetime.fromisoformat(blocked["end"])
        if blocked_start < starts_at or blocked_end > ends_at:
            raise PlanChangeConflict("invalid_temporary_mode_constraints")
    return TemporaryModeRequest(
        mode=value.mode,
        starts_at=starts_at,
        ends_at=ends_at,
        constraints=constraints,
    )


def _normalize_mode_constraints(value: dict[str, Any]) -> dict[str, Any]:
    allowed = {"blocked_intervals", "max_flexible_minutes", "reserve_minutes"}
    if set(value) - allowed:
        raise PlanChangeConflict("invalid_temporary_mode_constraints")
    result: dict[str, Any] = {}
    for key in ("max_flexible_minutes", "reserve_minutes"):
        if key not in value:
            continue
        amount = value[key]
        if isinstance(amount, bool) or not isinstance(amount, int) or not 0 <= amount <= 1020:
            raise PlanChangeConflict("invalid_temporary_mode_constraints")
        result[key] = amount
    blocked: list[dict[str, str]] = []
    raw_blocked = value.get("blocked_intervals", [])
    if not isinstance(raw_blocked, list) or len(raw_blocked) > 32:
        raise PlanChangeConflict("invalid_temporary_mode_constraints")
    for item in raw_blocked:
        if not isinstance(item, dict) or set(item) != {"start", "end"}:
            raise PlanChangeConflict("invalid_temporary_mode_constraints")
        try:
            start = _require_aware(datetime.fromisoformat(item["start"]), "start")
            end = _require_aware(datetime.fromisoformat(item["end"]), "end")
        except (TypeError, ValueError) as error:
            raise PlanChangeConflict("invalid_temporary_mode_constraints") from error
        if end <= start:
            raise PlanChangeConflict("invalid_temporary_mode_constraints")
        blocked.append({"start": start.isoformat(), "end": end.isoformat()})
    if blocked:
        result["blocked_intervals"] = blocked
    return result


def _mode_payload(value: TemporaryModeRequest | None) -> dict[str, Any] | None:
    if value is None:
        return None
    return {
        "mode": value.mode,
        "starts_at": value.starts_at.isoformat(),
        "ends_at": value.ends_at.isoformat(),
        "constraints": value.constraints,
    }


def _mode_local_dates(
    value: TemporaryModeRequest,
    *,
    user: User,
) -> set[date]:
    zone = get_user_timezone(user)
    try:
        current = value.starts_at.astimezone(zone).date()
        last = (value.ends_at - timedelta(microseconds=1)).astimezone(zone).date()
    except OverflowError as error:
        raise PlanChangeConflict(
            "temporary_mode_horizon_exceeded",
            max_days=MAX_AFFECTED_DAYS,
        ) from error
    span_days = (last - current).days + 1
    if span_days > MAX_AFFECTED_DAYS:
        raise PlanChangeConflict(
            "temporary_mode_horizon_exceeded",
            max_days=MAX_AFFECTED_DAYS,
        )
    result: set[date] = set()
    for offset in range(span_days):
        result.add(current + timedelta(days=offset))
    return result


def _lock_user(db: Session, *, user: User) -> None:
    owned = db.scalar(select(User.id).where(User.id == user.id).with_for_update())
    if owned is None:
        raise PlanChangeConflict("user_not_found")


def _lock_plans(db: Session, *, user: User, dates: list[date]) -> dict[date, DayPlan]:
    plans = db.scalars(
        select(DayPlan)
        .where(DayPlan.user_id == user.id, DayPlan.date.in_(dates))
        .order_by(DayPlan.date.asc(), DayPlan.id.asc())
        .with_for_update()
        .execution_options(populate_existing=True)
    ).all()
    return {plan.date: plan for plan in plans}


def _assert_unique_task_placements(plans) -> None:
    for plan in plans:
        placement_ids_by_task: dict[int, list[int]] = {}
        for item in plan.items:
            if item.task_id is None:
                continue
            placement_ids_by_task.setdefault(int(item.task_id), []).append(item.id)
        duplicate = next(
            (
                (task_id, placement_ids)
                for task_id, placement_ids in sorted(placement_ids_by_task.items())
                if len(placement_ids) > 1
            ),
            None,
        )
        if duplicate is not None:
            task_id, placement_ids = duplicate
            raise PlanChangeConflict(
                "duplicate_plan_placement",
                date=plan.date.isoformat(),
                day_plan_id=plan.id,
                task_id=task_id,
                placement_ids=placement_ids,
            )


def _is_undoable_change(change: PlanChange) -> bool:
    explicit = (change.inverse_payload or {}).get("undoable")
    if explicit is not None:
        return explicit is True
    result = (change.forward_payload or {}).get("result", {})
    return result.get("status") != "no_change"


def _planning_constraints(
    db: Session,
    *,
    user: User,
    plan_date: date,
    excluded_mode_id: UUID | None = None,
) -> tuple[list[TimeInterval], list[FlexibleCapacityLimit]]:
    bounds = _day_bounds(user, plan_date)
    utc_start = bounds.start.astimezone(timezone.utc)
    utc_end = bounds.end.astimezone(timezone.utc)
    blocks = db.scalars(
        select(CalendarBusyBlock).where(
            CalendarBusyBlock.user_id == user.id,
            CalendarBusyBlock.deleted_at.is_(None),
            CalendarBusyBlock.occurrence_start < utc_end,
            CalendarBusyBlock.occurrence_end > utc_start,
        )
    ).all()
    intervals: list[TimeInterval] = []
    zone = get_user_timezone(user)
    for block in blocks:
        interval = _clip_interval(
            _as_utc(block.occurrence_start).astimezone(zone),
            _as_utc(block.occurrence_end).astimezone(zone),
            bounds,
            "календарным событием",
        )
        if interval is not None:
            intervals.append(interval)

    modes = db.scalars(
        select(TemporaryLifeMode).where(
            TemporaryLifeMode.user_id == user.id,
            TemporaryLifeMode.status == "active",
            TemporaryLifeMode.starts_at < utc_end,
            TemporaryLifeMode.ends_at > utc_start,
        )
    ).all()
    capacity_limits: list[FlexibleCapacityLimit] = []
    for mode in modes:
        if excluded_mode_id is not None and mode.id == excluded_mode_id:
            continue
        constraints = _normalize_mode_constraints(mode.constraints or {})
        mode_interval = _clip_interval(
            _as_utc(mode.starts_at).astimezone(zone),
            _as_utc(mode.ends_at).astimezone(zone),
            bounds,
            f"временным режимом {mode.mode}",
        )
        if mode_interval is not None and (
            "max_flexible_minutes" in constraints
            or "reserve_minutes" in constraints
        ):
            capacity_limits.append(
                FlexibleCapacityLimit(
                    interval=mode_interval,
                    max_flexible_minutes=constraints.get("max_flexible_minutes"),
                    reserve_minutes=constraints.get("reserve_minutes", 0),
                )
            )
        for blocked in constraints.get("blocked_intervals", []):
            interval = _clip_interval(
                datetime.fromisoformat(blocked["start"]).astimezone(zone),
                datetime.fromisoformat(blocked["end"]).astimezone(zone),
                bounds,
                f"временным режимом {mode.mode}",
            )
            if interval is not None:
                intervals.append(interval)
    return intervals, capacity_limits


def _assert_replannable_plan(
    plan: DayPlan,
    *,
    tasks: dict[int, Task],
    occupied: list[TimeInterval],
    now: datetime,
    user: User,
) -> None:
    zone = get_user_timezone(user)
    local_now = now.astimezone(zone)
    for item in plan.items:
        interval = _item_interval(item, plan.date, zone)
        if item.task_id is None:
            raise PlanChangeConflict(
                "unsupported_non_task_placement",
                date=plan.date.isoformat(),
                item_id=item.id,
            )
        task = tasks.get(item.task_id)
        if task is None or interval is None:
            continue
        immutable = item.status == "done" or task.status == "done"
        immutable = immutable or task.scheduling_type == "fixed" or task.is_locked
        immutable = immutable or interval.start < local_now
        if immutable and interval.end > local_now and any(
            intervals_overlap(interval, busy) for busy in occupied
        ):
            raise PlanChangeConflict(
                "immutable_interval_conflict",
                date=plan.date.isoformat(),
                task_id=task.id,
            )


def _assert_restore_compatible(
    *,
    plan_date: date,
    changes: list[dict[str, Any]],
    occupied: list[TimeInterval],
    now: datetime,
    user: User,
) -> None:
    zone = get_user_timezone(user)
    local_now = now.astimezone(zone)
    for item in changes:
        if item["date"] != plan_date.isoformat() or item.get("before") is None:
            continue
        placement = item["before"]
        if placement.get("start_time") is None or placement.get("end_time") is None:
            continue
        interval = _serialized_interval(placement, plan_date, zone)
        if interval.end <= local_now:
            continue
        if any(intervals_overlap(interval, busy) for busy in occupied):
            raise PlanChangeConflict(
                "restore_interval_conflict",
                date=plan_date.isoformat(),
                task_id=int(item["task_id"]),
            )


def _placement_map(plan: DayPlan) -> dict[int, dict[str, Any]]:
    return {
        int(item.task_id): _serialize_placement(item)
        for item in plan.items
        if item.task_id is not None
    }


def _serialize_placement(item: PlanItem) -> dict[str, Any]:
    return {
        "placement_id": item.id,
        "start_time": item.start_time.isoformat() if item.start_time else None,
        "end_time": item.end_time.isoformat() if item.end_time else None,
        "status": item.status,
        "unscheduled_reason": item.unscheduled_reason,
    }


def _placement_changes(
    *,
    dates: list[date],
    before: dict[date, dict[int, dict[str, Any]]],
    after: dict[date, dict[int, dict[str, Any]]],
    tasks: dict[int, Task],
) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    for plan_date in dates:
        old = before.get(plan_date, {})
        new = after.get(plan_date, {})
        for task_id in sorted(set(old) | set(new)):
            if old.get(task_id) == new.get(task_id):
                continue
            changes.append(
                {
                    "date": plan_date.isoformat(),
                    "task_id": task_id,
                    "task_status": tasks[task_id].status if task_id in tasks else "planned",
                    "task_fact": (
                        _serialize_task_fact(tasks[task_id])
                        if task_id in tasks
                        else {"status": "planned"}
                    ),
                    "before": old.get(task_id),
                    "after": new.get(task_id),
                }
            )
    return changes


def _serialize_task_fact(task: Task) -> dict[str, Any]:
    return {
        "status": task.status,
        "target_date": task.target_date.isoformat(),
        "priority": task.priority,
        "estimated_minutes": task.estimated_minutes,
        "scheduling_type": task.scheduling_type,
        "fixed_start": task.fixed_start.isoformat() if task.fixed_start else None,
        "fixed_end": task.fixed_end.isoformat() if task.fixed_end else None,
        "preferred_window": task.preferred_window,
        "earliest_start": task.earliest_start.isoformat() if task.earliest_start else None,
        "latest_end": task.latest_end.isoformat() if task.latest_end else None,
        "deadline": _as_utc(task.deadline).isoformat() if task.deadline else None,
        "is_locked": task.is_locked,
        "program_id": str(task.program_id) if task.program_id else None,
        "commitment_id": str(task.commitment_id) if task.commitment_id else None,
    }


def _plan_diff(changes: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    moved: list[dict[str, Any]] = []
    unscheduled: list[dict[str, Any]] = []
    scheduled: list[dict[str, Any]] = []
    for item in changes:
        before = item.get("before") or {}
        after = item.get("after") or {}
        before_start = before.get("start_time")
        after_start = after.get("start_time")
        if before_start and after_start and (
            before_start != after_start or before.get("end_time") != after.get("end_time")
        ):
            moved.append(
                {
                    "date": item["date"],
                    "task_id": item["task_id"],
                    "old_start": before_start,
                    "old_end": before.get("end_time"),
                    "new_start": after_start,
                    "new_end": after.get("end_time"),
                }
            )
        elif after and not after_start:
            unscheduled.append(
                {
                    "date": item["date"],
                    "task_id": item["task_id"],
                    "reason": after.get("unscheduled_reason") or "not_scheduled",
                }
            )
        elif not before_start and after_start:
            scheduled.append(
                {
                    "date": item["date"],
                    "task_id": item["task_id"],
                    "start": after_start,
                    "end": after.get("end_time"),
                }
            )
    return {"moved": moved, "unscheduled": unscheduled, "scheduled": scheduled}


def _inverse_plan_diff(changes: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    reversed_changes = [
        {**item, "before": item.get("after"), "after": item.get("before")}
        for item in changes
    ]
    return _plan_diff(reversed_changes)


def _day_snapshot(plan: DayPlan) -> dict[str, Any]:
    items = [
        {"task_id": task_id, **placement}
        for task_id, placement in sorted(_placement_map(plan).items())
    ]
    return {
        "date": plan.date.isoformat(),
        "version": plan.version,
        "status": plan.status,
        "items": items,
    }


def _absent_day_snapshot(plan_date: date) -> dict[str, Any]:
    return {
        "date": plan_date.isoformat(),
        "version": 0,
        "status": "absent",
        "items": [],
    }


def _restore_placement(item: PlanItem, payload: dict[str, Any]) -> None:
    item.start_time = (
        time.fromisoformat(payload["start_time"])
        if payload.get("start_time")
        else None
    )
    item.end_time = time.fromisoformat(payload["end_time"]) if payload.get("end_time") else None
    item.status = payload["status"]
    item.unscheduled_reason = payload.get("unscheduled_reason")


def _item_interval(item: PlanItem, plan_date: date, zone: ZoneInfo) -> TimeInterval | None:
    if item.start_time is None or item.end_time is None:
        return None
    start = datetime.combine(plan_date, item.start_time, tzinfo=zone)
    end = datetime.combine(plan_date, item.end_time, tzinfo=zone)
    if end <= start:
        end += timedelta(days=1)
    return TimeInterval(start, end, item.title)


def _serialized_interval(
    placement: dict[str, Any],
    plan_date: date,
    zone: ZoneInfo,
) -> TimeInterval:
    start = datetime.combine(plan_date, time.fromisoformat(placement["start_time"]), tzinfo=zone)
    end = datetime.combine(plan_date, time.fromisoformat(placement["end_time"]), tzinfo=zone)
    if end <= start:
        end += timedelta(days=1)
    return TimeInterval(start, end)


def _clip_interval(
    start: datetime,
    end: datetime,
    bounds: TimeInterval,
    label: str,
) -> TimeInterval | None:
    clipped_start = max(start, bounds.start)
    clipped_end = min(end, bounds.end)
    if clipped_end <= clipped_start:
        return None
    return TimeInterval(clipped_start, clipped_end, label)


def _undo_expected_versions(
    value: int | dict[str, int],
    *,
    affected_dates: list[str],
) -> dict[str, int]:
    if isinstance(value, int):
        if (
            isinstance(value, bool)
            or len(affected_dates) != 1
            or not 0 <= value <= MAX_PLAN_VERSION
        ):
            raise PlanChangeConflict("invalid_expected_version")
        return {affected_dates[0]: value}
    if set(value) != set(affected_dates) or any(
        isinstance(item, bool)
        or not isinstance(item, int)
        or not 0 <= item <= MAX_PLAN_VERSION
        for item in value.values()
    ):
        raise PlanChangeConflict("invalid_expected_version")
    return {key: value[key] for key in sorted(value)}


def _replay_apply(
    db: Session,
    *,
    user: User,
    request_id: str,
    fingerprint: str,
) -> PlanMutationResult | None:
    change = db.scalar(
        select(PlanChange).where(
            PlanChange.user_id == user.id,
            PlanChange.request_id == request_id,
        )
    )
    if change is None:
        if db.scalar(
            select(MessageReceipt.id).where(
                MessageReceipt.user_id == user.id,
                MessageReceipt.request_id == request_id,
            )
        ) is not None:
            raise PlanChangeConflict("idempotency_conflict")
        return None
    payload = change.forward_payload or {}
    if payload.get("fingerprint") != fingerprint:
        raise PlanChangeConflict("idempotency_conflict")
    try:
        return PlanMutationResult.from_payload(payload["result"])
    except (KeyError, TypeError, ValueError) as error:
        raise PlanChangeConflict("idempotency_record_invalid") from error


def _replay_undo(
    db: Session,
    *,
    user: User,
    request_id: str,
    fingerprint: str,
) -> PlanMutationResult | None:
    receipt = db.scalar(
        select(MessageReceipt).where(
            MessageReceipt.user_id == user.id,
            MessageReceipt.request_id == request_id,
        )
    )
    if receipt is None:
        if db.scalar(
            select(PlanChange.id).where(
                PlanChange.user_id == user.id,
                PlanChange.request_id == request_id,
            )
        ) is not None:
            raise PlanChangeConflict("idempotency_conflict")
        return None
    payload = receipt.response_payload or {}
    if receipt.source != "plan_change_undo" or payload.get("fingerprint") != fingerprint:
        raise PlanChangeConflict("idempotency_conflict")
    try:
        return PlanMutationResult.from_payload(payload["result"])
    except (KeyError, TypeError, ValueError) as error:
        raise PlanChangeConflict("idempotency_record_invalid") from error


def _fingerprint(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _require_aware(value: datetime, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise PlanChangeConflict("timezone_required", field=field)
    return value


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
