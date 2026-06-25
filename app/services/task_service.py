from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.llm.parser import parse_user_message
from app.llm.schemas import ParsedTask, ParsedUserMessage
from app.models.task import Task
from app.models.user import User


def _get_task_target_date(parsed_message: ParsedUserMessage | None = None) -> date:
    if parsed_message and parsed_message.date == "tomorrow":
        return date.today() + timedelta(days=1)

    return date.today()


def create_tasks_from_parsed_tasks(
    db: Session,
    user: User,
    parsed_tasks: list[ParsedTask],
    parsed_message: ParsedUserMessage | None = None,
) -> list[Task]:
    tasks: list[Task] = []
    target_date = _get_task_target_date(parsed_message)

    for parsed_task in parsed_tasks:
        title = parsed_task.title.strip()

        if not title:
            continue

        exists = (
            db.query(Task)
            .filter(
                Task.user_id == user.id,
                Task.target_date == target_date,
                Task.title.ilike(title),
                Task.status == "planned",
            )
            .one_or_none()
        )

        if exists:
            continue

        task_data = {
            "user_id": user.id,
            "title": title[:255],
            "priority": parsed_task.priority,
            "estimated_minutes": parsed_task.estimated_minutes,
            "target_date": target_date,
            "status": "planned",
        }

        task = Task(**task_data)

        db.add(task)
        tasks.append(task)

    db.commit()

    for task in tasks:
        db.refresh(task)

    return tasks


def create_tasks_from_parsed_message(
    db: Session,
    user: User,
    parsed_message: ParsedUserMessage,
) -> list[Task]:
    return create_tasks_from_parsed_tasks(
        db=db,
        user=user,
        parsed_tasks=parsed_message.tasks,
        parsed_message=parsed_message,
    )


def create_tasks_from_text(
    db: Session,
    user: User,
    text: str,
) -> tuple[list[Task], ParsedUserMessage]:
    parsed_message = parse_user_message(text)

    tasks = create_tasks_from_parsed_message(
        db=db,
        user=user,
        parsed_message=parsed_message,
    )

    return tasks, parsed_message


def list_active_tasks(db: Session, user: User, target_date: date | None = None) -> list[Task]:
    query = (
        db.query(Task)
        .filter(
            Task.user_id == user.id,
            Task.status == "planned",
        )
    )

    if target_date is not None:
        query = query.filter(Task.target_date == target_date)

    return query.order_by(Task.target_date.asc(), Task.id.asc()).all()


def list_user_tasks(db: Session, user: User, target_date: date | None = None) -> list[Task]:
    query = db.query(Task).filter(Task.user_id == user.id)

    if target_date is not None:
        query = query.filter(Task.target_date == target_date)

    return query.order_by(Task.target_date.asc(), Task.id.asc()).all()


def _find_active_task_by_title(
    db: Session,
    user: User,
    title: str,
    target_date: date | None = None,
) -> Task | None:
    title_lower = title.lower().strip()

    if not title_lower:
        return None

    tasks = list_active_tasks(db=db, user=user, target_date=target_date)

    for task in tasks:
        task_title_lower = task.title.lower().strip()

        if title_lower in task_title_lower or task_title_lower in title_lower:
            return task

    return None


def find_active_tasks_by_titles(
    db: Session,
    user: User,
    titles: list[str],
    target_date: date | None = None,
) -> list[Task]:
    found: list[Task] = []

    for title in titles:
        task = _find_active_task_by_title(
            db=db,
            user=user,
            title=title,
            target_date=target_date,
        )

        if task and task not in found:
            found.append(task)

    return found


def mark_task_done(db: Session, user: User, task_id: int) -> Task | None:
    task = (
        db.query(Task)
        .filter(
            Task.id == task_id,
            Task.user_id == user.id,
        )
        .one_or_none()
    )

    if task is None:
        return None

    task.status = "done"
    db.commit()
    db.refresh(task)

    return task


def mark_task_done_by_title(
    db: Session,
    user: User,
    title: str,
    target_date: date | None = None,
) -> Task | None:
    task = _find_active_task_by_title(
        db=db,
        user=user,
        title=title,
        target_date=target_date,
    )

    if task is None:
        return None

    task.status = "done"
    db.commit()
    db.refresh(task)

    return task


def mark_tasks_done_by_titles(
    db: Session,
    user: User,
    titles: list[str],
    target_date: date | None = None,
) -> list[Task]:
    done_tasks: list[Task] = []

    for title in titles:
        task = _find_active_task_by_title(
            db=db,
            user=user,
            title=title,
            target_date=target_date,
        )

        if task is None:
            continue

        task.status = "done"
        done_tasks.append(task)

    db.commit()

    for task in done_tasks:
        db.refresh(task)

    return done_tasks


def clear_user_tasks(db: Session, user: User) -> int:
    tasks = (
        db.query(Task)
        .filter(Task.user_id == user.id)
        .all()
    )

    count = len(tasks)

    for task in tasks:
        db.delete(task)

    db.commit()

    return count


def format_tasks(tasks: list[Task]) -> str:
    if not tasks:
        return "Активных задач пока нет."

    lines = []

    for task in tasks:
        minutes = task.estimated_minutes or 60
        task_date = _format_task_target_date(task.target_date)
        priority = _format_task_priority(task.priority)
        lines.append(
            f"{task.id}. {task.title} — {task_date}, {priority}, {minutes} мин"
        )

    return "\n".join(lines)


def _format_task_target_date(target_date: date) -> str:
    today = date.today()

    if target_date == today:
        return "сегодня"

    if target_date == today + timedelta(days=1):
        return "завтра"

    return target_date.strftime("%d.%m.%Y")


def _format_task_priority(priority: str) -> str:
    priority_map = {
        "high": "важная",
        "medium": "обычная",
        "low": "низкий приоритет",
    }

    return priority_map.get(priority, priority)
