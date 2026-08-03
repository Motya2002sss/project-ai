from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.models.user import User


def get_user_timezone(user: User | None) -> ZoneInfo:
    timezone_name = user.timezone if user and user.timezone else "UTC"

    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def get_user_now(user: User | None, now: datetime | None = None) -> datetime:
    user_timezone = get_user_timezone(user)

    if now is None:
        return datetime.now(user_timezone)

    if now.tzinfo is None:
        return now.replace(tzinfo=user_timezone)

    return now.astimezone(user_timezone)


def resolve_target_date(
    value: str | date | None,
    user: User | None = None,
    now: datetime | None = None,
) -> date:
    today = get_user_now(user, now).date()

    if value is None or value == "today":
        return today

    if value == "tomorrow":
        return today + timedelta(days=1)

    if isinstance(value, date):
        return value

    return date.fromisoformat(value)


def combine_user_datetime(day: date, value: time, user: User | None) -> datetime:
    return datetime.combine(day, value, tzinfo=get_user_timezone(user))


def ceil_datetime(value: datetime, minutes: int) -> datetime:
    if minutes <= 0:
        raise ValueError("minutes must be positive")

    value = value.replace(second=0, microsecond=0)
    remainder = value.minute % minutes

    if remainder == 0:
        return value

    return value + timedelta(minutes=minutes - remainder)
