import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from app.bot.main import dp
from app.core.config import settings
from app.llm.parser import parse_user_message
from app.main import app
from app.models.task import Task
from app.services.goal_service import suggest_tasks_from_goals
from app.services.planning_service import rebuild_day_plan
from app.services.task_service import (
    create_tasks_from_parsed_message,
    create_tasks_from_parsed_tasks,
)


def main() -> None:
    settings.llm_provider = "mock"
    settings.llm_api_key = None

    samples = {
        "Мой график с 10 до 19, хочу спать в 00:30": ("update_profile", None),
        "Моя цель: накопить 500000 рублей, научиться рисовать": ("update_goals", None),
        "Покажи цели": ("show_goals", None),
        "Что сделать для целей?": ("suggest_goal_tasks", None),
        "Сегодня хочу разобрать документы": ("add_tasks", "today"),
        "Завтра хочу позаниматься математикой": ("add_tasks", "tomorrow"),
        "Покажи план завтра": ("show_plan", "tomorrow"),
        "Итог дня: документы сделал, математику не сделал": ("daily_summary", None),
    }

    assert hasattr(Task, "target_date")
    assert app is not None
    assert dp is not None
    assert callable(create_tasks_from_parsed_message)
    assert callable(create_tasks_from_parsed_tasks)
    assert callable(suggest_tasks_from_goals)
    assert callable(rebuild_day_plan)

    for text, expected in samples.items():
        parsed = parse_user_message(text)
        expected_intent, expected_date = expected
        assert parsed.intent == expected_intent, (text, parsed.intent, expected_intent)
        assert parsed.date == expected_date, (text, parsed.date, expected_date)

        if parsed.intent == "update_goals":
            assert parsed.budget_limit is None, (text, parsed.budget_limit)

    print("mvp check ok")


if __name__ == "__main__":
    main()
