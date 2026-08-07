import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from app.bot.main import dp
from app.core.config import settings
from app.llm.parser import parse_user_message
from app.main import app
from app.models.plan_item import PlanItem
from app.models.task import Task
from app.services.goal_service import suggest_tasks_from_goals
from app.services.planning_service import (
    choose_best_slot,
    find_available_slots,
    rebuild_day_plan,
)
from app.services.task_service import (
    create_tasks_from_parsed_message,
    create_tasks_from_parsed_tasks,
)


def main() -> None:
    settings.llm_enabled = False
    settings.llm_provider = "mock"
    settings.llm_api_key = None

    samples = {
        "Мой график с 10 до 19, хочу спать в 00:30": ("set_work_schedule", None),
        "Моя цель: накопить 500000 рублей, научиться рисовать": ("update_goals", None),
        "Покажи цели": ("show_goals", None),
        "Что сделать для целей?": ("suggest_goal_tasks", None),
        "Сегодня хочу разобрать документы": ("add_tasks", "today"),
        "Завтра хочу позаниматься математикой": ("add_tasks", "tomorrow"),
        "Покажи план завтра": ("show_plan", "tomorrow"),
        "Итог дня: документы сделал, математику не сделал": ("daily_summary", None),
    }

    assert hasattr(Task, "target_date")
    assert hasattr(Task, "scheduling_type")
    assert hasattr(Task, "fixed_start")
    assert hasattr(Task, "preferred_window")
    assert hasattr(Task, "is_locked")
    assert hasattr(PlanItem, "unscheduled_reason")
    assert app is not None
    assert dp is not None
    assert callable(create_tasks_from_parsed_message)
    assert callable(create_tasks_from_parsed_tasks)
    assert callable(suggest_tasks_from_goals)
    assert callable(rebuild_day_plan)
    assert callable(find_available_slots)
    assert callable(choose_best_slot)

    for text, expected in samples.items():
        parsed = parse_user_message(text)
        expected_intent, expected_date = expected
        assert parsed.intent == expected_intent, (text, parsed.intent, expected_intent)
        assert parsed.date == expected_date, (text, parsed.date, expected_date)

        if parsed.intent == "update_goals":
            assert parsed.budget_limit is None, (text, parsed.budget_limit)

    fixed = parse_user_message("Сегодня в 19:00 созвон на час")
    assert fixed.tasks[0].scheduling_type == "fixed"
    assert fixed.tasks[0].fixed_start == "19:00"
    assert fixed.tasks[0].estimated_minutes == 60

    cancelled = parse_user_message("Зал отменяется")
    assert cancelled.tasks[0].operation == "cancel"

    recurrence = parse_user_message("Утром хожу в зал")
    assert recurrence.tasks[0].needs_clarification is True

    ambiguous_work = parse_user_message("Добавь работу с 9 до 18")
    assert ambiguous_work.intent == "set_work_schedule"
    assert ambiguous_work.work_context == "ambiguous"
    assert ambiguous_work.tasks == []

    day_work = parse_user_message("Сегодня работаю с 10 до 20")
    assert day_work.intent == "set_day_availability"
    assert day_work.work_context == "day"

    print("mvp check ok")


if __name__ == "__main__":
    main()
