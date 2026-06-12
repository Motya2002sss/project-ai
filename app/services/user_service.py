from datetime import time

from sqlalchemy.orm import Session

from app.llm.schemas import ParsedUserMessage
from app.models.user import User


def get_or_create_user(
    db: Session,
    telegram_id: int,
    name: str | None = None,
) -> User:
    user = db.query(User).filter(User.telegram_id == telegram_id).one_or_none()

    if user:
        if name and user.name != name:
            user.name = name
            db.commit()
            db.refresh(user)
        return user

    user = User(
        telegram_id=telegram_id,
        name=name,
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return user


def _parse_hhmm(value: str | None) -> time | None:
    if not value:
        return None

    try:
        hour_raw, minute_raw = value.split(":")
        return time(hour=int(hour_raw), minute=int(minute_raw))
    except ValueError:
        return None


def update_user_profile_from_parsed_message(
    db: Session,
    user: User,
    parsed_message: ParsedUserMessage,
) -> User:
    work_start = _parse_hhmm(parsed_message.work_start)
    work_until = _parse_hhmm(parsed_message.work_until)
    sleep_time = _parse_hhmm(parsed_message.sleep_time)

    if work_start:
        user.work_start_time = work_start

    if work_until:
        user.work_end_time = work_until

    if sleep_time:
        user.sleep_time = sleep_time

    db.commit()
    db.refresh(user)

    return user


def format_user_profile(user: User) -> str:
    work_start = user.work_start_time.strftime("%H:%M") if user.work_start_time else "не указано"
    work_end = user.work_end_time.strftime("%H:%M") if user.work_end_time else "не указано"
    sleep = user.sleep_time.strftime("%H:%M") if user.sleep_time else "не указано"

    return (
        f"Имя: {user.name or 'не указано'}\n"
        f"Часовой пояс: {user.timezone}\n"
        f"Работа: {work_start}–{work_end}\n"
        f"Сон/отбой: {sleep}"
    )
