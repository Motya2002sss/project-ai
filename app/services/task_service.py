import re
from dataclasses import dataclass, field
from datetime import date, time, timedelta
from difflib import SequenceMatcher
from typing import Literal

from sqlalchemy.orm import Session

from app.llm.parser import parse_user_message
from app.llm.schemas import ParsedTask, ParsedUserMessage
from app.models.task import Task
from app.models.user import User
from app.services.time_service import resolve_target_date


TASK_MATCH_THRESHOLD = 0.72
TASK_MATCH_AMBIGUITY_MARGIN = 0.08


@dataclass
class TaskReferenceMatch:
    task: Task | None = None
    ambiguous: bool = False


@dataclass
class TaskMutationResult:
    created: list[Task] = field(default_factory=list)
    updated: list[Task] = field(default_factory=list)
    completed: list[Task] = field(default_factory=list)
    cancelled: list[Task] = field(default_factory=list)
    affected_dates: set[date] = field(default_factory=set)
    needs_clarification: bool = False
    clarification_question: str | None = None


def _get_task_target_date(
    user: User,
    parsed_message: ParsedUserMessage | None = None,
    parsed_task: ParsedTask | None = None,
) -> date:
    date_value = None

    if parsed_task and parsed_task.target_date:
        date_value = parsed_task.target_date
    elif parsed_message:
        date_value = parsed_message.date

    return resolve_target_date(date_value, user=user)


def _parse_hhmm(value: str | None) -> time | None:
    if not value:
        return None

    hour, minute = value.split(":")
    return time(hour=int(hour), minute=int(minute))


