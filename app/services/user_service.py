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


def get_or_create_user_by_external_id(
    db: Session,
    external_id: str,
    name: str | None = None,
    telegram_id: int | None = None,
) -> User:
    normalized_external_id = external_id.strip()

    if not normalized_external_id:
        raise ValueError("external_id must not be empty")

    user = db.query(User).filter(User.external_id == normalized_external_id).one_or_none()

    if user:
        changed = False

        if telegram_id is not None and user.telegram_id is None:
            user.telegram_id = telegram_id
            changed = True

        if name and user.name != name:
            user.name = name
            changed = True

        if changed:
            db.commit()
            db.refresh(user)

        return user

    if telegram_id is not None:
        user = db.query(User).filter(User.telegram_id == telegram_id).one_or_none()

        if user:
            changed = False

            if user.external_id is None:
                user.external_id = normalized_external_id
                changed = True

            if name and user.name != name:
                user.name = name
                changed = True

            if changed:
                db.commit()
                db.refresh(user)

            return user

    user = User(
        external_id=normalized_external_id,
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
