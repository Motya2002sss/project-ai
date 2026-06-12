import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from app.core.config import settings
from app.db.session import SessionLocal
from app.llm.parser import parse_user_message
from app.services.planning_service import format_day_plan, rebuild_today_plan
from app.services.task_service import (
    clear_user_tasks,
    create_tasks_from_parsed_message,
    format_tasks,
    list_active_tasks,
    mark_task_done,
    mark_task_done_by_title,
)
from app.services.user_service import (
    format_user_profile,
    get_or_create_user,
    update_user_profile_from_parsed_message,
)

logging.basicConfig(level=logging.INFO)

dp = Dispatcher()


@dp.message(CommandStart())
async def start_command(message: Message) -> None:
    telegram_user = message.from_user

    if telegram_user is None:
        await message.answer("Не смог определить пользователя Telegram.")
        return

    with SessionLocal() as db:
        user = get_or_create_user(
            db=db,
            telegram_id=telegram_user.id,
            name=telegram_user.full_name,
        )

    await message.answer(
        "Привет! Я AI Life Planner.\n\n"
        "Я помогаю планировать день без ручного заполнения ежедневника.\n\n"
        f"Твой внутренний ID: {user.id}\n\n"
        "Можешь писать обычным текстом:\n"
        "- Мой график с 9 до 18, хочу спать в 23:30\n"
        "- Покажи профиль\n"
        "- Хочу зал и подготовиться к собесу\n"
        "- Покажи план\n"
        "- Зал сделал\n"
        "- Я задержался до 20\n"
        "- Очисти задачи"
    )


@dp.message(Command("tasks"))
async def tasks_command(message: Message) -> None:
    telegram_user = message.from_user

    if telegram_user is None:
        await message.answer("Не смог определить пользователя Telegram.")
        return

    with SessionLocal() as db:
        user = get_or_create_user(db=db, telegram_id=telegram_user.id, name=telegram_user.full_name)
        tasks = list_active_tasks(db=db, user=user)
        tasks_text = format_tasks(tasks)

    await message.answer(f"Активные задачи:\n\n{tasks_text}")


@dp.message(Command("plan"))
async def plan_command(message: Message) -> None:
    telegram_user = message.from_user

    if telegram_user is None:
        await message.answer("Не смог определить пользователя Telegram.")
        return

    with SessionLocal() as db:
        user = get_or_create_user(db=db, telegram_id=telegram_user.id, name=telegram_user.full_name)
        day_plan = rebuild_today_plan(db=db, user=user)
        plan_text = format_day_plan(day_plan)

    await message.answer(f"Текущий план дня:\n\n{plan_text}")


@dp.message(Command("done"))
async def done_command(message: Message) -> None:
    telegram_user = message.from_user

    if telegram_user is None:
        await message.answer("Не смог определить пользователя Telegram.")
        return

    text = message.text or ""
    parts = text.split(maxsplit=1)

    if len(parts) < 2 or not parts[1].strip().isdigit():
        await message.answer("Укажи ID задачи.\n\nПример:\n/done 3")
        return

    task_id = int(parts[1].strip())

    with SessionLocal() as db:
        user = get_or_create_user(db=db, telegram_id=telegram_user.id, name=telegram_user.full_name)
        task = mark_task_done(db=db, user=user, task_id=task_id)

        if task is None:
            await message.answer(f"Задача с ID {task_id} не найдена.")
            return

        day_plan = rebuild_today_plan(db=db, user=user)
        plan_text = format_day_plan(day_plan)

    await message.answer(
        f"Готово. Задача выполнена:\n\n{task.title}\n\n"
        f"Обновленный план дня:\n\n{plan_text}"
    )


@dp.message(Command("clear"))
async def clear_command(message: Message) -> None:
    telegram_user = message.from_user

    if telegram_user is None:
        await message.answer("Не смог определить пользователя Telegram.")
        return

    with SessionLocal() as db:
        user = get_or_create_user(db=db, telegram_id=telegram_user.id, name=telegram_user.full_name)
        count = clear_user_tasks(db=db, user=user)
        rebuild_today_plan(db=db, user=user)

    await message.answer(f"Очистил задачи: {count}.\n\nПлан дня очищен.")


