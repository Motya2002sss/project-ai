import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from app.core.config import settings
from app.db.session import SessionLocal
from app.services.planning_service import format_day_plan, rebuild_today_plan
from app.services.task_service import create_tasks_from_text
from app.services.user_service import get_or_create_user

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
        "Я буду помогать тебе планировать день без ручного заполнения ежедневника.\n\n"
        f"Твой внутренний ID: {user.id}\n\n"
        "Напиши мне обычным текстом, что хочешь сделать сегодня или завтра.\n\n"
        "Например:\n"
        "Завтра работаю до 18, бюджет 1500, сил мало, хочу зал и подготовиться к собесу"
    )


@dp.message(Command("plan"))
async def plan_command(message: Message) -> None:
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

        day_plan = rebuild_today_plan(db=db, user=user)
        plan_text = format_day_plan(day_plan)

    await message.answer(
        "Текущий план дня:\n\n"
        f"{plan_text}"
    )


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

    with SessionLocal() as db:
        user = get_or_create_user(
            db=db,
            telegram_id=telegram_user.id,
            name=telegram_user.full_name,
        )

        tasks, parsed_message = create_tasks_from_text(
            db=db,
            user=user,
            text=text,
        )

        day_plan = rebuild_today_plan(
            db=db,
            user=user,
            parsed_message=parsed_message,
        )

        plan_text = format_day_plan(day_plan)

    task_lines = "\n".join(
        f"{index}. {task.title} — {task.priority}, {task.estimated_minutes or 60} мин"
        for index, task in enumerate(tasks, start=1)
    )

    parsed_info = (
        f"Дата: {parsed_message.date or 'не указана'}\n"
        f"Работа до: {parsed_message.work_until or 'не указано'}\n"
        f"Бюджет: {parsed_message.budget_limit or 'не указан'}\n"
        f"Энергия: {parsed_message.energy_level or 'не указана'}"
    )

    await message.answer(
        "Я разобрал сообщение:\n\n"
        f"{parsed_info}\n\n"
        "Сохранил задачи:\n\n"
        f"{task_lines}\n\n"
        "Черновой план дня:\n\n"
        f"{plan_text}\n\n"
        f"LLM mode: {settings.llm_provider}"
    )


async def main() -> None:
    if not settings.telegram_bot_token:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN is not set. Add it to your .env file."
        )

    bot = Bot(token=settings.telegram_bot_token)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
