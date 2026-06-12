from datetime import date, datetime, time, timedelta

from sqlalchemy.orm import Session

from app.llm.schemas import ParsedUserMessage
from app.models.day_plan import DayPlan
from app.models.plan_item import PlanItem
from app.models.task import Task
from app.models.user import User


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


def _start_time_from_parsed(user: User, parsed_message: ParsedUserMessage | None) -> time:
    if parsed_message and parsed_message.work_until:
        work_until = _parse_hhmm(parsed_message.work_until)

        if work_until:
            start_dt = datetime.combine(date.today(), work_until) + timedelta(minutes=30)
            return start_dt.time()

    if user.work_end_time:
        start_dt = datetime.combine(date.today(), user.work_end_time) + timedelta(minutes=30)
        return start_dt.time()

    return time(hour=18, minute=30)


def get_or_create_today_plan(db: Session, user: User) -> DayPlan:
    today = date.today()

    day_plan = (
        db.query(DayPlan)
        .filter(
            DayPlan.user_id == user.id,
            DayPlan.date == today,
        )
        .one_or_none()
    )

    if day_plan:
        return day_plan

    day_plan = DayPlan(
        user_id=user.id,
        date=today,
        summary="Автоматический план дня",
        status="draft",
    )

    db.add(day_plan)
    db.commit()
    db.refresh(day_plan)

    return day_plan


def rebuild_today_plan(
    db: Session,
    user: User,
    parsed_message: ParsedUserMessage | None = None,
) -> DayPlan:
    day_plan = get_or_create_today_plan(db, user)

    if parsed_message:
        day_plan.energy_level = parsed_message.energy_level
        day_plan.budget_limit = parsed_message.budget_limit
        day_plan.summary = parsed_message.raw_text or "Автоматический план дня"

    for item in list(day_plan.items):
        db.delete(item)

    planned_tasks = (
        db.query(Task)
        .filter(
            Task.user_id == user.id,
            Task.status == "planned",
        )
        .order_by(Task.priority.desc(), Task.id.asc())
        .all()
    )

    start_time = _start_time_from_parsed(user, parsed_message)
    current_dt = datetime.combine(date.today(), start_time)

    for task in planned_tasks:
        duration_minutes = estimate_task_minutes(task)

        if parsed_message and parsed_message.energy_level == "low":
            title = task.title.lower()

            if "зал" in title or "трен" in title:
                duration_minutes = min(duration_minutes, 45)

        end_dt = current_dt + timedelta(minutes=duration_minutes)

        plan_item = PlanItem(
            day_plan_id=day_plan.id,
            task_id=task.id,
            start_time=current_dt.time(),
            end_time=end_dt.time(),
            title=task.title,
            item_type="task",
            status="planned",
        )

        db.add(plan_item)
        current_dt = end_dt

    db.commit()
    db.refresh(day_plan)

    return day_plan


def format_day_plan(day_plan: DayPlan) -> str:
    if not day_plan.items:
        return "План пока пустой."

    sorted_items = sorted(
        day_plan.items,
        key=lambda item: item.start_time or time(hour=0, minute=0),
    )

    lines = []

    if day_plan.budget_limit:
        lines.append(f"Бюджет на день: {day_plan.budget_limit} ₽")

    if day_plan.energy_level:
        lines.append(f"Энергия: {day_plan.energy_level}")

    if lines:
        lines.append("")

    for item in sorted_items:
        start = item.start_time.strftime("%H:%M") if item.start_time else "??:??"
        end = item.end_time.strftime("%H:%M") if item.end_time else "??:??"

        lines.append(f"{start}–{end} — {item.title}")

    return "\n".join(lines)
