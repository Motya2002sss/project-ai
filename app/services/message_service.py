from dataclasses import dataclass
from datetime import date, time

from sqlalchemy.orm import Session

from app.llm.parser import parse_user_message
from app.llm.schemas import ParsedTask, ParsedUserMessage
from app.models.day_plan import DayPlan
from app.models.goal import Goal
from app.models.task import Task
from app.models.user import User
from app.schemas.api import (
    GoalResponse,
    MessageResponse,
    MessageSource,
    MovedPlanItemResponse,
    PlanDiffResponse,
    PlanItemResponse,
    PlanResponse,
    ProfileResponse,
    TaskResponse,
)
from app.services.goal_service import (
    create_goals_from_titles,
    format_goals,
    list_active_goals,
    suggest_tasks_from_goals,
)
from app.services.planning_service import (
    PlanBuildResult,
    build_day_plan_result,
    build_plan_focus,
    format_day_plan,
    get_plan_date,
    rebuild_day_plan,
)
from app.services.task_service import (
    TaskMutationResult,
    apply_parsed_task_operations,
    clear_user_tasks,
    create_tasks_from_parsed_tasks,
    find_active_tasks_by_titles,
    format_tasks,
    list_active_tasks,
    mark_tasks_done_by_titles,
)


@dataclass(frozen=True)
class _PlanPlacementSnapshot:
    task_id: int
    title: str
    start_time: time | None
    end_time: time | None
    status: str
from app.services.user_service import (
    format_user_profile,
    get_or_create_user_by_external_id,
    update_user_profile_from_parsed_message,
)


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
    )


def goal_to_response(goal: Goal) -> GoalResponse:
    return GoalResponse(
        id=goal.id,
        title=goal.title,
        category=goal.category,
        priority=goal.priority,
        status=goal.status,
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


def plan_to_response(day_plan: DayPlan) -> PlanResponse:
    return PlanResponse(
        id=day_plan.id,
        date=day_plan.date,
        summary=day_plan.summary,
        focus_text=build_plan_focus(day_plan),
        energy_level=day_plan.energy_level,
        budget_limit=day_plan.budget_limit,
        status=day_plan.status,
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
        + f"\n\n{format_day_plan(day_plan)}{_planning_context_hint(user)}"
    )


def _base_response(
    user_external_id: str,
    source: MessageSource,
    parsed_message: ParsedUserMessage,
    reply_text: str,
    *,
    affected_tasks: list[Task] | None = None,
    affected_goals: list[Goal] | None = None,
    user: User | None = None,
    day_plan: DayPlan | None = None,
    status: str = "applied",
    clarification_question: str | None = None,
    plan_diff: PlanDiffResponse | None = None,
) -> MessageResponse:
    return MessageResponse(
        user_external_id=user_external_id,
        source=source,
        intent=parsed_message.intent,
        parsed=parsed_message.model_dump(mode="json"),
        status=status,
        needs_clarification=status in {"needs_clarification", "conflict"},
        clarification_question=clarification_question,
        reply_text=reply_text,
        summary=reply_text,
        affected_tasks=[task_to_response(task) for task in affected_tasks or []],
        affected_goals=[goal_to_response(goal) for goal in affected_goals or []],
        profile=profile_to_response(user, user_external_id) if user else None,
        plan_summary=plan_to_response(day_plan) if day_plan else None,
        plan_diff=plan_diff or PlanDiffResponse(),
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
                status="needs_clarification",
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

    return _base_response(
        user_external_id,
        source,
        parsed_message,
        reply_text,
        affected_tasks=affected_tasks,
        day_plan=selected_result.day_plan,
        plan_diff=plan_diff,
    )


def process_user_message(
    db: Session,
    user_external_id: str,
    text: str,
    source: MessageSource = "telegram_text",
    user_name: str | None = None,
    telegram_id: int | None = None,
) -> MessageResponse:
    parsed_message = parse_user_message(text)
    user = get_or_create_user_by_external_id(
        db=db,
        external_id=user_external_id,
        name=user_name,
        telegram_id=telegram_id,
    )

    if parsed_message.intent in {"add_tasks", "mark_done"} or (
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
        plan_text = format_day_plan(day_plan)
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
        return _base_response(
            user_external_id,
            source,
            parsed_message,
            reply_text,
            user=user,
        )

    if parsed_message.intent == "show_plan":
        day_plan = rebuild_day_plan(db=db, user=user, parsed_message=parsed_message)
        reply_text = f"Текущий план дня:\n\n{format_day_plan(day_plan)}{_planning_context_hint(user)}"
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
        plan_text = format_day_plan(day_plan)
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
            f"{format_day_plan(day_plan)}{_planning_context_hint(user)}"
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
