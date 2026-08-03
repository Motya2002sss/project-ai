import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.core.config import settings
from app.db.session import SessionLocal
from app.services.message_service import process_user_message
from app.services.planning_service import format_day_plan, rebuild_today_plan
from app.services.task_service import (
    clear_user_tasks,
    format_tasks,
    list_active_tasks,
    mark_task_done,
)
from app.services.user_service import get_or_create_user

logging.basicConfig(level=logging.INFO)

dp = Dispatcher()


def _response_keyboard(response) -> InlineKeyboardMarkup | None:
    interaction = response.clarification or response.confirmation or response.conflict_details

    if interaction is None or not interaction.id or not interaction.options:
        return None

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=option.label,
                    callback_data=f"planner:{interaction.id}:{option.id}",
                )
            ]
            for option in interaction.options
        ]
    )


async def _answer_planner_response(message: Message, response) -> None:
    keyboard = _response_keyboard(response)

    if keyboard:
        await message.answer(response.reply_text, reply_markup=keyboard)
    else:
        await message.answer(response.reply_text)


def _planning_context_hint(user) -> str:
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
        "Я помогаю превращать обычный текст в цели, задачи и реалистичный план дня.\n\n"
        "Можешь писать обычным текстом:\n"
        "— Мой график с 10 до 19, хочу спать в 00:30\n"
        "— Моя цель: накопить резерв, научиться рисовать, сделать мобильное приложение\n"
        "— Что сделать для целей?\n"
        "— Сегодня хочу разобрать документы\n"
        "— Завтра хочу позаниматься математикой\n"
        "— Покажи план\n"
        "— Документы сделал\n"
        "— Итог дня: документы сделал, математику не сделал\n"
        "— Я задержался до 20\n"
        "— Очисти задачи"
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
        plan_text = format_day_plan(day_plan, user=user)
        hint = _planning_context_hint(user)

    await message.answer(f"Текущий план дня:\n\n{plan_text}{hint}")


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
        plan_text = format_day_plan(day_plan, user=user)
        hint = _planning_context_hint(user)

    await message.answer(
        f"Готово. Отметил выполненной:\n\n{task.title}\n\n"
        f"Обновленный план:\n\n{plan_text}{hint}"
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

    with SessionLocal() as db:
        response = process_user_message(
            db=db,
            user_external_id=f"telegram:{telegram_user.id}",
            text=text,
            source="telegram_text",
            user_name=telegram_user.full_name,
            telegram_id=telegram_user.id,
            request_id=(f"telegram-message:{message.message_id}" if getattr(message, "message_id", None) else None),
        )

    await _answer_planner_response(message, response)


@dp.callback_query(F.data.startswith("planner:"))
async def handle_planner_callback(callback: CallbackQuery) -> None:
    telegram_user = callback.from_user
    callback_data = callback.data or ""
    parts = callback_data.split(":", maxsplit=2)

    if len(parts) != 3 or callback.message is None:
        await callback.answer("Не удалось прочитать ответ.", show_alert=True)
        return

    _, interaction_id, option_id = parts

    with SessionLocal() as db:
        response = process_user_message(
            db=db,
            user_external_id=f"telegram:{telegram_user.id}",
            text=option_id,
            source="telegram_text",
            user_name=telegram_user.full_name,
            telegram_id=telegram_user.id,
            request_id=f"telegram-callback:{callback.id}",
            interaction_id=interaction_id,
            option_id=option_id,
        )

    await callback.answer()
    await _answer_planner_response(callback.message, response)


async def main() -> None:
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set. Add it to your .env file.")

    bot = Bot(token=settings.telegram_bot_token)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
