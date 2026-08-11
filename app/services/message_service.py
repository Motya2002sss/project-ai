import hashlib
import json
import logging
import re
from dataclasses import dataclass
from datetime import date, time, timedelta
from time import perf_counter
from uuid import uuid4

from sqlalchemy.orm import Session

from app.llm.parser import parse_user_message
from app.llm.schemas import ParsedTask, ParsedUserMessage
from app.models.day_plan import DayPlan
from app.models.goal import Goal
from app.models.routine import Routine
from app.models.task import Task
from app.models.user import User
from app.schemas.api import (
    ClarificationResponse,
    ConfirmationResponse,
    ConflictResponse,
    InteractionOptionResponse,
    GoalResponse,
    MessageReason,
    MessageResponse,
    MessageSource,
    MessageStatus,
    MovedPlanItemResponse,
    PlanDiffResponse,
    DayContextResponse,
    DayProgressResponse,
    DaySnapshotResponse,
    PlanItemResponse,
    PlanResponse,
    ProfileResponse,
    RoutineResponse,
    TaskResponse,
)
from app.services.goal_service import (
    create_goals_from_titles,
    format_goals,
    list_active_goals,
    suggest_tasks_from_goals,
)
from app.services.idempotency_service import (
    complete_message_request,
    fail_message_request,
    reserve_message_request,
)
from app.services.interaction_service import (
    create_pending_interaction,
    get_pending_interaction,
    resolve_interaction,
)
from app.services.message_policy import (
    detect_tracking_ambiguity,
    interaction_option,
    is_cancel_message,
    is_capability_request,
    is_explicit_routine_request,
    is_low_energy_replan_request,
    normalize_parsed_tasks,
    normalize_routine_title,
    task_for_one_time_tracking,
)
from app.services.planning_service import (
    PlanBuildResult,
    build_day_plan_result,
    build_plan_focus,
    effective_work_window,
    format_day_plan,
    format_plan_date,
    get_plan_date,
    rebuild_day_plan,
)
from app.services.routine_service import create_routine, list_active_routines
from app.services.task_service import (
    TaskMutationResult,
    apply_parsed_task_operations,
    clear_user_tasks,
    create_tasks_from_parsed_tasks,
    find_active_tasks_by_titles,
    format_tasks,
    list_active_tasks,
    list_user_tasks,
    mark_tasks_done_by_titles,
)
from app.services.time_service import get_user_now
from app.services.user_service import (
    format_user_profile,
    get_or_create_user_by_external_id,
    update_user_profile_from_parsed_message,
)


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _PlanPlacementSnapshot:
    task_id: int
    title: str
    start_time: time | None
    end_time: time | None
    status: str


def _planning_context_hint(user: User) -> str:
    if user.work_end_time and user.sleep_time:
        return ""

    missing = []

    if not user.work_end_time:
        missing.append("рабочее время")

    if not user.sleep_time:
        missing.append("время сна")

    missing_text = " и ".join(missing)

    return (
        f"\n\nПлан построен с настройками по умолчанию. "
        f"Чтобы точнее учитывать {missing_text}, напиши обычным текстом: "
        "«Мой график с 10 до 19, хочу спать в 00:30»."
    )


def task_to_response(task: Task) -> TaskResponse:
    return TaskResponse(
        id=task.id,
        goal_id=task.goal_id,
        title=task.title,
        priority=task.priority,
        estimated_minutes=task.estimated_minutes,
        target_date=task.target_date,
        scheduling_type=task.scheduling_type,
        fixed_start=task.fixed_start,
        fixed_end=task.fixed_end,
        preferred_window=task.preferred_window,
        earliest_start=task.earliest_start,
        latest_end=task.latest_end,
        deadline=task.deadline,
        is_locked=task.is_locked,
        status=task.status,
        routine_id=task.routine_id,
        occurrence_date=task.occurrence_date,
    )


def goal_to_response(goal: Goal) -> GoalResponse:
    return GoalResponse(
        id=goal.id,
        title=goal.title,
        category=goal.category,
        priority=goal.priority,
        status=goal.status,
    )


def routine_to_response(routine: Routine) -> RoutineResponse:
    return RoutineResponse(
        id=routine.id,
        title=routine.title,
        cadence=routine.cadence,
        weekdays=routine.weekdays or [],
        fixed_time=routine.fixed_time,
        preferred_window=routine.preferred_window,
        estimated_minutes=routine.estimated_minutes,
        start_date=routine.start_date,
        end_date=routine.end_date,
        active=routine.active,
    )


def profile_to_response(user: User, user_external_id: str) -> ProfileResponse:
    return ProfileResponse(
        user_external_id=user_external_id,
        name=user.name,
        timezone=user.timezone,
        work_start_time=user.work_start_time,
        work_end_time=user.work_end_time,
        sleep_time=user.sleep_time,
    )


def plan_to_response(day_plan: DayPlan, user: User | None = None) -> PlanResponse:
    return PlanResponse(
        id=day_plan.id,
        date=day_plan.date,
        summary=day_plan.summary,
        focus_text=build_plan_focus(day_plan, user or day_plan.user),
        energy_level=day_plan.energy_level,
        budget_limit=day_plan.budget_limit,
        status=day_plan.status,
        version=day_plan.version,
        items=[
            PlanItemResponse(
                id=item.id,
                task_id=item.task_id,
                title=item.title,
                item_type=item.item_type,
                status=item.status,
                start_time=item.start_time,
                end_time=item.end_time,
                unscheduled_reason=item.unscheduled_reason,
            )
            for item in day_plan.items
        ],
    )


def day_snapshot_to_response(
    db: Session,
    user: User,
    day_plan: DayPlan,
) -> DaySnapshotResponse:
    plan = plan_to_response(day_plan, user=user)
    tasks = list_user_tasks(db=db, user=user, target_date=day_plan.date)
    goals = list_active_goals(db=db, user=user)
    routines = list_active_routines(db=db, user=user)
    task_responses = [task_to_response(task) for task in tasks]
    done_count = sum(task.status == "done" for task in tasks)
    scheduled_items = [
        item
        for item in plan.items
        if item.start_time is not None and item.status in {"planned", "done"}
    ]
    unscheduled_items = [item for item in plan.items if item not in scheduled_items]
    completed_items = [item for item in plan.items if item.status == "done"]
    current_item = None
    current_time = get_user_now(user)
    week_start = day_plan.date - timedelta(days=day_plan.date.isoweekday() - 1)
    week_end = week_start + timedelta(days=6)
    week_tasks = (
        db.query(Task)
        .filter(
            Task.user_id == user.id,
            Task.target_date >= week_start,
            Task.target_date <= week_end,
            Task.status.in_(["planned", "done"]),
        )
        .all()
    )
    week_done_count = sum(task.status == "done" for task in week_tasks)

    if day_plan.date == current_time.date():
        current_clock = current_time.timetz().replace(tzinfo=None)
        current_item = next(
            (
                item
                for item in scheduled_items
                if item.status == "planned"
                and item.start_time is not None
                and item.end_time is not None
                and item.start_time <= current_clock < item.end_time
            ),
            None,
        )

    return DaySnapshotResponse(
        date=day_plan.date,
        as_of=current_time,
        focus_text=plan.focus_text,
        progress=DayProgressResponse(done=done_count, total=len(tasks)),
        week_progress=DayProgressResponse(
            done=week_done_count,
            total=len(week_tasks),
        ),
        scheduled_items=scheduled_items,
        unscheduled_items=unscheduled_items,
        completed_items=completed_items,
        current_item=current_item,
        completed_count=done_count,
        total_count=len(tasks),
        day_context=DayContextResponse(
            energy_level=day_plan.energy_level,
            budget_limit=day_plan.budget_limit,
            work_override_mode=day_plan.work_override_mode,
            work_start_time=effective_work_window(day_plan, user)[0],
            work_end_time=effective_work_window(day_plan, user)[1],
        ),
        tasks=task_responses,
        goals=[goal_to_response(goal) for goal in goals],
        routines=[routine_to_response(routine) for routine in routines],
        plan=plan,
        plan_version=day_plan.version,
    )


def _snapshot_plan_placements(
    db: Session,
    user: User,
) -> dict[tuple[date, int], _PlanPlacementSnapshot]:
    snapshots: dict[tuple[date, int], _PlanPlacementSnapshot] = {}
    day_plans = db.query(DayPlan).filter(DayPlan.user_id == user.id).all()

    for day_plan in day_plans:
        for item in day_plan.items:
            if item.task_id is None:
                continue

            snapshots[(day_plan.date, item.task_id)] = _PlanPlacementSnapshot(
                task_id=item.task_id,
                title=item.title,
                start_time=item.start_time,
                end_time=item.end_time,
                status=item.status,
            )

    return snapshots


