import hashlib
import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.day_plan import DayPlan
from app.models.message_receipt import MessageReceipt
from app.models.task import Task
from app.models.user import User
from app.schemas.api import DaySnapshotResponse, MessageResponse, PlanDiffResponse, TaskStatus
from app.schemas.mobile import MobileActionResponse, MobileTaskMutationResponse
from app.services.message_service import day_snapshot_to_response, task_to_response
from app.services.planning_service import get_plan_date, rebuild_day_plan
from app.services.task_service import set_task_status


class MobileTaskConflict(ValueError):
    pass


def get_mobile_today_snapshot(db: Session, user: User) -> DaySnapshotResponse:
    plan_date = get_plan_date(user=user)
    day_plan = (
        db.query(DayPlan)
        .filter(DayPlan.user_id == user.id, DayPlan.date == plan_date)
        .one_or_none()
    )

    if day_plan is None:
        day_plan = DayPlan(
            id=0,
            user_id=user.id,
            date=plan_date,
            summary="Автоматический план дня",
            status="draft",
            version=0,
        )

    return day_snapshot_to_response(db, user, day_plan)


def message_to_mobile_response(response: MessageResponse) -> MobileActionResponse:
    if response.request_id is None or response.day_snapshot is None:
        raise RuntimeError("Message pipeline returned an incomplete mobile response")

    return MobileActionResponse(
        request_id=response.request_id,
        status=response.status,
        reason=response.reason,
        reply_text=response.reply_text,
        retryable=response.status == "failed" or response.reason == "request_in_progress",
        plan_diff=response.plan_diff,
        clarification=response.clarification,
        confirmation=response.confirmation,
        conflict=response.conflict_details,
        day_snapshot=response.day_snapshot,
    )


def update_mobile_task_status(
    db: Session,
    user: User,
    *,
    task_id: int,
    task_status: TaskStatus,
) -> MobileTaskMutationResponse | None:
    try:
        locked_user = (
            db.query(User)
            .filter(User.id == user.id)
            .with_for_update()
            .one()
        )
        owned_task = (
            db.query(Task)
            .filter(
                Task.id == task_id,
                Task.user_id == locked_user.id,
                Task.status.in_(["planned", "done"]),
            )
            .with_for_update()
            .one_or_none()
        )

        if owned_task is None:
            return None

        previous_status = owned_task.status
        task = set_task_status(
            db=db,
            user=locked_user,
            task_id=task_id,
            task_status=task_status,
            commit=False,
        )

        if task is None:
            return None

        day_plan = rebuild_day_plan(
            db=db,
            user=locked_user,
            plan_date=task.target_date,
            commit=False,
        )
        changed = previous_status != task_status
        plan_diff = PlanDiffResponse(
            completed_task_ids=[task.id] if changed and task_status == "done" else [],
            updated_task_ids=[task.id] if changed and task_status == "planned" else [],
        )
        response = MobileTaskMutationResponse(
            status="applied" if changed else "no_change",
            task=task_to_response(task),
            plan_diff=plan_diff,
            day_snapshot=day_snapshot_to_response(db, locked_user, day_plan),
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    return response


def update_versioned_mobile_task_status(
    db: Session,
    user: User,
    *,
    task_id: int,
    task_status: TaskStatus,
    request_id: str,
    expected_plan_version: int,
) -> MobileTaskMutationResponse | None:
    fingerprint = _task_status_fingerprint(
        task_id=task_id,
        task_status=task_status,
        expected_plan_version=expected_plan_version,
    )
    replay = _replay_task_status(
        db,
        user=user,
        request_id=request_id,
        fingerprint=fingerprint,
    )
    if replay is not None:
        return replay
    try:
        locked_user = db.scalar(
            select(User).where(User.id == user.id).with_for_update()
        )
        if locked_user is None:
            return None
        replay = _replay_task_status(
            db,
            user=locked_user,
            request_id=request_id,
            fingerprint=fingerprint,
        )
        if replay is not None:
            return replay
        task = db.scalar(
            select(Task)
            .where(
                Task.id == task_id,
                Task.user_id == locked_user.id,
                Task.status.in_(["planned", "done"]),
            )
            .with_for_update()
        )
        if task is None:
            return None
        day_plan = db.scalar(
            select(DayPlan)
            .where(
                DayPlan.user_id == locked_user.id,
                DayPlan.date == task.target_date,
            )
            .with_for_update()
        )
        current_version = day_plan.version if day_plan is not None else 0
        if current_version != expected_plan_version:
            raise MobileTaskConflict("stale_plan_version")
        previous_status = task.status
        updated = set_task_status(
            db=db,
            user=locked_user,
            task_id=task_id,
            task_status=task_status,
            commit=False,
        )
        if updated is None:
            return None
        authoritative_plan = rebuild_day_plan(
            db=db,
            user=locked_user,
            plan_date=updated.target_date,
            commit=False,
        )
        changed = previous_status != task_status
        response = MobileTaskMutationResponse(
            status="applied" if changed else "no_change",
            task=task_to_response(updated),
            plan_diff=PlanDiffResponse(
                completed_task_ids=[updated.id]
                if changed and task_status == "done"
                else [],
                updated_task_ids=[updated.id]
                if changed and task_status == "planned"
                else [],
            ),
            day_snapshot=day_snapshot_to_response(
                db,
                locked_user,
                authoritative_plan,
            ),
        )
        db.add(
            MessageReceipt(
                user_id=locked_user.id,
                request_id=request_id,
                source="task_status_v2",
                status="applied",
                response_payload={
                    "fingerprint": fingerprint,
                    "result": response.model_dump(mode="json"),
                },
                expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            )
        )
        db.commit()
        return response
    except Exception:
        db.rollback()
        raise


def _task_status_fingerprint(
    *,
    task_id: int,
    task_status: TaskStatus,
    expected_plan_version: int,
) -> str:
    encoded = json.dumps(
        {
            "task_id": task_id,
            "status": task_status,
            "expected_plan_version": expected_plan_version,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _replay_task_status(
    db: Session,
    *,
    user: User,
    request_id: str,
    fingerprint: str,
) -> MobileTaskMutationResponse | None:
    receipt = db.scalar(
        select(MessageReceipt).where(
            MessageReceipt.user_id == user.id,
            MessageReceipt.request_id == request_id,
        )
    )
    if receipt is None:
        return None
    payload = receipt.response_payload or {}
    if (
        receipt.source != "task_status_v2"
        or payload.get("fingerprint") != fingerprint
    ):
        raise MobileTaskConflict("idempotency_conflict")
    try:
        return MobileTaskMutationResponse.model_validate(payload["result"])
    except (KeyError, TypeError, ValueError) as error:
        raise MobileTaskConflict("idempotency_record_invalid") from error
