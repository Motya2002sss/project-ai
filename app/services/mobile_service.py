from sqlalchemy.orm import Session

from app.models.task import Task
from app.models.user import User
from app.schemas.api import MessageResponse, PlanDiffResponse, TaskStatus
from app.schemas.mobile import MobileActionResponse, MobileTaskMutationResponse
from app.services.message_service import day_snapshot_to_response, task_to_response
from app.services.planning_service import rebuild_day_plan
from app.services.task_service import set_task_status


def message_to_mobile_response(response: MessageResponse) -> MobileActionResponse:
    if response.request_id is None or response.day_snapshot is None:
        raise RuntimeError("Message pipeline returned an incomplete mobile response")

    already_processing = (
        response.status == "no_change"
        and "уже обрабатывается" in response.reply_text.lower()
    )

    return MobileActionResponse(
        request_id=response.request_id,
        status=response.status,
        reply_text=response.reply_text,
        retryable=response.status == "failed" or already_processing,
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
