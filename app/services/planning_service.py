from datetime import date, datetime, time, timedelta

from sqlalchemy.orm import Session

from app.core.config import settings
from app.llm.schemas import ParsedUserMessage
from app.models.day_plan import DayPlan
from app.models.plan_item import PlanItem
from app.models.task import Task
from app.models.user import User


PRIORITY_ORDER = {
    "high": 0,
    "medium": 1,
    "low": 2,
}


def get_plan_date(parsed_message: ParsedUserMessage | None = None) -> date:
    if parsed_message and parsed_message.date == "tomorrow":
        return date.today() + timedelta(days=1)

    return date.today()


def format_plan_date(plan_date: date) -> str:
    today = date.today()

    if plan_date == today:
        return "сегодня"

    if plan_date == today + timedelta(days=1):
        return "завтра"

    return plan_date.strftime("%d.%m.%Y")


def estimate_task_minutes(task: Task) -> int:
    if task.estimated_minutes:
        return task.estimated_minutes

    title = task.title.lower()

    if "собес" in title or "подготов" in title:
        return 90

    if "зал" in title or "трен" in title:
        return 60

    if "магаз" in title or "продукт" in title:
        return 30

    return 60


def _parse_hhmm(value: str | None) -> time | None:
    if not value:
        return None

    try:
        hour_raw, minute_raw = value.split(":")
        return time(hour=int(hour_raw), minute=int(minute_raw))
    except ValueError:
        return None


def _start_time_from_parsed(user: User, parsed_message: ParsedUserMessage | None, plan_date: date) -> datetime:
    buffer = timedelta(minutes=settings.plan_start_buffer_minutes)

    if parsed_message and parsed_message.work_until:
        work_until = _parse_hhmm(parsed_message.work_until)

        if work_until:
            return datetime.combine(plan_date, work_until) + buffer

    if user.work_end_time:
        return datetime.combine(plan_date, user.work_end_time) + buffer

    default_start = _parse_hhmm(settings.default_plan_start_time) or time(hour=18, minute=30)
    return datetime.combine(plan_date, default_start)


def _get_sleep_deadline(user: User, current_dt: datetime) -> datetime | None:
    if not user.sleep_time:
        return None

    sleep_deadline = datetime.combine(current_dt.date(), user.sleep_time)

    if sleep_deadline <= current_dt:
        sleep_deadline += timedelta(days=1)

    return sleep_deadline


def get_or_create_day_plan(
    db: Session,
    user: User,
    plan_date: date,
) -> DayPlan:
    day_plan = (
        db.query(DayPlan)
        .filter(
            DayPlan.user_id == user.id,
            DayPlan.date == plan_date,
        )
        .one_or_none()
    )

    if day_plan:
        return day_plan

    day_plan = DayPlan(
        user_id=user.id,
        date=plan_date,
        summary="Автоматический план дня",
        status="draft",
    )

    db.add(day_plan)
    db.commit()
    db.refresh(day_plan)

    return day_plan


def rebuild_day_plan(
    db: Session,
    user: User,
    parsed_message: ParsedUserMessage | None = None,
) -> DayPlan:
    plan_date = get_plan_date(parsed_message)
    day_plan = get_or_create_day_plan(db=db, user=user, plan_date=plan_date)

    if parsed_message:
        day_plan.energy_level = parsed_message.energy_level or day_plan.energy_level
        day_plan.budget_limit = parsed_message.budget_limit or day_plan.budget_limit
        day_plan.summary = parsed_message.raw_text or "Автоматический план дня"

    day_plan.items.clear()
    db.flush()

    planned_tasks = (
        db.query(Task)
        .filter(
            Task.user_id == user.id,
            Task.status == "planned",
            Task.target_date == plan_date,
        )
        .all()
    )

    planned_tasks = sorted(
        planned_tasks,
        key=lambda task: (
            PRIORITY_ORDER.get(task.priority, 1),
            task.id,
        ),
    )

    current_dt = _start_time_from_parsed(
        user=user,
        parsed_message=parsed_message,
        plan_date=plan_date,
    )

    sleep_deadline = _get_sleep_deadline(user, current_dt)
    has_overload = False

    for task in planned_tasks:
        duration_minutes = estimate_task_minutes(task)

        if parsed_message and parsed_message.energy_level == "low":
            title = task.title.lower()

            if "зал" in title or "трен" in title:
                duration_minutes = min(duration_minutes, 45)

        end_dt = current_dt + timedelta(minutes=duration_minutes)

        if sleep_deadline and end_dt > sleep_deadline:
            has_overload = True

            plan_item = PlanItem(
                task_id=task.id,
                start_time=None,
                end_time=None,
                title=task.title,
                item_type="task",
                status="not_scheduled",
            )

            day_plan.items.append(plan_item)
            continue

        plan_item = PlanItem(
            task_id=task.id,
            start_time=current_dt.time(),
            end_time=end_dt.time(),
            title=task.title,
            item_type="task",
            status="planned",
        )

        day_plan.items.append(plan_item)
        current_dt = end_dt

    day_plan.status = "overloaded" if has_overload else "draft"

    db.commit()
    db.refresh(day_plan)

    return day_plan


def rebuild_today_plan(db: Session, user: User) -> DayPlan:
    return rebuild_day_plan(db=db, user=user, parsed_message=None)


def format_day_plan(day_plan: DayPlan) -> str:
    items = list(day_plan.items)

    scheduled_items = sorted(
        [item for item in items if item.status == "planned"],
        key=lambda item: item.start_time or time(hour=0, minute=0),
    )

    not_scheduled_items = [
        item for item in items if item.status == "not_scheduled"
    ]

    lines: list[str] = []

    lines.append(f"План на {format_plan_date(day_plan.date)}:")

    if day_plan.budget_limit:
        lines.append(f"Бюджет: {day_plan.budget_limit} ₽")

    if day_plan.energy_level:
        energy_map = {
            "low": "низкая",
            "medium": "средняя",
            "high": "высокая",
        }
        lines.append(f"Энергия: {energy_map.get(day_plan.energy_level, day_plan.energy_level)}")

    lines.append("")

    if scheduled_items:
        for item in scheduled_items:
            start = item.start_time.strftime("%H:%M") if item.start_time else "??:??"
            end = item.end_time.strftime("%H:%M") if item.end_time else "??:??"

            lines.append(f"{start}–{end} — {item.title}")
    else:
        lines.append("Запланированных задач пока нет.")

    if not_scheduled_items:
        lines.append("")
        lines.append("Не помещается до сна, лучше перенести:")

        for item in not_scheduled_items:
            lines.append(f"— {item.title}")

    return "\n".join(lines)