def _build_plan_diff(
    db: Session,
    user: User,
    mutation: TaskMutationResult,
    before: dict[tuple[date, int], _PlanPlacementSnapshot],
    plan_results: list[PlanBuildResult],
    *,
    conflict: str | None = None,
    clarification: str | None = None,
    availability_change: str | None = None,
) -> PlanDiffResponse:
    after = _snapshot_plan_placements(db, user)
    moved: list[MovedPlanItemResponse] = []

    for key, previous in before.items():
        current = after.get(key)

        if (
            current
            and previous.start_time
            and current.start_time
            and previous.start_time != current.start_time
        ):
            moved.append(
                MovedPlanItemResponse(
                    task_id=current.task_id,
                    title=current.title,
                    old_start=previous.start_time,
                    new_start=current.start_time,
                )
            )

    unscheduled_ids = sorted(
        {
            task_id
            for plan_result in plan_results
            for task_id in plan_result.unscheduled_task_ids
        }
    )

    return PlanDiffResponse(
        created_task_ids=[task.id for task in mutation.created],
        updated_task_ids=[task.id for task in mutation.updated],
        completed_task_ids=[task.id for task in mutation.completed],
        cancelled_task_ids=[task.id for task in mutation.cancelled],
        moved_plan_items=moved,
        unscheduled_task_ids=unscheduled_ids,
        availability_change=availability_change,
        conflict=conflict,
        clarification=clarification,
    )


def _unique_tasks(tasks: list[Task]) -> list[Task]:
    unique: list[Task] = []
    seen: set[int] = set()

    for task in tasks:
        if task.id in seen:
            continue

        seen.add(task.id)
        unique.append(task)

    return unique


def _task_mutation_reply(
    mutation: TaskMutationResult,
    day_plan: DayPlan,
    user: User,
) -> str:
    sections: list[str] = []

    if mutation.created:
        sections.append("Добавлено:\n" + "\n".join(f"+ {task.title}" for task in mutation.created))

    if mutation.updated:
        sections.append("Обновлено:\n" + "\n".join(f"→ {task.title}" for task in mutation.updated))

    if mutation.completed:
        sections.append("Выполнено:\n" + "\n".join(f"✓ {task.title}" for task in mutation.completed))

    if mutation.cancelled:
        sections.append("Отменено:\n" + "\n".join(f"- {task.title}" for task in mutation.cancelled))

    if not sections:
        sections.append("Новых изменений в задачах нет.")

    return (
        "Принял. План обновлён по фактическим изменениям.\n\n"
        + "\n\n".join(sections)
        + f"\n\n{format_day_plan(day_plan, user=user)}{_planning_context_hint(user)}"
    )


def _format_work_window(start: time | None, end: time | None) -> str:
    start_text = _format_clock(start, missing="начало не указано")
    end_text = _format_clock(end, missing="конец не указан")
    return f"{start_text}–{end_text}"


def _format_clock(value: time | None, *, missing: str = "время не указано") -> str:
    return value.strftime("%H:%M") if value else missing