@dp.message()
async def handle_text_message(message: Message) -> None:
    telegram_user = message.from_user

    if telegram_user is None:
        await message.answer("Не смог определить пользователя Telegram.")
        return

    text = message.text

    if not text:
        await message.answer("Пока я умею обрабатывать только текстовые сообщения.")
        return

    parsed_message = parse_user_message(text)

    with SessionLocal() as db:
        user = get_or_create_user(
            db=db,
            telegram_id=telegram_user.id,
            name=telegram_user.full_name,
        )

        if parsed_message.intent == "show_profile":
            profile_text = format_user_profile(user)

            await message.answer(
                "Твой профиль:\n\n"
                f"{profile_text}"
            )
            return

        if parsed_message.intent == "update_profile":
            user = update_user_profile_from_parsed_message(
                db=db,
                user=user,
                parsed_message=parsed_message,
            )

            profile_text = format_user_profile(user)

            await message.answer(
                "Запомнил настройки профиля:\n\n"
                f"{profile_text}\n\n"
                "Теперь при планировании буду учитывать этот график."
            )
            return

        if parsed_message.intent == "show_plan":
            day_plan = rebuild_today_plan(db=db, user=user)
            plan_text = format_day_plan(day_plan)

            await message.answer(f"Текущий план дня:\n\n{plan_text}")
            return

        if parsed_message.intent == "show_tasks":
            tasks = list_active_tasks(db=db, user=user)
            tasks_text = format_tasks(tasks)

            await message.answer(f"Активные задачи:\n\n{tasks_text}")
            return

        if parsed_message.intent == "clear_tasks":
            count = clear_user_tasks(db=db, user=user)
            rebuild_today_plan(db=db, user=user)

            await message.answer(f"Очистил задачи: {count}.\n\nПлан дня очищен.")
            return

        if parsed_message.intent == "mark_done":
            if not parsed_message.done_task_title:
                await message.answer("Не понял, какую задачу отметить выполненной.")
                return

            task = mark_task_done_by_title(
                db=db,
                user=user,
                title=parsed_message.done_task_title,
            )

            if task is None:
                await message.answer(
                    "Не нашел такую активную задачу.\n\n"
                    "Напиши «покажи задачи», чтобы посмотреть список."
                )
                return

            day_plan = rebuild_today_plan(db=db, user=user)
            plan_text = format_day_plan(day_plan)

            await message.answer(
                f"Отметил выполненной:\n\n{task.title}\n\n"
                f"Обновленный план:\n\n{plan_text}"
            )
            return

        if parsed_message.intent == "reschedule":
            day_plan = rebuild_today_plan(
                db=db,
                user=user,
                parsed_message=parsed_message,
            )
            plan_text = format_day_plan(day_plan)

            await message.answer(
                "Ок, перепланировал день с учетом изменений:\n\n"
                f"{plan_text}"
            )
            return

        tasks = create_tasks_from_parsed_message(
            db=db,
            user=user,
            parsed_message=parsed_message,
        )

        day_plan = rebuild_today_plan(
            db=db,
            user=user,
            parsed_message=parsed_message,
        )

        plan_text = format_day_plan(day_plan)

    if tasks:
        task_lines = "\n".join(
            f"{task.id}. {task.title} — {task.priority}, {task.estimated_minutes or 60} мин"
            for task in tasks
        )
    else:
        task_lines = "Новых задач нет."

    await message.answer(
        "Я разобрал сообщение:\n\n"
        f"Intent: {parsed_message.intent}\n"
        f"Дата: {parsed_message.date or 'не указана'}\n"
        f"Работа до: {parsed_message.work_until or 'не указано'}\n"
        f"Бюджет: {parsed_message.budget_limit or 'не указан'}\n"
        f"Энергия: {parsed_message.energy_level or 'не указана'}\n\n"
        "Сохранил задачи:\n\n"
        f"{task_lines}\n\n"
        "Черновой план дня:\n\n"
        f"{plan_text}\n\n"
        f"LLM mode: {settings.llm_provider}"
    )


async def main() -> None:
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set. Add it to your .env file.")

    bot = Bot(token=settings.telegram_bot_token)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