def create_tasks_from_parsed_tasks(
    db: Session,
    user: User,
    parsed_tasks: list[ParsedTask],
    parsed_message: ParsedUserMessage | None = None,
    commit: bool = True,
) -> list[Task]:
    tasks: list[Task] = []

    for parsed_task in parsed_tasks:
        if parsed_task.operation != "create" or parsed_task.needs_clarification:
            continue

        title = parsed_task.title.strip()

        if not title:
            continue

        target_date = _get_task_target_date(user, parsed_message, parsed_task)
        exists = (
            db.query(Task)
            .filter(
                Task.user_id == user.id,
                Task.target_date == target_date,
                Task.title.ilike(title),
                Task.status.in_(["planned", "done"]),
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
            "scheduling_type": parsed_task.scheduling_type or "flexible",
            "fixed_start": _parse_hhmm(parsed_task.fixed_start),
            "fixed_end": _parse_hhmm(parsed_task.fixed_end),
            "preferred_window": parsed_task.preferred_window,
            "earliest_start": _parse_hhmm(parsed_task.earliest_start),
            "latest_end": _parse_hhmm(parsed_task.latest_end),
            "deadline": parsed_task.deadline,
            "is_locked": parsed_task.scheduling_type == "fixed" or bool(parsed_task.fixed_start),
            "status": "planned",
        }

        task = Task(**task_data)

        db.add(task)
        tasks.append(task)

    db.flush()

    if commit:
        db.commit()

        for task in tasks:
            db.refresh(task)

    return tasks


def create_tasks_from_parsed_message(
    db: Session,
    user: User,
    parsed_message: ParsedUserMessage,
    commit: bool = True,
) -> list[Task]:
    return create_tasks_from_parsed_tasks(
        db=db,
        user=user,
        parsed_tasks=parsed_message.tasks,
        parsed_message=parsed_message,
        commit=commit,
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


def list_user_tasks(
    db: Session,
    user: User,
    target_date: date | None = None,
    *,
    include_cancelled: bool = False,
) -> list[Task]:
    query = db.query(Task).filter(Task.user_id == user.id)

    if not include_cancelled:
        query = query.filter(Task.status != "cancelled")

    if target_date is not None:
        query = query.filter(Task.target_date == target_date)

    return query.order_by(Task.target_date.asc(), Task.id.asc()).all()


def _normalize_title(value: str) -> str:
    value = value.lower().replace("ё", "е")
    value = re.sub(r"[^\w\s]", " ", value, flags=re.UNICODE)
    return re.sub(r"\s+", " ", value).strip()


def _task_match_score(reference: str, candidate: str) -> float:
    normalized_reference = _normalize_title(reference)
    normalized_candidate = _normalize_title(candidate)

    if not normalized_reference or not normalized_candidate:
        return 0.0

    if normalized_reference == normalized_candidate:
        return 1.0

    reference_tokens = set(normalized_reference.split())
    candidate_tokens = set(normalized_candidate.split())

    if reference_tokens.issubset(candidate_tokens) or candidate_tokens.issubset(reference_tokens):
        token_score = 0.88
    else:
        union = reference_tokens | candidate_tokens
        token_score = len(reference_tokens & candidate_tokens) / len(union) if union else 0.0

    sequence_score = SequenceMatcher(None, normalized_reference, normalized_candidate).ratio()
    return max(token_score, sequence_score * 0.85)


def find_task_reference(
    db: Session,
    user: User,
    title: str,
    *,
    target_date: date | None = None,
    statuses: tuple[str, ...] = ("planned",),
) -> TaskReferenceMatch:
    query = db.query(Task).filter(
        Task.user_id == user.id,
        Task.status.in_(statuses),
    )

    if target_date is not None:
        query = query.filter(Task.target_date == target_date)

    scored = sorted(
        (
            (_task_match_score(title, task.title), task)
            for task in query.order_by(Task.id.asc()).all()
        ),
        key=lambda item: (-item[0], item[1].id),
    )

    if not scored or scored[0][0] < TASK_MATCH_THRESHOLD:
        return TaskReferenceMatch()

    if (
        len(scored) > 1
        and scored[1][0] >= TASK_MATCH_THRESHOLD
        and scored[0][0] - scored[1][0] < TASK_MATCH_AMBIGUITY_MARGIN
    ):
        return TaskReferenceMatch(ambiguous=True)

    return TaskReferenceMatch(task=scored[0][1])


def _clarification_for_parsed_task(parsed_task: ParsedTask) -> str:
    if parsed_task.clarification_reason == "recurrence_not_supported":
        return f"Ты хочешь добавить «{parsed_task.title}» только на один день или как регулярную задачу?"

    if parsed_task.clarification_reason == "missing_fixed_time":
        return f"Во сколько запланировано «{parsed_task.title}»?"

    return parsed_task.clarification_reason or f"Уточни, как поступить с задачей «{parsed_task.title}»."


def _resolve_operation_task(
    db: Session,
    user: User,
    parsed_task: ParsedTask,
    parsed_message: ParsedUserMessage,
) -> TaskReferenceMatch:
    reference = parsed_task.referenced_task_title or parsed_task.title
    current_date = resolve_target_date(parsed_message.date, user=user)
    statuses = ("planned", "done") if parsed_task.operation == "complete" else ("planned", "cancelled")
    date_hint = None if parsed_task.operation == "update" else current_date
    match = find_task_reference(
        db=db,
        user=user,
        title=reference,
        target_date=date_hint,
        statuses=statuses,
    )

    if match.task is None and not match.ambiguous and date_hint is not None:
        return find_task_reference(
            db=db,
            user=user,
            title=reference,
            statuses=statuses,
        )

    return match


def apply_parsed_task_operations(
    db: Session,
    user: User,
    parsed_message: ParsedUserMessage,
    *,
    commit: bool = True,
) -> TaskMutationResult:
    result = TaskMutationResult()
    resolved_operations: list[tuple[ParsedTask, Task]] = []

    for parsed_task in parsed_message.tasks:
        if parsed_task.needs_clarification:
            result.needs_clarification = True
            result.clarification_question = _clarification_for_parsed_task(parsed_task)
            return result

        if parsed_task.operation == "create":
            continue

        match = _resolve_operation_task(db, user, parsed_task, parsed_message)
        reference = parsed_task.referenced_task_title or parsed_task.title

        if match.ambiguous:
            result.needs_clarification = True
            result.clarification_question = (
                f"Нашёл несколько похожих задач для «{reference}». Уточни полное название."
            )
            return result

        if match.task is None:
            result.needs_clarification = True
            result.clarification_question = (
                f"Не нашёл подходящую задачу «{reference}». Уточни название или сначала добавь её."
            )
            return result

        resolved_operations.append((parsed_task, match.task))

    created = create_tasks_from_parsed_tasks(
        db=db,
        user=user,
        parsed_tasks=parsed_message.tasks,
        parsed_message=parsed_message,
        commit=False,
    )
    result.created.extend(created)
    result.affected_dates.update(task.target_date for task in created)

    for parsed_task, task in resolved_operations:
        old_date = task.target_date

        if parsed_task.operation == "complete":
            if task.status != "done":
                task.status = "done"
                result.completed.append(task)
            result.affected_dates.add(task.target_date)
            continue

        if parsed_task.operation == "cancel":
            if task.status != "cancelled":
                task.status = "cancelled"
                result.cancelled.append(task)
            result.affected_dates.add(task.target_date)
            continue

        if parsed_task.target_date:
            task.target_date = resolve_target_date(parsed_task.target_date, user=user)

        if parsed_task.duration_delta_minutes:
            task.estimated_minutes = (task.estimated_minutes or 60) + parsed_task.duration_delta_minutes
        elif parsed_task.estimated_minutes:
            task.estimated_minutes = parsed_task.estimated_minutes

        if parsed_task.scheduling_type:
            task.scheduling_type = parsed_task.scheduling_type

        if parsed_task.fixed_start:
            task.fixed_start = _parse_hhmm(parsed_task.fixed_start)
            task.scheduling_type = "fixed"
            task.is_locked = True

        if parsed_task.fixed_end:
            task.fixed_end = _parse_hhmm(parsed_task.fixed_end)

        if parsed_task.preferred_window:
            task.preferred_window = parsed_task.preferred_window

        if parsed_task.earliest_start:
            task.earliest_start = _parse_hhmm(parsed_task.earliest_start)

        if parsed_task.latest_end:
            task.latest_end = _parse_hhmm(parsed_task.latest_end)

        if parsed_task.deadline:
            task.deadline = parsed_task.deadline

        result.updated.append(task)
        result.affected_dates.update({old_date, task.target_date})

    db.flush()

    if commit:
        db.commit()

        for task in result.created + result.updated + result.completed + result.cancelled:
            db.refresh(task)

    return result


def _find_active_task_by_title(
    db: Session,
    user: User,
    title: str,
    target_date: date | None = None,
) -> Task | None:
    match = find_task_reference(
        db=db,
        user=user,
        title=title,
        target_date=target_date,
        statuses=("planned",),
    )

    return None if match.ambiguous else match.task


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


def set_task_status(
    db: Session,
    user: User,
    task_id: int,
    task_status: Literal["planned", "done"],
    commit: bool = True,
) -> Task | None:
    if task_status not in {"planned", "done"}:
        raise ValueError("Unsupported task status")

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

    task.status = task_status
    db.flush()

    if commit:
        db.commit()
        db.refresh(task)

    return task


def mark_task_done(db: Session, user: User, task_id: int, *, commit: bool = True) -> Task | None:
    return set_task_status(
        db=db,
        user=user,
        task_id=task_id,
        task_status="done",
        commit=commit,
    )


def mark_task_done_by_title(
    db: Session,
    user: User,
    title: str,
    target_date: date | None = None,
    commit: bool = True,
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
    db.flush()

    if commit:
        db.commit()
        db.refresh(task)

    return task


def mark_tasks_done_by_titles(
    db: Session,
    user: User,
    titles: list[str],
    target_date: date | None = None,
    commit: bool = True,
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

    db.flush()

    if commit:
        db.commit()

        for task in done_tasks:
            db.refresh(task)

    return done_tasks


def clear_user_tasks(db: Session, user: User, *, commit: bool = True) -> int:
    tasks = (
        db.query(Task)
        .filter(Task.user_id == user.id)
        .all()
    )

    count = len(tasks)

    for task in tasks:
        db.delete(task)

    db.flush()

    if commit:
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