def _process_work_schedule_message(
    db: Session,
    user: User,
    user_external_id: str,
    source: MessageSource,
    parsed_message: ParsedUserMessage,
) -> MessageResponse:
    next_start = time.fromisoformat(parsed_message.work_start) if parsed_message.work_start else user.work_start_time
    next_end = time.fromisoformat(parsed_message.work_until) if parsed_message.work_until else user.work_end_time
    next_sleep = time.fromisoformat(parsed_message.sleep_time) if parsed_message.sleep_time else user.sleep_time
    changed = (
        next_start != user.work_start_time
        or next_end != user.work_end_time
        or next_sleep != user.sleep_time
    )
    window = _format_work_window(next_start, next_end)

    if not changed:
        return _base_response(
            user_external_id,
            source,
            parsed_message,
            f"Рабочее время уже установлено: {window}. План менять не пришлось.",
            user=user,
            status="no_change",
        )

    before = _snapshot_plan_placements(db, user)

    try:
        update_user_profile_from_parsed_message(
            db=db,
            user=user,
            parsed_message=parsed_message,
            commit=False,
        )
        plan_result = build_day_plan_result(
            db=db,
            user=user,
            plan_date=get_plan_date(user=user),
            commit=False,
        )
        change = f"Рабочее время обновлено: {window}."
        plan_diff = _build_plan_diff(
            db,
            user,
            TaskMutationResult(),
            before,
            [plan_result],
            availability_change=change,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    return _base_response(
        user_external_id,
        source,
        parsed_message,
        change,
        user=user,
        day_plan=plan_result.day_plan,
        plan_diff=plan_diff,
    )


def _process_day_availability_message(
    db: Session,
    user: User,
    user_external_id: str,
    source: MessageSource,
    parsed_message: ParsedUserMessage,
) -> MessageResponse:
    plan_date = get_plan_date(parsed_message, user=user)
    existing = (
        db.query(DayPlan)
        .filter(DayPlan.user_id == user.id, DayPlan.date == plan_date)
        .one_or_none()
    )
    next_mode = "off" if parsed_message.work_context == "off" else "busy"
    next_start = time.fromisoformat(parsed_message.work_start) if parsed_message.work_start else None
    next_end = time.fromisoformat(parsed_message.work_until) if parsed_message.work_until else None
    changed = (
        existing is None
        or existing.work_override_mode != next_mode
        or existing.work_start_time != next_start
        or existing.work_end_time != next_end
    )

    if not changed:
        label = format_plan_date(plan_date, user=user).capitalize()
        reply = (
            f"{label} уже отмечен как день без работы."
            if next_mode == "off"
            else f"Рабочее время на {format_plan_date(plan_date, user=user)} уже установлено."
        )
        return _base_response(
            user_external_id,
            source,
            parsed_message,
            reply,
            day_plan=existing,
            status="no_change",
        )

    before = _snapshot_plan_placements(db, user)

    try:
        plan_result = build_day_plan_result(
            db=db,
            user=user,
            parsed_message=parsed_message,
            plan_date=plan_date,
            commit=False,
        )
        effective_start, effective_end = effective_work_window(plan_result.day_plan, user)
        day_label = format_plan_date(plan_date, user=user)
        change = (
            f"На {day_label} рабочее время отключено."
            if next_mode == "off"
            else f"Рабочее время на {day_label} обновлено: {_format_work_window(effective_start, effective_end)}."
        )
        plan_diff = _build_plan_diff(
            db,
            user,
            TaskMutationResult(),
            before,
            [plan_result],
            availability_change=change,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    return _base_response(
        user_external_id,
        source,
        parsed_message,
        change,
        day_plan=plan_result.day_plan,
        plan_diff=plan_diff,
    )


def _base_response(
    user_external_id: str,
    source: MessageSource,
    parsed_message: ParsedUserMessage,
    reply_text: str,
    *,
    affected_tasks: list[Task] | None = None,
    affected_goals: list[Goal] | None = None,
    affected_routines: list[Routine] | None = None,
    user: User | None = None,
    day_plan: DayPlan | None = None,
    status: MessageStatus = "applied",
    reason: MessageReason | None = None,
    clarification_question: str | None = None,
    plan_diff: PlanDiffResponse | None = None,
    clarification: ClarificationResponse | None = None,
    confirmation: ConfirmationResponse | None = None,
    conflict_details: ConflictResponse | None = None,
) -> MessageResponse:
    return MessageResponse(
        user_external_id=user_external_id,
        source=source,
        intent=parsed_message.intent,
        parsed=parsed_message.model_dump(mode="json"),
        status=status,
        reason=reason,
        needs_clarification=status in {
            "needs_clarification",
            "clarification_required",
            "conflict",
        },
        clarification_question=clarification_question,
        reply_text=reply_text,
        summary=reply_text,
        affected_tasks=[task_to_response(task) for task in affected_tasks or []],
        affected_goals=[goal_to_response(goal) for goal in affected_goals or []],
        affected_routines=[routine_to_response(routine) for routine in affected_routines or []],
        profile=profile_to_response(user, user_external_id) if user else None,
        plan_summary=plan_to_response(day_plan) if day_plan else None,
        plan_diff=plan_diff or PlanDiffResponse(),
        clarification=clarification,
        confirmation=confirmation,
        conflict_details=conflict_details,
    )


def _ensure_task_operations(parsed_message: ParsedUserMessage) -> None:
    if parsed_message.intent == "mark_done" and not parsed_message.tasks and parsed_message.done_task_title:
        parsed_message.tasks = [
            ParsedTask(
                title=parsed_message.done_task_title,
                operation="complete",
                target_date=parsed_message.date,
                referenced_task_title=parsed_message.done_task_title,
            )
        ]


def _process_task_operations_message(
    db: Session,
    user: User,
    user_external_id: str,
    source: MessageSource,
    parsed_message: ParsedUserMessage,
) -> MessageResponse:
    _ensure_task_operations(parsed_message)
    before = _snapshot_plan_placements(db, user)

    try:
        mutation = apply_parsed_task_operations(
            db=db,
            user=user,
            parsed_message=parsed_message,
            commit=False,
        )

        if mutation.needs_clarification:
            db.rollback()
            question = mutation.clarification_question or "Уточни, как изменить план."
            return _base_response(
                user_external_id,
                source,
                parsed_message,
                question,
                status="clarification_required",
                clarification_question=question,
                plan_diff=PlanDiffResponse(clarification=question),
            )

        selected_date = get_plan_date(parsed_message, user=user)
        affected_dates = set(mutation.affected_dates) or {selected_date}
        plan_results: list[PlanBuildResult] = []

        for affected_date in sorted(affected_dates):
            plan_results.append(
                build_day_plan_result(
                    db=db,
                    user=user,
                    parsed_message=parsed_message if affected_date == selected_date else None,
                    plan_date=affected_date,
                    commit=False,
                )
            )

        conflicts = [
            conflict
            for plan_result in plan_results
            for conflict in plan_result.conflicts
        ]

        if conflicts:
            conflict_message = conflicts[0].message
            db.rollback()
            return _base_response(
                user_external_id,
                source,
                parsed_message,
                conflict_message,
                status="conflict",
                clarification_question=conflict_message,
                plan_diff=PlanDiffResponse(conflict=conflict_message),
            )

        response_date = selected_date

        if mutation.created:
            response_date = mutation.created[-1].target_date
        elif mutation.updated:
            response_date = mutation.updated[-1].target_date
        elif mutation.completed:
            response_date = mutation.completed[-1].target_date
        elif mutation.cancelled:
            response_date = mutation.cancelled[-1].target_date

        selected_result = next(
            (result for result in plan_results if result.day_plan.date == response_date),
            plan_results[-1],
        )
        plan_diff = _build_plan_diff(
            db=db,
            user=user,
            mutation=mutation,
            before=before,
            plan_results=plan_results,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    affected_tasks = _unique_tasks(
        mutation.created + mutation.updated + mutation.completed + mutation.cancelled
    )
    reply_text = _task_mutation_reply(mutation, selected_result.day_plan, user)

    response_status = "applied" if affected_tasks else "no_change"

    return _base_response(
        user_external_id,
        source,
        parsed_message,
        reply_text,
        affected_tasks=affected_tasks,
        day_plan=selected_result.day_plan,
        plan_diff=plan_diff,
        status=response_status,
    )


def _process_parsed_user_message(
    db: Session,
    user: User,
    user_external_id: str,
    parsed_message: ParsedUserMessage,
    source: MessageSource = "telegram_text",
) -> MessageResponse:
    if parsed_message.intent in {"add_tasks", "create_task", "create_event", "mark_done"} or (
        parsed_message.intent == "reschedule" and parsed_message.tasks
    ):
        return _process_task_operations_message(
            db=db,
            user=user,
            user_external_id=user_external_id,
            source=source,
            parsed_message=parsed_message,
        )

    if parsed_message.intent == "show_goals":
        goals = list_active_goals(db=db, user=user)
        reply_text = f"Твои цели:\n\n{format_goals(goals)}"
        return _base_response(
            user_external_id,
            source,
            parsed_message,
            reply_text,
            affected_goals=goals,
        )

    if parsed_message.intent == "update_goals":
        created_goals = create_goals_from_titles(db=db, user=user, titles=parsed_message.goals)
        all_goals = list_active_goals(db=db, user=user)
        goals_text = format_goals(all_goals)

        if created_goals:
            reply_text = (
                "Запомнил цели:\n\n"
                + "\n".join(f"- {goal.title}" for goal in created_goals)
                + "\n\nТекущий список целей:\n\n"
                + goals_text
            )
        else:
            reply_text = (
                "Не нашел новых целей или они уже были добавлены.\n\n"
                f"Текущий список целей:\n\n{goals_text}"
            )

        return _base_response(
            user_external_id,
            source,
            parsed_message,
            reply_text,
            affected_goals=created_goals,
        )

    if parsed_message.intent == "suggest_goal_tasks":
        goals = list_active_goals(db=db, user=user)

        if not goals:
            reply_text = (
                "Пока нет активных целей.\n\n"
                "Напиши обычным текстом, к чему хочешь прийти. Например: "
                "«Моя цель: накопить резерв, научиться рисовать, улучшить здоровье»."
            )
            return _base_response(
                user_external_id,
                source,
                parsed_message,
                reply_text,
            )

        suggested_tasks = suggest_tasks_from_goals(goals)
        before = _snapshot_plan_placements(db, user)

        try:
            tasks = create_tasks_from_parsed_tasks(
                db=db,
                user=user,
                parsed_tasks=suggested_tasks,
                parsed_message=parsed_message,
                commit=False,
            )
            plan_result = build_day_plan_result(
                db=db,
                user=user,
                parsed_message=parsed_message,
                commit=False,
            )

            if plan_result.conflicts:
                conflict_message = plan_result.conflicts[0].message
                db.rollback()
                return _base_response(
                    user_external_id,
                    source,
                    parsed_message,
                    conflict_message,
                    status="conflict",
                    clarification_question=conflict_message,
                    plan_diff=PlanDiffResponse(conflict=conflict_message),
                )

            mutation = TaskMutationResult(
                created=tasks,
                affected_dates={plan_result.day_plan.date},
            )
            plan_diff = _build_plan_diff(
                db=db,
                user=user,
                mutation=mutation,
                before=before,
                plan_results=[plan_result],
            )
            db.commit()
        except Exception:
            db.rollback()
            raise

        day_plan = plan_result.day_plan
        plan_text = format_day_plan(day_plan, user=user)
        task_lines = "\n".join(f"- {task.title}" for task in tasks)
        prefix = f"Добавил задачи по целям:\n\n{task_lines}" if tasks else "Задачи по целям уже есть в активном плане."
        reply_text = f"{prefix}\n\nПлан дня:\n\n{plan_text}{_planning_context_hint(user)}"

        return _base_response(
            user_external_id,
            source,
            parsed_message,
            reply_text,
            affected_tasks=tasks,
            day_plan=day_plan,
            plan_diff=plan_diff,
        )

    if parsed_message.intent == "show_profile":
        reply_text = f"Твой профиль:\n\n{format_user_profile(user)}"
        return _base_response(
            user_external_id,
            source,
            parsed_message,
            reply_text,
            user=user,
        )

    if parsed_message.intent == "update_profile":
        user = update_user_profile_from_parsed_message(db=db, user=user, parsed_message=parsed_message)
        reply_text = (
            "Запомнил настройки профиля:\n\n"
            f"{format_user_profile(user)}\n\n"
            "Теперь буду учитывать это при планировании."
        )

    if parsed_message.intent == "set_work_schedule":
        return _process_work_schedule_message(
            db,
            user,
            user_external_id,
            source,
            parsed_message,
        )

    if parsed_message.intent == "set_day_availability":
        return _process_day_availability_message(
            db,
            user,
            user_external_id,
            source,
            parsed_message,
        )
        return _base_response(
            user_external_id,
            source,
            parsed_message,
            reply_text,
            user=user,
        )

    if parsed_message.intent == "show_plan":
        day_plan = rebuild_day_plan(db=db, user=user, parsed_message=parsed_message)
        reply_text = (
            f"Текущий план дня:\n\n{format_day_plan(day_plan, user=user)}"
            f"{_planning_context_hint(user)}"
        )
        return _base_response(
            user_external_id,
            source,
            parsed_message,
            reply_text,
            day_plan=day_plan,
        )

    if parsed_message.intent == "show_tasks":
        task_date = get_plan_date(parsed_message, user=user) if parsed_message.date else None
        tasks = list_active_tasks(db=db, user=user, target_date=task_date)
        reply_text = f"Активные задачи:\n\n{format_tasks(tasks)}"
        return _base_response(
            user_external_id,
            source,
            parsed_message,
            reply_text,
            affected_tasks=tasks,
        )

    if parsed_message.intent == "clear_tasks":
        before = _snapshot_plan_placements(db, user)
        selected_date = get_plan_date(parsed_message, user=user)
        affected_dates = {plan_date for plan_date, _ in before} | {selected_date}

        try:
            count = clear_user_tasks(db=db, user=user, commit=False)
            plan_results = [
                build_day_plan_result(
                    db=db,
                    user=user,
                    parsed_message=parsed_message if affected_date == selected_date else None,
                    plan_date=affected_date,
                    commit=False,
                )
                for affected_date in sorted(affected_dates)
            ]
            plan_result = next(
                result for result in plan_results if result.day_plan.date == selected_date
            )
            plan_diff = _build_plan_diff(
                db=db,
                user=user,
                mutation=TaskMutationResult(affected_dates={plan_result.day_plan.date}),
                before=before,
                plan_results=plan_results,
            )
            db.commit()
        except Exception:
            db.rollback()
            raise

        day_plan = plan_result.day_plan
        reply_text = f"Очистил задачи: {count}.\n\nПлан дня очищен.{_planning_context_hint(user)}"
        return _base_response(
            user_external_id,
            source,
            parsed_message,
            reply_text,
            day_plan=day_plan,
            plan_diff=plan_diff,
        )

    if parsed_message.intent == "daily_summary":
        summary_date = get_plan_date(parsed_message, user=user)
        before = _snapshot_plan_placements(db, user)

        try:
            done_tasks = mark_tasks_done_by_titles(
                db=db,
                user=user,
                titles=parsed_message.done_task_titles,
                target_date=summary_date,
                commit=False,
            )
            skipped_tasks = find_active_tasks_by_titles(
                db=db,
                user=user,
                titles=parsed_message.skipped_task_titles,
                target_date=summary_date,
            )
            plan_result = build_day_plan_result(
                db=db,
                user=user,
                parsed_message=parsed_message,
                plan_date=summary_date,
                commit=False,
            )

            if plan_result.conflicts:
                conflict_message = plan_result.conflicts[0].message
                db.rollback()
                return _base_response(
                    user_external_id,
                    source,
                    parsed_message,
                    conflict_message,
                    status="conflict",
                    clarification_question=conflict_message,
                    plan_diff=PlanDiffResponse(conflict=conflict_message),
                )

            mutation = TaskMutationResult(
                completed=done_tasks,
                affected_dates={summary_date},
            )
            plan_diff = _build_plan_diff(
                db=db,
                user=user,
                mutation=mutation,
                before=before,
                plan_results=[plan_result],
            )
            db.commit()
        except Exception:
            db.rollback()
            raise

        day_plan = plan_result.day_plan
        plan_text = format_day_plan(day_plan, user=user)
        done_text = "\n".join(f"- {task.title}" for task in done_tasks) or "ничего не отметил"
        skipped_text = "\n".join(f"- {task.title}" for task in skipped_tasks) or "нет"
        reply_text = (
            "Итог дня принял.\n\n"
            f"Выполнено:\n{done_text}\n\n"
            f"Осталось активным:\n{skipped_text}\n\n"
            f"Обновленный план:\n\n{plan_text}{_planning_context_hint(user)}"
        )
        return _base_response(
            user_external_id,
            source,
            parsed_message,
            reply_text,
            affected_tasks=done_tasks + skipped_tasks,
            day_plan=day_plan,
            plan_diff=plan_diff,
        )

    if parsed_message.intent == "reschedule":
        before = _snapshot_plan_placements(db, user)

        try:
            plan_result = build_day_plan_result(
                db=db,
                user=user,
                parsed_message=parsed_message,
                commit=False,
            )

            if plan_result.conflicts:
                conflict_message = plan_result.conflicts[0].message
                db.rollback()
                return _base_response(
                    user_external_id,
                    source,
                    parsed_message,
                    conflict_message,
                    status="conflict",
                    clarification_question=conflict_message,
                    plan_diff=PlanDiffResponse(conflict=conflict_message),
                )

            plan_diff = _build_plan_diff(
                db=db,
                user=user,
                mutation=TaskMutationResult(affected_dates={plan_result.day_plan.date}),
                before=before,
                plan_results=[plan_result],
            )
            db.commit()
        except Exception:
            db.rollback()
            raise

        day_plan = plan_result.day_plan
        reply_text = (
            "Ок, перепланировал день с учетом изменений:\n\n"
            f"{format_day_plan(day_plan, user=user)}{_planning_context_hint(user)}"
        )
        return _base_response(
            user_external_id,
            source,
            parsed_message,
            reply_text,
            day_plan=day_plan,
            plan_diff=plan_diff,
        )

    reply_text = "Не понял, какое изменение нужно внести. Опиши задачу или ограничение другими словами."
    return _base_response(user_external_id, source, parsed_message, reply_text)


def _option_models(options: list[dict]) -> list[InteractionOptionResponse]:
    return [InteractionOptionResponse.model_validate(option) for option in options]


def _clarification_payload(interaction) -> ClarificationResponse:
    return ClarificationResponse(
        id=interaction.id,
        question=interaction.question or "Уточни, что нужно сделать.",
        options=_option_models(interaction.options),
        free_text_allowed=True,
        expires_at=interaction.expires_at,
    )


def _confirmation_payload(interaction) -> ConfirmationResponse:
    context = interaction.context or {}
    return ConfirmationResponse(
        id=interaction.id,
        title=context.get("title", "Применить изменение?"),
        summary=context.get("summary", interaction.question or "Проверь изменение перед применением."),
        options=_option_models(interaction.options),
        expires_at=interaction.expires_at,
        base_plan_version=interaction.base_plan_version,
    )


def _conflict_payload(interaction, message: str) -> ConflictResponse:
    return ConflictResponse(
        id=interaction.id,
        message=message,
        options=_option_models(interaction.options),
        expires_at=interaction.expires_at,
    )


def _current_plan_version(db: Session, user: User, plan_date: date) -> int:
    plan = (
        db.query(DayPlan)
        .filter(DayPlan.user_id == user.id, DayPlan.date == plan_date)
        .one_or_none()
    )
    return plan.version if plan else 0


def _build_tracking_clarification(
    db: Session,
    user: User,
    user_external_id: str,
    source: MessageSource,
    parsed_message: ParsedUserMessage,
    *,
    subject: str,
    one_time_title: str,
    routine_title: str,
) -> MessageResponse:
    options = [
        {
            "id": "routine",
            "label": f"Ежедневно напоминать: {routine_title}",
            "value": "ежедневное напоминание",
        },
        {
            "id": "one_time",
            "label": "Разовую задачу на сегодня",
            "value": "разовая задача",
        },
        {
            "id": "capability",
            "label": "Отдельный трекер",
            "value": "отдельный трекер",
        },
    ]
    interaction = create_pending_interaction(
        db,
        user,
        source=source,
        kind="clarification",
        original_message=parsed_message.raw_text or subject,
        context={
            "flow": "tracking_kind",
            "subject": subject,
            "one_time_title": one_time_title,
            "routine_title": routine_title,
            "parsed_message": parsed_message.model_dump(mode="json"),
        },
        question="Что именно добавить?",
        options=options,
    )
    clarification = _clarification_payload(interaction)
    reply = (
        "Что именно добавить?\n\n"
        f"• Ежедневно напоминать: {routine_title}\n"
        "• Разовую задачу на сегодня\n"
        "• Отдельный трекер\n\n"
        "Можно выбрать вариант или ответить своими словами."
    )
    return _base_response(
        user_external_id,
        source,
        parsed_message,
        reply,
        status="clarification_required",
        clarification_question=clarification.question,
        clarification=clarification,
        plan_diff=PlanDiffResponse(clarification=clarification.question),
    )


def _build_work_schedule_clarification(
    db: Session,
    user: User,
    user_external_id: str,
    source: MessageSource,
    parsed_message: ParsedUserMessage,
) -> MessageResponse:
    start = time.fromisoformat(parsed_message.work_start) if parsed_message.work_start else None
    end = time.fromisoformat(parsed_message.work_until) if parsed_message.work_until else None
    question = (
        f"Ты хочешь указать рабочее время с {_format_clock(start)} "
        f"до {_format_clock(end)} или добавить отдельную задачу?"
    )
    options = [
        {"id": "work_schedule", "label": "Рабочее время", "value": "рабочее время"},
        {"id": "task", "label": "Отдельная задача", "value": "отдельная задача"},
        {"id": "cancel", "label": "Отмена", "value": "отмена"},
    ]
    interaction = create_pending_interaction(
        db,
        user,
        source=source,
        kind="clarification",
        original_message=parsed_message.raw_text or "",
        context={
            "flow": "work_schedule_ambiguity",
            "parsed_message": parsed_message.model_dump(mode="json"),
        },
        question=question,
        options=options,
    )
    clarification = _clarification_payload(interaction)
    return _base_response(
        user_external_id,
        source,
        parsed_message,
        question,
        status="clarification_required",
        clarification_question=question,
        clarification=clarification,
        plan_diff=PlanDiffResponse(clarification=question),
    )


def _build_work_schedule_confirmation(
    db: Session,
    user: User,
    user_external_id: str,
    source: MessageSource,
    parsed_message: ParsedUserMessage,
) -> MessageResponse:
    start = time.fromisoformat(parsed_message.work_start) if parsed_message.work_start else user.work_start_time
    end = time.fromisoformat(parsed_message.work_until) if parsed_message.work_until else user.work_end_time
    summary = f"Постоянный график по будням: {_format_work_window(start, end)}."
    interaction = create_pending_interaction(
        db,
        user,
        source=source,
        kind="confirmation",
        original_message=parsed_message.raw_text or "",
        context={
            "flow": "work_schedule_confirmation",
            "title": "Обновить постоянный рабочий график?",
            "summary": summary,
            "parsed_message": parsed_message.model_dump(mode="json"),
        },
        question=summary,
        options=[
            {"id": "apply", "label": "Применить", "value": "применить"},
            {"id": "cancel", "label": "Отмена", "value": "отмена"},
        ],
        base_plan_version=_current_plan_version(db, user, get_plan_date(user=user)),
    )
    confirmation = _confirmation_payload(interaction)
    return _base_response(
        user_external_id,
        source,
        parsed_message,
        f"{confirmation.title}\n\n{confirmation.summary}",
        status="confirmation_required",
        confirmation=confirmation,
    )


def _build_day_off_confirmation(
    db: Session,
    user: User,
    user_external_id: str,
    source: MessageSource,
    parsed_message: ParsedUserMessage,
) -> MessageResponse:
    plan_date = get_plan_date(parsed_message, user=user)
    day_label = format_plan_date(plan_date, user=user)
    summary = f"Убрать рабочее время только на {day_label}? Постоянный профиль не изменится."
    interaction = create_pending_interaction(
        db,
        user,
        source=source,
        kind="confirmation",
        original_message=parsed_message.raw_text or "",
        context={
            "flow": "day_off_confirmation",
            "title": "Отметить день без работы?",
            "summary": summary,
            "parsed_message": parsed_message.model_dump(mode="json"),
        },
        question=summary,
        options=[
            {"id": "apply", "label": "Применить", "value": "применить"},
            {"id": "cancel", "label": "Отмена", "value": "отмена"},
        ],
        base_plan_version=_current_plan_version(db, user, plan_date),
    )
    confirmation = _confirmation_payload(interaction)
    return _base_response(
        user_external_id,
        source,
        parsed_message,
        f"{confirmation.title}\n\n{confirmation.summary}",
        status="confirmation_required",
        confirmation=confirmation,
    )


def _create_routine_confirmation(
    db: Session,
    user: User,
    user_external_id: str,
    source: MessageSource,
    parsed_message: ParsedUserMessage,
    *,
    title: str,
    preferred_window: str | None = None,
    fixed_time: time | None = None,
    cadence: str = "daily",
    weekdays: list[int] | None = None,
) -> MessageResponse:
    window_labels = {
        "morning": "утром",
        "afternoon": "днём",
        "evening": "вечером",
    }
    schedule_label = (
        f"в {fixed_time.strftime('%H:%M')}"
        if fixed_time
        else window_labels.get(preferred_window or "", preferred_window or "без точного времени")
    )
    cadence_label = {
        "daily": "каждый день",
        "weekdays": "по будням",
        "selected_weekdays": "в выбранные дни",
    }.get(cadence, cadence)
    summary = f"{title}. {cadence_label.capitalize()} · {schedule_label}."
    options = [
        {"id": "apply", "label": "Применить", "value": "применить"},
        {"id": "edit", "label": "Изменить", "value": "изменить"},
        {"id": "cancel", "label": "Отмена", "value": "отмена"},
    ]
    target_date = get_plan_date(parsed_message, user=user)
    interaction = create_pending_interaction(
        db,
        user,
        source=source,
        kind="confirmation",
        original_message=parsed_message.raw_text or title,
        context={
            "flow": "create_routine",
            "title": "Добавить регулярное напоминание?",
            "summary": summary,
            "routine_title": title,
            "cadence": cadence,
            "weekdays": weekdays or [],
            "preferred_window": preferred_window,
            "fixed_time": fixed_time.isoformat() if fixed_time else None,
            "parsed_message": parsed_message.model_dump(mode="json"),
        },
        question=summary,
        options=options,
        base_plan_version=_current_plan_version(db, user, target_date),
    )
    confirmation = _confirmation_payload(interaction)
    return _base_response(
        user_external_id,
        source,
        parsed_message,
        f"{confirmation.title}\n\n{confirmation.summary}",
        status="confirmation_required",
        confirmation=confirmation,
    )


def _routine_schedule_from_text(text: str) -> tuple[str, list[int]]:
    lowered = text.lower().replace("ё", "е")

    if "по будням" in lowered:
        return "weekdays", []

    weekday_names = {
        "понедель": 0,
        "вторник": 1,
        "сред": 2,
        "четверг": 3,
        "пятниц": 4,
        "суббот": 5,
        "воскрес": 6,
    }
    selected = sorted({value for name, value in weekday_names.items() if name in lowered})

    if selected:
        return "selected_weekdays", selected

    return "daily", []


def _routine_time_options() -> list[dict[str, str]]:
    return [
        {"id": "morning", "label": "Утром", "value": "утром"},
        {"id": "afternoon", "label": "Днём", "value": "днём"},
        {"id": "evening", "label": "Вечером", "value": "вечером"},
        {"id": "exact_time", "label": "Указать точное время", "value": "точное время"},
        {"id": "cancel", "label": "Отмена", "value": "отмена"},
    ]


def _build_explicit_routine_interaction(
    db: Session,
    user: User,
    user_external_id: str,
    source: MessageSource,
    parsed_message: ParsedUserMessage,
) -> MessageResponse | None:
    if not is_explicit_routine_request(parsed_message.raw_text or ""):
        return None

    recurring = next((task for task in parsed_message.tasks if task.recurrence_hint), None)

    if recurring is None:
        return None

    title = normalize_routine_title(recurring.title)
    cadence, weekdays = _routine_schedule_from_text(parsed_message.raw_text or "")

    fixed_time = recurring.fixed_start or _fixed_time_from_text(parsed_message.raw_text or "")

    if recurring.preferred_window or fixed_time:
        return _create_routine_confirmation(
            db,
            user,
            user_external_id,
            source,
            parsed_message,
            title=title,
            preferred_window=recurring.preferred_window,
            fixed_time=fixed_time,
            cadence=cadence,
            weekdays=weekdays,
        )

    interaction = create_pending_interaction(
        db,
        user,
        source=source,
        kind="clarification",
        original_message=parsed_message.raw_text or title,
        context={
            "flow": "tracking_time",
            "routine_title": title,
            "cadence": cadence,
            "weekdays": weekdays,
            "parsed_message": parsed_message.model_dump(mode="json"),
        },
        question="Когда лучше напоминать?",
        options=_routine_time_options(),
    )
    return _repeat_clarification(user_external_id, source, parsed_message, interaction)


def _apply_routine_confirmation(
    db: Session,
    user: User,
    user_external_id: str,
    source: MessageSource,
    parsed_message: ParsedUserMessage,
    interaction,
) -> MessageResponse:
    user = db.query(User).filter(User.id == user.id).with_for_update().one()
    plan_date = get_plan_date(parsed_message, user=user)

    if interaction.base_plan_version != _current_plan_version(db, user, plan_date):
        resolve_interaction(db, interaction, status="stale")
        return _base_response(
            user_external_id,
            source,
            parsed_message,
            "План уже изменился. Повтори запрос, и я соберу актуальное предложение.",
            status="no_change",
        )

    context = interaction.context or {}
    before = _snapshot_plan_placements(db, user)

    try:
        resolve_interaction(db, interaction, commit=False)
        creation = create_routine(
            db,
            user,
            title=context["routine_title"],
            cadence=context.get("cadence", "daily"),
            weekdays=context.get("weekdays") or [],
            fixed_time=(
                time.fromisoformat(context["fixed_time"])
                if context.get("fixed_time")
                else None
            ),
            preferred_window=context.get("preferred_window"),
            estimated_minutes=10,
            start_date=plan_date,
            commit=False,
        )
        plan_result = build_day_plan_result(
            db=db,
            user=user,
            plan_date=plan_date,
            commit=False,
        )

        if plan_result.conflicts:
            db.rollback()
            message = plan_result.conflicts[0].message
            return _base_response(
                user_external_id,
                source,
                parsed_message,
                message,
                status="conflict",
                clarification_question=message,
                plan_diff=PlanDiffResponse(conflict=message),
            )

        mutation = TaskMutationResult(
            created=creation.occurrences,
            affected_dates={plan_date},
        )
        plan_diff = _build_plan_diff(db, user, mutation, before, [plan_result])

        if creation.created:
            plan_diff.created_routine_ids.append(creation.routine.id)

        db.commit()
    except Exception:
        db.rollback()
        raise

    status = "applied" if creation.created or creation.occurrences else "no_change"
    reply = (
        f"Добавил напоминание: {creation.routine.title}."
        if creation.created
        else "Такое напоминание уже существует. План не изменён."
    )
    return _base_response(
        user_external_id,
        source,
        parsed_message,
        reply,
        affected_tasks=creation.occurrences,
        affected_routines=[creation.routine],
        day_plan=plan_result.day_plan,
        plan_diff=plan_diff,
        status=status,
    )


def _build_low_energy_confirmation(
    db: Session,
    user: User,
    user_external_id: str,
    source: MessageSource,
    parsed_message: ParsedUserMessage,
) -> MessageResponse | None:
    plan_date = get_plan_date(parsed_message, user=user)
    day_plan = rebuild_day_plan(db=db, user=user, plan_date=plan_date)
    references = {
        (task.referenced_task_title or task.title).lower().replace("ё", "е")
        for task in parsed_message.tasks
        if task.referenced_task_title or task.title
    }
    candidates = [
        task
        for task in list_active_tasks(db=db, user=user, target_date=plan_date)
        if task.scheduling_type != "fixed"
        and not task.is_locked
        and task.priority != "high"
        and all(
            reference not in task.title.lower().replace("ё", "е")
            and task.title.lower().replace("ё", "е") not in reference
            for reference in references
        )
    ]

    if not candidates:
        return None

    moved_lines = "\n".join(f"→ {task.title} — на завтра" for task in candidates)
    summary = "Чтобы оставить главное, предлагаю:\n" + moved_lines
    options = [
        {"id": "apply", "label": "Применить изменения", "value": "применить"},
        {"id": "cancel", "label": "Оставить как есть", "value": "отмена"},
    ]
    interaction = create_pending_interaction(
        db,
        user,
        source=source,
        kind="confirmation",
        original_message=parsed_message.raw_text or "",
        context={
            "flow": "low_energy_replan",
            "title": "Освободить день?",
            "summary": summary,
            "move_task_ids": [task.id for task in candidates],
            "parsed_message": parsed_message.model_dump(mode="json"),
        },
        question=summary,
        options=options,
        base_plan_version=day_plan.version,
    )
    confirmation = _confirmation_payload(interaction)
    return _base_response(
        user_external_id,
        source,
        parsed_message,
        f"{confirmation.title}\n\n{confirmation.summary}",
        status="confirmation_required",
        confirmation=confirmation,
        day_plan=day_plan,
    )


def _apply_low_energy_replan(
    db: Session,
    user: User,
    user_external_id: str,
    source: MessageSource,
    parsed_message: ParsedUserMessage,
    interaction,
) -> MessageResponse:
    user = db.query(User).filter(User.id == user.id).with_for_update().one()
    plan_date = get_plan_date(parsed_message, user=user)
    current_version = _current_plan_version(db, user, plan_date)

    if interaction.base_plan_version != current_version:
        resolve_interaction(db, interaction, status="stale")
        return _base_response(
            user_external_id,
            source,
            parsed_message,
            "План уже изменился. Повтори запрос, и я соберу актуальное предложение.",
            status="no_change",
        )

    before = _snapshot_plan_placements(db, user)

    try:
        resolve_interaction(db, interaction, commit=False)
        mutation = apply_parsed_task_operations(
            db=db,
            user=user,
            parsed_message=parsed_message,
            commit=False,
        )

        if mutation.needs_clarification:
            db.rollback()
            question = mutation.clarification_question or "Уточни, какую задачу изменить."
            return _base_response(
                user_external_id,
                source,
                parsed_message,
                question,
                status="clarification_required",
                clarification_question=question,
                plan_diff=PlanDiffResponse(clarification=question),
            )

        tomorrow = plan_date.fromordinal(plan_date.toordinal() + 1)
        move_ids = set((interaction.context or {}).get("move_task_ids", []))
        moved_tasks = (
            db.query(Task)
            .filter(
                Task.user_id == user.id,
                Task.id.in_(move_ids),
                Task.target_date == plan_date,
                Task.status == "planned",
            )
            .all()
            if move_ids
            else []
        )

        for task in moved_tasks:
            task.target_date = tomorrow

        mutation.updated.extend(task for task in moved_tasks if task not in mutation.updated)
        mutation.affected_dates.update({plan_date, tomorrow})
        plan_results = [
            build_day_plan_result(
                db=db,
                user=user,
                parsed_message=parsed_message if affected_date == plan_date else None,
                plan_date=affected_date,
                commit=False,
            )
            for affected_date in sorted(mutation.affected_dates)
        ]
        conflicts = [conflict for result in plan_results for conflict in result.conflicts]

        if conflicts:
            db.rollback()
            message = conflicts[0].message
            return _base_response(
                user_external_id,
                source,
                parsed_message,
                message,
                status="conflict",
                clarification_question=message,
                plan_diff=PlanDiffResponse(conflict=message),
            )

        today_result = next(result for result in plan_results if result.day_plan.date == plan_date)
        plan_diff = _build_plan_diff(db, user, mutation, before, plan_results)
        db.commit()
    except Exception:
        db.rollback()
        raise

    affected = _unique_tasks(mutation.created + mutation.updated + mutation.completed + mutation.cancelled)
    return _base_response(
        user_external_id,
        source,
        parsed_message,
        "Изменения применены. Оставил главное и перенёс согласованные задачи на завтра.",
        affected_tasks=affected,
        day_plan=today_result.day_plan,
        plan_diff=plan_diff,
    )
def _preferred_window_from_text(text: str, option_id: str | None = None) -> str | None:
    if option_id in {"morning", "afternoon", "evening"}:
        return option_id

    lowered = text.lower().replace("ё", "е")

    if re.search(r"\b(?:утром|утро|с утра)\b", lowered):
        return "morning"

    if re.search(r"\b(?:днем|после обеда)\b", lowered):
        return "afternoon"

    if re.search(r"\b(?:вечером|вечер)\b", lowered):
        return "evening"

    return None


def _fixed_time_from_text(text: str) -> str | None:
    match = re.search(
        r"(?:\b(?:в|на)\s*(\d{1,2})(?::(\d{2}))?\b|^\s*(\d{1,2})(?::(\d{2}))?\s*$)",
        text,
        re.IGNORECASE,
    )

    if not match:
        return None

    hour = int(match.group(1) or match.group(3))
    minute = int(match.group(2) or match.group(4) or 0)

    if hour > 23 or minute > 59:
        return None

    return f"{hour:02d}:{minute:02d}"


def _repeat_clarification(
    user_external_id: str,
    source: MessageSource,
    parsed_message: ParsedUserMessage,
    interaction,
) -> MessageResponse:
    clarification = _clarification_payload(interaction)
    return _base_response(
        user_external_id,
        source,
        parsed_message,
        clarification.question,
        status="clarification_required",
        clarification_question=clarification.question,
        clarification=clarification,
        plan_diff=PlanDiffResponse(clarification=clarification.question),
    )


def _handle_pending_interaction(
    db: Session,
    user: User,
    user_external_id: str,
    source: MessageSource,
    text: str,
    interaction,
    option_id: str | None,
) -> MessageResponse:
    context = interaction.context or {}
    parsed_message = ParsedUserMessage.model_validate(
        context.get("parsed_message") or {"intent": "add_tasks", "raw_text": interaction.original_message}
    )

    if is_cancel_message(text) or option_id == "cancel":
        resolve_interaction(db, interaction, status="cancelled")
        return _base_response(
            user_external_id,
            source,
            parsed_message,
            "Хорошо, оставил план без изменений.",
            status="no_change",
        )

    selected = interaction_option(interaction.options, option_id, text)
    flow = context.get("flow")

    if flow == "work_schedule_ambiguity":
        if selected == "work_schedule":
            resolve_interaction(db, interaction, commit=False)
            parsed_message.intent = "set_work_schedule"
            parsed_message.work_context = "permanent"
            parsed_message.tasks = []
            return _process_work_schedule_message(
                db,
                user,
                user_external_id,
                source,
                parsed_message,
            )

        if selected == "task" and parsed_message.work_start and parsed_message.work_until:
            resolve_interaction(db, interaction, commit=False)
            start = time.fromisoformat(parsed_message.work_start)
            end = time.fromisoformat(parsed_message.work_until)
            duration = (end.hour * 60 + end.minute) - (start.hour * 60 + start.minute)

            if duration <= 0:
                duration += 24 * 60

            task_message = ParsedUserMessage(
                intent="create_task",
                date=parsed_message.date or "today",
                tasks=[
                    ParsedTask(
                        title="Работа",
                        scheduling_type="fixed",
                        target_date=parsed_message.date or "today",
                        fixed_start=parsed_message.work_start,
                        fixed_end=parsed_message.work_until,
                        estimated_minutes=duration,
                    )
                ],
                raw_text=interaction.original_message,
            )
            return _process_parsed_user_message(
                db,
                user,
                user_external_id,
                task_message,
                source,
            )

        return _repeat_clarification(user_external_id, source, parsed_message, interaction)

    if flow == "work_schedule_confirmation":
        if selected == "apply":
            resolve_interaction(db, interaction, commit=False)
            return _process_work_schedule_message(
                db,
                user,
                user_external_id,
                source,
                parsed_message,
            )

        return _base_response(
            user_external_id,
            source,
            parsed_message,
            interaction.question or "Применить постоянный рабочий график?",
            status="confirmation_required",
            confirmation=_confirmation_payload(interaction),
        )

    if flow == "day_off_confirmation":
        if selected == "apply":
            resolve_interaction(db, interaction, commit=False)
            return _process_day_availability_message(
                db,
                user,
                user_external_id,
                source,
                parsed_message,
            )

        return _base_response(
            user_external_id,
            source,
            parsed_message,
            interaction.question or "Убрать рабочее время на этот день?",
            status="confirmation_required",
            confirmation=_confirmation_payload(interaction),
        )

    if flow == "tracking_kind":
        lowered = text.lower().replace("ё", "е")

        if selected is None:
            if re.search(
                r"\b(?:ежеднев\w*|кажд\w*\s+день|регуляр\w*|напоминай\w*)\b",
                lowered,
            ):
                selected = "routine"
            elif re.search(r"\b(?:разов|один раз|на сегодня)\b", lowered):
                selected = "one_time"
            elif re.search(r"\b(?:трекер|счетчик|отдельн)\b", lowered):
                selected = "capability"

        if selected == "capability":
            resolve_interaction(db, interaction)
            return _base_response(
                user_external_id,
                source,
                parsed_message,
                "Отдельного трекера для этого пока нет. Могу добавить разовую задачу или ежедневное напоминание.",
                status="unsupported_capability",
            )

        if selected == "one_time":
            resolve_interaction(db, interaction, commit=False)
            one_time = ParsedUserMessage(
                intent="add_tasks",
                date="today",
                tasks=[task_for_one_time_tracking(context["one_time_title"])],
                raw_text=interaction.original_message,
            )
            return _process_parsed_user_message(
                db,
                user,
                user_external_id,
                one_time,
                source,
            )

        if selected == "routine":
            preferred_window = _preferred_window_from_text(text)
            fixed_time = _fixed_time_from_text(text)

            if preferred_window or fixed_time:
                return _create_routine_confirmation(
                    db,
                    user,
                    user_external_id,
                    source,
                    parsed_message,
                    title=context["routine_title"],
                    preferred_window=preferred_window,
                    fixed_time=time.fromisoformat(fixed_time) if fixed_time else None,
                )

            next_interaction = create_pending_interaction(
                db,
                user,
                source=source,
                kind="clarification",
                original_message=interaction.original_message,
                context={**context, "flow": "tracking_time"},
                question="Когда лучше напоминать?",
                options=_routine_time_options(),
            )
            return _repeat_clarification(
                user_external_id,
                source,
                parsed_message,
                next_interaction,
            )

        return _repeat_clarification(user_external_id, source, parsed_message, interaction)

    if flow == "tracking_time":
        preferred_window = _preferred_window_from_text(text, selected)
        fixed_time = _fixed_time_from_text(text)

        if selected == "exact_time" and fixed_time is None:
            next_interaction = create_pending_interaction(
                db,
                user,
                source=source,
                kind="clarification",
                original_message=interaction.original_message,
                context={**context, "flow": "tracking_exact_time"},
                question="Во сколько напоминать?",
                options=[{"id": "cancel", "label": "Отмена", "value": "отмена"}],
            )
            return _repeat_clarification(
                user_external_id,
                source,
                parsed_message,
                next_interaction,
            )

        if not preferred_window and not fixed_time:
            return _repeat_clarification(user_external_id, source, parsed_message, interaction)

        return _create_routine_confirmation(
            db,
            user,
            user_external_id,
            source,
            parsed_message,
            title=context["routine_title"],
            preferred_window=preferred_window,
            fixed_time=time.fromisoformat(fixed_time) if fixed_time else None,
            cadence=context.get("cadence", "daily"),
            weekdays=context.get("weekdays") or [],
        )

    if flow == "tracking_exact_time":
        fixed_time = _fixed_time_from_text(text)

        if not fixed_time:
            return _repeat_clarification(user_external_id, source, parsed_message, interaction)

        return _create_routine_confirmation(
            db,
            user,
            user_external_id,
            source,
            parsed_message,
            title=context["routine_title"],
            fixed_time=time.fromisoformat(fixed_time),
            cadence=context.get("cadence", "daily"),
            weekdays=context.get("weekdays") or [],
        )

    if flow in {"fixed_conflict", "fixed_time"}:
        fixed_start = _fixed_time_from_text(text)

        if selected == "choose_time" and not fixed_start:
            next_interaction = create_pending_interaction(
                db,
                user,
                source=source,
                kind="clarification",
                original_message=interaction.original_message,
                context={**context, "flow": "fixed_time"},
                question="На какое время поставить новое событие?",
                options=[{"id": "cancel", "label": "Отмена", "value": "отмена"}],
            )
            return _repeat_clarification(
                user_external_id,
                source,
                parsed_message,
                next_interaction,
            )

        if fixed_start and parsed_message.tasks:
            resolve_interaction(db, interaction, commit=False)
            parsed_message.tasks[0].fixed_start = fixed_start
            parsed_message.tasks[0].fixed_end = None
            parsed_message.tasks[0].scheduling_type = "fixed"
            parsed_message.tasks[0].needs_clarification = False
            return _process_parsed_user_message(
                db,
                user,
                user_external_id,
                parsed_message,
                source,
            )

        return _repeat_clarification(user_external_id, source, parsed_message, interaction)

    if flow == "task_clarification":
        if selected == "one_time" and parsed_message.tasks:
            resolve_interaction(db, interaction, commit=False)
            parsed_message.tasks[0].needs_clarification = False
            parsed_message.tasks[0].recurrence_hint = None
            parsed_message.tasks[0].scheduling_type = "flexible"
            return _process_parsed_user_message(
                db,
                user,
                user_external_id,
                parsed_message,
                source,
            )

        if selected == "routine" and parsed_message.tasks:
            preferred_window = parsed_message.tasks[0].preferred_window or _preferred_window_from_text(text)
            fixed_time = parsed_message.tasks[0].fixed_start

            if preferred_window or fixed_time:
                return _create_routine_confirmation(
                    db,
                    user,
                    user_external_id,
                    source,
                    parsed_message,
                    title=parsed_message.tasks[0].title,
                    preferred_window=preferred_window,
                    fixed_time=fixed_time,
                    cadence=_routine_schedule_from_text(interaction.original_message)[0],
                    weekdays=_routine_schedule_from_text(interaction.original_message)[1],
                )

        return _repeat_clarification(user_external_id, source, parsed_message, interaction)

    if flow == "low_energy_replan":
        if selected == "apply":
            return _apply_low_energy_replan(
                db,
                user,
                user_external_id,
                source,
                parsed_message,
                interaction,
            )

        return _base_response(
            user_external_id,
            source,
            parsed_message,
            interaction.question or "Применить изменения?",
            status="confirmation_required",
            confirmation=_confirmation_payload(interaction),
        )

    if flow == "create_routine":
        if selected == "apply":
            return _apply_routine_confirmation(
                db,
                user,
                user_external_id,
                source,
                parsed_message,
                interaction,
            )

        if selected == "edit":
            next_interaction = create_pending_interaction(
                db,
                user,
                source=source,
                kind="clarification",
                original_message=interaction.original_message,
                context={**context, "flow": "tracking_time"},
                question="Когда лучше напоминать?",
                options=_routine_time_options(),
            )
            return _repeat_clarification(
                user_external_id,
                source,
                parsed_message,
                next_interaction,
            )

        return _base_response(
            user_external_id,
            source,
            parsed_message,
            interaction.question or "Применить напоминание?",
            status="confirmation_required",
            confirmation=_confirmation_payload(interaction),
        )

    return _repeat_clarification(user_external_id, source, parsed_message, interaction)


def _persist_response_interaction(
    db: Session,
    user: User,
    user_external_id: str,
    source: MessageSource,
    parsed_message: ParsedUserMessage,
    response: MessageResponse,
) -> MessageResponse:
    if response.status == "clarification_required" and response.clarification is None:
        is_recurrence = any(task.recurrence_hint for task in parsed_message.tasks)
        options = (
            [
                {"id": "routine", "label": "Регулярное напоминание", "value": "регулярно"},
                {"id": "one_time", "label": "Разовая задача", "value": "разовая задача"},
                {"id": "cancel", "label": "Отмена", "value": "отмена"},
            ]
            if is_recurrence
            else [{"id": "cancel", "label": "Отмена", "value": "отмена"}]
        )
        question = response.clarification_question or "Уточни, что нужно сделать."
        interaction = create_pending_interaction(
            db,
            user,
            source=source,
            kind="clarification",
            original_message=parsed_message.raw_text or "",
            context={
                "flow": "task_clarification",
                "parsed_message": parsed_message.model_dump(mode="json"),
            },
            question=question,
            options=options,
        )
        response.clarification = _clarification_payload(interaction)

    if response.status == "conflict" and response.conflict_details is None:
        message = response.plan_diff.conflict or response.reply_text
        options = [
            {"id": "choose_time", "label": "Выбрать другое время", "value": "другое время"},
            {"id": "cancel", "label": "Отмена", "value": "отмена"},
        ]
        interaction = create_pending_interaction(
            db,
            user,
            source=source,
            kind="conflict",
            original_message=parsed_message.raw_text or "",
            context={
                "flow": "fixed_conflict",
                "parsed_message": parsed_message.model_dump(mode="json"),
            },
            question=message,
            options=options,
        )
        response.conflict_details = _conflict_payload(interaction, message)

    return response


def _attach_day_snapshot(
    db: Session,
    user: User,
    response: MessageResponse,
    parsed_message: ParsedUserMessage,
) -> None:
    plan_date = get_plan_date(user=user)
    day_plan = (
        db.query(DayPlan)
        .filter(DayPlan.user_id == user.id, DayPlan.date == plan_date)
        .one_or_none()
    )

    if day_plan is None:
        day_plan = rebuild_day_plan(db=db, user=user, plan_date=plan_date)

    if response.plan_summary is None:
        response.plan_summary = plan_to_response(day_plan)
    response.day_snapshot = day_snapshot_to_response(db, user, day_plan)


def _run_standard_message(
    db: Session,
    user: User,
    user_external_id: str,
    source: MessageSource,
    parsed_message: ParsedUserMessage,
) -> tuple[User, MessageResponse]:
    if parsed_message.intent in {
        "set_work_schedule",
        "set_day_availability",
        "update_profile",
        "update_goals",
        "suggest_goal_tasks",
        "add_tasks",
        "create_task",
        "create_event",
        "mark_done",
        "daily_summary",
        "clear_tasks",
        "reschedule",
    }:
        user = (
            db.query(User)
            .filter(User.id == user.id)
            .with_for_update()
            .one()
        )

    response = _process_parsed_user_message(
        db,
        user,
        user_external_id,
        parsed_message,
        source,
    )
    response = _persist_response_interaction(
        db,
        user,
        user_external_id,
        source,
        parsed_message,
        response,
    )
    return user, response


def process_user_message(
    db: Session,
    user_external_id: str,
    text: str,
    source: MessageSource = "telegram_text",
    user_name: str | None = None,
    telegram_id: int | None = None,
    request_id: str | None = None,
    interaction_id: str | None = None,
    option_id: str | None = None,
    _resolved_user: User | None = None,
) -> MessageResponse:
    started_at = perf_counter()
    normalized_request_id = (request_id or str(uuid4())).strip()[:128]
    user = _resolved_user or get_or_create_user_by_external_id(
        db=db,
        external_id=user_external_id,
        name=user_name,
        telegram_id=telegram_id,
    )
    request_fingerprint = _message_request_fingerprint(
        source=source,
        text=text,
        interaction_id=interaction_id,
        option_id=option_id,
    )
    reservation = reserve_message_request(
        db,
        user,
        request_id=normalized_request_id,
        source=source,
        fingerprint=request_fingerprint,
    )

    if reservation.cached_response:
        return reservation.cached_response

    if reservation.processing:
        parsed_message = ParsedUserMessage(intent="show_plan")
        response = _base_response(
            user_external_id,
            source,
            parsed_message,
            "Это изменение уже обрабатывается. Текст сохранён; повтор не создаст дубликат.",
            status="no_change",
            reason="request_in_progress",
        )
        response.request_id = normalized_request_id
        _attach_day_snapshot(db, user, response, parsed_message)
        return response

    receipt = reservation.receipt

    if receipt is None:
        raise RuntimeError("Could not reserve message request")

    if receipt.status == "failed":
        receipt.status = "processing"
        db.commit()

    parser_started_at = perf_counter()

    try:
        pending = get_pending_interaction(db, user, interaction_id)

        if pending:
            parsed_message = ParsedUserMessage.model_validate(
                (pending.context or {}).get("parsed_message")
                or {"intent": "add_tasks", "raw_text": pending.original_message}
            )
            parser_ms = 0.0
            response = _handle_pending_interaction(
                db,
                user,
                user_external_id,
                source,
                text,
                pending,
                option_id,
            )
        elif interaction_id:
            parsed_message = ParsedUserMessage(intent="show_plan")
            parser_ms = 0.0
            response = _base_response(
                user_external_id,
                source,
                parsed_message,
                "Это уточнение уже закрыто или устарело. План не изменён.",
                status="no_change",
            )
        else:
            parsed_message = parse_user_message(text)
            parser_ms = (perf_counter() - parser_started_at) * 1000
            normalize_parsed_tasks(parsed_message, text)

            if parsed_message.work_context == "ambiguous":
                response = _build_work_schedule_clarification(
                    db,
                    user,
                    user_external_id,
                    source,
                    parsed_message,
                )
            elif parsed_message.intent == "set_work_schedule" and re.search(
                r"\bпо\s+будням\b",
                text,
                re.IGNORECASE,
            ):
                response = _build_work_schedule_confirmation(
                    db,
                    user,
                    user_external_id,
                    source,
                    parsed_message,
                )
            elif parsed_message.intent == "set_day_availability" and parsed_message.work_context == "off":
                plan_date = get_plan_date(parsed_message, user=user)
                existing_plan = (
                    db.query(DayPlan)
                    .filter(DayPlan.user_id == user.id, DayPlan.date == plan_date)
                    .one_or_none()
                )
                has_work = (
                    effective_work_window(existing_plan, user)[1] is not None
                    if existing_plan
                    else user.work_end_time is not None
                )
                response = (
                    _build_day_off_confirmation(
                        db,
                        user,
                        user_external_id,
                        source,
                        parsed_message,
                    )
                    if has_work
                    else _run_standard_message(
                        db,
                        user,
                        user_external_id,
                        source,
                        parsed_message,
                    )[1]
                )
            elif is_capability_request(text):
                response = _base_response(
                    user_external_id,
                    source,
                    parsed_message,
                    "Такой отдельной функции пока нет. Могу помочь сформулировать разовую задачу или напоминание.",
                    status="unsupported_capability",
                )
            else:
                ambiguity = detect_tracking_ambiguity(text, parsed_message)

                if ambiguity:
                    response = _build_tracking_clarification(
                        db,
                        user,
                        user_external_id,
                        source,
                        parsed_message,
                        subject=ambiguity.subject,
                        one_time_title=ambiguity.one_time_title,
                        routine_title=ambiguity.routine_title,
                    )
                else:
                    response = _build_explicit_routine_interaction(
                        db,
                        user,
                        user_external_id,
                        source,
                        parsed_message,
                    )

                    if response is None and is_low_energy_replan_request(text, parsed_message):
                        response = _build_low_energy_confirmation(
                            db,
                            user,
                            user_external_id,
                            source,
                            parsed_message,
                        )

                    if response is None:
                        user, response = _run_standard_message(
                            db,
                            user,
                            user_external_id,
                            source,
                            parsed_message,
                        )

        response.request_id = normalized_request_id
        _attach_day_snapshot(db, user, response, parsed_message)
        complete_message_request(db, receipt, response)
    except Exception:
        db.rollback()
        fail_message_request(db, receipt)
        raise

    total_ms = (perf_counter() - started_at) * 1000
    logger.info(
        "message processed request_id=%s source=%s provider=%s status=%s "
        "request_total_ms=%.1f parser_total_ms=%.1f",
        normalized_request_id,
        source,
        parsed_message.parser_provider,
        response.status,
        total_ms,
        parser_ms,
    )
    return response


def _message_request_fingerprint(
    *,
    source: str,
    text: str,
    interaction_id: str | None,
    option_id: str | None,
) -> str:
    payload = json.dumps(
        {
            "source": source,
            "text": " ".join(text.split()),
            "interaction_id": interaction_id,
            "option_id": option_id,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def process_authenticated_user_message(
    db: Session,
    *,
    user: User,
    text: str,
    source: MessageSource = "ios_text",
    request_id: str | None = None,
    interaction_id: str | None = None,
    option_id: str | None = None,
) -> MessageResponse:
    """Run the message pipeline for a session-owned user without an identity selector."""

    return process_user_message(
        db=db,
        user_external_id=f"account:{user.public_id}",
        text=text,
        source=source,
        request_id=request_id,
        interaction_id=interaction_id,
        option_id=option_id,
        _resolved_user=user,
    )
