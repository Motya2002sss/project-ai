from sqlalchemy.orm import Session

from app.llm.parser import parse_user_message
from app.llm.schemas import ParsedUserMessage
from app.models.day_plan import DayPlan
from app.models.goal import Goal
from app.models.task import Task
from app.models.user import User
from app.schemas.api import (
    GoalResponse,
    MessageResponse,
    MessageSource,
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
from app.services.planning_service import format_day_plan, get_plan_date, rebuild_day_plan
from app.services.task_service import (
    clear_user_tasks,
    create_tasks_from_parsed_message,
    create_tasks_from_parsed_tasks,
    find_active_tasks_by_titles,
    format_tasks,
    list_active_tasks,
    mark_task_done_by_title,
    mark_tasks_done_by_titles,
)
from app.services.user_service import (
    format_user_profile,
    get_or_create_user_by_external_id,
    update_user_profile_from_parsed_message,
)


def task_to_response(task: Task) -> TaskResponse:
    return TaskResponse(
        id=task.id,
        title=task.title,
        priority=task.priority,
        estimated_minutes=task.estimated_minutes,
        target_date=task.target_date,
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
            )
            for item in day_plan.items
        ],
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
) -> MessageResponse:
    return MessageResponse(
        user_external_id=user_external_id,
        source=source,
        intent=parsed_message.intent,
        parsed=parsed_message.model_dump(mode="json"),
        reply_text=reply_text,
        summary=reply_text,
        affected_tasks=[task_to_response(task) for task in affected_tasks or []],
        affected_goals=[goal_to_response(goal) for goal in affected_goals or []],
        profile=profile_to_response(user, user_external_id) if user else None,
        plan_summary=plan_to_response(day_plan) if day_plan else None,
    )


def process_user_message(
    db: Session,
    user_external_id: str,
    text: str,
    source: MessageSource = "telegram_text",
) -> MessageResponse:
    user = get_or_create_user_by_external_id(db=db, external_id=user_external_id)
    parsed_message = parse_user_message(text)

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
        tasks = create_tasks_from_parsed_tasks(
            db=db,
            user=user,
            parsed_tasks=suggested_tasks,
            parsed_message=parsed_message,
        )
        day_plan = rebuild_day_plan(db=db, user=user, parsed_message=parsed_message)
        plan_text = format_day_plan(day_plan)
        task_lines = "\n".join(f"- {task.title}" for task in tasks)
        prefix = f"Добавил задачи по целям:\n\n{task_lines}" if tasks else "Задачи по целям уже есть в активном плане."
        reply_text = f"{prefix}\n\nПлан дня:\n\n{plan_text}"

        return _base_response(
            user_external_id,
            source,
            parsed_message,
            reply_text,
            affected_tasks=tasks,
            day_plan=day_plan,
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
        reply_text = f"Текущий план дня:\n\n{format_day_plan(day_plan)}"
        return _base_response(
            user_external_id,
            source,
            parsed_message,
            reply_text,
            day_plan=day_plan,
        )

    if parsed_message.intent == "show_tasks":
        tasks = list_active_tasks(db=db, user=user)
        reply_text = f"Активные задачи:\n\n{format_tasks(tasks)}"
        return _base_response(
            user_external_id,
            source,
            parsed_message,
            reply_text,
            affected_tasks=tasks,
        )

    if parsed_message.intent == "clear_tasks":
        count = clear_user_tasks(db=db, user=user)
        day_plan = rebuild_day_plan(db=db, user=user, parsed_message=parsed_message)
        reply_text = f"Очистил задачи: {count}.\n\nПлан дня очищен."
        return _base_response(
            user_external_id,
            source,
            parsed_message,
            reply_text,
            day_plan=day_plan,
        )

    if parsed_message.intent == "daily_summary":
        summary_date = get_plan_date(parsed_message)
        done_tasks = mark_tasks_done_by_titles(
            db=db,
            user=user,
            titles=parsed_message.done_task_titles,
            target_date=summary_date,
        )
        skipped_tasks = find_active_tasks_by_titles(
            db=db,
            user=user,
            titles=parsed_message.skipped_task_titles,
            target_date=summary_date,
        )
        day_plan = rebuild_day_plan(db=db, user=user, parsed_message=parsed_message)
        plan_text = format_day_plan(day_plan)
        done_text = "\n".join(f"- {task.title}" for task in done_tasks) or "ничего не отметил"
        skipped_text = "\n".join(f"- {task.title}" for task in skipped_tasks) or "нет"
        reply_text = (
            "Итог дня принял.\n\n"
            f"Выполнено:\n{done_text}\n\n"
            f"Осталось активным:\n{skipped_text}\n\n"
            f"Обновленный план:\n\n{plan_text}"
        )
        return _base_response(
            user_external_id,
            source,
            parsed_message,
            reply_text,
            affected_tasks=done_tasks + skipped_tasks,
            day_plan=day_plan,
        )

    if parsed_message.intent == "mark_done":
        if not parsed_message.done_task_title:
            reply_text = "Не понял, какую задачу отметить выполненной."
            return _base_response(user_external_id, source, parsed_message, reply_text)

        task_date = get_plan_date(parsed_message)
        task = mark_task_done_by_title(
            db=db,
            user=user,
            title=parsed_message.done_task_title,
            target_date=task_date,
        )

        if task is None:
            reply_text = "Не нашел такую активную задачу.\n\nНапиши «покажи задачи», чтобы посмотреть список."
            return _base_response(user_external_id, source, parsed_message, reply_text)

        day_plan = rebuild_day_plan(db=db, user=user, parsed_message=parsed_message)
        reply_text = f"Отметил выполненной:\n\n{task.title}\n\nОбновленный план:\n\n{format_day_plan(day_plan)}"
        return _base_response(
            user_external_id,
            source,
            parsed_message,
            reply_text,
            affected_tasks=[task],
            day_plan=day_plan,
        )

    if parsed_message.intent == "reschedule":
        day_plan = rebuild_day_plan(db=db, user=user, parsed_message=parsed_message)
        reply_text = f"Ок, перепланировал день с учетом изменений:\n\n{format_day_plan(day_plan)}"
        return _base_response(
            user_external_id,
            source,
            parsed_message,
            reply_text,
            day_plan=day_plan,
        )

    tasks = create_tasks_from_parsed_message(db=db, user=user, parsed_message=parsed_message)
    day_plan = rebuild_day_plan(db=db, user=user, parsed_message=parsed_message)
    task_lines = "\n".join(f"- {task.title}" for task in tasks) if tasks else "Новых задач нет."
    reply_text = f"Принял. Добавил задачи:\n\n{task_lines}\n\nПлан дня:\n\n{format_day_plan(day_plan)}"

    return _base_response(
        user_external_id,
        source,
        parsed_message,
        reply_text,
        affected_tasks=tasks,
        day_plan=day_plan,
    )
